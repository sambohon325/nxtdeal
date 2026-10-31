"""Public recipient opt-outs; no login, tracking redirect or GET mutation."""
import hmac
import re
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import HTMLResponse
from core import marketing_email_footer as footer
from core.dealeros import ledger
from core.entities import Entity

router = APIRouter()


def find(token):
    from api.routers import marketing_operations as m
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise HTTPException(404, "Invalid unsubscribe link")
    action = next((e for e in m.all_of(m.ACTION) if hmac.compare_digest(e.attributes.get("unsubscribe_token", ""), token)), None)
    if not action:
        raise HTTPException(404, "Invalid unsubscribe link")
    return action


def page(content):
    return HTMLResponse('<!doctype html><html><meta name="viewport" content="width=device-width"><title>Email preferences</title><body style="font:18px/1.6 Arial;max-width:560px;margin:60px auto;padding:24px">' + content + '</body></html>', headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"})


@router.get("/email-readiness")
def readiness(authorization: str = Header(None)):
    from api.routers import marketing_operations as m
    m.authorized(authorization)
    issues, dealer = [], None
    for fn in (footer.identity, footer.public_base):
        try:
            result = fn()
            if isinstance(result, dict):
                dealer = result
        except HTTPException as exc:
            issues.append(exc.detail)
    return {"identity": dealer, "issues": issues, "ready": not issues, "delivery_tracking": "provider_connection" if m.provider_ready() else "smtp_acceptance_only"}


@router.get("/unsubscribe/{token}")
def confirmation(token: str):
    from api.routers.marketing_operations import _lock
    with _lock:
        find(token)
    return page('<h1>Email preferences</h1><p>Stop promotional emails from this dealership. / Cancela los correos promocionales de este concesionario.</p><form method="post"><button style="padding:14px 24px">Unsubscribe / Cancelar suscripción</button></form>')


@router.post("/unsubscribe/{token}")
def unsubscribe(token: str):
    from api.routers import marketing_operations as m
    from api.routers.sales_crm_advanced import transaction
    with m._lock, transaction():
        action = find(token)
        address = action.attributes.get("sent_to") or action.attributes.get("approved_to")
        if not address:
            raise HTTPException(409, "Message has not been prepared for a recipient")
        key = footer.email_key(address)
        if not ledger.get_entity(key):
            ledger.add_entity(Entity(key, "MarketingEmailSuppression", {"source": "recipient_unsubscribe", "action_id": action.id, "created_at": m.now()}))
        # Also suppress duplicate CRM records sharing this address at dispatch.
        for e in m.all_of(m.ACTION):
            if e.attributes.get("channel") != "email" or e.attributes.get("status") not in {"draft", "approved", "rejected"}:
                continue
            try:
                m.check_recipient(e.attributes)
            except HTTPException as exc:
                if "unsubscribed" in str(exc.detail):
                    e.attributes.update(status="cancelled", reason="Recipient unsubscribed", revision=e.attributes.get("revision", 0)+1)
    return page('<h1>You are unsubscribed / Suscripción cancelada</h1><p>You will no longer receive promotional emails from this dealership.</p>')
