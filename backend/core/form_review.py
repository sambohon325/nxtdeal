"""Draft packet evidence preflight. Submitted references are claims, never approval.

This evaluates engineering completeness only. It neither retrieves evidence nor
stores a grant, generates legal text, enables signing, or determines applicable law.
"""
from datetime import date, datetime, timezone
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

Text = Annotated[str, Field(min_length=1, max_length=256, pattern=r".*\S.*")]
State = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]


class DraftModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TransactionScope(DraftModel):
    dealer_id: Text
    location_id: Text
    selling_state: State
    buyer_state: State
    delivery_state: State
    registration_state: State
    transaction: Literal["cash", "dealer_held_installment", "assigned_installment", "lease"]
    vehicle: Literal["new", "used"]
    payment_frequency: Literal["monthly", "weekly", "biweekly", "not_applicable"]


class EvidenceClaim(DraftModel):
    reference: Text
    reviewer: Text
    reviewed_on: date
    review_due: date
    revoked: bool = False


class FormCandidate(DraftModel):
    form_id: Text
    revision: Text
    publisher: Text
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    effective_on: date
    retired_on: date | None = None
    dealer_id: Text
    location_id: Text
    jurisdiction: State
    transaction: Literal["cash", "dealer_held_installment", "assigned_installment", "lease"]
    vehicle: Literal["new", "used"]
    rights: list[Literal["populate", "reproduce", "print", "sign", "distribute"]] = Field(default_factory=list, max_length=5)
    rights_evidence: EvidenceClaim | None = None
    applicability_evidence: EvidenceClaim | None = None


class PacketDraft(DraftModel):
    scope: TransactionScope
    forms: list[FormCandidate] = Field(default_factory=list, max_length=100)
    required_form_ids: list[Text] = Field(default_factory=list, max_length=100)
    form_list_evidence: EvidenceClaim | None = None
    calculation_evidence: EvidenceClaim | None = None
    mapping_evidence: EvidenceClaim | None = None
    external_review_evidence: EvidenceClaim | None = None
    signature_delivery_evidence: EvidenceClaim | None = None
    retention_evidence: EvidenceClaim | None = None
    security_evidence: EvidenceClaim | None = None


def assess_packet_draft(draft: PacketDraft, *, today=None):
    today = today or datetime.now(timezone.utc).date()
    gaps = []
    def gap(field, reason):
        gaps.append({"field": field, "reason": reason})
    def evidence(field, claim):
        if claim is None:
            gap(field, "missing_evidence")
        elif claim.revoked:
            gap(field, "revoked_evidence")
        elif claim.reviewed_on > today or claim.review_due <= claim.reviewed_on:
            gap(field, "invalid_review_dates")
        elif claim.review_due <= today:
            gap(field, "review_expired")

    scope = draft.scope
    if any(state != "TX" for state in (scope.selling_state, scope.buyer_state, scope.delivery_state, scope.registration_state)):
        gap("scope", "separate_jurisdiction_review_required")
    if scope.transaction != "dealer_held_installment" or scope.vehicle != "used":
        gap("scope", "outside_proposed_pilot")
    if scope.payment_frequency == "not_applicable":
        gap("scope.payment_frequency", "installment_schedule_required")
    for field in ("form_list_evidence", "calculation_evidence", "mapping_evidence", "external_review_evidence",
                  "signature_delivery_evidence", "retention_evidence", "security_evidence"):
        evidence(field, getattr(draft, field))
    if not draft.required_form_ids:
        gap("required_form_ids", "reviewed_form_list_required")
    if len(set(draft.required_form_ids)) != len(draft.required_form_ids):
        gap("required_form_ids", "duplicate_form_id")
    present = set()
    for index, form in enumerate(draft.forms):
        path = f"forms[{index}]"
        if form.form_id in present:
            gap(path, "duplicate_form_id")
        present.add(form.form_id)
        if form.form_id not in draft.required_form_ids:
            gap(path, "form_not_on_reviewed_list")
        for field, expected in (("dealer_id", scope.dealer_id), ("location_id", scope.location_id),
                                ("jurisdiction", scope.selling_state), ("transaction", scope.transaction), ("vehicle", scope.vehicle)):
            if getattr(form, field) != expected:
                gap(f"{path}.{field}", "scope_mismatch")
        if form.effective_on > today:
            gap(path, "form_not_yet_effective")
        if form.retired_on is not None and form.retired_on <= today:
            gap(path, "form_retired")
        if set(form.rights) != {"populate", "reproduce", "print", "sign", "distribute"}:
            gap(f"{path}.rights", "packet_use_rights_incomplete")
        evidence(f"{path}.rights_evidence", form.rights_evidence)
        evidence(f"{path}.applicability_evidence", form.applicability_evidence)
    for missing in sorted(set(draft.required_form_ids) - present):
        gap("forms", f"required_form_missing:{missing}")
    return {"assessment": "gaps_found" if gaps else "evidence_claims_complete",
            "production_enabled": False, "executable": False, "evidence_verified": False,
            "as_of": today.isoformat(), "gaps": gaps, "form_count": len(draft.forms),
            "notice": "Draft completeness check only. Evidence references and document hashes have not been independently verified. Named reviewers must confirm applicability, rights and calculations; contract execution remains blocked."}
