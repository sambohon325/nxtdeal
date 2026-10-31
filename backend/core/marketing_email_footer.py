"""Dealer-owned campaign identity and recipient-specific opt-out links."""
import hashlib
import os
import secrets
from html import escape
from urllib.parse import urlsplit

from fastapi import HTTPException
from core.dealeros import ledger


def identity():
    record = ledger.get_entity("SYSCFG-00001")
    a = record.attributes if record else {}
    required = ("dealership_name", "address_line1", "city", "state", "zip_code")
    if any(not str(a.get(k) or "").strip() for k in required):
        raise HTTPException(409, "Complete the dealership name and mailing address in Administration → Organizations before sending campaigns")
    return {"name": str(a.get("dba_name") or a["dealership_name"]).strip(), "address": ", ".join(str(a[k]).strip() for k in ("address_line1", "address_line2", "city", "state", "zip_code") if a.get(k))}


def public_base():
    value = os.getenv("NXTDEAL_MARKETING_PUBLIC_URL", "").rstrip("/")
    p = urlsplit(value)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise HTTPException(503, "Configure the public HTTPS campaign unsubscribe address before sending")
    return value


def email_key(address):
    return "MUNSUB-" + hashlib.sha256(address.strip().casefold().encode()).hexdigest()


def is_suppressed(address):
    return ledger.get_entity(email_key(address)) is not None


def prepare(action):
    dealer = identity()
    token = action.get("unsubscribe_token") or secrets.token_urlsafe(32)
    url = public_base() + "/marketing/operations/unsubscribe/" + token
    footer = f'<div data-nxtdeal-footer="true" style="padding:24px;font:12px/1.6 Arial,sans-serif;color:#555;background:#f5f5f5;text-align:center">{escape(dealer["name"])}<br>{escape(dealer["address"])}<br><a href="{escape(url, quote=True)}" style="color:#333">Unsubscribe / Cancelar suscripción</a></div>'
    body = action["body"] + "\n\n" + dealer["name"] + "\n" + dealer["address"] + "\nUnsubscribe / Cancelar suscripción: " + url
    html = action.get("html_body", "")
    if html:
        # Keep imported designs intact. The required footer is outside author content.
        pos = html.lower().rfind("</body>")
        html = html[:pos] + footer + html[pos:] if pos >= 0 else html + footer
    return {"unsubscribe_token": token, "unsubscribe_url": url, "mailing_identity": dealer, "send_body": body, "send_html_body": html}
