import re

from core.ai_assistant import (
    ask_ai
)

from core.workload_dashboard_api import (
    get_dashboard as get_workload_dashboard
)

from core.leaderboard_api import (
    get_dashboard as get_leaderboard_dashboard
)

from core.escalation_dashboard_api import (
    get_dashboard as get_escalation_dashboard
)

from core.security import (
    can_access_dashboard,
    can_access_entity
)

from core.permissions import (
    ADMIN,
    OPERATIONS,
    SALES,
    FINANCE,
    MARKETING
)

from core.repository import repository

from core.entity_menu_links import build_suggested_actions


# Keyword -> dashboard key. Two jobs: (1) workload/leaderboard/escalations skip the LLM
# entirely and return a canned formatted answer straight from the dashboard function,
# same shortcut behavior as before this pass; (2) EVERY key here also drives
# `suggested_dashboard` on the response (whether or not the LLM was invoked), which the
# frontend uses to offer a "View in Dashboard" button in the chat — workspace is
# chat-triggered now, not tab-triggered, see BUILD_QUEUE.md. Every match is checked
# against core/permissions.py's DASHBOARD_ACCESS via can_access_dashboard() before
# either returning real data or suggesting a dashboard the caller's role can't open —
# this fast-path route was NOT going through that check before Phase 9's dashboard ACL
# landed, a real gap fixed here (previously any role could get real workload/leaderboard/
# escalation data through chat even if /dashboard/workload etc. would refuse them).
DASHBOARD_TERMS = {

    "workload": [
        "workload",
        "work load",
        "active workload",
        "heaviest workload"
    ],

    "leaderboard": [
        "leaderboard",
        "top performer",
        "best performer",
        "highest performer",
        "who is on top"
    ],

    "escalations": [
        "escalation",
        "escalated",
        "escalated lead",
        "escalated leads",
        "stalled lead",
        "stalled leads"
    ],

    "sales": [
        "sales dashboard",
        "sales numbers",
        "sales overview",
        "sales summary"
    ],

    "service": [
        "service dashboard",
        "service overview",
        "service summary"
    ],

    "finance": [
        "finance dashboard",
        "finance overview",
        "finance summary",
        "funding status"
    ],

    "executive": [
        "executive dashboard",
        "executive summary",
        "company overview",
        "dealership overview",
        "overall performance"
    ],

    "pipeline": [
        "pipeline",
        "sales pipeline",
        "lead pipeline",
        "funnel"
    ],

    "followup": [
        "follow-up",
        "follow up",
        "needs follow-up",
        "followup"
    ],

    "manager": [
        "manager dashboard",
        "team performance",
        "team overview"
    ],

    "velocity": [
        "velocity",
        "deal velocity",
        "sales velocity",
        "deal speed"
    ]
}


def _match_dashboard_key(q):

    for key, terms in DASHBOARD_TERMS.items():

        if any(term in q for term in terms):

            return key

    return None


# Entity/profile lookup is chat-only now (2026-07-13, session 21) — there used to be a
# separate "type an ID" box in the workspace sidebar; Sam asked for everything to go
# through chat instead, matching how dashboards are already surfaced (`suggested_dashboard`
# above). NXTDeal entity IDs are always `PREFIX-NNNNN` (core/id_generator.py — VEH, CUST,
# LEAD, FIN, LENDER, SRV, DOC, IMG, EMP, DEAL), so a simple pattern catches "show me
# CUST-00042", "look up EMP-00003", "pull up VEH-00017's profile", etc. without needing
# stricter phrase-matching like DASHBOARD_TERMS uses.
_ENTITY_ID_PATTERN = re.compile(r"\b([A-Z]{2,10}-\d{4,6})\b")


# Admin-only structured views, surfaced through chat the same way department dashboards
# are (2026-07-13, session 26) — per Sam: "everything runs through the chat," including
# on the admin side. The employee roster, audit log, and compliance layer used to
# auto-load or sit as static content in /admin; now they're asked for, same as a
# department dashboard or an entity profile. Kept as a separate suggestion field
# (suggested_admin_panel) rather than folding into DASHBOARD_TERMS/suggested_dashboard,
# since these render as their own structured views (a table, a filterable log, a score
# card) — not a generic bar chart like every real DASHBOARD_ACCESS key does.
ADMIN_PANEL_TERMS = {

    "roster": [
        "employee roster",
        "roster",
        "list employees",
        "who has access",
        "list credentials",
        "employee directory"
    ],

    "audit": [
        "audit log",
        "audit trail",
        "who did what",
        "recent activity",
        "audit history"
    ],

    # Agentic bot layer (session 36) -- who the bot is currently covering for, ADMIN
    # only, same gating shape as roster/audit above. (The old "compliance score/layer/
    # status" placeholder that used to live in this dict was retired session 38 --
    # compliance is now a real, ADMIN+OPERATIONS-visible feature with its own dedicated
    # ACL tier, see COMPLIANCE_ALERT_TERMS below, matching how INTELLIGENCE_PANEL_TERMS/
    # DEAL_PANEL_TERMS each got their own tier instead of sharing this strict
    # ADMIN-only dict.)
    "bot_coverage": [
        "bot coverage",
        "who's covering",
        "who is covering",
        "coverage schedule"
    ]
}


def _match_admin_panel_key(q):

    for key, terms in ADMIN_PANEL_TERMS.items():

        if any(term in q for term in terms):

            return key

    return None


# Employee IDs specifically (core/id_generator.py's EMP- prefix) — used only to detect a
# password-reset request, not general entity lookup (that's _match_entity_id above).
_EMPLOYEE_ID_PATTERN = re.compile(r"\b(EMP-\d{4,6})\b")


def _match_reset_password_request(question, role):
    """Recognizes an admin asking to reset someone's password in chat (e.g. "reset
    password for EMP-00003"). Deliberately does NOT execute anything here, and never
    will from this function alone — resetting a credential is a mutating,
    security-sensitive action, unlike the read-only dashboard/profile/roster/audit
    suggestions elsewhere in this module. Chat only ever attaches
    `suggested_reset_password`, which the frontend renders as an explicit confirmation
    card in the workspace panel; the actual POST /auth/admin/reset-password call still
    requires a separate, deliberate admin click. Silently returns None for a non-ADMIN
    caller (same "just don't suggest it" behavior as an unmatched DASHBOARD_TERMS
    question or an inaccessible entity ID) rather than trying to execute or explain —
    there's no real account-enumeration risk here since a non-admin can't act on the
    suggestion either way, but there's no reason to confirm a real employee_id's
    existence to a non-admin by echoing it back either."""

    if role != ADMIN:
        return None

    q = question.lower()

    if "reset" not in q or "password" not in q:
        return None

    match = _EMPLOYEE_ID_PATTERN.search(question.upper())

    if not match:
        return None

    return match.group(1)


# Non-admin structured views, open to any authenticated role — same chat-first
# principle as ADMIN_PANEL_TERMS above, but for content that isn't role-restricted at
# all (2026-07-13, session 27 — Sam: "push the same logic to Workspace, Readiness, and
# Network... all of NXTDeal needs to function with the same ideology"). The readiness
# score used to be static content on /readiness; now it's asked for too. Kept as its
# own suggestion field (suggested_panel, not suggested_admin_panel) since there's no
# ADMIN gate at all here — conflating the two would make a future reader wonder why a
# "panel" sometimes needs ADMIN and sometimes doesn't. (The old "performance_rank"/
# "growth_opportunities" static placeholders that used to live in this dict were
# retired session 38 -- the Network page is now a real, ADMIN+OPERATIONS+FINANCE-gated
# feature with its own dedicated intent, see NETWORK_PANEL_TERMS below, matching how
# INTELLIGENCE_PANEL_TERMS got its own tier instead of staying "open to any role.")
GENERAL_PANEL_TERMS = {

    "readiness_score": [
        "readiness score",
        "how ready are we",
        "readiness status"
    ],
}


def _match_general_panel_key(q):

    for key, terms in GENERAL_PANEL_TERMS.items():

        if any(term in q for term in terms):

            return key

    return None


# Marketing asset design/approval workflow (2026-07-13, session 30 -- phase 1 of
# folding NXTDeal's product suite into NXTDeal). Same chat-first shape as every other
# panel here: "templates" and "my_assets" are open to any role (requesting/checking on
# your own assets isn't privileged); "pending_approvals" is MARKETING/ADMIN-only, same
# gating shape ADMIN_PANEL_TERMS already uses.
ASSET_PANEL_TERMS = {

    "templates": [
        "asset templates",
        "marketing templates",
        "create an ad",
        "design a flyer",
        "make a flyer",
        "make a social post",
        "create a flyer"
    ],

    "pending_approvals": [
        "pending approvals",
        "assets to review",
        "approve assets",
        "asset approval queue",
        "review assets"
    ],

    "my_assets": [
        "my assets",
        "my pending assets",
        "assets i requested",
        "assets i've requested"
    ]
}


def _match_asset_panel_key(q):

    for key, terms in ASSET_PANEL_TERMS.items():

        if any(term in q for term in terms):

            return key

    return None


_ASSET_PANEL_LABELS = {
    "templates": "asset templates",
    "pending_approvals": "the asset approval queue",
    "my_assets": "your assets"
}


def _format_asset_panel_ack(key):

    label = _ASSET_PANEL_LABELS.get(key, key)

    return f"Here's {label} — view it in the workspace panel →"


# Campaign & customer-lifecycle engine (2026-07-13, session 31 -- phase 2 of the
# NXTDeal suite integration). Same chat-first shape as ASSET_PANEL_TERMS: "types" and
# "my_campaigns" are open to any role (starting a draft or checking your own campaigns
# isn't privileged); "pending_campaigns" (the activation queue) is MARKETING/ADMIN-only,
# mirroring "pending_approvals" above exactly.
CAMPAIGN_PANEL_TERMS = {

    "types": [
        "campaign types",
        "campaign templates",
        "start a campaign",
        "run a campaign",
        "create a campaign",
        "launch a campaign",
        "retention campaign",
        "run a retention campaign",
        "inventory ads",
        "conquest campaign",
        "accessory accelerator"
    ],

    "pending_campaigns": [
        "pending campaigns",
        "campaigns to activate",
        "campaign activation queue",
        "review campaigns",
        "activate a campaign"
    ],

    "my_campaigns": [
        "my campaigns",
        "campaigns i created",
        "campaigns i've created",
        "my pending campaigns"
    ]
}


def _match_campaign_panel_key(q):

    for key, terms in CAMPAIGN_PANEL_TERMS.items():

        if any(term in q for term in terms):

            return key

    return None


_CAMPAIGN_PANEL_LABELS = {
    "types": "campaign types",
    "pending_campaigns": "the campaign activation queue",
    "my_campaigns": "your campaigns"
}


def _format_campaign_panel_ack(key):

    label = _CAMPAIGN_PANEL_LABELS.get(key, key)

    return f"Here's {label} — view it in the workspace panel →"


# Website / inventory builder (2026-07-13, session 32 -- phase 3, the last piece of the
# NXTDeal suite integration before "DMS style systems"). Same chat-first shape as
# CAMPAIGN_PANEL_TERMS: "sections"/"my_sites" open to any role (starting a draft or
# checking your own sites isn't privileged); "pending_sites" (the publish queue) is
# MARKETING/ADMIN-only, mirroring "pending_approvals"/"pending_campaigns" exactly.
WEBSITE_PANEL_TERMS = {

    "sections": [
        "build a website",
        "build a site",
        "website builder",
        "site builder",
        "start a website",
        "new dealership website",
        "add a section",
        "edit my website"
    ],

    "pending_sites": [
        "pending sites",
        "sites to review",
        "sites to publish",
        "site approval queue",
        "review websites",
        "pending websites"
    ],

    "my_sites": [
        "my website",
        "my websites",
        "my sites",
        "sites i built",
        "sites i've built"
    ]
}


def _match_website_panel_key(q):

    for key, terms in WEBSITE_PANEL_TERMS.items():

        if any(term in q for term in terms):

            return key

    return None


_WEBSITE_PANEL_LABELS = {
    "sections": "the website builder",
    "pending_sites": "the website publish queue",
    "my_sites": "your websites"
}


def _format_website_panel_ack(key):

    label = _WEBSITE_PANEL_LABELS.get(key, key)

    return f"Here's {label} — view it in the workspace panel →"


# DMS Deal Desk (2026-07-13, session 33 -- phase 1 of the DMS buildout, modeled on
# DealerSocket/Tekion's Desking + F&I + Contracting modules). Narrower than the
# ASSET/CAMPAIGN/WEBSITE panels above -- a Deal touches real pricing/financing, so
# every key here is gated to core/permissions.py's DEAL ENTITY_ACCESS list
# (ADMIN/OPERATIONS/SALES/FINANCE, no MARKETING/SERVICE), and "pending_financing" is
# further narrowed to the F&I-capable roles (ADMIN/OPERATIONS/FINANCE, no SALES) --
# matching core/deals_api.py's `_can_do_financing`.
_DEAL_ROLES = (ADMIN, OPERATIONS, SALES, FINANCE)
_DEAL_FINANCING_ROLES = (ADMIN, OPERATIONS, FINANCE)

DEAL_PANEL_TERMS = {

    "start_deal": [
        "sell a car",
        "sell this vehicle",
        "start a deal",
        "new deal",
        "desk a deal",
        "deal desk"
    ],

    "pending_financing": [
        "pending financing",
        "financing decisions",
        "financing queue",
        "deals awaiting financing",
        "review financing"
    ],

    "my_deals": [
        "my deals",
        "deals i'm working",
        "deals i've started",
        "my deal desk"
    ]
}


def _match_deal_panel_key(q):

    for key, terms in DEAL_PANEL_TERMS.items():

        if any(term in q for term in terms):

            return key

    return None


_DEAL_PANEL_LABELS = {
    "start_deal": "the deal desk",
    "pending_financing": "deals awaiting a financing decision",
    "my_deals": "your deals"
}


def _format_deal_panel_ack(key):

    label = _DEAL_PANEL_LABELS.get(key, key)

    return f"Here's {label} — view it in the workspace panel →"


# Department Intelligence reporting layer (2026-07-13, session 35 -- Sam: "add this
# product functionality into the admin - its our product 'bumper bi' that creates
# dashboards across the dealership," modeled on a real cross-dealership KPI-dashboard
# product's Sales/Service/Parts/F&I/Accounting layout). Narrower than
# ASSET/CAMPAIGN/WEBSITE/DEAL -- this is cross-department profit/margin data, gated to
# ADMIN/OPERATIONS/FINANCE (core/department_intelligence_api.py's DEPT_INTEL_ROLES) for
# every department, not split further per-department the way DASHBOARD_ACCESS is
# elsewhere, since Department Intelligence's whole pitch is seeing everything in one
# place. Renamed session 68 (Sam: "i want to take out the term 'bumper bi'... What i do
# want to do is include that level of reporting for each reporting section of every
# department") -- the branding is gone, the underlying KPI+trend engine is unchanged.
DEPT_INTEL_ROLES = (ADMIN, OPERATIONS, FINANCE)

INTELLIGENCE_PANEL_TERMS = {

    # Not a real department (see core/department_intelligence.py's DEPARTMENTS) -- a
    # UI-routing key only, same shape as ASSET_PANEL_TERMS's "templates"/
    # CAMPAIGN_PANEL_TERMS's "types" browse screens. Checked first so "show all
    # department intelligence dashboards" doesn't get swallowed by "executive"'s bare
    # "department intelligence" term below.
    "departments": [
        "department intelligence departments", "all department intelligence dashboards",
        "department intelligence dashboards", "browse department intelligence"
    ],

    "sales": [
        "department intelligence sales", "sales intelligence", "sales profit leaks"
    ],

    "service": [
        "department intelligence service", "service intelligence", "service profit leaks"
    ],

    "parts": [
        "department intelligence parts", "parts intelligence", "parts profit leaks",
        "obsolete inventory"
    ],

    "fi": [
        "department intelligence f&i", "department intelligence fi", "f&i intelligence",
        "fi intelligence", "finance intelligence"
    ],

    "executive": [
        "department intelligence", "profit leaks", "executive overview",
        "accounting intelligence", "cross department profit", "where is our profit"
    ],
}


def _match_intelligence_panel_key(q):

    for key, terms in INTELLIGENCE_PANEL_TERMS.items():

        if any(term in q for term in terms):

            return key

    return None


_INTELLIGENCE_PANEL_LABELS = {
    "departments": "Department Intelligence",
    "sales": "Sales Intelligence",
    "service": "Service Intelligence",
    "parts": "Parts Intelligence",
    "fi": "F&I Intelligence",
    "executive": "Executive Overview",
}


def _format_intelligence_panel_ack(key):

    label = _INTELLIGENCE_PANEL_LABELS.get(key, key)

    return f"Here's {label} — view it in the workspace panel →"


# Agentic bot layer (2026-07-13, session 36 -- Sam: "create a agentic bot for each
# section... it will prompt the user throughout the day with things that need to be
# done depending on their role"). Open to any authenticated role, same as the floating
# bot widget itself (frontend/components/BotWidget.tsx) -- the task list is already
# personalized server-side to the caller's own employee_id/role/section
# (core/bot_tasks.py), so there's nothing to further gate here the way
# ASSET/CAMPAIGN/WEBSITE/DEAL/intelligence panels gate specific sub-keys.
BOT_TASK_TERMS = [
    "my tasks",
    "show my tasks",
    "bot tasks",
    "daily tasks",
    "what should i be doing",
    "what should i do today",
    "what should i do"
]


def _match_bot_task_intent(q):

    return any(term in q for term in BOT_TASK_TERMS)


def _format_bot_task_ack():

    return "Here's your task list — view it in the workspace panel →"


# Employee $ value/effectiveness (2026-07-13, session 37) -- ADMIN + OPERATIONS, a
# separate tuple from ADMIN_PANEL_TERMS's strict ADMIN-only gate below (roster/audit/
# compliance/bot_coverage are all narrower than this on purpose), same dedicated-dict
# pattern INTELLIGENCE_PANEL_TERMS/DEAL_PANEL_TERMS already use for their own ACL tiers.
EMPLOYEE_VALUE_ROLES = (ADMIN, OPERATIONS)

EMPLOYEE_VALUE_TERMS = [
    "employee value",
    "employee effectiveness",
    "who is more effective",
    "employee performance value",
    "effectiveness score"
]


def _match_employee_value_intent(q):

    return any(term in q for term in EMPLOYEE_VALUE_TERMS)


def _format_employee_value_ack():

    return "Here's employee value/effectiveness — view it in the workspace panel →"


# Compliance agent (2026-07-13, session 38) -- Sam: "there needs to be a complete
# compliance level baked into every part of this... If it fails a compliance review it
# needs to be flagged, stopped, and not allowed to go through until the corrections are
# made... notify managers/admin." Same ADMIN+OPERATIONS tier as EMPLOYEE_VALUE_TERMS
# above (matches core/permissions.py's COMPLIANCE_ALERT ENTITY_ACCESS), its own
# dedicated dict rather than folding into the strict ADMIN-only ADMIN_PANEL_TERMS.
COMPLIANCE_ROLES = (ADMIN, OPERATIONS)

COMPLIANCE_ALERT_TERMS = [
    "compliance alerts",
    "compliance issues",
    "compliance violations",
    "compliance score",
    "compliance layer",
    "compliance status",
    "flagged compliance",
    "review compliance"
]


def _match_compliance_alert_intent(q):

    return any(term in q for term in COMPLIANCE_ALERT_TERMS)


def _format_compliance_alert_ack():

    return "Here are the current compliance alerts — view them in the workspace panel →"


# Network intelligence layer (2026-07-13, session 38) -- Sam: "the network is a
# collection of other dealers... applying department intelligence and its kpi reports
# pulled from other NXTDeal dealers (blind labeled for anonymity)... an ai driven audit
# on their dealership to see where they need to improve." Reuses Department
# Intelligence's exact ACL tier
# (ADMIN/OPERATIONS/FINANCE) since this is built directly on the same cross-department
# profit data, just benchmarked against (simulated) peers -- narrower than the old
# "open to any role" performance_rank/growth_opportunities placeholders this replaces.
NETWORK_ROLES = (ADMIN, OPERATIONS, FINANCE)

NETWORK_PANEL_TERMS = {

    "benchmark": [
        "network rank",
        "how do we rank",
        "performance rank",
        "network benchmark",
        "compare to other dealers",
        "peer comparison",
        "area trends",
        "industry trends"
    ],

    "audit": [
        "growth opportunities",
        "network audit",
        "dealership audit",
        "where do we need to improve",
        "ai audit"
    ],
}


def _match_network_panel_key(q):

    for key, terms in NETWORK_PANEL_TERMS.items():

        if any(term in q for term in terms):

            return key

    return None


_NETWORK_PANEL_LABELS = {
    "benchmark": "the network benchmark",
    "audit": "the network audit",
}


def _format_network_panel_ack(key):

    label = _NETWORK_PANEL_LABELS.get(key, key)

    return f"Here's {label} — view it in the workspace panel →"


def _match_entity_id(question, role):
    """Looks for something that looks like an entity ID anywhere in the question. Returns
    it only if it actually exists on the graph AND the caller's role can see that entity
    type (core/security.py's can_access_entity — same rule /entity/{id} and /profile/{id}
    already enforce) — an unknown or forbidden ID just means no suggestion, not an error,
    same as how an unmatched DASHBOARD_TERMS question just skips suggested_dashboard."""

    match = _ENTITY_ID_PATTERN.search(question.upper())

    if not match:
        return None

    entity_id = match.group(1)

    entity = repository.get_entity(entity_id)

    if not entity:
        return None

    if not can_access_entity(role, entity.entity_type):
        return None

    return entity_id


def _format_workload():

    workload = get_workload_dashboard()

    lines = [
        "📊 Current Workload",
        ""
    ]

    for employee in workload:

        lines.append(
            f"Employee: {employee['employee_id']}"
        )

        lines.append(
            f"Active Workload: {employee['active_workload']}"
        )

        lines.append("")

    return "\n".join(lines)


def _format_leaderboard():

    leaderboard = (
        get_leaderboard_dashboard()
    )

    lines = [
        "🏆 Leaderboard",
        ""
    ]

    for rank, employee in enumerate(
        leaderboard,
        start=1
    ):

        if isinstance(employee, dict):

            lines.append(
                f"{rank}. {employee.get('employee_id', 'Unknown')}"
            )

            lines.append(
                f"   Conversion Rate: {employee.get('conversion_rate', 0)}%"
            )

        else:

            lines.append(
                f"{rank}. {employee}"
            )

        lines.append("")

    return "\n".join(lines)


def _format_escalations():

    escalations = (
        get_escalation_dashboard()
    )

    lines = [
        "⚠️ Escalated Leads",
        ""
    ]

    if not escalations:

        lines.append(
            "No escalated leads found."
        )

    else:

        for lead in escalations:

            if isinstance(lead, dict):

                for key, value in lead.items():

                    lines.append(
                        f"{key}: {value}"
                    )

                lines.append("")

            else:

                lines.append(
                    str(lead)
                )

                lines.append("")

    return "\n".join(lines)


# Only these three have a canned formatter that skips the LLM entirely — unchanged
# behavior from before this pass. Every other DASHBOARD_TERMS key falls through to
# ask_ai() but still gets `suggested_dashboard` attached so the frontend can offer it.
_FORMATTERS = {
    "workload": _format_workload,
    "leaderboard": _format_leaderboard,
    "escalations": _format_escalations
}


_ADMIN_PANEL_LABELS = {
    "roster": "the employee roster",
    "audit": "the audit log",
    "bot_coverage": "bot coverage"
}


def _format_admin_panel_ack(key):

    label = _ADMIN_PANEL_LABELS.get(key, key)

    return f"Here's {label} — view it in the workspace panel →"


def _format_reset_password_ack(employee_id):

    return (
        f"I can start a password reset for {employee_id} — confirm in the workspace "
        "panel to generate a new temp password. Nothing changes until you confirm →"
    )


_GENERAL_PANEL_LABELS = {
    "readiness_score": "the readiness score",
}


def _format_general_panel_ack(key):

    label = _GENERAL_PANEL_LABELS.get(key, key)

    return f"Here's {label} — view it in the workspace panel →"


def ask(question, role=None, caller_employee_id=None):
    """`caller_employee_id` (security-hardening pass, 2026-07-20, Task #5):
    optional, threaded through from api/app.py's /ai/chat route -- passed to
    ask_ai() below as the real `actor` recorded on every AiActionLog entry.
    Named `caller_employee_id` rather than `employee_id` specifically to
    avoid colliding with `reset_employee_id` below (an unrelated local, the
    id of an EMPLOYEE BEING RESET, not the caller)."""

    q = question.lower()

    dashboard_key = _match_dashboard_key(q)
    entity_id = _match_entity_id(question, role)
    admin_panel_key = _match_admin_panel_key(q)
    reset_employee_id = _match_reset_password_request(question, role)
    general_panel_key = _match_general_panel_key(q)
    asset_panel_key = _match_asset_panel_key(q)
    campaign_panel_key = _match_campaign_panel_key(q)
    website_panel_key = _match_website_panel_key(q)
    deal_panel_key = _match_deal_panel_key(q)
    intelligence_panel_key = _match_intelligence_panel_key(q)
    bot_task_intent = _match_bot_task_intent(q)
    employee_value_intent = _match_employee_value_intent(q)
    compliance_alert_intent = _match_compliance_alert_intent(q)
    network_panel_key = _match_network_panel_key(q)

    if dashboard_key and not can_access_dashboard(role, dashboard_key):

        return {
            "response":
                f"You don't have access to the '{dashboard_key}' dashboard with your "
                "current role."
        }

    if admin_panel_key and role != ADMIN:

        return {
            "response":
                f"You don't have access to the '{admin_panel_key}' admin panel with "
                "your current role."
        }

    if asset_panel_key == "pending_approvals" and role not in (ADMIN, MARKETING):

        return {
            "response":
                "You don't have access to the asset approval queue with your current "
                "role — MARKETING or ADMIN can review pending assets."
        }

    if campaign_panel_key == "pending_campaigns" and role not in (ADMIN, MARKETING):

        return {
            "response":
                "You don't have access to the campaign activation queue with your "
                "current role — MARKETING or ADMIN can activate pending campaigns."
        }

    if website_panel_key == "pending_sites" and role not in (ADMIN, MARKETING):

        return {
            "response":
                "You don't have access to the website publish queue with your current "
                "role — MARKETING or ADMIN can publish pending sites."
        }

    if deal_panel_key and role not in _DEAL_ROLES:

        return {
            "response":
                "You don't have access to the deal desk with your current role — "
                "sales, finance, operations, or admin can work deals."
        }

    if deal_panel_key == "pending_financing" and role not in _DEAL_FINANCING_ROLES:

        return {
            "response":
                "You don't have access to the financing decision queue with your "
                "current role — finance, operations, or admin can decide financing."
        }

    if intelligence_panel_key and role not in DEPT_INTEL_ROLES:

        return {
            "response":
                "You don't have access to Department Intelligence with your current "
                "role — admin, operations, or finance can open it."
        }

    if employee_value_intent and role not in EMPLOYEE_VALUE_ROLES:

        return {
            "response":
                "You don't have access to employee value data with your current "
                "role — admin or operations can open it."
        }

    if compliance_alert_intent and role not in COMPLIANCE_ROLES:

        return {
            "response":
                "You don't have access to compliance alerts with your current "
                "role — admin or operations can review them."
        }

    if network_panel_key and role not in NETWORK_ROLES:

        return {
            "response":
                "You don't have access to the network with your current role — "
                "admin, operations, or finance can open it."
        }

    # Precedence for the plain-text reply when multiple things match: a reset request is
    # the most specific/actionable ask, then an admin panel, then an asset panel, then a
    # campaign panel, then a website panel, then a deal panel, then a department
    # intelligence panel,
    # then a general panel, then the existing canned dashboard formatters, then the LLM
    # fallback. Every suggestion field below is attached independently of which of these
    # produced the text — same pattern suggested_profile already uses alongside
    # suggested_dashboard.
    #
    # resolved_entities (session 76) and report_suggestion (session 76 follow-up) only
    # ever get real values out of the ask_ai() fallback branch below (the LLM is the
    # only path that can look up an arbitrary entity or build a report via tool calls)
    # -- every canned/formatter branch leaves both empty, which is correct: those paths
    # already have their own explicit suggested_* field.
    resolved_entities = []
    report_suggestion = None

    if reset_employee_id:

        response_text = _format_reset_password_ack(reset_employee_id)

    elif admin_panel_key:

        response_text = _format_admin_panel_ack(admin_panel_key)

    elif asset_panel_key:

        response_text = _format_asset_panel_ack(asset_panel_key)

    elif campaign_panel_key:

        response_text = _format_campaign_panel_ack(campaign_panel_key)

    elif website_panel_key:

        response_text = _format_website_panel_ack(website_panel_key)

    elif deal_panel_key:

        response_text = _format_deal_panel_ack(deal_panel_key)

    elif intelligence_panel_key:

        response_text = _format_intelligence_panel_ack(intelligence_panel_key)

    elif bot_task_intent:

        response_text = _format_bot_task_ack()

    elif employee_value_intent:

        response_text = _format_employee_value_ack()

    elif compliance_alert_intent:

        response_text = _format_compliance_alert_ack()

    elif network_panel_key:

        response_text = _format_network_panel_ack(network_panel_key)

    elif general_panel_key:

        response_text = _format_general_panel_ack(general_panel_key)

    elif dashboard_key in _FORMATTERS:

        response_text = _FORMATTERS[dashboard_key]()

    else:

        response_text, resolved_entities, report_suggestion = ask_ai(question, role, employee_id=caller_employee_id)

    # Session 76: a direct PREFIX-NNNNN hit (_match_entity_id above) is itself a
    # resolved entity, whether or not ask_ai() was ever called this turn -- feed it into
    # the same suggested_actions builder as anything the LLM looked up via tool calls,
    # so e.g. "what's going on with VEH-00042" offers the same real dashboard links as
    # asking about it by name would.
    if entity_id:
        entity = repository.get_entity(entity_id)
        if entity:
            resolved_entities = resolved_entities + [{
                "id": entity.id,
                "entity_type": entity.entity_type,
                "attributes": entity.attributes,
            }]

    suggested_actions = build_suggested_actions(resolved_entities)

    response = {
        "response": response_text
    }

    if suggested_actions:

        response["suggested_actions"] = suggested_actions

    if report_suggestion:

        response["suggested_report"] = report_suggestion

    if dashboard_key:

        response["suggested_dashboard"] = dashboard_key

    if general_panel_key:

        response["suggested_panel"] = general_panel_key

    if asset_panel_key:

        response["suggested_asset_panel"] = asset_panel_key

    if campaign_panel_key:

        response["suggested_campaign_panel"] = campaign_panel_key

    if website_panel_key:

        response["suggested_website_panel"] = website_panel_key

    if deal_panel_key:

        response["suggested_deal_panel"] = deal_panel_key

    if intelligence_panel_key:

        response["suggested_intelligence_panel"] = intelligence_panel_key

    if bot_task_intent:

        response["suggested_bot_panel"] = "my_tasks"

    if employee_value_intent:

        response["suggested_employee_value"] = True

    if compliance_alert_intent:

        response["suggested_compliance_panel"] = True

    if network_panel_key:

        response["suggested_network_panel"] = network_panel_key

    if entity_id:

        response["suggested_profile"] = entity_id

    if admin_panel_key:

        response["suggested_admin_panel"] = admin_panel_key

    if reset_employee_id:

        response["suggested_reset_password"] = reset_employee_id

    return response
