"""
AI-demo lead capture + accounts (2026-07-25, Sam: the demo needs a real lead-gen form — name,
position, dealership, city, state/country, phone, email — plus a bot check and a username/password
so a prospect can return without re-filling the form).

Lives in the Hub (hub-api) because the demo tenant itself is non-persistent: leads are durable
growth data NXTDeal works, so they belong here and survive demo redeploys. This module owns the
lead/account records, sign-up (with Cloudflare Turnstile bot verification), login, and a
password-reset flow. The actual demo SANDBOX session is still minted by demo-api after auth — this
just gates entry and remembers the prospect.

Turnstile: if TURNSTILE_SECRET_KEY is set on hub-api, sign-up server-verifies the token with
Cloudflare; if it's not set yet, verification is skipped (allowed) so the form works during setup
and automatically starts enforcing the moment you add the key.
"""

import json
import os
import secrets as pysecrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from hub_core.auth import hash_password, verify_password
from hub_core import demo_leads_storage as store

DEMO_ACCOUNTS_PATH = store.DEMO_ACCOUNTS_PATH
RESET_TTL_SECONDS = 60 * 60  # 1 hour
_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _norm_email(email):
    return (email or "").strip().lower()


# ---------------------------------------------------------------------------------------------
# Cloudflare Turnstile (bot protection)
# ---------------------------------------------------------------------------------------------

def _turnstile_secret():
    return os.environ.get("TURNSTILE_SECRET_KEY", "").strip()


def turnstile_enabled():
    return bool(_turnstile_secret())


def verify_turnstile(token, remoteip=None):
    """Returns True if the human passed (or if Turnstile isn't configured yet)."""
    secret = _turnstile_secret()
    if not secret:
        return True  # not configured — allow so the form works before keys are added
    if not token:
        return False
    body = {"secret": secret, "response": token}
    if remoteip:
        body["remoteip"] = remoteip
    data = urllib.parse.urlencode(body).encode("utf-8")
    try:
        request = urllib.request.Request(_TURNSTILE_VERIFY_URL, data=data, method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
        return bool(result.get("success"))
    except (urllib.error.URLError, json.JSONDecodeError, ValueError):
        # If Cloudflare is unreachable, fail CLOSED (treat as not verified) — a configured
        # Turnstile that can't be checked shouldn't silently let bots through.
        return False


# ---------------------------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------------------------

def _public(record):
    """Non-secret view handed back to the client (never salt/hash)."""
    return {
        "email": record.get("email"),
        "username": record.get("username"),
        "name": record.get("name"),
        "position": record.get("position"),
        "persona": record.get("persona"),
        "dealership": record.get("dealership"),
        "city": record.get("city"),
        "region": record.get("region"),
        "country": record.get("country"),
        "phone": record.get("phone"),
    }


def _lead_view(record):
    """Admin/Hub-console view of a lead (profile + timestamps, no credentials)."""
    v = _public(record)
    v["created_at"] = record.get("created_at")
    v["last_login"] = record.get("last_login")
    return v


def sign_up(*, name, email, password, persona, position=None, dealership=None, city=None,
            region=None, country=None, phone=None, username=None, turnstile_token=None, remoteip=None):
    email = _norm_email(email)
    if not email or "@" not in email:
        return {"error": "Enter a valid email address."}
    if not (name or "").strip():
        return {"error": "Enter your name."}
    if len(password or "") < 8:
        return {"error": "Password must be at least 8 characters."}
    if not (persona or "").strip():
        return {"error": "Pick the role that best describes you."}
    if store.get(email):
        return {"error": "An account with this email already exists — sign in instead."}
    if username and store.get_by_username(username) and _norm_email(username) != email:
        return {"error": "That username is taken — try another."}
    if not verify_turnstile(turnstile_token, remoteip=remoteip):
        return {"error": "The bot check didn't pass — please try again."}

    salt_hex, hash_hex = hash_password(password)
    record = {
        "email": email,
        "username": (username or email).strip(),
        "name": name.strip(),
        "position": position,
        "persona": persona,
        "dealership": dealership,
        "city": city,
        "region": region,
        "country": country,
        "phone": phone,
        "salt": salt_hex,
        "hash": hash_hex,
        "created_at": _now(),
        "last_login": _now(),
    }
    store.put(email, record)
    store.save_demo_accounts(DEMO_ACCOUNTS_PATH)
    return {"ok": True, "account": _public(record)}


def log_in(identifier, password):
    rec = store.get(_norm_email(identifier)) or store.get_by_username(identifier)
    if not rec or not verify_password(password, rec["salt"], rec["hash"]):
        return {"error": "Incorrect email/username or password."}
    rec["last_login"] = _now()
    store.save_demo_accounts(DEMO_ACCOUNTS_PATH)
    return {"ok": True, "account": _public(rec)}


def _expose_reset_token():
    """SECURITY: the reset token must never be handed back to an anonymous caller — that let
    anyone reset any demo account by POSTing its email. It is surfaced ONLY when an operator
    explicitly opts in (local testing), never by default."""
    return os.environ.get("HUB_EXPOSE_RESET_TOKEN") == "1"


def request_reset(email):
    """Start a password reset. ALWAYS returns an identical body so the response never reveals
    whether the email exists (no enumeration). The token is generated only when the account
    exists and is delivered out-of-band; it is not returned to the caller unless an operator
    opts in via HUB_EXPOSE_RESET_TOKEN (local testing)."""
    rec = store.get(_norm_email(email))
    if not rec:
        return {"ok": True}
    token = pysecrets.token_urlsafe(24)
    rec["reset_token"] = token
    rec["reset_expires"] = (datetime.now(timezone.utc) + timedelta(seconds=RESET_TTL_SECONDS)).isoformat()
    store.save_demo_accounts(DEMO_ACCOUNTS_PATH)
    # TODO: deliver via a real email provider. Never echo the token to the client by default.
    if _expose_reset_token():
        return {"ok": True, "dev_reset_token": token}
    return {"ok": True}


def reset_password(email, token, new_password):
    rec = store.get(_norm_email(email))
    if not rec or not rec.get("reset_token") or rec.get("reset_token") != token:
        return {"error": "Invalid or expired reset link."}
    try:
        expires = datetime.fromisoformat(rec.get("reset_expires"))
        if datetime.now(timezone.utc) > expires:
            return {"error": "That reset link expired — request a new one."}
    except (TypeError, ValueError):
        return {"error": "Invalid reset link."}
    if len(new_password or "") < 8:
        return {"error": "Password must be at least 8 characters."}
    salt_hex, hash_hex = hash_password(new_password)
    rec["salt"], rec["hash"] = salt_hex, hash_hex
    rec.pop("reset_token", None)
    rec.pop("reset_expires", None)
    store.save_demo_accounts(DEMO_ACCOUNTS_PATH)
    return {"ok": True}


def list_leads():
    return sorted(
        (_lead_view(r) for r in store.all_records().values()),
        key=lambda r: r.get("created_at") or "",
        reverse=True,
    )


def config():
    return {"turnstile_enabled": turnstile_enabled()}
