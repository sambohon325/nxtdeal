"""
core/bot_tasks.py — the agentic bot's per-section daily task engine (2026-07-13,
session 36). Sam: "create a agentic bot for each section - operations, sales,
marketing, inventory, service, finance, administration, readiness, and network...
it will prompt the user throughout the day with things that need to be done depending
on their role assigned and section they're in."

Same honesty bar Department Intelligence (session 35) set: every task this module produces either
(a) is a real derivation from a live graph query -- leads overdue for follow-up, deals
stuck in financing, pending asset/campaign/website approvals, service records missing
cost/labor data, obsolete parts value, escalated leads -- or (b) is a plain time-of-day
suggestion, identical in spirit to the static `suggestedPrompts` arrays every page
already ships (never a fabricated count attached to a task that doesn't check anything).

Seniority ("Add seniority levels per department", Sam's session-36 scoping answer)
rides on the Employee.Title string already in the graph (imports/generate_seed_data.py's
EMPLOYEES list -- "Sales Consultant" vs "Sales Manager" vs "General Manager", etc.)
rather than a new field: infer_tier() keyword-matches the title so a future title
("Controller", "Parts Manager", "Owner", ...) slots into a tier automatically, no data
migration needed.

The 9 catalog keys below map 1:1 onto the 9 "sections" Sam listed: Operations, Sales,
Marketing, Inventory, Service, Finance (the six /workspace department tabs --
frontend/app/workspace/page.tsx's `agents` array) plus Administration, Readiness, and
Network (the other three chat-first pages). Inventory/Administration/Readiness/Network
aren't real job functions the way Sales/Service/Finance/Marketing/Operations are (nobody
holds the title "Inventory Manager" in this org chart), so those four catalogs are
tier-invariant -- the same task list regardless of the caller's seniority tier.
"""

from datetime import datetime, timezone

from core.dealeros import ledger

from core.entity_types import SERVICE_RECORD

from core.lead_assignment import get_employee_leads
from core.follow_up_queue import get_follow_up_queue
from core.escalation_dashboard_api import get_dashboard as get_escalation_dashboard

from core.deals import list_deals
from core.assets import list_pending_approvals as list_pending_asset_approvals
from core.campaigns import list_pending_campaigns
from core.websites import list_pending_approvals as list_pending_website_approvals

from core.department_intelligence import compute_parts_kpis

from core.bot_learning import get_task_affinity

from core.permissions import (
    ADMIN,
    OPERATIONS,
    SALES,
    MARKETING,
    SERVICE,
    FINANCE
)


TIER_STAFF = "staff"
TIER_MANAGER = "manager"
TIER_EXECUTIVE = "executive"


# Checked most-specific-phrase-first so "general manager" lands as executive rather
# than falling through to the plain "manager" keyword in _MANAGER_TITLE_PHRASES.
_EXECUTIVE_TITLE_PHRASES = [
    "general manager",
    "owner",
    "president",
    "vice president",
    " vp ",
    "ceo",
    "coo",
    "cfo",
    "controller",
]

_MANAGER_TITLE_PHRASES = [
    "manager",
    "director",
    "lead",
]


def infer_tier(title):
    """Keyword-matches an Employee.Title string into a seniority tier. Padded with
    spaces so single-word phrases like "vp" don't false-match inside an unrelated
    longer word."""

    t = f" {(title or '').strip().lower()} "

    if any(phrase in t for phrase in _EXECUTIVE_TITLE_PHRASES):
        return TIER_EXECUTIVE

    if any(phrase in t for phrase in _MANAGER_TITLE_PHRASES):
        return TIER_MANAGER

    return TIER_STAFF


def _now():
    return datetime.now(timezone.utc)


def time_bucket(now=None):
    """Server-clock time-of-day bucket. NXTDeal doesn't model each dealership's local
    timezone (same documented limitation as Department Intelligence's daily snapshots and everywhere
    else this backend touches real clock time) -- this reflects the server's clock, not
    necessarily the dealership's."""

    hour = (now or _now()).hour

    if hour < 11:
        return "morning"

    if hour < 15:
        return "midday"

    return "end_of_day"


def get_employee(employee_id):
    return ledger.get_entity(employee_id)


def department_of(employee):
    """Employee.Department (e.g. "Sales") lowercased to match a catalog key --
    deliberately distinct from the ACL role (ADMIN/OPERATIONS/SALES/...) assigned at
    login; an employee's job function and their login access level are two different
    facts about them."""

    if not employee:
        return None

    return (employee.attributes.get("Department") or "").strip().lower() or None


_ROLE_TO_DEPARTMENT_FALLBACK = {
    ADMIN: "administration",
    OPERATIONS: "operations",
    SALES: "sales",
    MARKETING: "marketing",
    SERVICE: "service",
    FINANCE: "finance",
}


def resolve_department_key(employee, role):
    """Prefer the employee's own Department attribute; fall back to their login role
    when there's no Employee entity behind the session or its Department string doesn't
    match a catalog key."""

    dept = department_of(employee)

    if dept in TASK_CATALOG:
        return dept

    return _ROLE_TO_DEPARTMENT_FALLBACK.get(role, "operations")


# frontend/app/workspace/page.tsx's department tabs are "Operations"/"Sales"/
# "Marketing"/"Inventory"/"Service"/"Finance"; the other three pages pass
# "Administration"/"Readiness"/"Network". Normalizing case here keeps bot_tasks.py the
# single place that knows the catalog's key casing.
def normalize_section(section):
    return (section or "").strip().lower() or None


# ---------------------------------------------------------------------------
# Gap-detection -- every function below either returns a short, real detail string (a
# genuine graph-derived count/value) or None when there's nothing to flag right now.
# ---------------------------------------------------------------------------

def _gap_leads_followup(employee_id):

    lead_ids = get_employee_leads(employee_id)
    queue = get_follow_up_queue(lead_ids, threshold_days=1)

    if not queue:
        return None

    return f"{len(queue)} of your leads haven't been touched in over a day."


def _gap_deals_stuck_in_financing(employee_id=None, hours=24):

    stuck = 0

    for deal in list_deals(status="financing"):

        updated_at = deal.attributes.get("updated_at")

        if not updated_at:
            continue

        try:
            updated = datetime.fromisoformat(updated_at)
        except ValueError:
            continue

        age_hours = (_now() - updated).total_seconds() / 3600

        if age_hours >= hours:
            stuck += 1

    if not stuck:
        return None

    return f"{stuck} deal(s) have been awaiting a financing decision for over 24 hours."


def _gap_escalations(employee_id=None):

    escalations = get_escalation_dashboard()

    if not escalations:
        return None

    return f"{len(escalations)} lead(s) are currently escalated."


def _gap_pending_assets(employee_id=None):

    n = len(list_pending_asset_approvals())

    return f"{n} asset(s) are waiting for approval." if n else None


def _gap_pending_campaigns(employee_id=None):

    n = len(list_pending_campaigns())

    return f"{n} campaign(s) are waiting to be activated." if n else None


def _gap_pending_websites(employee_id=None):

    n = len(list_pending_website_approvals())

    return f"{n} website(s) are waiting for approval." if n else None


def _gap_service_missing_cost_data(employee_id=None):

    count = 0

    for entity in ledger.get_all().values():

        if entity.entity_type != SERVICE_RECORD:
            continue

        attrs = entity.attributes

        if attrs.get("PayType") == "Warranty":
            continue

        if not attrs.get("PartsCost") or not attrs.get("LaborHours"):
            count += 1

    return (
        f"{count} repair order(s) are missing parts cost or labor hours."
        if count else None
    )


def _gap_obsolete_parts(employee_id=None):

    try:
        value = compute_parts_kpis()["raw"]["obsolete_value"]
    except Exception:
        return None

    if not value:
        return None

    return f"${value:,.2f} in parts inventory looks obsolete (no sale in 180+ days)."


# ---------------------------------------------------------------------------
# Task catalog -- department -> tier -> [task template, ...]. Prompts are exact
# phrases already recognized by core/ai_api.py's intent dictionaries (DASHBOARD_TERMS,
# ASSET_PANEL_TERMS, CAMPAIGN_PANEL_TERMS, WEBSITE_PANEL_TERMS, DEAL_PANEL_TERMS,
# INTELLIGENCE_PANEL_TERMS, ADMIN_PANEL_TERMS, GENERAL_PANEL_TERMS) so clicking one and
# sending it into chat actually lands on the right panel, not the LLM fallback.
# ---------------------------------------------------------------------------

def _uniform(tasks):
    return {TIER_STAFF: tasks, TIER_MANAGER: tasks, TIER_EXECUTIVE: tasks}


TASK_CATALOG = {

    "sales": {
        TIER_STAFF: [
            {
                "key": "sales_followup_leads",
                "title": "Follow up on leads needing attention",
                "description": "Some of your leads haven't been followed up on.",
                "prompt": "Which leads need follow-up?",
                "time_bucket": "any",
                "gap_check": _gap_leads_followup,
            },
            {
                "key": "sales_check_pipeline",
                "title": "Check your pipeline",
                "description": "Start the day with a look at where your deals stand.",
                "prompt": "Show sales pipeline",
                "time_bucket": "morning",
                "gap_check": None,
            },
            {
                "key": "sales_review_deals",
                "title": "Check on your deals",
                "description": "See what's moving through the deal desk right now.",
                "prompt": "Show my deals",
                "time_bucket": "any",
                "gap_check": None,
            },
        ],
        TIER_MANAGER: [
            {
                "key": "sales_mgr_leaderboard",
                "title": "Review the team leaderboard",
                "description": "Check how the team is pacing today.",
                "prompt": "Who's on top of the leaderboard?",
                "time_bucket": "morning",
                "gap_check": None,
            },
            {
                "key": "sales_mgr_financing_queue",
                "title": "Clear deals stuck in financing",
                "description": "Some deals have been waiting on a financing decision.",
                "prompt": "Show deals awaiting financing",
                "time_bucket": "any",
                "gap_check": _gap_deals_stuck_in_financing,
            },
            {
                "key": "sales_mgr_escalations",
                "title": "Check for escalated leads",
                "description": "Some leads may need a manager's attention.",
                "prompt": "Are there any escalated leads?",
                "time_bucket": "any",
                "gap_check": _gap_escalations,
            },
            {
                "key": "sales_mgr_workload",
                "title": "Check team workload balance",
                "description": "See who's carrying the heaviest lead load today.",
                "prompt": "Show current workload",
                "time_bucket": "morning",
                "gap_check": None,
            },
        ],
        TIER_EXECUTIVE: [
            {
                "key": "sales_exec_intelligence",
                "title": "Review the executive rollup",
                "description": "Start the day with the cross-department profit picture.",
                "prompt": "Show department intelligence",
                "time_bucket": "morning",
                "gap_check": None,
            },
            {
                "key": "sales_exec_readiness",
                "title": "Check dealership readiness",
                "description": "See where each department stands today.",
                "prompt": "What's our readiness score?",
                "time_bucket": "any",
                "gap_check": None,
            },
            {
                "key": "sales_exec_network",
                "title": "Check network performance rank",
                "description": "See how this store compares across the network.",
                "prompt": "How do we rank against the network?",
                "time_bucket": "any",
                "gap_check": None,
            },
        ],
    },

    "service": {
        TIER_STAFF: [
            {
                "key": "service_today_appts",
                "title": "Check today's appointments",
                "description": "Confirm who's on the schedule today.",
                "prompt": "What appointments are scheduled today?",
                "time_bucket": "morning",
                "gap_check": None,
            },
            {
                "key": "service_overdue_orders",
                "title": "Chase overdue service orders",
                "description": "Some repair orders may be running behind.",
                "prompt": "Any overdue service orders?",
                "time_bucket": "any",
                "gap_check": None,
            },
            {
                "key": "service_log_cost_data",
                "title": "Log missing repair-order data",
                "description": "Some closed repair orders are missing cost/labor entries.",
                "prompt": "Show service workload",
                "time_bucket": "end_of_day",
                "gap_check": _gap_service_missing_cost_data,
            },
        ],
        TIER_MANAGER: [
            {
                "key": "service_mgr_workload",
                "title": "Review technician workload",
                "description": "See how work is distributed across the shop today.",
                "prompt": "Show service workload",
                "time_bucket": "morning",
                "gap_check": None,
            },
            {
                "key": "service_mgr_intelligence",
                "title": "Check the effective labor rate trend",
                "description": "See today's service profitability vs. yesterday.",
                "prompt": "Show service intelligence",
                "time_bucket": "any",
                "gap_check": None,
            },
            {
                "key": "service_mgr_cost_data",
                "title": "Follow up on missing cost data",
                "description": "Some closed repair orders are missing cost/labor entries.",
                "prompt": "Show service workload",
                "time_bucket": "end_of_day",
                "gap_check": _gap_service_missing_cost_data,
            },
        ],
        TIER_EXECUTIVE: [
            {
                "key": "service_exec_intelligence",
                "title": "Review the executive rollup",
                "description": "See how service contributes to today's overall gross.",
                "prompt": "Show department intelligence",
                "time_bucket": "morning",
                "gap_check": None,
            },
        ],
    },

    "finance": {
        TIER_STAFF: [
            {
                "key": "finance_staff_financing_queue",
                "title": "Review deals awaiting a decision",
                "description": "Some deals need a financing decision.",
                "prompt": "Show deals awaiting financing",
                "time_bucket": "any",
                "gap_check": _gap_deals_stuck_in_financing,
            },
            {
                "key": "finance_staff_pipeline",
                "title": "Check the finance pipeline",
                "description": "Start the day with a look at what's in progress.",
                "prompt": "Show finance pipeline",
                "time_bucket": "morning",
                "gap_check": None,
            },
        ],
        TIER_MANAGER: [
            {
                "key": "finance_mgr_financing_queue",
                "title": "Clear the financing decision queue",
                "description": "Some deals have been waiting on a financing decision.",
                "prompt": "Show deals awaiting financing",
                "time_bucket": "any",
                "gap_check": _gap_deals_stuck_in_financing,
            },
            {
                "key": "finance_mgr_reserve",
                "title": "Review reserve income",
                "description": "Check today's F&I performance vs. yesterday.",
                "prompt": "Show F&I intelligence",
                "time_bucket": "any",
                "gap_check": None,
            },
            {
                "key": "finance_mgr_pipeline",
                "title": "Check the finance pipeline",
                "description": "Start the day with a look at what's in progress.",
                "prompt": "Show finance pipeline",
                "time_bucket": "morning",
                "gap_check": None,
            },
        ],
        TIER_EXECUTIVE: [
            {
                "key": "finance_exec_rollup",
                "title": "Review the executive gross profit rollup",
                "description": "Start the day with the cross-department profit picture.",
                "prompt": "Show department intelligence",
                "time_bucket": "morning",
                "gap_check": None,
            },
            {
                "key": "finance_exec_readiness",
                "title": "Check dealership readiness",
                "description": "See where each department stands today.",
                "prompt": "What's our readiness score?",
                "time_bucket": "any",
                "gap_check": None,
            },
        ],
    },

    "marketing": {
        TIER_STAFF: [
            {
                "key": "marketing_staff_assets",
                "title": "Submit or check your assets",
                "description": "See where your marketing assets stand in the approval queue.",
                "prompt": "Show my assets",
                "time_bucket": "any",
                "gap_check": None,
            },
            {
                "key": "marketing_staff_campaigns",
                "title": "Check campaign audience previews",
                "description": "Some campaigns are ready for an audience preview.",
                "prompt": "Show pending campaigns",
                "time_bucket": "any",
                "gap_check": _gap_pending_campaigns,
            },
            {
                "key": "marketing_staff_websites",
                "title": "Check on your websites",
                "description": "See where your website drafts stand.",
                "prompt": "Show my websites",
                "time_bucket": "any",
                "gap_check": None,
            },
        ],
        TIER_MANAGER: [
            {
                "key": "marketing_mgr_approvals",
                "title": "Review the asset approval queue",
                "description": "Some assets are waiting on a sign-off.",
                "prompt": "Show pending approvals",
                "time_bucket": "any",
                "gap_check": _gap_pending_assets,
            },
            {
                "key": "marketing_mgr_campaigns",
                "title": "Review the campaign activation queue",
                "description": "Some campaigns are ready to activate.",
                "prompt": "Show pending campaigns",
                "time_bucket": "any",
                "gap_check": _gap_pending_campaigns,
            },
            {
                "key": "marketing_mgr_websites",
                "title": "Review the website publish queue",
                "description": "Some sites are ready to publish.",
                "prompt": "Show pending websites",
                "time_bucket": "any",
                "gap_check": _gap_pending_websites,
            },
        ],
        TIER_EXECUTIVE: [
            {
                "key": "marketing_exec_rollup",
                "title": "Review the executive rollup",
                "description": "See how marketing spend is tracking against results.",
                "prompt": "Show department intelligence",
                "time_bucket": "morning",
                "gap_check": None,
            },
        ],
    },

    "operations": {
        TIER_STAFF: [
            {
                "key": "ops_staff_workload",
                "title": "Check team workload",
                "description": "See how work is distributed today.",
                "prompt": "Show current workload",
                "time_bucket": "morning",
                "gap_check": None,
            },
            {
                "key": "ops_staff_escalations",
                "title": "Check for escalated leads",
                "description": "Some leads may need attention.",
                "prompt": "Are there any escalated leads?",
                "time_bucket": "any",
                "gap_check": _gap_escalations,
            },
        ],
        TIER_MANAGER: [
            {
                "key": "ops_mgr_workload",
                "title": "Balance team workload",
                "description": "See who's carrying the heaviest load today.",
                "prompt": "Show current workload",
                "time_bucket": "morning",
                "gap_check": None,
            },
            {
                "key": "ops_mgr_financing_queue",
                "title": "Check deals awaiting financing",
                "description": "Some deals have been waiting on a financing decision.",
                "prompt": "Show deals awaiting financing",
                "time_bucket": "any",
                "gap_check": _gap_deals_stuck_in_financing,
            },
            {
                "key": "ops_mgr_escalations",
                "title": "Review escalated leads",
                "description": "Some leads may need attention.",
                "prompt": "Are there any escalated leads?",
                "time_bucket": "any",
                "gap_check": _gap_escalations,
            },
        ],
        TIER_EXECUTIVE: [
            {
                "key": "ops_exec_rollup",
                "title": "Review the executive rollup",
                "description": "Start the day with the cross-department profit picture.",
                "prompt": "Show department intelligence",
                "time_bucket": "morning",
                "gap_check": None,
            },
            {
                "key": "ops_exec_readiness",
                "title": "Check dealership readiness",
                "description": "See where each department stands today.",
                "prompt": "What's our readiness score?",
                "time_bucket": "any",
                "gap_check": None,
            },
            {
                "key": "ops_exec_network",
                "title": "Check network performance rank",
                "description": "See how this store compares across the network.",
                "prompt": "How do we rank against the network?",
                "time_bucket": "any",
                "gap_check": None,
            },
        ],
    },

    # Administration/Inventory/Readiness/Network aren't real job functions (nobody's
    # Title is "Inventory Manager") -- tier-invariant on purpose, see module docstring.
    "administration": _uniform([
        {
            "key": "admin_roster",
            "title": "Review the employee roster",
            "description": "Check for accounts needing a password reset or role update.",
            "prompt": "Show employee roster",
            "time_bucket": "morning",
            "gap_check": None,
        },
        {
            "key": "admin_audit",
            "title": "Scan the audit log for anomalies",
            "description": "Review recent account and access activity.",
            "prompt": "Show audit log",
            "time_bucket": "any",
            "gap_check": None,
        },
        {
            "key": "admin_compliance",
            "title": "Check the compliance layer",
            "description": "Review the current compliance status.",
            "prompt": "Show compliance status",
            "time_bucket": "any",
            "gap_check": None,
        },
        {
            "key": "admin_bot_coverage",
            "title": "Check active bot coverage",
            "description": "See who the bot is currently covering for.",
            "prompt": "Show bot coverage",
            "time_bucket": "any",
            "gap_check": None,
        },
    ]),

    "inventory": _uniform([
        {
            "key": "inventory_aging",
            "title": "Check aging inventory",
            "description": "See which vehicles have been sitting the longest.",
            "prompt": "What inventory is aging?",
            "time_bucket": "morning",
            "gap_check": None,
        },
        {
            "key": "inventory_vehicles_60",
            "title": "Review vehicles over 60 days",
            "description": "Flag units that may need a price adjustment.",
            "prompt": "Show vehicles over 60 days",
            "time_bucket": "any",
            "gap_check": None,
        },
        {
            "key": "inventory_health",
            "title": "Check overall inventory health",
            "description": "Get a snapshot of the current lot mix.",
            "prompt": "Show inventory health",
            "time_bucket": "any",
            "gap_check": None,
        },
    ]),

    "readiness": _uniform([
        {
            "key": "readiness_score",
            "title": "Check department readiness",
            "description": "See how prepared each department is today.",
            "prompt": "What's our readiness score?",
            "time_bucket": "morning",
            "gap_check": None,
        },
    ]),

    "network": _uniform([
        {
            "key": "network_rank",
            "title": "Check network performance rank",
            "description": "See how this store compares across the network.",
            "prompt": "How do we rank against the network?",
            "time_bucket": "morning",
            "gap_check": None,
        },
        {
            "key": "network_growth",
            "title": "Review growth opportunities",
            "description": "See what other stores are doing better.",
            "prompt": "What are our growth opportunities?",
            "time_bucket": "any",
            "gap_check": None,
        },
    ]),
}


def generate_tasks(employee_id, role, section):
    """The main entry point: a prioritized list of task suggestions for this employee
    right now, given their real Employee.Title tier, the section/department they're
    looking at, and the server's current time-of-day bucket. Each item:
    {key, title, description, prompt, priority}. Suppressed task types (see
    core/bot_learning.py) are dropped entirely rather than shown greyed out -- an
    employee who's told the bot three times in a row that a suggestion isn't useful
    shouldn't have to keep dismissing it."""

    employee = get_employee(employee_id)
    tier = infer_tier(employee.attributes.get("Title") if employee else None)

    dept_key = normalize_section(section)

    if dept_key not in TASK_CATALOG:
        dept_key = resolve_department_key(employee, role)

    templates = TASK_CATALOG.get(dept_key, {}).get(tier, [])

    bucket = time_bucket()
    results = []

    for template in templates:

        if template["time_bucket"] not in ("any", bucket):
            continue

        detail = None

        if template["gap_check"]:

            detail = template["gap_check"](employee_id)

            if detail is None:
                continue

        affinity = get_task_affinity(employee_id, template["key"])

        if affinity["suppressed"]:
            continue

        description = (
            f'{template["description"]} {detail}' if detail else template["description"]
        )

        priority = affinity["priority_boost"] + (2 if template["gap_check"] else 0)

        results.append({
            "key": template["key"],
            "title": template["title"],
            "description": description,
            "prompt": template["prompt"],
            "priority": priority,
        })

    results.sort(key=lambda t: t["priority"], reverse=True)

    # Coaching Intensity Tiers (2026-07-19) -- a deferred import, since
    # core/coaching.py itself imports infer_tier/TIER_* from this module at
    # module level (a real circular-import risk if this were a top-level
    # import instead, same "deferred, in-function import" technique
    # core/loan_servicing.py's get_loan_financials() already established for
    # its own core/payments.py import). A pure post-processing step -- never
    # rewrites a task's own real title/description/prompt text.
    from core.coaching import apply_intensity_to_tasks
    results, _intensity, _resolved_from = apply_intensity_to_tasks(results, employee_id, role=role, department=dept_key)

    return results
