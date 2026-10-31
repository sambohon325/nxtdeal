"""
core/esignature.py -- eSignature (session 104 follow-up), the sixth of Sam's ~10
"completely missing" dealership workflows (Up System, BDC, Manager TO, Demo Drive,
Credit App, eSignature, F&I Workflow, Delivery Checklist, Lost Sale Recovery, Orphan
Owner Mining -- session 92's original spec).

2026-10-14 release boundary: creation, send, consent and signing are restricted to
the isolated non-persistent demo. External delivery is disabled in every mode until
reviewed contracting is implemented. The historical behavior below describes the
demo mechanics, not production readiness or legal sufficiency.

A real signing envelope (SignatureRequest): who needs to sign (customer, an optional
co-signer, and the dealer rep), against a snapshot of a specific Deal's generated
contract (core/deals.py's generate_contract() output). The contract is COPIED into
the envelope at creation time, not referenced live -- this is deliberate: what a
signer actually signed should never silently change if the underlying Deal record is
edited afterward, the same "snapshot, don't reference" precedent
core/dealership_events.py's audience-at-publish-time snapshot already established for
this codebase.

Honest scope note: there is no live e-signature platform (DocuSign, HelloSign, Adobe
Sign) connected in this sandbox. "Sending" an envelope is a state transition, not a
real email/SMS dispatch -- same honest-simulation precedent as
core/campaigns.py's activate_campaign(). "Signing" is a real, enforced action (a
signer must have given ESIGN-Act-style consent first, and must type their name to
sign) but it is a typed-name capture, not a cryptographic signature or a verified
IP/device fingerprint -- no such capability exists here, and this module never claims
otherwise.

Deliberately NOT wired into core/compliance.py's `deal_fund` gate this pass (which
would be a natural next step -- E-SIGN Act, 15 U.S.C. 7001, requires a genuine
signature before a credit transaction is complete). Skipped for the same reason
session 104's Credit Application work skipped wiring ECOA reasons into the compliance
gate: this codebase's real seed data already has many historically-funded Deals with
no SignatureRequest on file, and retroactively flagging all of them the moment this
rule existed would be a real, disruptive side effect (a flood of new
ComplianceAlert-driven DMs to every admin) rather than a considered decision -- flagged
for Sam to decide on directly, not assumed.
"""

from datetime import datetime, timezone
from copy import deepcopy
from core.contracting_readiness import execution_block

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import SIGNATURE_REQUEST, DEAL
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core import integrations_registry

STATUSES = ["draft", "sent", "completed", "declined", "voided"]
SIGNER_STATUSES = ["pending", "signed", "declined"]
SIGNER_ROLES = ["customer", "co_signer", "dealer_rep"]

_VERIFICATION_NOTE = (
    "Typed-name signature captured in NXTDeal. No cryptographic signature, "
    "biometric capture, or verified IP/device fingerprint is performed in this "
    "sandbox -- there is no connected e-signature platform."
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _all_requests():
    return [e for e in ledger.get_all().values() if e.entity_type == SIGNATURE_REQUEST]


def get_signature_request(request_id):
    entity = ledger.get_entity(request_id)
    if entity and entity.entity_type == SIGNATURE_REQUEST:
        return entity
    return None


def _new_signer(name, role, email=None, phone=None):
    return {
        "name": name,
        "role": role,
        "email": email or None,
        "phone": phone or None,
        "esign_consent": False,
        "esign_consent_at": None,
        "status": "pending",
        "signed_at": None,
        "typed_signature": None,
        "decline_reason": None,
    }


def create_signature_request(linked_deal_id, created_by, signers):
    """`signers` is a list of {"name", "role", "email"?, "phone"?} dicts -- at least
    one required. Requires the Deal to already have a generated contract on file
    (core/deals.py's generate_contract()); an envelope has nothing real to sign
    against otherwise."""

    deal = ledger.get_entity(linked_deal_id)
    if not deal or deal.entity_type != DEAL:
        return {"error": f"'{linked_deal_id}' is not a Deal"}

    contract = deal.attributes.get("contract")
    if not contract:
        return {"error": "This deal has no generated contract yet -- generate the contract before sending it for signature."}

    blocked = execution_block("signature_create")
    if blocked:
        return blocked

    if not signers:
        return {"error": "At least one signer is required"}

    built_signers = []
    for s in signers:
        name = (s.get("name") or "").strip()
        role = s.get("role")
        if not name:
            return {"error": "Every signer needs a name"}
        if role not in SIGNER_ROLES:
            return {"error": f"role must be one of {SIGNER_ROLES}"}
        built_signers.append(_new_signer(name, role, email=s.get("email"), phone=s.get("phone")))

    request_id = id_generator.generate("SIGN")

    entity = Entity(
        id=request_id,
        entity_type=SIGNATURE_REQUEST,
        attributes={
            "linked_deal_id": linked_deal_id,
            "status": "draft",
            "contract_snapshot": deepcopy(contract),
            "execution_mode": "sample_only",
            "signers": built_signers,
            "created_by": created_by,
            "created_at": _now(),
            "sent_at": None,
            "completed_at": None,
            "voided_at": None,
            "updated_at": _now(),
        },
    )

    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    return entity


def add_signer(request_id, name, role, email=None, phone=None):

    req = get_signature_request(request_id)
    if not req:
        return {"error": "Signature request not found"}

    if req.attributes.get("status") != "draft":
        return {"error": f"Envelope is '{req.attributes.get('status')}' -- signers can only be added while it's a draft"}

    name = (name or "").strip()
    if not name:
        return {"error": "Signer name is required"}
    if role not in SIGNER_ROLES:
        return {"error": f"role must be one of {SIGNER_ROLES}"}

    req.attributes["signers"].append(_new_signer(name, role, email=email, phone=phone))
    req.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return req


def remove_signer(request_id, signer_index):

    req = get_signature_request(request_id)
    if not req:
        return {"error": "Signature request not found"}

    if req.attributes.get("status") != "draft":
        return {"error": f"Envelope is '{req.attributes.get('status')}' -- signers can only be edited while it's a draft"}

    signers = req.attributes.get("signers") or []
    if not (0 <= signer_index < len(signers)):
        return {"error": "No signer at that index"}

    signers.pop(signer_index)
    req.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return req


def send_signature_request(request_id):
    """SIMULATED send -- no real email/SMS dispatch happens here, see this module's
    docstring. Marks the envelope 'sent' so signers can now consent + sign."""

    req = get_signature_request(request_id)
    if not req:
        return {"error": "Signature request not found"}

    if req.attributes.get("status") != "draft":
        return {"error": f"Envelope is already '{req.attributes.get('status')}'"}

    blocked = execution_block("signature_send")
    if blocked:
        return blocked

    if not req.attributes.get("signers"):
        return {"error": "Add at least one signer before sending"}

    # Route through the e-signature seam (Phase 3). With no e-sign adapter registered the
    # send is simulated (typed-name in-app signing still works exactly as before); register
    # a DocuSign/Dropbox Sign adapter and the SAME send delivers real signing links.
    dispatch = integrations_registry.send_signature({
        "envelope_id": req.id,
        "linked_deal_id": req.attributes.get("linked_deal_id"),
        "signers": req.attributes.get("signers"),
    })

    if dispatch.get("error"):
        return dispatch

    req.attributes["status"] = "sent"
    req.attributes["sent_at"] = _now()
    req.attributes["updated_at"] = _now()
    req.attributes["send_mode"] = "live" if not dispatch.get("simulated") else "simulated"
    req.attributes["send_provider"] = dispatch.get("provider")

    save_graph(GRAPH_PATH)

    return req


def capture_signer_consent(request_id, signer_index):
    """The real permissible-consent gate before a signature can be captured -- the
    ESIGN Act (15 U.S.C. 7001) requires a consumer's affirmative consent to conduct
    the transaction electronically before an e-signature is valid. sign() below
    refuses to run without this on file for that signer, an enforced gate, same
    shape as core/credit_app.py's give_fcra_consent()."""

    req = get_signature_request(request_id)
    if not req:
        return {"error": "Signature request not found"}

    if req.attributes.get("status") != "sent":
        return {"error": "Consent can only be captured once the envelope has been sent"}

    blocked = execution_block("signature_consent")
    if blocked:
        return blocked

    signers = req.attributes.get("signers") or []
    if not (0 <= signer_index < len(signers)):
        return {"error": "No signer at that index"}

    if signers[signer_index]["status"] != "pending":
        return {"error": f"This signer is already '{signers[signer_index]['status']}'"}

    signers[signer_index]["esign_consent"] = True
    signers[signer_index]["esign_consent_at"] = _now()
    req.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return req


def _names_reasonably_match(typed, on_file):
    typed_norm = "".join(ch for ch in typed.lower() if ch.isalnum())
    on_file_parts = [p for p in on_file.lower().split() if p]
    return any("".join(ch for ch in part if ch.isalnum()) in typed_norm for part in on_file_parts if len(part) > 1)


def sign(request_id, signer_index, typed_signature):

    req = get_signature_request(request_id)
    if not req:
        return {"error": "Signature request not found"}

    if req.attributes.get("status") != "sent":
        return {"error": "This envelope isn't awaiting signatures"}

    blocked = execution_block("signature_sign")
    if blocked:
        return blocked

    signers = req.attributes.get("signers") or []
    if not (0 <= signer_index < len(signers)):
        return {"error": "No signer at that index"}

    signer = signers[signer_index]

    if signer["status"] != "pending":
        return {"error": f"This signer is already '{signer['status']}'"}

    if not signer["esign_consent"]:
        return {"error": "This signer must consent to electronic signature before signing"}

    typed_signature = (typed_signature or "").strip()
    if not typed_signature:
        return {"error": "Typed signature is required"}

    if not _names_reasonably_match(typed_signature, signer["name"]):
        return {"error": f"Typed signature doesn't appear to match the signer on file ('{signer['name']}')"}

    signer["status"] = "signed"
    signer["signed_at"] = _now()
    signer["typed_signature"] = typed_signature
    signer["verification_note"] = _VERIFICATION_NOTE

    req.attributes["updated_at"] = _now()

    if all(s["status"] == "signed" for s in signers):
        req.attributes["status"] = "completed"
        req.attributes["completed_at"] = _now()

    save_graph(GRAPH_PATH)

    return req


def decline_signer(request_id, signer_index, reason):
    """A decline from any one required signer voids the whole envelope -- matching
    how a real e-sign platform behaves (a declined envelope needs a new one, not a
    partial completion)."""

    req = get_signature_request(request_id)
    if not req:
        return {"error": "Signature request not found"}

    if req.attributes.get("status") != "sent":
        return {"error": "This envelope isn't awaiting signatures"}

    if not (reason or "").strip():
        return {"error": "A decline requires a reason"}

    signers = req.attributes.get("signers") or []
    if not (0 <= signer_index < len(signers)):
        return {"error": "No signer at that index"}

    signers[signer_index]["status"] = "declined"
    signers[signer_index]["decline_reason"] = reason.strip()

    req.attributes["status"] = "declined"
    req.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return req


def void_signature_request(request_id):

    req = get_signature_request(request_id)
    if not req:
        return {"error": "Signature request not found"}

    if req.attributes.get("status") in ("completed", "voided"):
        return {"error": f"Envelope is already '{req.attributes.get('status')}'"}

    req.attributes["status"] = "voided"
    req.attributes["voided_at"] = _now()
    req.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return req


def list_signature_requests(linked_deal_id=None, status=None):

    requests = _all_requests()

    if linked_deal_id:
        requests = [r for r in requests if r.attributes.get("linked_deal_id") == linked_deal_id]

    if status:
        requests = [r for r in requests if r.attributes.get("status") == status]

    requests.sort(key=lambda r: r.attributes.get("created_at") or "", reverse=True)

    return requests


def is_deal_fully_signed(deal_id):
    """Real helper for a future compliance-gate wiring (see this module's docstring
    on why that wiring isn't done this pass) -- True if any SignatureRequest linked
    to this deal has reached 'completed'."""

    return any(r.attributes.get("status") == "completed" for r in list_signature_requests(linked_deal_id=deal_id))


def get_stats():
    """Real numbers off real records -- counts by status and a completion rate over
    sent envelopes. Empty/None where there's no sample yet, never a fabricated
    figure, same convention as core/demo_drive.py's / core/credit_app.py's
    get_stats()."""

    requests = _all_requests()

    if not requests:
        return {
            "total": 0,
            "draft": 0,
            "sent": 0,
            "completed": 0,
            "declined": 0,
            "voided": 0,
            "completion_rate_pct": None,
        }

    sent_or_beyond = [r for r in requests if r.attributes.get("status") in ("sent", "completed", "declined")]
    completed = sum(1 for r in requests if r.attributes.get("status") == "completed")

    return {
        "total": len(requests),
        "draft": sum(1 for r in requests if r.attributes.get("status") == "draft"),
        "sent": sum(1 for r in requests if r.attributes.get("status") == "sent"),
        "completed": completed,
        "declined": sum(1 for r in requests if r.attributes.get("status") == "declined"),
        "voided": sum(1 for r in requests if r.attributes.get("status") == "voided"),
        "completion_rate_pct": round(100 * completed / len(sent_or_beyond), 1) if sent_or_beyond else None,
    }
