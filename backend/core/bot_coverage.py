"""
core/bot_coverage.py — admin-activated "run the bot as this employee" coverage window
(2026-07-13, session 36). Sam: "if the person is sick / not there, the admin can decide
to run the bot version of that operator for the day (or hours they're not at the
dealership)." Scoping answer on autonomy: "the admin can decide one way or the other
for the timeframe set" -- so mode (draft vs. auto) is chosen per coverage window, not
fixed globally.

A BotCoverage is an ordinary graph entity (ADMIN-only per core/permissions.py), same
rule as everything else in this codebase -- the covered employee, who activated it, the
time window, the role/section the bot should act under, and the mode all live as
attributes, not a separate scheduler store.

Safety boundary: "auto" mode does NOT mean the bot can do anything the covered employee
could. core/bot_actions.py's ACTION_HANDLERS is a small, explicit whitelist of low-risk,
reversible actions -- nothing that moves money, sends anything externally, or publishes/
approves on someone else's behalf. That matches this codebase's existing convention of
gating money-moving/publishing actions behind an explicit human step (deal financing/
funding, campaign activation, website publish, and asset approval all already require a
deliberate click from a permitted role) -- covering for someone who's out sick isn't a
reason to relax that. Every auto-executed action is written to the audit log, never
silently (see core/bot_actions.py).
"""

from datetime import datetime, timezone

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import BOT_COVERAGE, EMPLOYEE
from core.audit import audit_log
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
# (import added session 39: end_coverage persists via save_graph)

MODE_DRAFT = "draft"
MODE_AUTO = "auto"

VALID_MODES = (MODE_DRAFT, MODE_AUTO)


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat()


def start_coverage(admin_id, employee_id, role, section, starts_at, ends_at, mode, note=None):

    employee = ledger.get_entity(employee_id)

    if not employee or employee.entity_type != EMPLOYEE:
        return {"error": f"Employee '{employee_id}' not found"}

    if mode not in VALID_MODES:
        return {"error": f"Unknown mode '{mode}' -- must be one of {VALID_MODES}"}

    if not starts_at or not ends_at:
        return {"error": "starts_at and ends_at are both required"}

    if ends_at <= starts_at:
        return {"error": "ends_at must be after starts_at"}

    if mode == MODE_AUTO:
        # Security-hardening pass (2026-07-20, Task #7 "Build Bot Permission
        # Layer"): "auto" mode is the one real thing this whole coverage
        # window can unattendedly DO -- gated by core.bot_permissions's
        # real, default-deny bot.coverage.auto_mode capability, checked
        # once here at admin-click time so a denied request fails loud
        # immediately rather than silently starting a window that
        # core.bot_actions.run_action()'s own per-call check (see that
        # module) would just no-op for the whole time it's "active" anyway.
        from core.bot_permissions import is_capability_granted, normalize_department
        department = normalize_department(section)
        if not is_capability_granted(
            "bot.coverage.auto_mode", employee_id=employee_id, department=department
        ):
            return {
                "error": (
                    f"Auto-mode Bot Coverage is not currently granted for "
                    f"'{employee_id}'"
                    + (f" or the {department} department" if department else "")
                    + " -- an ADMIN must grant the bot.coverage.auto_mode "
                    "capability first (Administration > Roles & Permissions "
                    "> Bot Permissions)."
                )
            }

    coverage_id = id_generator.generate("BOTCOV")

    coverage = Entity(
        id=coverage_id,
        entity_type=BOT_COVERAGE,
        attributes={
            "employee_id": employee_id,
            "activated_by": admin_id,
            "role": role,
            "section": section,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "mode": mode,
            "note": note,
            "status": "active",
            "created_at": _iso(_now()),
            "ended_at": None,
            "ended_by": None,
        },
    )

    ledger.add_entity(coverage)

    audit_log.record(
        event_type="bot_coverage_started",
        summary=(
            f"{admin_id} activated {mode} bot coverage for {employee_id} "
            f"from {starts_at} to {ends_at}"
        ),
        entity_id=coverage_id,
        actor=admin_id,
        details={
            "employee_id": employee_id,
            "mode": mode,
            "starts_at": starts_at,
            "ends_at": ends_at,
        },
    )

    # Security-hardening pass (2026-07-20, Task #7): start_coverage() never
    # called save_graph() at all before this pass -- the same missing-
    # persistence bug class this codebase's own CLAUDE.md documents finding
    # and fixing ~19+ times elsewhere (core/deals.py, core/campaigns.py,
    # etc.). A BotCoverage window created through the live app would not
    # have survived a server restart. Fixed here since this function was
    # already being touched for the real permission-gate change above.
    save_graph(GRAPH_PATH)

    return {"coverage": dict(coverage.attributes, id=coverage_id)}


def end_coverage(coverage_id, ended_by):

    coverage = ledger.get_entity(coverage_id)

    if not coverage or coverage.entity_type != BOT_COVERAGE:
        return {"error": f"Coverage '{coverage_id}' not found"}

    if coverage.attributes.get("status") == "ended":
        return {"error": f"Coverage '{coverage_id}' has already ended"}

    coverage.attributes["status"] = "ended"
    coverage.attributes["ended_at"] = _iso(_now())
    coverage.attributes["ended_by"] = ended_by

    save_graph(GRAPH_PATH)

    audit_log.record(
        event_type="bot_coverage_ended",
        summary=f"{ended_by} ended bot coverage {coverage_id}",
        entity_id=coverage_id,
        actor=ended_by,
    )

    return {"coverage": dict(coverage.attributes, id=coverage_id)}


def _all_coverage():
    return [e for e in ledger.get_all().values() if e.entity_type == BOT_COVERAGE]


def list_coverage(active_only=False):

    records = _all_coverage()

    now = _iso(_now())

    if active_only:
        records = [
            c for c in records
            if c.attributes.get("status") == "active"
            and c.attributes.get("starts_at", "") <= now <= c.attributes.get("ends_at", "")
        ]

    records.sort(key=lambda c: c.attributes.get("created_at", ""), reverse=True)

    return [dict(c.attributes, id=c.id) for c in records]


def get_active_coverage_for(employee_id):
    """The active BotCoverage attributes dict covering this employee right now
    (status=="active" and starts_at <= now <= ends_at), or None."""

    now = _iso(_now())

    for coverage in _all_coverage():

        attrs = coverage.attributes

        if attrs.get("employee_id") != employee_id:
            continue

        if attrs.get("status") != "active":
            continue

        if attrs.get("starts_at", "") <= now <= attrs.get("ends_at", ""):
            return dict(attrs, id=coverage.id)

    return None
