"""Transactional loyalty accounting, scoped to the deployment's tenant storage.

Customer identity stays in the graph. SQLite owns loyalty accounting so concurrent
workers cannot spend the same points; graph attributes are legacy migration input.
No external discount application or customer verification is simulated here.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from core.storage_paths import storage_path


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier(prefix):
    return f"{prefix}-{uuid4().hex}"


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class LoyaltyError(ValueError):
    pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
 customer_id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
 enrolled_at TEXT NOT NULL, terms_version TEXT NOT NULL, source TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entries (
 id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES members(customer_id),
 kind TEXT NOT NULL, points INTEGER NOT NULL, reason TEXT NOT NULL,
 source TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL,
 reference TEXT, metadata TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS entries_member ON entries(customer_id, created_at);
CREATE TABLE IF NOT EXISTS holds (
 id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES members(customer_id),
 reward_id TEXT NOT NULL, points INTEGER NOT NULL CHECK(points > 0),
 appointment_id TEXT NOT NULL, location TEXT NOT NULL, status TEXT NOT NULL,
 expires_at TEXT NOT NULL, created_at TEXT NOT NULL, snapshot TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS one_hold_per_visit ON holds(appointment_id)
 WHERE status='reserved';
CREATE TABLE IF NOT EXISTS documents (
 kind TEXT NOT NULL, id TEXT NOT NULL, version INTEGER NOT NULL,
 data TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(kind,id,version));
CREATE TABLE IF NOT EXISTS requests (
 key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
 id TEXT PRIMARY KEY, data TEXT NOT NULL, status TEXT NOT NULL,
 error TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
 id TEXT PRIMARY KEY, action TEXT NOT NULL, actor TEXT NOT NULL,
 data TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS entries_no_update BEFORE UPDATE ON entries
 BEGIN SELECT RAISE(ABORT, 'Ledger entries are immutable'); END;
CREATE TRIGGER IF NOT EXISTS entries_no_delete BEFORE DELETE ON entries
 BEGIN SELECT RAISE(ABORT, 'Ledger entries are immutable'); END;
"""


@contextmanager
def transaction():
    path = Path(storage_path("loyalty.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=20, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(SCHEMA)
        from core.loyalty_workflows import SCHEMA as WORKFLOW_SCHEMA
        db.executescript(WORKFLOW_SCHEMA)
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def audit(db, action, actor, data):
    db.execute("INSERT INTO audit VALUES (?,?,?,?,?)",
               (identifier("AUD"), action, actor, encoded(data), now()))


def once(db, key, payload, operation):
    if not key or len(key) > 200:
        raise LoyaltyError("A request key of 1–200 characters is required.")
    fingerprint = hashlib.sha256(encoded(payload).encode()).hexdigest()
    previous = db.execute("SELECT * FROM requests WHERE key=?", (key,)).fetchone()
    if previous:
        if previous["fingerprint"] != fingerprint:
            raise LoyaltyError("This request key was already used for a different action.")
        return json.loads(previous["result"])
    result = operation()
    db.execute("INSERT INTO requests VALUES (?,?,?)", (key, fingerprint, encoded(result)))
    return result


DEFAULT_PROGRAM = dict(id="default", name="Loyalty & Rewards", status="draft",
                       terms_version="1", enrollment_enabled=False,
                       earning_enabled=False, redemption_enabled=False,
                       locations=[], hold_hours=48, description="")


def documents(db, kind):
    rows = db.execute("""SELECT d.* FROM documents d JOIN
      (SELECT id,MAX(version) v FROM documents WHERE kind=? GROUP BY id) latest
      ON d.id=latest.id AND d.version=latest.v WHERE d.kind=?""", (kind, kind)).fetchall()
    return [dict(json.loads(r["data"]), id=r["id"], version=r["version"]) for r in rows]


def program(db):
    return next(iter(documents(db, "program")), dict(DEFAULT_PROGRAM, version=0))


def active_program(db):
    row = db.execute("SELECT data FROM documents WHERE kind='program' AND json_extract(data,'$.status')!='draft' ORDER BY version DESC LIMIT 1").fetchone()
    return json.loads(row["data"]) if row else dict(DEFAULT_PROGRAM, version=0)


def published(db, kind, at=None):
    # A future version must not hide the version applicable to an older purchase.
    selected = {}
    for row in db.execute("SELECT * FROM documents WHERE kind=? ORDER BY version", (kind,)):
        value = dict(json.loads(row["data"]), id=row["id"], version=row["version"])
        if value.get("status") != "draft" and value.get("starts_at", "") <= (at or now()):
            selected[row["id"]] = value
    return [v for v in selected.values() if v.get("status") == "active"
            and (not v.get("ends_at") or v["ends_at"] > (at or now()))]


def require_integer(value, label, minimum=0):
    if type(value) is not int or value < minimum or value > 1_000_000_000:
        raise LoyaltyError(f"{label} must be a whole number between {minimum} and 1,000,000,000.")


def save_document(kind, data, actor):
    if kind not in {"program", "rule", "reward", "campaign"}:
        raise LoyaltyError("Unknown configuration type.")
    data = dict(data)
    if not str(data.get("name", "")).strip():
        raise LoyaltyError("A name is required.")
    if data.get("status") not in {"draft", "active", "paused", "retired"}:
        raise LoyaltyError("Choose a valid status.")
    for field in ("starts_at", "ends_at"):
        if data.get(field):
            try:
                parsed = datetime.fromisoformat(data[field])
                if parsed.tzinfo is None:
                    raise ValueError()
                data[field] = parsed.astimezone(timezone.utc).isoformat()
            except (ValueError, TypeError):
                raise LoyaltyError("Dates must include a timezone.")
    if data.get("ends_at") and data["ends_at"] <= data.get("starts_at", ""):
        raise LoyaltyError("End date must follow start date.")
    if kind == "program":
        data["id"] = "default"
        require_integer(data.get("hold_hours", 48), "Reservation hours", 1)
        if data.get("hold_hours", 48) > 720:
            raise LoyaltyError("Reservation duration cannot exceed 720 hours.")
        for flag in ("enrollment_enabled", "earning_enabled", "redemption_enabled"):
            if type(data.get(flag)) is not bool:
                raise LoyaltyError(f"{flag} must be true or false.")
        if not data.get("terms_version"):
            raise LoyaltyError("A terms version is required.")
    if kind in {"rule", "campaign"}:
        if data.get("trigger") not in {"service", "parts", "delivery"}:
            raise LoyaltyError("Choose service, parts, or delivery.")
        if data.get("calculation") not in {"fixed", "per_dollar"}:
            raise LoyaltyError("Choose fixed points or points per dollar.")
        require_integer(data.get("points"), "Points", 1)
        if kind == "campaign":
            require_integer(data.get("member_limit", 1), "Member limit", 1)
            require_integer(data.get("points_cap", 100000), "Campaign points cap", 1)
    if kind == "reward":
        require_integer(data.get("point_cost"), "Points cost", 1)
        require_integer(data.get("discount_cents", 0), "Discount cents")
        if data.get("department") not in {"Service", "Parts", "Sales"}:
            raise LoyaltyError("Choose a supported department.")
    if not isinstance(data.get("locations", []), list) or any(not isinstance(x, str) for x in data.get("locations", [])):
        raise LoyaltyError("Locations must be a list of location IDs.")
    with transaction() as db:
        doc_id = data.get("id") or identifier(kind.upper())
        version = db.execute("SELECT COALESCE(MAX(version),0) FROM documents WHERE kind=? AND id=?",
                             (kind, doc_id)).fetchone()[0]
        if data.get("version", 0) != version:
            raise LoyaltyError("This item changed. Refresh before saving.")
        if version and kind != "program" and data.get("status") != "draft":
            # Changing a published version cannot silently backdate a new rate.
            old = db.execute("SELECT data FROM documents WHERE kind=? AND id=? AND version=?", (kind, doc_id, version)).fetchone()
            old_start = json.loads(old["data"]).get("starts_at", "")
            if not data.get("starts_at") or data.get("starts_at") == old_start:
                data["starts_at"] = now()
        data.update(id=doc_id, version=version+1)
        db.execute("INSERT INTO documents VALUES (?,?,?,?,?,?)",
                   (kind, doc_id, version+1, encoded(data), actor, now()))
        audit(db, f"save_{kind}", actor, data)
        return data


def add_entry(db, customer, kind, points, reason, source, actor, reference=None, metadata=None):
    entry_id = identifier("LLED")
    db.execute("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?,?)",
               (entry_id, customer, kind, points, reason, source, actor, now(), reference, encoded(metadata or {})))
    return entry_id


def release_expired(db):
    rows = db.execute("SELECT id FROM holds WHERE status='reserved' AND expires_at<=?", (now(),)).fetchall()
    for row in rows:
        db.execute("UPDATE holds SET status='expired' WHERE id=?", (row["id"],))
        audit(db, "reservation_expired", "system", {"reservation_id": row["id"]})
    # Resolve cancellation even if the process stopped between graph persistence
    # and loyalty cleanup. Reads and all redemption operations reconcile holds.
    from core.dealeros import ledger
    for hold in db.execute("SELECT id,appointment_id,customer_id FROM holds WHERE status='reserved'").fetchall():
        appointment = ledger.get_entity(hold["appointment_id"])
        if appointment and (appointment.attributes.get("status") in {"cancelled", "no_show"}
                            or appointment.attributes.get("customer_id") != hold["customer_id"]):
            db.execute("UPDATE holds SET status='released' WHERE id=?", (hold["id"],))
            audit(db, "reservation_released", "system", {"reservation_id": hold["id"], "reason": "Appointment canceled or customer changed"})


def member(db, customer):
    record = db.execute("SELECT * FROM members WHERE customer_id=?", (customer,)).fetchone()
    if not record:
        raise LoyaltyError("Customer is not enrolled in this program.")
    posted = db.execute("SELECT COALESCE(SUM(points),0) FROM entries WHERE customer_id=?", (customer,)).fetchone()[0]
    reserved = db.execute("SELECT COALESCE(SUM(points),0) FROM holds WHERE customer_id=? AND status='reserved'", (customer,)).fetchone()[0]
    entries = [dict(r) for r in db.execute("SELECT * FROM entries WHERE customer_id=? ORDER BY rowid DESC LIMIT 200", (customer,))]
    holds = [dict(r) for r in db.execute("SELECT * FROM holds WHERE customer_id=? ORDER BY created_at DESC LIMIT 200", (customer,))]
    for row in entries:
        row["metadata"] = json.loads(row["metadata"])
    for row in holds:
        row["reward"] = json.loads(row.pop("snapshot"))
    return dict(record, posted=posted, reserved=reserved, available=posted-reserved,
                pending=0, entries=entries, reservations=holds)


def enroll(customer, name, actor, key, terms_version, legacy_points=0):
    with transaction() as db:
        def perform():
            if db.execute("SELECT 1 FROM members WHERE customer_id=?", (customer,)).fetchone():
                return member(db, customer)
            config = active_program(db)
            if config["status"] != "active" or not config["enrollment_enabled"]:
                raise LoyaltyError("Enrollment is paused. Activate the program first.")
            if terms_version != config["terms_version"]:
                raise LoyaltyError("Review and accept the current terms version.")
            require_integer(abs(legacy_points), "Opening balance")
            db.execute("INSERT INTO members VALUES (?,?,?,?,?,?)",
                       (customer, name, "active", now(), terms_version, actor))
            if legacy_points:
                add_entry(db, customer, "migration", legacy_points, "Imported legacy balance", customer, actor)
            audit(db, "enroll", actor, {"customer_id": customer, "terms_version": terms_version})
            return member(db, customer)
        return once(db, key, ["enroll", customer, terms_version, actor], perform)


def get_member(customer):
    with transaction() as db:
        release_expired(db)
        return member(db, customer)


def adjust(customer, points, reason, actor, key):
    require_integer(abs(points), "Adjustment")
    if not points or not reason.strip():
        raise LoyaltyError("A nonzero adjustment and reason are required.")
    with transaction() as db:
        def perform():
            member(db, customer)
            add_entry(db, customer, "adjustment", points, reason, key, actor)
            audit(db, "adjustment", actor, {"customer_id": customer, "points": points, "reason": reason})
            return member(db, customer)
        return once(db, key, ["adjust", customer, points, reason, actor], perform)


def calculate(db, event):
    require_integer(event.get("eligible_cents"), "Eligible cents")
    if event.get("kind") not in {"service", "parts", "delivery"}:
        raise LoyaltyError("Unsupported purchase type.")
    rules = [r for r in published(db, "rule", event.get("occurred_at"))
             if r["trigger"] == event["kind"] and
             (not r.get("locations") or event["location"] in r["locations"])]
    if len(rules) > 1:
        raise LoyaltyError("Multiple base rules match. Resolve the overlap before posting.")
    result = []
    for rule in rules:
        points = rule["points"] if rule["calculation"] == "fixed" else event["eligible_cents"] * rule["points"] // 100
        result.append({"rule_id": rule["id"], "version": rule["version"], "points": points, "name": rule["name"]})
    campaign_id = event.get("campaign_id")
    if campaign_id:
        campaign = next((r for r in published(db, "campaign", event.get("occurred_at"))
                         if r["id"] == campaign_id and r["trigger"] == event["kind"]
                         and (not r.get("locations") or event["location"] in r["locations"])), None)
        if not campaign:
            raise LoyaltyError("Campaign is not eligible for this purchase.")
        rows = db.execute("SELECT customer_id,points,metadata FROM entries WHERE kind='bonus'").fetchall()
        matched = [r for r in rows if json.loads(r["metadata"]).get("rule_id") == campaign_id]
        points = campaign["points"] if campaign["calculation"] == "fixed" else event["eligible_cents"] * campaign["points"] // 100
        if sum(r["customer_id"] == event.get("customer_id") for r in matched) >= campaign.get("member_limit", 1):
            raise LoyaltyError("Campaign member limit reached.")
        if sum(r["points"] for r in matched) + points > campaign.get("points_cap", 100000):
            raise LoyaltyError("Campaign points cap reached.")
        result.append(dict(rule_id=campaign_id, version=campaign["version"], points=points, name=campaign["name"], bonus=True))
    return result


def preview(event):
    with transaction() as db:
        awards = calculate(db, event)
        return {"awards": awards, "points": sum(a["points"] for a in awards), "rounding": "Round down after eligible cents × rate / 100"}


def process_purchase(event, actor):
    """Trusted finalized-source adapter. Correct revisions require an explicit reversal.

    The adapter supplies eligible spend after discounts and exclusions, in cents.
    No client-supplied transaction is treated as provider-confirmed by the router.
    """
    event = dict(event)
    try:
        occurred = datetime.fromisoformat(event["occurred_at"])
        if occurred.tzinfo is None or occurred > datetime.now(timezone.utc):
            raise ValueError()
        event["occurred_at"] = occurred.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, KeyError):
        raise LoyaltyError("A valid past transaction timestamp with timezone is required.")
    if not event.get("source_id") or not event.get("source_system"):
        raise LoyaltyError("Source system and transaction ID are required.")
    source = f"{event['source_system']}:{event['source_id']}"
    with transaction() as db:
        if event.get("source_system")=="nxtdeal" and db.execute("SELECT 1 FROM loyalty_receipts WHERE source_id=?",(event["source_id"],)).fetchone():
            raise LoyaltyError("This native transaction already has a loyalty receipt.")
        prior = db.execute("SELECT data,status FROM events WHERE id=?", (source,)).fetchone()
        if prior and prior["data"] != encoded(event):
            raise LoyaltyError("This transaction has different data. Reverse it explicitly before correcting it.")
        def perform():
            config = active_program(db)
            if config["status"] != "active" or not config["earning_enabled"]:
                raise LoyaltyError("Earning is paused.")
            if event.get("status") != "finalized":
                raise LoyaltyError("Only finalized purchases earn points.")
            current = member(db, event["customer_id"])
            if current["status"] != "active":
                raise LoyaltyError("Membership is not active.")
            if config.get("locations") and event["location"] not in config["locations"]:
                raise LoyaltyError("Location does not participate in this program.")
            awards = calculate(db, event)
            for award in awards:
                add_entry(db, event["customer_id"], "bonus" if award.get("bonus") else "earn",
                          award["points"], award["name"], source, actor, metadata=award | {"location": event["location"], "eligible_cents": event["eligible_cents"]})
            return {"source_id": source, "awards": awards, "points": sum(a["points"] for a in awards)}
        try:
            result = once(db, "purchase:"+source, event, perform)
        except LoyaltyError as exc:
            db.execute("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?)", (source, encoded(event), "failed", str(exc), now()))
            return {"error": str(exc), "source_id": source, "status": "failed"}
        db.execute("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?)", (source, encoded(event), "processed", None, now()))
        return result


def reserve(customer, reward_id, appointment_id, location, actor, key):
    if not appointment_id.strip() or not location.strip():
        raise LoyaltyError("Appointment and location are required.")
    with transaction() as db:
        release_expired(db)
        def perform():
            config = active_program(db)
            if config["status"] != "active" or not config["redemption_enabled"]:
                raise LoyaltyError("Redemption is paused.")
            current = member(db, customer)
            if current["status"] != "active":
                raise LoyaltyError("Membership is not active.")
            reward = next((r for r in published(db, "reward") if r["id"] == reward_id), None)
            if not reward:
                raise LoyaltyError("Reward is not currently available.")
            for locations in (config.get("locations", []), reward.get("locations", [])):
                if locations and location not in locations:
                    raise LoyaltyError("Reward cannot be used at this location.")
            if current["available"] < reward["point_cost"]:
                raise LoyaltyError("Not enough available points.")
            if db.execute("SELECT 1 FROM holds WHERE appointment_id=? AND status='reserved'", (appointment_id,)).fetchone():
                raise LoyaltyError("This appointment already has a reserved reward.")
            hold_id = identifier("HOLD")
            expiry = (datetime.now(timezone.utc)+timedelta(hours=config["hold_hours"])).isoformat()
            db.execute("INSERT INTO holds VALUES (?,?,?,?,?,?,?,?,?,?)", (hold_id, customer, reward_id, reward["point_cost"], appointment_id, location, "reserved", expiry, now(), encoded(reward)))
            audit(db, "reserve", actor, {"reservation_id": hold_id, "customer_id": customer})
            return {"reservation_id": hold_id, "status": "reserved", "expires_at": expiry}
        return once(db, key, ["reserve", customer, reward_id, appointment_id, location, actor], perform)


def resolve_hold(customer, hold_id, action, actor, key, source="", reason=""):
    if action not in {"release", "confirm"}:
        raise LoyaltyError("Unknown reservation action.")
    with transaction() as db:
        release_expired(db)
        def perform():
            hold = db.execute("SELECT * FROM holds WHERE id=? AND customer_id=?", (hold_id, customer)).fetchone()
            if not hold:
                raise LoyaltyError("Reservation not found.")
            if hold["status"] != "reserved":
                raise LoyaltyError("Reservation is no longer active.")
            if action == "confirm":
                if not source.strip() or not reason.strip():
                    raise LoyaltyError("Final invoice reference and benefit-application confirmation are required.")
                if db.execute("SELECT 1 FROM entries WHERE kind='redeem' AND source=?", (source,)).fetchone():
                    raise LoyaltyError("This invoice already has a confirmed redemption.")
                if member(db, customer)["available"] < 0:
                    raise LoyaltyError("Balance changed. Resolve the shortfall before confirming.")
                add_entry(db, customer, "redeem", -hold["points"], "Reward applied: "+json.loads(hold["snapshot"])["name"], source, actor, hold_id, {"confirmation": reason, "location": hold["location"]})
            status = "redeemed" if action == "confirm" else "released"
            db.execute("UPDATE holds SET status=? WHERE id=?", (status, hold_id))
            audit(db, action, actor, {"reservation_id": hold_id, "reason": reason, "source": source})
            return {"reservation_id": hold_id, "status": status}
        return once(db, key, [action, customer, hold_id, source, reason, actor], perform)


def reverse(customer, entry_id, points, reason, actor, key):
    require_integer(points, "Reversal points", 1)
    if not reason.strip():
        raise LoyaltyError("A refund or correction reason is required.")
    with transaction() as db:
        def perform():
            entry = db.execute("SELECT * FROM entries WHERE id=? AND customer_id=?", (entry_id, customer)).fetchone()
            if not entry or entry["kind"] not in {"earn", "bonus", "redeem"}:
                raise LoyaltyError("Choose an award or redemption to reverse.")
            reversed_points = db.execute("SELECT COALESCE(SUM(ABS(points)),0) FROM entries WHERE kind='reversal' AND reference=?", (entry_id,)).fetchone()[0]
            if reversed_points + points > abs(entry["points"]):
                raise LoyaltyError("Reversal exceeds the remaining original points.")
            add_entry(db, customer, "reversal", -points if entry["points"] > 0 else points, reason, key, actor, entry_id)
            return member(db, customer)
        return once(db, key, ["reverse", customer, entry_id, points, reason, actor], perform)


def workspace():
    with transaction() as db:
        release_expired(db)
        members = []
        for row in db.execute("SELECT customer_id FROM members ORDER BY name"):
            m = member(db, row["customer_id"])
            members.append({k:v for k,v in m.items() if k not in {"entries", "reservations"}})
        totals = {r["kind"]: r["points"] for r in db.execute("SELECT kind,SUM(points) points FROM entries GROUP BY kind")}
        return {"program": program(db), "active_program": active_program(db), "rules": documents(db,"rule"), "rewards": documents(db,"reward"),
                "campaigns": documents(db,"campaign"), "members": members, "totals": totals,
                "available": sum(m["available"] for m in members), "reserved": sum(m["reserved"] for m in members),
                "events": [dict(r) for r in db.execute("SELECT id,status,error,created_at FROM events ORDER BY created_at DESC LIMIT 200")] +
                          [dict(r) for r in db.execute("SELECT 'native:'||source_id id,status,error,updated_at created_at FROM loyalty_jobs ORDER BY updated_at DESC LIMIT 100")],
                "activity": [dict(r) for r in db.execute("SELECT * FROM entries ORDER BY rowid DESC LIMIT 200")],
                "audit": [dict(r) for r in db.execute("SELECT * FROM audit ORDER BY rowid DESC LIMIT 100")],
                "updated_at": now()}


def retry_event(event_id, actor):
    if event_id.startswith("native:"):
        from core.loyalty_workflows import reconcile
        return reconcile()
    with transaction() as db:
        row = db.execute("SELECT data FROM events WHERE id=?", (event_id,)).fetchone()
        if not row:
            raise LoyaltyError("Source event not found.")
        event = json.loads(row["data"])
    return process_purchase(event, actor)


def configured():
    if not Path(storage_path("loyalty.sqlite3")).exists():
        return False
    with transaction() as db:
        return bool(documents(db, "program"))


def guard_legacy_write():
    if configured():
        raise LoyaltyError("Use Marketing → Loyalty & Rewards. Legacy writes are disabled after program configuration to prevent competing balances.")


def legacy_member(customer):
    if not configured():
        return None
    try:
        m = get_member(customer)
    except LoyaltyError:
        return None
    return dict(customer_id=customer, name=m["name"], enrolled=True, enrolled_at=m["enrolled_at"],
                points_balance=m["available"], lifetime_points=None, tier=None, visits=0, referrals=0,
                ledger=[dict(entry_id=e["id"], entry_type=e["kind"], points=e["points"], reason=e["reason"],
                             department="", timestamp=e["created_at"], balance_after=None) for e in m["entries"]],
                redemptions=[dict(redemption_id=h["id"],reward_id=h["reward_id"],reward_name=h["reward"]["name"],
                                  point_cost=h["points"],department=h["reward"].get("department",""),timestamp=h["created_at"])
                             for h in m["reservations"] if h["status"]=="redeemed"])


def customer_view(customer):
    """Safe projection for a future verified-session route; no actor/internal notes."""
    with transaction() as db:
        release_expired(db)
        config = active_program(db)
        summary = {k:config.get(k) for k in ("name", "description", "terms_version", "terms", "locations", "enrollment_enabled")}
        if not db.execute("SELECT 1 FROM members WHERE customer_id=?", (customer,)).fetchone():
            return {"enrolled": False, "program": summary, "rewards": []}
        m = member(db, customer)
        m.pop("source", None)
        for entry in m["entries"]:
            entry.pop("actor", None)
            entry.pop("metadata", None)
            # Adjustment explanations are an internal support record.
            if entry["kind"] in {"adjustment", "reversal"}:
                entry["reason"] = "Points adjustment" if entry["kind"] == "adjustment" else "Transaction correction"
        rewards = []
        for r in published(db, "reward"):
            eligible = config["status"] == "active" and config["redemption_enabled"] and m["status"] == "active" and m["available"] >= r["point_cost"]
            rewards.append(r | {"eligible": eligible, "eligibility_note": "Choose a participating location and eligible visit" if eligible else "Not currently available for redemption"})
        return {"enrolled": True, "program": summary, "member": m, "rewards": rewards}


def backup_database(destination):
    """Called by the tenant backup workflow; SQLite backup takes a consistent snapshot."""
    source = Path(storage_path("loyalty.sqlite3"))
    if not source.exists():
        return None
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as destination_db:
        source_db.backup(destination_db)
    return str(destination)
