"""
core/coaching.py -- the fourth and final pillar of Sam's "NXTDeal Workforce AI"
vision (2026-07-19), closing out Assistant ("Help Me With This Screen")/
Automation/Coverage/Coaching. Scoped directly with Sam via two rounds of
AskUserQuestion before any code was written, since real employee-evaluation
content is a materially higher HR/legal-risk category than the rest of this
session's operational business-intelligence work. Three real pieces, each
scoped to Sam's own "Recommended" answer:

  1. Intensity Tiers (Participant/Productive/Aggressive) change ONLY the bot's
     nudge frequency and tone -- no new mutation capability. A real, persisted,
     4-level override (individual > seniority tier > department > global
     default), mirroring core/permissions_registry.py's PermissionOverride
     pattern exactly (a new override for the same scope+target deactivates,
     not deletes, the prior one). apply_intensity_to_tasks()/
     apply_intensity_to_guidance() are pure post-processing wrappers over
     core/bot_tasks.py's generate_tasks()/core/screen_guidance.py's
     get_screen_guidance() -- they never rewrite an item's own real,
     already-computed title/description/prompt text (rewriting real computed
     sentences on the fly risks producing a misleading or nonsensical result);
     they only (a) trim the list by real priority at the Participant tier and
     (b) attach a structural urgency_label the frontend renders as a badge.
     Productive is deliberately a complete no-op -- today's existing bot
     behavior, byte-for-byte unchanged, for any employee with no override set.

  2. AI Performance Reviews -- Sam's own answer: "Data-grounded draft only,
     never auto-sent." A PerformanceReview is a real, own-lifecycle entity
     (draft -> finalized -> shared), same "own lifecycle" reasoning
     OperationsTask/DamageReport/Payment/AutomationExecution/
     StrategicInitiative/EmployeeShift/MarketingContentDraft already
     established. The metrics block is composed ENTIRELY from already-real,
     already-computed engines -- core/employee_value.py's compute_employee_value()
     (the one real per-employee $ signal covering every department, honestly
     basis-labeled ledger/blended/industry_estimate) plus, for Sales/Service,
     that department's own real scorecard (core/sales_menu.py's
     _salesperson_scorecards(), core/service_reporting.py's
     get_technician_scorecard()). The narrative sentences built from those
     numbers are PLAIN TEMPLATED FACT STATEMENTS -- no OpenAI call, no
     subjective judgment language ("excellent"/"needs improvement"/etc.),
     matching this codebase's established "real rules, never fake AI
     judgment" convention (core/network_audit.py, core/lead_record.py's
     next_best_action(), core/collections.py's risk scoring). A manager's own
     real, separately-recorded subjective assessment lives in a distinct
     manager_notes field -- never generated, always typed by a human. A draft
     is never visible to the reviewed employee until a manager explicitly
     marks it "shared."

  3. AI Career Pathing -- Sam's own answer: "Real internal mobility signal."
     Compares an employee's real compute_employee_value() figure against the
     real population of OTHER employees at the same current seniority tier
     (core/bot_tasks.py's infer_tier(), the same staff/manager/executive
     ladder core/permissions_registry.py's Approval Hierarchy already reuses)
     in the same department -- a real, comparative $ delta, not a fabricated
     skills assessment. No tenure signal is used: Employee has no HireDate
     field anywhere in this codebase (confirmed absent, same finding sessions
     65/94/106/109/110 already independently made), so "how long they've been
     here" can't be honestly computed. No fabricated next-role suggestion is
     made -- only the one real, mechanical next tier up (infer_tier()'s own
     ladder) and a real comparative finding sentence.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import COACHING_INTENSITY_OVERRIDE, PERFORMANCE_REVIEW, EMPLOYEE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH, AUDIT_PATH
from core.audit_storage import save_audit_log
from core.audit import audit_log

from core.permissions import ADMIN, OPERATIONS
from core.bot_tasks import infer_tier, TIER_STAFF, TIER_MANAGER, TIER_EXECUTIVE


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1. Coaching Intensity Tiers
# ---------------------------------------------------------------------------

TIER_PARTICIPANT = "participant"
TIER_PRODUCTIVE = "productive"
TIER_AGGRESSIVE = "aggressive"
VALID_INTENSITY_TIERS = (TIER_PARTICIPANT, TIER_PRODUCTIVE, TIER_AGGRESSIVE)
DEFAULT_INTENSITY = TIER_PRODUCTIVE

SCOPE_GLOBAL = "global"
SCOPE_DEPARTMENT = "department"
SCOPE_ROLE = "role"
SCOPE_INDIVIDUAL = "individual"
VALID_SCOPES = (SCOPE_GLOBAL, SCOPE_DEPARTMENT, SCOPE_ROLE, SCOPE_INDIVIDUAL)

# "role" scope is deliberately interpreted as SENIORITY TIER (staff/manager/
# executive, infer_tier()'s own ladder), not one of the 6 platform ACL roles
# (ADMIN/SALES/etc.) -- a manager-tier employee wanting lighter-touch nudges
# than their own staff is a real, meaningful coaching concept; ADMIN-vs-SALES
# nudge tone is not. Stated here explicitly as a deliberate interpretation.
_VALID_ROLE_TARGETS = (TIER_STAFF, TIER_MANAGER, TIER_EXECUTIVE)

_GLOBAL_TARGET = "*"

INTENSITY_CATALOG = [
    {
        "key": TIER_PARTICIPANT,
        "label": "Participant",
        "description": (
            "Lighter touch -- only the top half of real, currently-flagged items "
            "surface (by real priority), tagged 'Worth a look' / 'FYI'."
        ),
    },
    {
        "key": TIER_PRODUCTIVE,
        "label": "Productive",
        "description": (
            "The default -- today's existing bot behavior, completely unchanged. "
            "Every real item surfaces with no added urgency labeling."
        ),
    },
    {
        "key": TIER_AGGRESSIVE,
        "label": "Aggressive",
        "description": (
            "Every real item surfaces (there is no fabricated 'more' to add -- "
            "every item already traces to a real, detected condition), tagged "
            "'Do this now' / 'Take action'."
        ),
    },
]

SCOPE_CATALOG = [
    {"key": SCOPE_GLOBAL, "label": "Global default"},
    {"key": SCOPE_DEPARTMENT, "label": "Per department"},
    {"key": SCOPE_ROLE, "label": "Per seniority tier (staff / manager / executive)"},
    {"key": SCOPE_INDIVIDUAL, "label": "Per individual employee"},
]


def get_intensity_catalog():
    return {
        "tiers": INTENSITY_CATALOG,
        "scopes": SCOPE_CATALOG,
        "default_intensity": DEFAULT_INTENSITY,
    }


def _active_intensity_override(scope, scope_target):
    for e in ledger.get_all().values():
        if (
            e.entity_type == COACHING_INTENSITY_OVERRIDE
            and e.attributes.get("scope") == scope
            and e.attributes.get("scope_target") == scope_target
            and e.attributes.get("active")
        ):
            return e
    return None


def resolve_intensity(employee_id=None, role=None, department=None):
    """Most-specific-wins: individual > seniority tier > department > global
    default (Productive). Returns (intensity, resolved_from)."""

    tier = None
    if employee_id:
        employee = ledger.get_entity(employee_id)
        if employee and employee.entity_type == EMPLOYEE:
            department = department or employee.attributes.get("Department")
            tier = infer_tier(employee.attributes.get("Title"))

    # Department scope targets are always compared lowercase -- Employee.Department
    # is stored capitalized ("Sales") while core/bot_tasks.py's own TASK_CATALOG
    # keys (and this function's own `department` fallback param from that module)
    # are lowercase -- normalizing here means a manager can set an override with
    # either casing and it still resolves correctly.
    department = (department or "").strip().lower() or None

    if employee_id:
        override = _active_intensity_override(SCOPE_INDIVIDUAL, employee_id)
        if override:
            return override.attributes.get("intensity"), "individual"

    if tier:
        override = _active_intensity_override(SCOPE_ROLE, tier)
        if override:
            return override.attributes.get("intensity"), "role"

    if department:
        override = _active_intensity_override(SCOPE_DEPARTMENT, department)
        if override:
            return override.attributes.get("intensity"), "department"

    override = _active_intensity_override(SCOPE_GLOBAL, _GLOBAL_TARGET)
    if override:
        return override.attributes.get("intensity"), "global"

    return DEFAULT_INTENSITY, "default"


def set_intensity_override(scope, scope_target, intensity, set_by, reason=""):
    """A new override for the same (scope, scope_target) pair deactivates any
    prior one rather than deleting it -- full history stays inspectable, only
    the currently-active setting changes."""

    if scope not in VALID_SCOPES:
        return {"error": f"Unknown scope '{scope}' -- must be one of {VALID_SCOPES}"}

    if intensity not in VALID_INTENSITY_TIERS:
        return {"error": f"Unknown intensity '{intensity}' -- must be one of {VALID_INTENSITY_TIERS}"}

    if scope == SCOPE_INDIVIDUAL:
        target = ledger.get_entity(scope_target)
        if not target or target.entity_type != EMPLOYEE:
            return {"error": f"Employee '{scope_target}' not found"}
    elif scope == SCOPE_ROLE:
        if scope_target not in _VALID_ROLE_TARGETS:
            return {"error": f"Unknown tier '{scope_target}' -- must be one of {_VALID_ROLE_TARGETS}"}
    elif scope == SCOPE_GLOBAL:
        scope_target = _GLOBAL_TARGET
    elif scope == SCOPE_DEPARTMENT:
        if not scope_target:
            return {"error": "scope_target (a department name) is required for department scope"}
        scope_target = scope_target.strip().lower()

    prior = _active_intensity_override(scope, scope_target)
    if prior is not None:
        prior.attributes["active"] = False
        prior.attributes["superseded_at"] = _now()

    override_id = id_generator.generate("CTIER")
    entity = Entity(
        id=override_id,
        entity_type=COACHING_INTENSITY_OVERRIDE,
        attributes={
            "scope": scope,
            "scope_target": scope_target,
            "intensity": intensity,
            "reason": reason,
            "active": True,
            "set_by": set_by,
            "created_at": _now(),
            "superseded_at": None,
        },
    )
    ledger.add_entity(entity)

    audit_log.record(
        event_type="coaching_intensity_set",
        summary=f"Set coaching intensity to '{intensity}' for {scope}={scope_target}",
        entity_id=scope_target if scope == SCOPE_INDIVIDUAL else None,
        actor=set_by,
        details={"scope": scope, "scope_target": scope_target, "intensity": intensity, "reason": reason},
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)
    return {"id": entity.id, **entity.attributes}


def list_intensity_overrides():
    overrides = [e for e in ledger.get_all().values() if e.entity_type == COACHING_INTENSITY_OVERRIDE]
    overrides.sort(key=lambda e: e.attributes.get("created_at") or "", reverse=True)
    return [{"id": e.id, **e.attributes} for e in overrides]


def _urgency_label(intensity, priority):
    if intensity == TIER_PARTICIPANT:
        return "Worth a look" if priority >= 3 else "FYI"
    if intensity == TIER_AGGRESSIVE:
        return "Do this now" if priority >= 3 else "Take action"
    return None


def _apply_intensity(items, intensity, priority_key="priority"):
    """Real, mechanical post-processing over an already-generated task/guidance
    list. Never rewrites an item's own real, already-computed title/
    description/prompt text -- only trims the list (Participant only) and
    attaches a structural urgency_label."""

    if intensity not in VALID_INTENSITY_TIERS:
        intensity = DEFAULT_INTENSITY

    items = list(items)

    if intensity == TIER_PRODUCTIVE:
        return items

    ranked = sorted(items, key=lambda i: i.get(priority_key) or 0, reverse=True)

    if intensity == TIER_PARTICIPANT and ranked:
        keep = max(1, len(ranked) // 2)
        ranked = ranked[:keep]

    out = []
    for item in ranked:
        item = dict(item)
        item["coaching_intensity"] = intensity
        item["urgency_label"] = _urgency_label(intensity, item.get(priority_key) or 0)
        out.append(item)

    return out


def apply_intensity_to_tasks(tasks, employee_id, role=None, department=None):
    intensity, resolved_from = resolve_intensity(employee_id, role=role, department=department)
    return _apply_intensity(tasks, intensity), intensity, resolved_from


def apply_intensity_to_guidance(guidance, employee_id, role=None, department=None):
    intensity, resolved_from = resolve_intensity(employee_id, role=role, department=department)
    return _apply_intensity(guidance, intensity), intensity, resolved_from


# ---------------------------------------------------------------------------
# 2. AI Performance Reviews -- data-grounded draft only, never auto-sent
# ---------------------------------------------------------------------------

REVIEW_STATUS_DRAFT = "draft"
REVIEW_STATUS_FINALIZED = "finalized"
REVIEW_STATUS_SHARED = "shared"
VALID_REVIEW_STATUSES = (REVIEW_STATUS_DRAFT, REVIEW_STATUS_FINALIZED, REVIEW_STATUS_SHARED)


def _sales_scorecard_for(employee_id):
    from core.sales_menu import _salesperson_scorecards
    for s in _salesperson_scorecards():
        if s["employee_id"] == employee_id:
            return s
    return None


def _service_scorecard_for(employee_id):
    from core.service_reporting import get_technician_scorecard
    for t in get_technician_scorecard()["technicians"]:
        if t["technician_id"] == employee_id:
            return t
    return None


def compose_review_metrics(employee_id):
    """The real, factual metrics block a Performance Review draft is built
    from -- always sourced from an already-real, already-computed engine,
    never a fresh subjective judgment."""

    from core.employee_value import compute_employee_value

    value = compute_employee_value(employee_id)
    if value is None:
        return None

    department = value["department"]
    department_scorecard = None
    if department == "sales":
        department_scorecard = _sales_scorecard_for(employee_id)
    elif department == "service":
        department_scorecard = _service_scorecard_for(employee_id)

    return {
        "employee_id": employee_id,
        "name": value["name"],
        "department": department,
        "title": value["title"],
        "tier": value["tier"],
        "value_estimate": value,
        "department_scorecard": department_scorecard,
        "department_scorecard_note": (
            None if department_scorecard else
            f"No dedicated real per-employee scorecard exists for the '{department}' department yet -- "
            "the $ Effectiveness Estimate above is the only real per-employee metric available for this review."
        ),
    }


def _factual_summary_sentences(metrics):
    """Plain, factual, templated sentences off real numbers only -- no AI call,
    no subjective judgment language. A manager's own real assessment is a
    separate, human-typed field (manager_notes), never generated."""

    value = metrics["value_estimate"]
    sentences = [
        f"{metrics['name']} ({metrics['title'] or metrics['department']}) has an estimated monthly "
        f"value contribution of ${value['monthly_value_estimate']:,.2f}, based on "
        f"{value['sample_size']} real recorded record(s) (basis: {value['basis']})."
    ]

    dc = metrics.get("department_scorecard")
    if metrics["department"] == "sales" and dc:
        sentence = (
            f"Over the tracked window: {dc['units_sold_funded']} funded unit(s), "
            f"${dc['gross_profit']:,.2f} in gross profit, a "
            f"{round(dc['conversion_rate'] * 100, 1)}% lead conversion rate"
        )
        if dc.get("show_rate") is not None:
            sentence += f", and a {round(dc['show_rate'] * 100, 1)}% appointment show rate."
        else:
            sentence += "."
        sentences.append(sentence)
    elif metrics["department"] == "service" and dc:
        sentence = (
            f"Over the tracked window: {dc['ro_count']} repair order(s) recorded, "
            f"{dc['total_labor_hours']} labor hour(s), ${dc['total_revenue']:,.2f} in revenue"
        )
        if dc.get("avg_revenue_per_ro") is not None:
            sentence += f" (${dc['avg_revenue_per_ro']:,.2f} average per RO)."
        else:
            sentence += "."
        sentences.append(sentence)
    elif metrics.get("department_scorecard_note"):
        sentences.append(metrics["department_scorecard_note"])

    automation = value.get("automation_coverage")
    if automation:
        sentences.append(
            f"Of {automation['distinct_task_types']} distinct bot-suggested task type(s) this "
            f"employee has acted on or dismissed, {automation['automatable_task_types']} "
            f"({automation['automation_pct']}%) are on NXTDeal's real auto-executable whitelist."
        )

    sentences.append(value["note"])

    return sentences


def create_performance_review(employee_id, created_by, period_label=""):
    """Composes a real, data-grounded draft -- never auto-sent, never visible to
    the reviewed employee until a manager explicitly marks it 'shared'."""

    metrics = compose_review_metrics(employee_id)
    if metrics is None:
        return {"error": f"Employee '{employee_id}' not found"}

    review_id = id_generator.generate("PREV")
    entity = Entity(
        id=review_id,
        entity_type=PERFORMANCE_REVIEW,
        attributes={
            "employee_id": employee_id,
            "employee_name": metrics["name"],
            "department": metrics["department"],
            "tier": metrics["tier"],
            "period_label": period_label,
            "status": REVIEW_STATUS_DRAFT,
            "metrics_snapshot": metrics,
            "factual_summary": _factual_summary_sentences(metrics),
            "manager_notes": "",
            "created_by": created_by,
            "created_at": _now(),
            "finalized_by": None,
            "finalized_at": None,
            "shared_by": None,
            "shared_at": None,
        },
    )
    ledger.add_entity(entity)

    audit_log.record(
        event_type="performance_review_drafted",
        summary=f"Drafted a performance review for {metrics['name']} ({employee_id})",
        entity_id=employee_id,
        actor=created_by,
        details={"review_id": review_id, "period_label": period_label},
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)
    return {"id": entity.id, **entity.attributes}


def update_review_notes(review_id, manager_notes, updated_by):
    """A manager's own real, human-typed assessment -- never generated,
    editable only while the review is still a draft."""

    review = ledger.get_entity(review_id)
    if not review or review.entity_type != PERFORMANCE_REVIEW:
        return {"error": f"Performance review '{review_id}' not found"}

    if review.attributes.get("status") != REVIEW_STATUS_DRAFT:
        return {"error": "Manager notes can only be edited while the review is still a draft"}

    review.attributes["manager_notes"] = manager_notes
    review.attributes["notes_updated_by"] = updated_by
    review.attributes["notes_updated_at"] = _now()

    save_graph(GRAPH_PATH)
    return {"id": review.id, **review.attributes}


def finalize_review(review_id, finalized_by):
    """Locks the draft -- metrics and manager notes are now fixed, ready for a
    real human decision on whether/when to share it with the employee. Still
    NOT visible to the employee at this stage."""

    review = ledger.get_entity(review_id)
    if not review or review.entity_type != PERFORMANCE_REVIEW:
        return {"error": f"Performance review '{review_id}' not found"}

    if review.attributes.get("status") != REVIEW_STATUS_DRAFT:
        return {"error": f"Review is already '{review.attributes.get('status')}', not a draft"}

    review.attributes["status"] = REVIEW_STATUS_FINALIZED
    review.attributes["finalized_by"] = finalized_by
    review.attributes["finalized_at"] = _now()

    audit_log.record(
        event_type="performance_review_finalized",
        summary=f"Finalized performance review {review_id} for {review.attributes.get('employee_name')}",
        entity_id=review.attributes.get("employee_id"),
        actor=finalized_by,
        details={"review_id": review_id},
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)
    return {"id": review.id, **review.attributes}


def share_review(review_id, shared_by):
    """The one real, explicit action that makes a review visible to the
    reviewed employee -- never automatic, never triggered by drafting or
    finalizing alone."""

    review = ledger.get_entity(review_id)
    if not review or review.entity_type != PERFORMANCE_REVIEW:
        return {"error": f"Performance review '{review_id}' not found"}

    if review.attributes.get("status") != REVIEW_STATUS_FINALIZED:
        return {"error": "A review must be finalized before it can be shared"}

    review.attributes["status"] = REVIEW_STATUS_SHARED
    review.attributes["shared_by"] = shared_by
    review.attributes["shared_at"] = _now()

    audit_log.record(
        event_type="performance_review_shared",
        summary=f"Shared performance review {review_id} with {review.attributes.get('employee_name')}",
        entity_id=review.attributes.get("employee_id"),
        actor=shared_by,
        details={"review_id": review_id},
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)
    return {"id": review.id, **review.attributes}


def discard_review(review_id, discarded_by):
    """A draft that was never finalized can be discarded outright (removed from
    the ledger) -- a finalized/shared review cannot, since it's now a real
    record of a decision that was made."""

    review = ledger.get_entity(review_id)
    if not review or review.entity_type != PERFORMANCE_REVIEW:
        return {"error": f"Performance review '{review_id}' not found"}

    if review.attributes.get("status") != REVIEW_STATUS_DRAFT:
        return {"error": "Only a still-draft review can be discarded"}

    del ledger.entities[review_id]

    audit_log.record(
        event_type="performance_review_discarded",
        summary=f"Discarded draft performance review {review_id}",
        entity_id=review.attributes.get("employee_id"),
        actor=discarded_by,
        details={"review_id": review_id},
    )

    save_graph(GRAPH_PATH)
    save_audit_log(AUDIT_PATH)
    return {"success": True}


def get_review(review_id):
    review = ledger.get_entity(review_id)
    if not review or review.entity_type != PERFORMANCE_REVIEW:
        return None
    return {"id": review.id, **review.attributes}


def list_reviews(employee_id=None, status=None):
    reviews = [e for e in ledger.get_all().values() if e.entity_type == PERFORMANCE_REVIEW]
    if employee_id:
        reviews = [r for r in reviews if r.attributes.get("employee_id") == employee_id]
    if status:
        reviews = [r for r in reviews if r.attributes.get("status") == status]
    reviews.sort(key=lambda r: r.attributes.get("created_at") or "", reverse=True)
    return [{"id": r.id, **r.attributes} for r in reviews]


# ---------------------------------------------------------------------------
# 3. AI Career Pathing -- a real internal mobility signal
# ---------------------------------------------------------------------------

_NEXT_TIER = {TIER_STAFF: TIER_MANAGER, TIER_MANAGER: TIER_EXECUTIVE}

_READY_THRESHOLD_PCT = 25.0
_GAP_THRESHOLD_PCT = -25.0


def get_career_pathing_signal(employee_id):
    """A real, comparative $ signal only -- never a fabricated skills
    assessment or a guaranteed promotion recommendation. No tenure input,
    since Employee has no HireDate field anywhere in this codebase."""

    from core.employee_value import compute_employee_value, list_employee_values

    value = compute_employee_value(employee_id)
    if value is None:
        return {"error": f"Employee '{employee_id}' not found"}

    department = value["department"]
    tier = value["tier"]

    peers = [
        v for v in list_employee_values(department=department)
        if v["tier"] == tier and v["employee_id"] != employee_id
    ]

    next_tier = _NEXT_TIER.get(tier)

    if not peers:
        return {
            "employee_id": employee_id,
            "name": value["name"],
            "department": department,
            "tier": tier,
            "next_tier": next_tier,
            "signal": "insufficient_peer_data",
            "finding": (
                f"No other real {tier}-tier employee exists in the '{department}' department "
                "to compare against yet."
            ),
            "value_estimate": value,
        }

    peer_avg = sum(p["monthly_value_estimate"] for p in peers) / len(peers)
    delta_pct = round(100 * (value["monthly_value_estimate"] - peer_avg) / peer_avg, 1) if peer_avg else None

    if delta_pct is not None and delta_pct >= _READY_THRESHOLD_PCT:
        signal = "ready_for_more_responsibility"
        finding = (
            f"{value['name']}'s estimated monthly value (${value['monthly_value_estimate']:,.2f}) is "
            f"{delta_pct}% above the real {tier}-tier peer average in {department} "
            f"(${peer_avg:,.2f}, {len(peers)} peer(s))."
        )
        if next_tier:
            finding += f" A real, honest signal worth a conversation about {next_tier}-tier readiness."
    elif delta_pct is not None and delta_pct <= _GAP_THRESHOLD_PCT:
        signal = "skill_gap"
        finding = (
            f"{value['name']}'s estimated monthly value (${value['monthly_value_estimate']:,.2f}) is "
            f"{abs(delta_pct)}% below the real {tier}-tier peer average in {department} "
            f"(${peer_avg:,.2f}, {len(peers)} peer(s))."
        )
    else:
        signal = "on_par_with_peers"
        finding = (
            f"{value['name']}'s estimated monthly value (${value['monthly_value_estimate']:,.2f}) is "
            f"within the normal range of the real {tier}-tier peer average in {department} "
            f"(${peer_avg:,.2f}, {len(peers)} peer(s))."
        )

    return {
        "employee_id": employee_id,
        "name": value["name"],
        "department": department,
        "tier": tier,
        "next_tier": next_tier,
        "signal": signal,
        "finding": finding,
        "peer_average_monthly_value": round(peer_avg, 2),
        "peer_sample_size": len(peers),
        "delta_pct": delta_pct,
        "value_estimate": value,
        "basis_note": (
            "A comparative signal only, off compute_employee_value()'s own real/blended/"
            "industry-estimate $ figure -- not a fabricated skills assessment, and not a "
            "guaranteed promotion recommendation. No tenure data exists anywhere in this "
            "codebase to factor in, stated honestly rather than guessed at."
        ),
    }


def get_career_pathing_board(department=None, signal=None):
    """The real, cross-employee view for a manager/HR screen."""

    from core.employee_value import list_employee_values

    values = list_employee_values(department=department)
    results = []
    for v in values:
        result = get_career_pathing_signal(v["employee_id"])
        if signal and result.get("signal") != signal:
            continue
        results.append(result)

    by_signal = {}
    for r in results:
        by_signal[r.get("signal", "unknown")] = by_signal.get(r.get("signal", "unknown"), 0) + 1

    return {"count": len(results), "by_signal": by_signal, "employees": results}
