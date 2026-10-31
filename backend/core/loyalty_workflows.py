"""Customer access and canonical transaction connections for loyalty.

Invitations are staff-issued capabilities, not claims of email/SMS verification.
Only hashes are persisted. Customer sessions cannot authenticate staff APIs.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import secrets

from core import loyalty_program as lp
from core.dealeros import ledger
from core.entity_types import CUSTOMER, SERVICE_RECORD, PART_SALE, DELIVERY

SCHEMA = """
CREATE TABLE IF NOT EXISTS loyalty_invites(hash TEXT PRIMARY KEY, customer_id TEXT NOT NULL,
 expires_at TEXT NOT NULL, used_at TEXT, actor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS loyalty_sessions(hash TEXT PRIMARY KEY, customer_id TEXT NOT NULL,
 expires_at TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, csrf TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS loyalty_preferences(customer_id TEXT PRIMARY KEY, promotions INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS loyalty_receipts(source_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL,
 data TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS loyalty_notifications(id TEXT PRIMARY KEY, customer_id TEXT NOT NULL,
 kind TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL, read_at TEXT);
CREATE TABLE IF NOT EXISTS loyalty_jobs(source_id TEXT PRIMARY KEY, actor TEXT NOT NULL,
 status TEXT NOT NULL, error TEXT, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS loyalty_refunds(id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
 cents INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
"""


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def customer_record(customer_id):
    entity = ledger.get_entity(customer_id)
    if not entity or entity.entity_type != CUSTOMER:
        raise lp.LoyaltyError("Customer is not in this dealership.")
    return entity


def invite(customer_id, actor, reason):
    customer_record(customer_id)
    if not reason.strip():
        raise lp.LoyaltyError("Record how the customer's identity was checked.")
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    with lp.transaction() as db:
        # Issuing a replacement invalidates outstanding invitations.
        db.execute("UPDATE loyalty_invites SET used_at=? WHERE customer_id=? AND used_at IS NULL", (lp.now(), customer_id))
        db.execute("INSERT INTO loyalty_invites VALUES (?,?,?,NULL,?)", (digest(token), customer_id, expires, actor))
        lp.audit(db, "customer_invitation", actor, {"customer_id": customer_id, "identity_check": reason})
    return {"invitation": token, "expires_at": expires}


def accept_invitation(token):
    with lp.transaction() as db:
        row = db.execute("SELECT * FROM loyalty_invites WHERE hash=? AND used_at IS NULL AND expires_at>?", (digest(token), lp.now())).fetchone()
        if not row:
            raise lp.LoyaltyError("Invitation is invalid, expired, or already used. Ask your dealership for a new invitation.")
        customer_record(row["customer_id"])
        db.execute("UPDATE loyalty_invites SET used_at=? WHERE hash=?", (lp.now(), row["hash"]))
        session, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        expires = (datetime.now(timezone.utc)+timedelta(hours=12)).isoformat()
        db.execute("INSERT INTO loyalty_sessions VALUES (?,?,?,0,?)", (digest(session), row["customer_id"], expires, csrf))
        lp.audit(db, "customer_sign_in", "customer", {"customer_id": row["customer_id"]})
        return session, {"csrf": csrf, "expires_at": expires}


def session(token, csrf=None):
    with lp.transaction() as db:
        row = db.execute("SELECT * FROM loyalty_sessions WHERE hash=? AND revoked=0 AND expires_at>?", (digest(token or ""), lp.now())).fetchone()
        if not row or (csrf is not None and not secrets.compare_digest(csrf, row["csrf"])):
            raise lp.LoyaltyError("Your rewards session expired. Request a new dealership invitation.")
        customer_record(row["customer_id"])
        return dict(row)


def revoke(customer_id, actor):
    with lp.transaction() as db:
        db.execute("UPDATE loyalty_sessions SET revoked=1 WHERE customer_id=?", (customer_id,))
        db.execute("UPDATE loyalty_invites SET used_at=? WHERE customer_id=? AND used_at IS NULL", (lp.now(), customer_id))
        lp.audit(db, "customer_access_revoked", actor, {"customer_id": customer_id})
    return {"revoked": True}


def appointments(customer_id):
    from core.appointments import list_appointments
    with lp.transaction() as db:
        config = lp.active_program(db)
    locations = config.get("locations") or ["default"]
    return [{"id": a.id, "label": f"{a.attributes.get('department')} · {a.attributes.get('scheduled_start')}",
             "department": a.attributes.get("department"), "scheduled_start": a.attributes.get("scheduled_start"),
             "status": a.attributes.get("status"), "location": a.attributes.get("location_id") or locations[0]}
            for a in list_appointments(linked_entity_id=customer_id)
            if a.attributes.get("customer_id") == customer_id and a.attributes.get("status") in {"scheduled", "confirmed", "arrived"}]


def reserve_for_visit(customer_id, reward_id, appointment_id, actor, key):
    visit = next((a for a in appointments(customer_id) if a["id"] == appointment_id), None)
    if not visit:
        raise lp.LoyaltyError("Select one of your upcoming appointments.")
    with lp.transaction() as db:
        reward = next((r for r in lp.published(db, "reward") if r["id"] == reward_id), None)
    if not reward or reward.get("department") != visit["department"]:
        raise lp.LoyaltyError("This reward does not apply to the selected visit.")
    result = lp.reserve(customer_id, reward_id, appointment_id, visit["location"], actor, key)
    # Keep the hold through the visit rather than expiring it before a future booking.
    try:
        start = datetime.fromisoformat(visit["scheduled_start"])
        if start.tzinfo:
            expiry = max(datetime.fromisoformat(result["expires_at"]), start+timedelta(hours=24)).isoformat()
            with lp.transaction() as db:
                db.execute("UPDATE holds SET expires_at=? WHERE id=? AND status='reserved'", (expiry, result["reservation_id"]))
            result["expires_at"] = expiry
    except (ValueError, TypeError):
        pass
    return result


def request_visit(customer_id, scheduled_start, location, notes, key):
    from core.appointments import create_appointment
    customer_record(customer_id)
    try:
        start=datetime.fromisoformat(scheduled_start)
        if start.tzinfo is None or not datetime.now(timezone.utc)<start<datetime.now(timezone.utc)+timedelta(days=180):
            raise ValueError()
    except (ValueError,TypeError):
        raise lp.LoyaltyError("Choose a future preferred time within 180 days.")
    with lp.transaction() as db:
        def perform():
            config=lp.active_program(db)
            if location not in (config.get("locations") or ["default"]):
                raise lp.LoyaltyError("Choose a participating dealership.")
            # Recover a graph save completed before a process interruption.
            existing=next((a for a in ledger.get_all().values() if a.entity_type=="Appointment" and a.attributes.get("loyalty_booking_key")==customer_id+":"+key),None)
            if existing:
                attrs=existing.attributes
                if (attrs.get("scheduled_start")!=start.isoformat() or attrs.get("location_id")!=location
                        or attrs.get("notes")!="Customer requested time; staff confirmation required. "+notes):
                    raise lp.LoyaltyError("This booking request key was already used with different details.")
                return {"appointment_id":existing.id,"status":"scheduled","confirmation_required":True}
            appointment=create_appointment("Service","service",start.isoformat(),"customer:"+customer_id,customer_id=customer_id,
                                           notes="Customer requested time; staff confirmation required. "+notes,
                                           location_id=location,loyalty_booking_key=customer_id+":"+key,confirmation_required=True)
            if isinstance(appointment,dict):
                raise lp.LoyaltyError(appointment.get("error","Unable to request visit."))
            lp.audit(db,"customer_visit_requested","customer:"+customer_id,{"appointment_id":appointment.id})
            return {"appointment_id":appointment.id,"status":"scheduled","confirmation_required":True}
        return lp.once(db,"booking:"+customer_id+":"+key,[customer_id,scheduled_start,location,notes],perform)


def preferences(customer_id, promotions=None):
    with lp.transaction() as db:
        if promotions is not None:
            db.execute("INSERT INTO loyalty_preferences VALUES (?,?) ON CONFLICT(customer_id) DO UPDATE SET promotions=excluded.promotions", (customer_id, int(promotions)))
            lp.audit(db, "communication_preference", "customer", {"customer_id": customer_id, "promotions": promotions})
        row = db.execute("SELECT promotions FROM loyalty_preferences WHERE customer_id=?", (customer_id,)).fetchone()
        return {"promotions": bool(row[0]) if row else False}


def customer_view(customer_id):
    result = lp.customer_view(customer_id)
    result["appointments"] = appointments(customer_id)
    result["preferences"] = preferences(customer_id)
    with lp.transaction() as db:
        result["receipts"] = [json.loads(r[0]) for r in db.execute("SELECT data FROM loyalty_receipts WHERE customer_id=? ORDER BY created_at DESC LIMIT 100", (customer_id,))]
        for receipt in result["receipts"]:
            receipt["refunded_cents"]=db.execute("SELECT COALESCE(SUM(cents),0) FROM loyalty_refunds WHERE source_id=?",(receipt["source_id"],)).fetchone()[0]
        result["notifications"] = [dict(r) for r in db.execute("SELECT id,kind,message,created_at,read_at FROM loyalty_notifications WHERE customer_id=? ORDER BY created_at DESC LIMIT 100", (customer_id,))]
    return result


def notify(db, customer_id, kind, message, key):
    db.execute("INSERT OR IGNORE INTO loyalty_notifications VALUES (?,?,?,?,?,NULL)", (key, customer_id, kind, message, lp.now()))


def cents(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise ValueError()
        result = int((amount*100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        lp.require_integer(result, "Eligible cents")
        return result
    except (ValueError, ArithmeticError):
        raise lp.LoyaltyError("The transaction needs a valid finalized amount.")


def source_transaction(source_id):
    entity = ledger.get_entity(source_id)
    if not entity:
        raise lp.LoyaltyError("Transaction not found.")
    a = entity.attributes
    if entity.entity_type == SERVICE_RECORD:
        matches=[c for c in ledger.get_all().values() if c.entity_type==CUSTOMER and a.get("CustomerID")
                 and c.attributes.get("CustomerID")==a["CustomerID"]]
        customer=matches[0] if len(matches)==1 else None
        if not customer or a.get("Status") != "Completed":
            raise lp.LoyaltyError("Repair order must belong to a customer and be completed.")
        if a.get("PayType", "Customer Pay") != "Customer Pay":
            raise lp.LoyaltyError("Warranty/internal repair orders do not earn customer points.")
        customer_id, kind, amount = customer.id, "service", cents(a.get("Cost", 0))
    elif entity.entity_type == PART_SALE:
        customer_id = a.get("customer_id")
        if not customer_id and a.get("CustomerID"):
            matches=[c for c in ledger.get_all().values() if c.entity_type==CUSTOMER and c.attributes.get("CustomerID")==a["CustomerID"]]
            customer_id=matches[0].id if len(matches)==1 else None
        if a.get("status",a.get("Status","" )).lower() != "completed":
            raise lp.LoyaltyError("Parts sale must be finalized.")
        kind, amount = "parts", cents(a.get("total",a.get("TotalSale",a.get("SalePrice",0))))
    elif entity.entity_type == DELIVERY:
        if a.get("status") not in {"delivered","completed"}:
            raise lp.LoyaltyError("Vehicle delivery is not complete.")
        customer_id, kind, amount = a.get("customer_id"), "delivery", 0
    else:
        raise lp.LoyaltyError("Use a repair order, completed parts sale, or delivered vehicle record.")
    customer_record(customer_id)
    return {"source_id":source_id, "source_system":"nxtdeal", "customer_id":customer_id, "kind":kind,
            "eligible_cents":amount, "location":a.get("location_id") or "default", "status":"finalized",
            "occurred_at":a.get("loyalty_finalized_at") or lp.now(), "campaign_id":a.get("loyalty_campaign_id")}


def complete_transaction(source_id, actor, reservation_id=None):
    """Native checkout receipt: rewards and earning commit together.

    Original gross amount remains on the canonical source. The receipt records
    the separately accounted loyalty discount and resulting net eligible amount.
    No external gateway payment or DMS write is claimed.
    """
    event = source_transaction(source_id)
    with lp.transaction() as db:
        previous = db.execute("SELECT data FROM loyalty_receipts WHERE source_id=?", (source_id,)).fetchone()
        if previous:
            receipt = json.loads(previous[0])
            if receipt["customer_id"]!=event["customer_id"] or receipt["gross_cents"]!=event["eligible_cents"]:
                raise lp.LoyaltyError("The source changed after checkout. Reconcile the original receipt before continuing.")
            if receipt.get("reservation_id") != reservation_id and reservation_id:
                raise lp.LoyaltyError("This transaction is already finalized. Use a linked correction.")
            return receipt
        config = lp.active_program(db)
        if config["status"] != "active" or not config["earning_enabled"]:
            raise lp.LoyaltyError("Loyalty earning is paused.")
        lp.release_expired(db)
        member = lp.member(db, event["customer_id"])
        if member["status"] != "active":
            raise lp.LoyaltyError("Membership is not active.")
        if config.get("locations") and event["location"] not in config["locations"]:
            raise lp.LoyaltyError("Transaction location is not participating.")
        # Prevent the old manual source route and checkout from awarding twice.
        if (db.execute("SELECT 1 FROM entries WHERE source=?", ("nxtdeal:"+source_id,)).fetchone()
                or db.execute("SELECT 1 FROM events WHERE id=? AND status='processed'",("nxtdeal:"+source_id,)).fetchone()):
            raise lp.LoyaltyError("This source already has loyalty entries. Reconcile before checkout.")
        discount = 0
        if reservation_id:
            if not config["redemption_enabled"]:
                raise lp.LoyaltyError("Redemption is paused.")
            hold = db.execute("SELECT * FROM holds WHERE id=? AND customer_id=? AND status='reserved'", (reservation_id, event["customer_id"])).fetchone()
            if not hold or hold["location"] != event["location"] or member["available"] < 0:
                raise lp.LoyaltyError("Reservation is unavailable for this customer/location.")
            reward = json.loads(hold["snapshot"])
            if reward.get("department", "").lower() != {"service":"service", "parts":"parts", "delivery":"sales"}[event["kind"]]:
                raise lp.LoyaltyError("Reward does not apply to this purchase type.")
            # Monetary value must be explicitly configured; never infer it from a name.
            discount = reward.get("discount_cents", 0)
            if not discount or discount > event["eligible_cents"]:
                raise lp.LoyaltyError("Reward needs a configured discount no greater than eligible spend.")
        net = event["eligible_cents"] - discount
        awards = lp.calculate(db, event | {"eligible_cents": net})
        if reservation_id:
            lp.add_entry(db, event["customer_id"], "redeem", -hold["points"], "Reward applied: "+reward["name"], "nxtdeal:"+source_id, actor, reservation_id)
            db.execute("UPDATE holds SET status='redeemed' WHERE id=?", (reservation_id,))
        for award in awards:
            lp.add_entry(db, event["customer_id"], "bonus" if award.get("bonus") else "earn", award["points"], award["name"], "nxtdeal:"+source_id, actor, metadata=award | {"location":event["location"]})
        receipt = {"source_id":source_id, "customer_id":event["customer_id"], "kind":event["kind"],
                   "gross_cents":event["eligible_cents"], "discount_cents":discount, "net_cents":net,
                   "points_earned":sum(a["points"] for a in awards), "points_used":hold["points"] if reservation_id else 0,
                   "reservation_id":reservation_id, "balance_after":lp.member(db,event["customer_id"])["available"], "created_at":lp.now()}
        db.execute("INSERT INTO loyalty_receipts VALUES (?,?,?,?)", (source_id,event["customer_id"],lp.encoded(receipt),lp.now()))
        db.execute("UPDATE loyalty_jobs SET status='processed',error=NULL,updated_at=? WHERE source_id=?",(lp.now(),source_id))
        lp.audit(db, "native_checkout", actor, receipt)
        notify(db,event["customer_id"],"receipt",f"Your {event['kind']} receipt is ready. {receipt['points_earned']} points earned.","receipt:"+source_id)
        return receipt


def native_sources(customer_id):
    rows=[]
    for entity in ledger.get_all().values():
        if entity.entity_type not in {SERVICE_RECORD,PART_SALE,DELIVERY}:
            continue
        try:
            row=source_transaction(entity.id)
            if row["customer_id"]==customer_id:
                rows.append(row)
        except lp.LoyaltyError:
            continue
    return rows[-100:]


def link_parts_sale(source_id, customer_id, location, reason, actor):
    from copy import deepcopy
    from core.storage import save_graph
    from core.storage_paths import GRAPH_PATH
    customer_record(customer_id)
    entity=ledger.get_entity(source_id)
    if not entity or entity.entity_type!=PART_SALE or not reason.strip():
        raise lp.LoyaltyError("Select a parts sale and record invoice/customer verification.")
    if entity.attributes.get("customer_id") not in (None,"",customer_id):
        raise lp.LoyaltyError("This sale is already assigned to another customer.")
    external_id=entity.attributes.get("CustomerID")
    if external_id and external_id!=customer_record(customer_id).attributes.get("CustomerID"):
        raise lp.LoyaltyError("The invoice customer reference belongs to another customer.")
    cents(entity.attributes.get("SalePrice",entity.attributes.get("total")))
    with lp.transaction() as db:
        config=lp.active_program(db)
        if location not in (config.get("locations") or ["default"]):
            raise lp.LoyaltyError("Choose a participating location.")
        old=deepcopy(entity.attributes)
        entity.attributes.update(customer_id=customer_id,status="completed",location_id=location,
                                 loyalty_finalized_at=lp.now(),loyalty_finalization_reason=reason)
        try:
            save_graph(GRAPH_PATH)
        except Exception:
            entity.attributes=old
            raise
        lp.audit(db,"parts_sale_verified",actor,{"source_id":source_id,"customer_id":customer_id,"reason":reason})
        db.execute("INSERT OR IGNORE INTO loyalty_jobs VALUES (?,?,'pending',NULL,?)",(source_id,actor,lp.now()))
    return {"source_id":source_id,"customer_id":customer_id}


def enqueue(source_id, actor):
    if not lp.configured():
        return
    with lp.transaction() as db:
        db.execute("INSERT OR IGNORE INTO loyalty_jobs VALUES (?,?,'pending',NULL,?)",(source_id,actor,lp.now()))


def reconcile():
    """Bounded durable queue. Failed finalizations remain visible and retryable."""
    if not lp.configured():
        return {"processed":0}
    with lp.transaction() as db:
        # Recover a source saved immediately before a process/queue interruption.
        # Unmarked historical imports are deliberately not silently backfilled.
        for entity in list(ledger.get_all().values()):
            if entity.entity_type in {SERVICE_RECORD, PART_SALE, DELIVERY} and entity.attributes.get("loyalty_finalized_at"):
                db.execute("INSERT OR IGNORE INTO loyalty_jobs VALUES (?,?,'pending',NULL,?)",(entity.id,"system",lp.now()))
        lp.release_expired(db)
        jobs=[dict(r) for r in db.execute("SELECT * FROM loyalty_jobs WHERE status IN ('pending','failed','awaiting_reward') ORDER BY updated_at LIMIT 100")]
    processed=0
    for job in jobs:
        try:
            event=source_transaction(job["source_id"])
            with lp.transaction() as db:
                enrolled=db.execute("SELECT 1 FROM members WHERE customer_id=?",(event["customer_id"],)).fetchone()
                if not enrolled:
                    raise lp.LoyaltyError("Customer must enroll before points can be awarded.")
                held=db.execute("SELECT 1 FROM holds WHERE customer_id=? AND status='reserved'",(event["customer_id"],)).fetchone()
            if held:
                with lp.transaction() as db:
                    db.execute("UPDATE loyalty_jobs SET status='awaiting_reward',error=?,updated_at=? WHERE source_id=?",("Select the reserved reward during checkout.",lp.now(),job["source_id"]))
                continue
            complete_transaction(job["source_id"],job["actor"])
            with lp.transaction() as db:
                db.execute("UPDATE loyalty_jobs SET status='processed',error=NULL,updated_at=? WHERE source_id=?",(lp.now(),job["source_id"]))
            processed+=1
        except lp.LoyaltyError as exc:
            with lp.transaction() as db:
                db.execute("UPDATE loyalty_jobs SET status='failed',error=?,updated_at=? WHERE source_id=?",(str(exc),lp.now(),job["source_id"]))
    return {"processed":processed}


def refund(source_id, amount, reason, key, actor):
    lp.require_integer(amount,"Refund cents",1)
    if not reason.strip():
        raise lp.LoyaltyError("Refund reason is required.")
    with lp.transaction() as db:
        def perform():
            row=db.execute("SELECT * FROM loyalty_receipts WHERE source_id=?",(source_id,)).fetchone()
            if not row:
                raise lp.LoyaltyError("Loyalty receipt not found.")
            receipt=json.loads(row["data"])
            prior=db.execute("SELECT COALESCE(SUM(cents),0) FROM loyalty_refunds WHERE source_id=?",(source_id,)).fetchone()[0]
            total=prior+amount
            if total>receipt["net_cents"]:
                raise lp.LoyaltyError("Refund exceeds the remaining eligible amount.")
            entries=db.execute("SELECT * FROM entries WHERE source=? AND kind IN ('earn','bonus','redeem')",("nxtdeal:"+source_id,)).fetchall()
            for e in entries:
                target=abs(e["points"])*total//receipt["net_cents"]
                if e["kind"]=="redeem" and total!=receipt["net_cents"]:
                    continue  # Restore spent reward points only on a full return.
                reversed_points=db.execute("SELECT COALESCE(SUM(ABS(points)),0) FROM entries WHERE kind='reversal' AND reference=?",(e["id"],)).fetchone()[0]
                delta=max(0,target-reversed_points)
                if delta:
                    lp.add_entry(db,row["customer_id"],"reversal",delta if e["points"]<0 else -delta,reason,key,actor,e["id"])
            db.execute("INSERT INTO loyalty_refunds VALUES (?,?,?,?,?)",(key,source_id,amount,reason,lp.now()))
            notify(db,row["customer_id"],"refund","Your receipt was adjusted following a refund.","refund:"+key)
            lp.audit(db,"refund",actor,{"source_id":source_id,"refund_cents":amount,"reason":reason})
            return {"source_id":source_id,"refunded_cents":total,"balance":lp.member(db,row["customer_id"])["available"]}
        return lp.once(db,"refund:"+key,[source_id,amount,reason,actor],perform)
