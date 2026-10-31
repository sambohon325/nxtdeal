"""Scoped assistant grants, separate from employee session credentials and graph data.

Pre-registered public clients only; code + S256 PKCE, exact redirects, audience
binding, rotating refresh tokens and durable revocation. No implicit/client grants.
SQLite transactions keep one-use credentials atomic across concurrent requests.
"""
import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlsplit, urlencode

from core.storage_paths import storage_path

SCOPES = {"nxtdeal:read", "nxtdeal:propose"}
TTL = 3600
GRANT_TTL = 30 * 86400


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def https_url(value):
    p = urlsplit(value)
    if (p.scheme != "https" or not p.hostname or p.username or p.password or p.fragment
            or any(ord(c) < 33 for c in value) or "\\" in value):
        raise ValueError("An exact HTTPS URL without credentials or fragment is required")
    return value


def issuer():
    return https_url(os.getenv("NXTDEAL_PUBLIC_API_URL", "https://api.nxtdeal.app").rstrip("/"))


def resource():
    return issuer() + "/agent-fabric/mcp"


def frontend():
    return https_url(os.getenv("NXTDEAL_PUBLIC_APP_URL", "https://app.nxtdeal.app").rstrip("/"))


@contextmanager
def database():
    path = Path(storage_path("assistant_oauth.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    if os.name != "nt":
        path.chmod(0o600)
    db.row_factory = sqlite3.Row
    try:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS clients(id TEXT PRIMARY KEY, name TEXT NOT NULL, redirects TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, client TEXT NOT NULL, redirect TEXT NOT NULL, challenge TEXT NOT NULL, state TEXT NOT NULL, scopes TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS grants(id TEXT PRIMARY KEY, employee TEXT NOT NULL, client TEXT NOT NULL, scopes TEXT NOT NULL, departments TEXT NOT NULL, audience TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, credential_version TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS codes(hash TEXT PRIMARY KEY, grant_id TEXT NOT NULL, redirect TEXT NOT NULL, challenge TEXT NOT NULL, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY, grant_id TEXT NOT NULL, kind TEXT NOT NULL, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at REAL NOT NULL, employee TEXT, event TEXT NOT NULL, target TEXT NOT NULL);
        ''')
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM tokens WHERE expires<?", (time.time(),))
        db.execute("DELETE FROM codes WHERE expires<?", (time.time(),))
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def audit(db, employee, event, target):
    db.execute("INSERT INTO audit(at,employee,event,target) VALUES(?,?,?,?)", (time.time(), employee, event, target))


def active_employee(employee):
    from core.auth import credential_store
    record = credential_store.get_record(employee)
    if not record or record.get("disabled") or record.get("must_change_password") or record.get("ip_allowlist"):
        raise PermissionError("Employee access is no longer active")
    return record


def credential_version(employee):
    record = active_employee(employee)
    return digest(str(record.get("salt", "")) + ":" + str(record.get("hash", "")))


def interactive(actor, admin=False):
    record = active_employee(actor["employee_id"])
    if actor.get("principal") != "session" or (admin and record["role"] != "ADMIN"):
        raise PermissionError("Interactive administrator session required" if admin else "Interactive employee session required")


def register_client(actor, name, redirects):
    interactive(actor, admin=True)
    if not name.strip() or len(name) > 100 or not 1 <= len(redirects) <= 5:
        raise ValueError("Client name and one to five exact callbacks required")
    for uri in redirects:
        https_url(uri)
        if len(uri) > 2000 or urlsplit(uri).query:
            raise ValueError("Callback must not contain query parameters")
    client_id = "nxtclient_" + secrets.token_urlsafe(20)
    with database() as db:
        if db.execute("SELECT count(*) FROM clients WHERE disabled=0").fetchone()[0] >= 50:
            raise ValueError("Client limit reached")
        db.execute("INSERT INTO clients VALUES(?,?,?,0)", (client_id, name.strip(), json.dumps(sorted(set(redirects)))))
        audit(db, actor["employee_id"], "client.registered", client_id)
    return {"client_id": client_id, "client_name": name.strip(), "redirect_uris": redirects, "token_endpoint_auth_method": "none"}


def disable_client(actor, client_id):
    interactive(actor, admin=True)
    with database() as db:
        db.execute("UPDATE clients SET disabled=1 WHERE id=?", (client_id,))
        db.execute("UPDATE grants SET revoked=1 WHERE client=?", (client_id,))
        audit(db, actor["employee_id"], "client.disabled", client_id)


def begin(params):
    if params.get("response_type") != "code" or params.get("code_challenge_method") != "S256":
        raise ValueError("Authorization code and S256 PKCE required")
    if params.get("resource") != resource():
        raise ValueError("Invalid resource")
    challenge = params.get("code_challenge", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", challenge):
        raise ValueError("Invalid S256 challenge")
    state = params.get("state", "")
    if not 1 <= len(state) <= 1024:
        raise ValueError("Bounded OAuth state required")
    scopes = set(params.get("scope", "").split())
    if "nxtdeal:read" not in scopes or not scopes <= SCOPES:
        raise ValueError("Invalid scope")
    with database() as db:
        client = db.execute("SELECT * FROM clients WHERE id=? AND disabled=0", (params.get("client_id"),)).fetchone()
        if not client or params.get("redirect_uri") not in json.loads(client["redirects"]):
            raise ValueError("Unregistered client or callback")
        db.execute("DELETE FROM requests WHERE expires<?", (time.time(),))
        if db.execute("SELECT count(*) FROM requests").fetchone()[0] >= 1000:
            raise ValueError("Too many pending requests")
        request_id = secrets.token_urlsafe(32)
        db.execute("INSERT INTO requests VALUES(?,?,?,?,?,?,?)", (digest(request_id), client["id"], params["redirect_uri"], challenge, state, " ".join(sorted(scopes)), time.time()+600))
    return request_id


def pending(db, request_id):
    row = db.execute("SELECT r.*,c.name FROM requests r JOIN clients c ON c.id=r.client WHERE r.id=? AND r.expires>? AND c.disabled=0", (digest(request_id), time.time())).fetchone()
    if not row:
        raise ValueError("Connection request expired or already handled; restart from your assistant")
    return row


def review(actor, request_id):
    from core import agent_fabric as fabric
    interactive(actor)
    with database() as db:
        row = pending(db, request_id)
        return {"client_name": row["name"], "client_id": row["client"], "redirect_uri": row["redirect"],
                "scopes": row["scopes"].split(), "expires": row["expires"], "resource": resource(),
                "departments": [a["department"] for a in fabric.catalog(actor)["agents"]]}


def consent(actor, request_id, departments, approve):
    from core import agent_fabric as fabric
    interactive(actor)
    allowed = {a["department"] for a in fabric.catalog(actor)["agents"]}
    if approve and (not departments or not set(departments) <= allowed):
        raise ValueError("Select only departments available to your employee role")
    with database() as db:
        row = pending(db, request_id)
        db.execute("DELETE FROM requests WHERE id=?", (row["id"],))
        result = {"state": row["state"]}
        if approve:
            if db.execute("SELECT count(*) FROM grants WHERE employee=? AND revoked=0 AND expires>?", (actor["employee_id"], time.time())).fetchone()[0] >= 30:
                raise ValueError("Revoke an old connection before adding another")
            grant_id = secrets.token_urlsafe(24)
            code = secrets.token_urlsafe(32)
            db.execute("INSERT INTO grants VALUES(?,?,?,?,?,?,?,?,?,0)", (grant_id, actor["employee_id"], row["client"], row["scopes"], json.dumps(sorted(set(departments))), resource(), time.time(), time.time()+GRANT_TTL, credential_version(actor["employee_id"])))
            db.execute("INSERT INTO codes VALUES(?,?,?,?,?,0)", (digest(code), grant_id, row["redirect"], row["challenge"], time.time()+120))
            audit(db, actor["employee_id"], "grant.approved", grant_id)
            result["code"] = code
        else:
            result["error"] = "access_denied"
            audit(db, actor["employee_id"], "grant.denied", row["client"])
        return {"redirect_url": row["redirect"] + "?" + urlencode(result)}


def valid_grant(db, grant_id, client_id=None):
    row = db.execute("SELECT g.* FROM grants g JOIN clients c ON g.client=c.id WHERE g.id=? AND g.revoked=0 AND c.disabled=0 AND g.expires>?", (grant_id, time.time())).fetchone()
    if not row or row["audience"] != resource() or (client_id is not None and row["client"] != client_id):
        raise ValueError("Invalid grant")
    if not hmac.compare_digest(row["credential_version"], credential_version(row["employee"])):
        raise ValueError("Employee credentials changed")
    return row


def issue(db, grant):
    if db.execute("SELECT count(*) FROM tokens WHERE grant_id=?", (grant["id"],)).fetchone()[0] >= 5000:
        raise ValueError("Connection refresh limit reached; revoke and reconnect")
    access, refresh = "nxtoa_" + secrets.token_urlsafe(32), "nxtrf_" + secrets.token_urlsafe(32)
    expiry = min(time.time()+TTL, grant["expires"])
    db.execute("INSERT INTO tokens VALUES(?,?,?, ?,0)", (digest(access), grant["id"], "access", expiry))
    db.execute("INSERT INTO tokens VALUES(?,?,?, ?,0)", (digest(refresh), grant["id"], "refresh", grant["expires"]))
    return {"access_token": access, "refresh_token": refresh, "token_type": "Bearer", "expires_in": max(0, int(expiry-time.time())), "scope": grant["scopes"]}


def exchange(params):
    if params.get("resource") != resource() or not params.get("client_id"):
        raise ValueError("Invalid resource or client")
    replay = False
    with database() as db:
        kind = params.get("grant_type")
        if kind == "authorization_code":
            row = db.execute("SELECT * FROM codes WHERE hash=?", (digest(params.get("code", "")),)).fetchone()
            if not row or row["expires"] <= time.time():
                raise ValueError("Invalid grant")
            grant = valid_grant(db, row["grant_id"], params["client_id"])
            verifier = params.get("code_verifier", "")
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
            if not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier) or not hmac.compare_digest(challenge, row["challenge"]) or params.get("redirect_uri") != row["redirect"]:
                raise ValueError("Invalid grant")
            if row["used"]:
                replay = True
            else:
                db.execute("UPDATE codes SET used=1 WHERE hash=?", (row["hash"],))
        elif kind == "refresh_token":
            row = db.execute("SELECT * FROM tokens WHERE hash=? AND kind='refresh'", (digest(params.get("refresh_token", "")),)).fetchone()
            if not row or row["expires"] <= time.time():
                raise ValueError("Invalid grant")
            grant = valid_grant(db, row["grant_id"], params["client_id"])
            if params.get("scope", grant["scopes"]) != grant["scopes"]:
                raise ValueError("Scope cannot change during refresh")
            if row["used"]:
                replay = True
            else:
                db.execute("UPDATE tokens SET used=1 WHERE hash=?", (row["hash"],))
        else:
            raise ValueError("Unsupported grant type")
        if replay:
            db.execute("UPDATE grants SET revoked=1 WHERE id=?", (grant["id"],))
            audit(db, grant["employee"], "grant.replay_revoked", grant["id"])
        else:
            result = issue(db, grant)
    if replay:
        raise ValueError("Invalid grant")
    return result


def verify(token):
    if not token or not token.startswith("nxtoa_"):
        return None
    try:
        with database() as db:
            row = db.execute("SELECT * FROM tokens WHERE hash=? AND kind='access' AND expires>?", (digest(token), time.time())).fetchone()
            if not row:
                return None
            grant = valid_grant(db, row["grant_id"])
            employee = active_employee(grant["employee"])
            return {"employee_id": grant["employee"], "role": employee["role"], "principal": "oauth",
                    "session_id": digest(token)[:24], "oauth_grant": grant["id"], "oauth_scopes": grant["scopes"].split(), "oauth_departments": json.loads(grant["departments"])}
    except (ValueError, PermissionError):
        return None


def revoke(actor, grant_id):
    interactive(actor)
    with database() as db:
        db.execute("UPDATE grants SET revoked=1 WHERE id=? AND employee=?", (grant_id, actor["employee_id"]))
        audit(db, actor["employee_id"], "grant.revoked", grant_id)


def revoke_token(token, client_id):
    with database() as db:
        row = db.execute("SELECT g.* FROM grants g JOIN tokens t ON t.grant_id=g.id WHERE t.hash=? AND g.client=?", (digest(token), client_id)).fetchone()
        if row:
            db.execute("UPDATE grants SET revoked=1 WHERE id=?", (row["id"],))
            audit(db, row["employee"], "grant.token_revoked", row["id"])


def connections(actor):
    interactive(actor)
    with database() as db:
        grants = [dict(r) for r in db.execute("SELECT g.id,c.name,g.scopes,g.departments,g.created,g.expires,g.revoked FROM grants g JOIN clients c ON g.client=c.id WHERE employee=? ORDER BY created DESC LIMIT 100", (actor["employee_id"],))]
        clients = [dict(r) for r in db.execute("SELECT id,name,redirects,disabled FROM clients ORDER BY name")] if active_employee(actor["employee_id"])["role"] == "ADMIN" else []
    return {"mcp_url": resource(), "issuer": issuer(), "grants": grants, "clients": clients,
            "registration": "Pre-registered public clients with exact HTTPS callbacks and S256 PKCE", "scopes": sorted(SCOPES)}
