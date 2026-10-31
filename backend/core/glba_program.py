"""
core/glba_program.py -- GLBA Safeguards Rule Information Security Program tracking
(security-hardening pass, 2026-07-20, Task #11 "Add GLBA + PCI-DSS readiness
controls," half 2 of 2).

core/compliance_rules.py already has one real, narrow, cited GLBA control --
_check_glba_safeguards_encryption(), blocking a plaintext-HTTP API Connection, tagged
`law: "Gramm-Leach-Bliley Act Safeguards Rule"`, `citation: "16 CFR 314.4"`. That's a
real per-entity BLOCKING check, and it stays exactly as-is -- this module does not
duplicate or replace it. What's been genuinely missing is any tracking of the
broader thing the Safeguards Rule (16 CFR 314) actually requires a financial
institution (which a dealership extending in-house/BHPH financing legally is) to
maintain: a documented, current Information Security Program with real, named
components -- not a single technical control, a whole program.

The real 7 components the Safeguards Rule names (16 CFR 314.4), each tracked here as
its own GlbaProgramItem:

  qualified_individual        -- 314.4(a): designate one real, named individual
                                  responsible for the program.
  risk_assessment              -- 314.4(b): a written risk assessment identifying
                                  reasonably foreseeable internal/external risks to
                                  customer information.
  safeguards_implementation    -- 314.4(c): the actual technical/physical/
                                  administrative safeguards -- this is where
                                  compliance_rules.py's own encryption check lives as
                                  ONE real, automated example of a safeguard already
                                  enforced; this program item tracks the broader,
                                  human-documented safeguards program around it.
  staff_training                -- 314.4(e): security awareness training for
                                  personnel.
  service_provider_oversight    -- 314.4(f): selecting service providers capable of
                                  safeguarding information, contractually requiring
                                  them to.
  incident_response_plan        -- 314.4(h): a written incident response plan.
  board_reporting                -- 314.4(i): periodic reporting to the board (or a
                                  senior officer, for a dealership with no board) on
                                  the program's overall status.

Every component is honest-manual-entry -- there is no way to compute "has this
dealership documented a risk assessment" from graph data, the same reasoning
core/lending_compliance.py's own docstring already applies to OFAC screening/cash
reporting (a real, checkable precondition captured by an actual human action, not a
fabricated automatic signal). What IS real and computed here: the readiness
percentage (get_glba_readiness_summary()) is a genuine roll-up of whatever real
statuses have actually been entered -- never defaulted to "compliant," and an
un-entered component counts as not_started, not silently excluded from the
denominator.

Deliberately reuses core/compliance_rules.py's own NOT_LEGAL_ADVICE_NOTICE-style
disclosure rather than inventing a second one -- every dashboard response here states
plainly that this is a real tracking tool, not a legal compliance certification.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import GLBA_PROGRAM_ITEM
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


PROGRAM_COMPONENTS = {
    "qualified_individual": {
        "label": "Qualified Individual Designated",
        "citation": "16 CFR 314.4(a)",
        "description": "One real, named individual designated as responsible for "
                        "the Information Security Program.",
    },
    "risk_assessment": {
        "label": "Written Risk Assessment",
        "citation": "16 CFR 314.4(b)",
        "description": "A written risk assessment identifying reasonably "
                        "foreseeable internal/external risks to customer "
                        "information's confidentiality/integrity/availability.",
    },
    "safeguards_implementation": {
        "label": "Safeguards Implementation & Testing",
        "citation": "16 CFR 314.4(c)/(d)",
        "description": "The documented technical/physical/administrative "
                        "safeguards program, and regular testing/monitoring of it. "
                        "core/compliance_rules.py's own "
                        "glba_safeguards_encryption rule is one real, automated "
                        "safeguard already enforced within this broader program.",
    },
    "staff_training": {
        "label": "Staff Security Awareness Training",
        "citation": "16 CFR 314.4(e)",
        "description": "Security awareness training provided to personnel with "
                        "access to customer information.",
    },
    "service_provider_oversight": {
        "label": "Service Provider Oversight",
        "citation": "16 CFR 314.4(f)",
        "description": "Service providers are selected and contractually required "
                        "to maintain appropriate safeguards for customer "
                        "information they access.",
    },
    "incident_response_plan": {
        "label": "Written Incident Response Plan",
        "citation": "16 CFR 314.4(h)",
        "description": "A written plan for responding to a security event "
                        "affecting customer information's confidentiality/"
                        "integrity/availability.",
    },
    "board_reporting": {
        "label": "Board / Senior Officer Reporting",
        "citation": "16 CFR 314.4(i)",
        "description": "Periodic (at least annual) reporting to the board of "
                        "directors, or a senior officer where no board exists, on "
                        "the program's overall status.",
    },
}

VALID_STATUSES = ("not_started", "in_progress", "complete", "needs_review")

NOT_LEGAL_ADVICE_NOTICE = (
    "This is a real tracking tool for the GLBA Safeguards Rule's 7 named program "
    "components (16 CFR 314.4), populated by honest, human-entered status -- not an "
    "automated compliance certification, and not a substitute for review by a "
    "licensed compliance officer or attorney."
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _get_item(component_key):
    """Returns the current real GlbaProgramItem entity for a component key, or None
    if it's never been touched (not_started, honestly, rather than an entity that
    doesn't exist yet)."""

    for entity in ledger.entities.values():
        if entity.entity_type == GLBA_PROGRAM_ITEM and entity.attributes.get("component_key") == component_key:
            return entity

    return None


def get_component_status(component_key):
    """Computed-default-then-real-value, matching core/lending_compliance.py's own
    established pattern -- a component with no real GlbaProgramItem on file yet is
    honestly reported as not_started, never silently omitted or defaulted to
    compliant."""

    if component_key not in PROGRAM_COMPONENTS:
        return {"error": f"Unknown GLBA program component '{component_key}'."}

    catalog_entry = PROGRAM_COMPONENTS[component_key]
    item = _get_item(component_key)

    if item is None:
        return {
            "component_key": component_key,
            **catalog_entry,
            "status": "not_started",
            "owner_employee_id": None,
            "last_reviewed_at": None,
            "notes": "",
            "updated_by": None,
            "updated_at": None,
        }

    return {
        "component_key": component_key,
        **catalog_entry,
        "status": item.attributes.get("status", "not_started"),
        "owner_employee_id": item.attributes.get("owner_employee_id"),
        "last_reviewed_at": item.attributes.get("last_reviewed_at"),
        "notes": item.attributes.get("notes", ""),
        "updated_by": item.attributes.get("updated_by"),
        "updated_at": item.attributes.get("updated_at"),
    }


def list_program_items():
    """Real status for all 7 components, in catalog order."""

    return [get_component_status(key) for key in PROGRAM_COMPONENTS]


def set_component_status(component_key, status, owner_employee_id, notes, updated_by, last_reviewed_at=None):
    """The real, single mutation this module offers -- upserts one GlbaProgramItem
    per component_key (one real record per component, not a growing history list;
    each update overwrites the current status, matching how a program-status tracker
    is actually used day to day, unlike core/lending_compliance.py's own
    append-only cash-payment log where every individual payment is its own real
    event worth preserving)."""

    if component_key not in PROGRAM_COMPONENTS:
        return {"error": f"Unknown GLBA program component '{component_key}'."}

    if status not in VALID_STATUSES:
        return {"error": f"status must be one of {VALID_STATUSES}"}

    now = _now()
    existing = _get_item(component_key)

    if existing is None:
        item_id = id_generator.generate("GLBA")
        item = Entity(
            id=item_id,
            entity_type=GLBA_PROGRAM_ITEM,
            attributes={
                "component_key": component_key,
                "status": status,
                "owner_employee_id": owner_employee_id,
                "notes": notes or "",
                "last_reviewed_at": last_reviewed_at or now,
                "updated_by": updated_by,
                "updated_at": now,
                "created_at": now,
            },
        )
        ledger.add_entity(item)
    else:
        existing.attributes["status"] = status
        existing.attributes["owner_employee_id"] = owner_employee_id
        existing.attributes["notes"] = notes or ""
        existing.attributes["last_reviewed_at"] = last_reviewed_at or now
        existing.attributes["updated_by"] = updated_by
        existing.attributes["updated_at"] = now
        item = existing

    save_graph(GRAPH_PATH)

    return get_component_status(component_key)


def get_glba_readiness_summary():
    """The one real computed figure this module offers -- a genuine roll-up of
    whatever real statuses have actually been entered, never fabricated. An
    un-entered component counts as not_started in the denominator, not silently
    excluded, so a fresh, never-touched program honestly reports 0% rather than
    100% or an undefined result."""

    items = list_program_items()
    total = len(items)
    complete = sum(1 for i in items if i["status"] == "complete")
    in_progress = sum(1 for i in items if i["status"] == "in_progress")
    needs_review = sum(1 for i in items if i["status"] == "needs_review")
    not_started = sum(1 for i in items if i["status"] == "not_started")

    readiness_pct = round((complete / total) * 100, 1) if total else 0.0

    return {
        "generated_at": _now(),
        "total_components": total,
        "complete": complete,
        "in_progress": in_progress,
        "needs_review": needs_review,
        "not_started": not_started,
        "readiness_pct": readiness_pct,
        "items": items,
        "not_legal_or_compliance_advice": NOT_LEGAL_ADVICE_NOTICE,
    }
