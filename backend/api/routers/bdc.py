"""BDC orchestration over canonical audiences, templates and CRM sequences."""
import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime
from fastapi import APIRouter, Header, HTTPException
from pydantic import Field
from api.deps import _authenticate
from api.routers import sales_crm_advanced as seq
from api.routers import marketing_operations as delivery
from core.dealeros import ledger
from core import marketing_inventory
from core.email_templates import render_email_html, render_email_text
from core.email_templates_api import _can_access
from core.dealer_email_access import validate_email_patch, EmailHTMLCheck

router = APIRouter(prefix="/bdc", tags=["BDC center"])

class Step(seq.Model):
    channel: str = "email"
    delay_minutes: int = Field(default=0, ge=0, le=525600, strict=True)
    template_id: str | None = Field(default=None, max_length=100)
    subject: str = Field(default="", max_length=160)
    body: str = Field(default="", max_length=4000)
    inventory_ids: list[str] = Field(default_factory=list, max_length=6)

class Campaign(seq.Model):
    name: str = Field(min_length=1, max_length=100)
    audience_id: str = Field(min_length=1, max_length=100)
    steps: list[Step] = Field(min_length=1, max_length=20)
    start_local: str = Field(default="", max_length=32)

class Edit(Campaign):
    revision: int = Field(ge=1, strict=True)

class Launch(seq.Model):
    revision: int = Field(ge=1, strict=True)
    review_token: str = Field(min_length=64, max_length=64)
    start_at: datetime


def audience_ids(audience_id, actor):
    e = ledger.get_entity(audience_id)
    if not e or e.entity_type not in {"MarketingList", seq.SEGMENT} or e.attributes.get("archived"):
        raise HTTPException(422, "Choose an active saved list or segment")
    if e.entity_type == seq.SEGMENT:
        seq.segment_access(e, actor)
        return [r["id"] for r in seq.crm.records() if seq.matches(r, e.attributes)]
    return list(dict.fromkeys(e.attributes.get("member_ids", [])))


def resolve_steps(steps, authorization):
    actor = seq.crm.authorized(authorization)
    payload, _ = _authenticate(authorization)
    result = []
    for step in steps:
        s = step.model_dump()
        if s["channel"] not in {"email", "sms", "call"}:
            raise HTTPException(422, "Choose email, SMS or a call task")
        if step.template_id:
            t = seq.find(step.template_id, "EmailTemplate")
            if not _can_access(payload["role"], actor, t):
                raise HTTPException(403, "You do not have access to this email template")
            if step.channel != "email" or t.attributes.get("channel") != "email":
                raise HTTPException(422, "Choose an email template for an email step")
            try:
                validate_email_patch(payload["role"], actor, {}, t.attributes)
                t = deepcopy(t)
                for block in t.attributes.get("blocks", []):
                    fields = block.get("fields", {})
                    if fields.get("dealer_design") and fields.get("html"):
                        raw = fields["html"]
                        raw = re.sub(r'<tr data-nxtdeal-managed-footer="true">.*?</tr>', "", raw, flags=re.S)
                        # Older approved designs used this exact final footer cell.
                        raw = re.sub(r'<tr><td style="padding:28px;font-size:12px;.*?</tr>(?=</table></td></tr></table>$)', "", raw, flags=re.S)
                        fields["html"] = raw
                html = render_email_html(t)
                EmailHTMLCheck().feed(html)
                if len(html.encode("utf-8")) > 500000:
                    raise ValueError("Email is larger than 500 KB")
            except (ValueError, TypeError) as exc:
                raise HTTPException(422, str(exc)) from exc
            s.update(subject=t.attributes.get("subject", ""), body=render_email_text(t), html_body=html)
        
        if step.inventory_ids:
            if step.channel != "email":
                raise HTTPException(422, "Suggested inventory requires an email step")
            rows = marketing_inventory.snapshot(step.inventory_ids)
            cards, text = marketing_inventory.render(rows)
            s["body"] += text
            html = s.get("html_body") or "<p>" + __import__("html").escape(step.body).replace("\n", "<br>") + "</p>"
            pos = html.lower().rfind("</body>")
            s["html_body"] = html[:pos] + cards + html[pos:] if pos >= 0 else html + cards
            s["inventory_snapshot"] = rows
        result.append(s)
    return result


def require_complete(campaign):
    if not campaign.attributes.get("bdc_config"):
        raise HTTPException(422, "Open this legacy sequence in existing follow-ups")
    for step in campaign.attributes["steps"]:
        if not step.get("body", "").strip() or (step["channel"] == "email" and not step.get("subject", "").strip()):
            raise HTTPException(422, "Each step needs a message; emails also need a subject")


def eligible(campaign, actor):
    require_complete(campaign)
    ids = audience_ids(campaign.attributes["bdc_config"]["audience_id"], actor)
    existing = {e.attributes["recipient_id"] for e in seq.all_of(seq.ENROLLMENT) if e.attributes["sequence_id"] == campaign.id}
    included, excluded = [], []
    for rid in ids:
        recipient = ledger.get_entity(rid)
        reason = seq.stop_reason(recipient, {"started_at": seq.now().isoformat()})
        if rid in existing:
            reason = "Already enrolled in this campaign"
        if not reason:
            for step in campaign.attributes["steps"]:
                if step["channel"] == "call":
                    if recipient.entity_type != "Lead":
                        reason = "Call tasks require a lead record"
                else:
                    try:
                        delivery.check_recipient({"channel": step["channel"], "recipient_id": rid, "sequence_id": campaign.id, "sequence_revision": campaign.attributes["revision"]})
                    except HTTPException as exc:
                        reason = str(exc.detail)
                if reason:
                    break
        if reason:
            excluded.append({"id": rid, "reason": reason})
        else:
            included.append(rid)
    token = hashlib.sha256(json.dumps({"id":campaign.id,"revision":campaign.attributes["revision"],"included":sorted(included),"excluded":excluded}, sort_keys=True).encode()).hexdigest()
    return {"eligible_ids":included,"excluded":excluded,"total":len(ids),"review_token":token}


@router.get("/inventory-options")
def inventory_options(authorization: str = Header(None)):
    seq.crm.authorized(authorization)
    return marketing_inventory.available()


@router.get("/campaigns")
def campaigns(authorization: str = Header(None)):
    seq.crm.authorized(authorization)
    return [seq.serial(e) for e in seq.all_of(seq.SEQUENCE) if e.attributes.get("bdc_config")]


@router.post("/campaigns")
def create(body: Campaign, authorization: str = Header(None)):
    actor = seq.crm.authorized(authorization)
    with seq._lock, seq.transaction():
        audience_ids(body.audience_id, actor)
        steps = resolve_steps(body.steps, authorization)
        e = seq.create("CRMSEQ", seq.SEQUENCE, {"name":body.name,"steps":steps,"archived":False,"bdc_config":body.model_dump(),"bdc_status":"draft"}, actor)
    return seq.serial(e)


@router.put("/campaigns/{campaign_id}")
def edit(campaign_id: str, body: Edit, authorization: str = Header(None)):
    actor = seq.crm.authorized(authorization)
    with seq._lock, seq.transaction():
        e = seq.find(campaign_id, seq.SEQUENCE)
        seq.can_edit(e, actor, authorization)
        if any(x.attributes["sequence_id"] == e.id for x in seq.all_of(seq.ENROLLMENT)):
            raise HTTPException(409, "This campaign has started. Create a new campaign to change its message or audience")
        audience_ids(body.audience_id, actor)
        seq.revise(e, body.revision, {"name":body.name,"steps":resolve_steps(body.steps, authorization),"bdc_config":body.model_dump(exclude={"revision"}),"bdc_status":"draft"}, actor)
    return seq.serial(e)


@router.get("/campaigns/{campaign_id}/review")
def review(campaign_id: str, authorization: str = Header(None)):
    actor = seq.crm.authorized(authorization)
    with seq._lock:
        e = seq.find(campaign_id, seq.SEQUENCE)
        seq.can_edit(e, actor, authorization)
        if not e.attributes.get("bdc_config"):
            raise HTTPException(422, "Open this legacy sequence in existing follow-ups")
        return {**eligible(e,actor),"steps":deepcopy(e.attributes["steps"]),"channels":{c:delivery.channel_ready(c) for c in ("email","sms")},"approval_required":True}


@router.post("/campaigns/{campaign_id}/launch")
def launch(campaign_id: str, body: Launch, authorization: str = Header(None)):
    actor = seq.crm.authorized(authorization)
    if body.start_at.tzinfo is None:
        raise HTTPException(422, "Start time requires a timezone")
    with seq._lock, seq.transaction():
        e = seq.find(campaign_id, seq.SEQUENCE)
        seq.can_edit(e, actor, authorization)
        # Retried requests cannot add recipients or dispatch twice.
        if e.attributes.get("bdc_launch_token") == body.review_token:
            return {"enrolled":e.attributes["bdc_enrolled"],"replayed":True}
        if e.attributes.get("bdc_status") == "scheduled":
            raise HTTPException(409, "Campaign already started. Manage its existing follow-ups")
        check = eligible(e,actor)
        if e.attributes["revision"] != body.revision or check["review_token"] != body.review_token:
            raise HTTPException(409, "Audience or campaign changed. Review the current recipients again")
        if not check["eligible_ids"] or len(check["eligible_ids"]) > 100:
            raise HTTPException(422, "Choose an audience with 1–100 eligible recipients")
        # Reuse the canonical enrollment path and its transactional duplicate guards.
        enrolled = seq.enroll_locked(e.id, seq.Enroll(recipient_ids=check["eligible_ids"],start_at=body.start_at),actor)
        seq.revise(e,body.revision,{"bdc_status":"scheduled","bdc_launch_token":body.review_token,"bdc_enrolled":len(enrolled)},actor)
    return {"enrolled":len(enrolled),"replayed":False}


@router.get("/results")
def results(authorization: str = Header(None)):
    seq.crm.authorized(authorization)
    actions = [e for e in seq.all_of(delivery.ACTION) if e.attributes.get("sequence_enrollment_id")]
    return {"messages":dict(Counter(e.attributes["status"] for e in actions)),"followups":dict(Counter(e.attributes["status"] for e in seq.all_of(seq.ENROLLMENT))),"attribution":"Message outcomes only. Sales and service revenue are not attributed."}


class Permission(seq.Model):
    recipient_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1, strict=True)
    evidence: str = Field(min_length=15, max_length=1000)


@router.post("/campaigns/{campaign_id}/permission")
def record_permission(campaign_id: str, body: Permission, authorization: str = Header(None)):
    """Record permission for one reviewed email, never a global subscription."""
    actor = seq.crm.authorized(authorization)
    with seq._lock, seq.transaction():
        campaign = seq.find(campaign_id, seq.SEQUENCE)
        seq.can_edit(campaign, actor, authorization)
        require_complete(campaign)
        if campaign.attributes["revision"] != body.revision:
            raise HTTPException(409, "Campaign changed. Review it again")
        if len(campaign.attributes["steps"]) != 1 or campaign.attributes["steps"][0]["channel"] != "email":
            raise HTTPException(422, "Single-message permission requires one email step")
        if any(e.attributes["sequence_id"] == campaign.id for e in seq.all_of(seq.ENROLLMENT)):
            raise HTTPException(409, "This campaign has already started")
        if body.recipient_id not in audience_ids(campaign.attributes["bdc_config"]["audience_id"], actor):
            raise HTTPException(422, "Recipient is not in this audience")
        recipient = ledger.get_entity(body.recipient_id)
        if not recipient or recipient.entity_type not in {"Lead", "Customer"}:
            raise HTTPException(404, "Contact not found")
        if any(recipient.attributes.get(k) in (True, "true", "True", "1", 1) for k in ("DoNotContact", "do_not_contact", "unsubscribed")):
            raise HTTPException(409, "Contact is opted out; permission cannot override an opt-out")
        permission = {"revision": body.revision, "evidence": body.evidence, "recorded_by": actor, "recorded_at": seq.now().isoformat()}
        recipient.attributes.setdefault("bdc_email_permissions", {})[campaign_id] = permission
        seq.create("CRMPERM", "SalesCrmPermissionAudit", {"recipient_id": recipient.id, "campaign_id": campaign_id, **permission}, actor)
    return {"recorded": True, "scope": "one_email", "campaign_id": campaign_id}
