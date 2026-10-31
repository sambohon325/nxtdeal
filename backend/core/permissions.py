from core.entity_types import (
    VEHICLE,
    CUSTOMER,
    LEAD,
    FINANCE_CONTRACT,
    LENDER,
    SERVICE_RECORD,
    DOCUMENT,
    IMAGE,
    ASSET,
    CAMPAIGN,
    WEBSITE,
    DEAL,
    PART,
    PART_SALE,
    DEPARTMENT_SNAPSHOT,
    BOT_COVERAGE,
    BOT_TASK_EVENT,
    CONNECTION,
    EMPLOYEE_VALUE_SNAPSHOT,
    COMPLIANCE_ALERT,
    NETWORK_PEER_SNAPSHOT,
    KNOWLEDGE_ARTICLE,
    EMAIL_TEMPLATE,
    MARKETING_LIST,
    SOCIAL_POST,
    AD_CAMPAIGN,
    TRIGGER_ALERT,
    EVENT,
    EVENT_RSVP,
    EVENT_TASK,
    PERSONAL_SITE,
    WEBSITE_CHAT_SESSION,
    WEBSITE_CHAT_MESSAGE,
    WEBSITE_ANALYTICS_EVENT
)

ADMIN = "ADMIN"

OPERATIONS = "OPERATIONS"

SALES = "SALES"

MARKETING = "MARKETING"

SERVICE = "SERVICE"

FINANCE = "FINANCE"

# BDC (Business Development Center) -- the phone/appointment-setting team (Bumper parity,
# 2026-07-25). Historically BDC reps carried the SALES role (see core/bdc.py); this makes
# BDC a first-class role so a dealer can staff a dedicated BDC and scope their view to the
# lead-followup surface without handing them the full sales desk.
BDC = "BDC"


ENTITY_ACCESS = {

    VEHICLE: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    CUSTOMER: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    LEAD: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        BDC
    ],

    FINANCE_CONTRACT: [
        ADMIN,
        OPERATIONS,
        FINANCE
    ],

    LENDER: [
        ADMIN,
        OPERATIONS,
        FINANCE
    ],

    SERVICE_RECORD: [
        ADMIN,
        OPERATIONS,
        SERVICE
    ],

    DOCUMENT: [
        ADMIN,
        OPERATIONS,
        SALES,
        SERVICE,
        FINANCE
    ],

    IMAGE: [
        ADMIN,
        OPERATIONS,
        SALES,
        SERVICE,
        MARKETING
    ],

    # Marketing assets aren't confidential internally (unlike finance contracts) --
    # every role can see one, same visibility tier as VEHICLE. Who can CREATE/APPROVE
    # one is a separate, narrower check in core/assets_api.py (any role can request;
    # only MARKETING/ADMIN can approve/reject), not this general read-access list.
    ASSET: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    # Campaign & customer-lifecycle engine (session 31) -- same broad internal
    # visibility as ASSET/VEHICLE: retention campaigns are service-flavored, finance
    # renewal campaigns are finance-flavored, inventory ads/accessory accelerator are
    # sales-flavored, so every department can see the campaign list. Who can CREATE one
    # (any role) vs ACTIVATE one (MARKETING/ADMIN only, mirrors asset approval) is a
    # narrower check in core/campaigns_api.py, not this general read-access list.
    CAMPAIGN: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    # Website/inventory builder (session 32) -- same broad internal visibility as
    # ASSET/CAMPAIGN: a dealership's public site touches sales (inventory page) and
    # marketing (everything else), and there's nothing confidential about a public-
    # facing page. Who can build/submit (any role) vs approve/publish (MARKETING/
    # ADMIN) is a narrower check in core/websites_api.py, not this general read list.
    WEBSITE: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    # Email/SMS builder (session 79) -- same broad internal visibility as CAMPAIGN/
    # WEBSITE: nothing confidential about a marketing message's draft content, and
    # every department can be the one that needs to send an individual follow-up.
    # Who can create/edit their own template (any role, or ADMIN) vs. someone else's
    # is a narrower ownership check in core/email_templates_api.py, not this general
    # read-access list.
    EMAIL_TEMPLATE: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    # Marketing Lists (session 82) -- same broad internal visibility as CAMPAIGN/
    # EMAIL_TEMPLATE, deliberately including SALES: Sam explicitly asked for list
    # curation/browsing to appear on the Sales side too, not just Marketing. Who can
    # create/curate membership (creator, or MARKETING/ADMIN) vs. who can browse is a
    # narrower ownership check in core/marketing_lists_api.py, not this general
    # read-access list.
    MARKETING_LIST: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    # Social / Reputation + Advertising (session 83) -- same broad-visibility rule as
    # ASSET/CAMPAIGN/WEBSITE: any role can see what's posted/running, creation is ACL'd
    # in core/social_posts_api.py/core/advertising_api.py instead (mirrors the asset/
    # campaign/website workflow's "any role creates, MARKETING/ADMIN approves" split).
    SOCIAL_POST: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    AD_CAMPAIGN: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    # Events dash (session 84) -- TriggerAlert/Event/EventRSVP are all broadly
    # readable (same rule as SOCIAL_POST/AD_CAMPAIGN above) since the whole point is
    # a Marketing<->Sales handoff -- SALES specifically needs to see and act on these
    # (promote/dismiss an alert, work an event's RSVP list), not just MARKETING/ADMIN.
    # Fine-grained "who can promote/publish" stays in core/trigger_alerts_api.py/
    # core/dealership_events_api.py, same split as every other workflow entity here.
    TRIGGER_ALERT: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    EVENT: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    EVENT_RSVP: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    # Event Project Management (2026-07-18) -- same broad-visibility rule as EVENT
    # itself; mutation gated in core/event_planning_api.py.
    EVENT_TASK: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    # Website Builder overhaul (session 85) -- same broad-visibility rule as
    # WEBSITE itself: any role can see personal sites/chat sessions/analytics,
    # creation/action is ACL'd in core/personal_sites_api.py/core/website_chat_api.py
    # instead (mirrors the asset/campaign/website "any role creates, MARKETING/ADMIN
    # approves" split, with SALES also able to act on its own personal site + chat
    # leads, same reasoning as the Events dash above).
    PERSONAL_SITE: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    WEBSITE_CHAT_SESSION: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    WEBSITE_CHAT_MESSAGE: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    WEBSITE_ANALYTICS_EVENT: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    # DMS Deal Desk (session 33) -- narrower than ASSET/CAMPAIGN/WEBSITE on purpose:
    # a Deal touches real pricing, financing terms, and eventually a real
    # FinanceContract, so it's scoped to the same roles as FINANCE_CONTRACT plus SALES
    # (who actually desks/sells the car) -- MARKETING and SERVICE have no reason to see
    # deal-in-progress pricing/financing detail. Who can desk (SALES too) vs who can
    # move financing/contract/funding forward (FINANCE-gated, money-sensitive) is a
    # narrower split enforced in core/deals_api.py, not this general read list.
    DEAL: [
        ADMIN,
        OPERATIONS,
        SALES,
        FINANCE
    ],

    # Parts inventory/sales (Department Intelligence, session 35) -- same broad internal
    # visibility as VEHICLE/ASSET: nothing confidential about parts stock or sales
    # lines. Who can see the Department Intelligence *dashboard* built on top of this
    # data is a narrower check (ADMIN/OPERATIONS/FINANCE only, see DEPT_INTEL_ROLES in
    # core/department_intelligence_api.py) --
    # this list is just general entity-read visibility, same distinction ASSET/
    # CAMPAIGN/WEBSITE already draw between "who can see the entity" and "who can see
    # the aggregate view built from it."
    PART: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    PART_SALE: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    # A DepartmentSnapshot is an internal KPI record, not dealership operational data --
    # scoped to exactly the roles who can open the Department Intelligence dashboard
    # itself (Sam's access decision, session 35), not the broader ENTITY_ACCESS tiers
    # above.
    DEPARTMENT_SNAPSHOT: [
        ADMIN,
        OPERATIONS,
        FINANCE
    ],

    # Agentic bot layer (session 36) -- a BotCoverage is who's-covering-for-whom, an
    # admin-only operational concern, same tier as the audit log (ADMIN-only
    # DASHBOARD_ACCESS entry below), not general dealership data. BotTaskEvent is
    # internal bot telemetry (did an employee act on or dismiss a suggestion) -- visible
    # to ADMIN/OPERATIONS for the same "GM-level oversight of the whole store" reasoning
    # DEPARTMENT_SNAPSHOT already uses, narrower than DEPARTMENT_SNAPSHOT since FINANCE
    # has no reason to see another department's bot-dismissal history.
    BOT_COVERAGE: [
        ADMIN
    ],

    BOT_TASK_EVENT: [
        ADMIN,
        OPERATIONS
    ],

    # Integration platform (session 37) -- who configured which data source is an
    # admin-level operational concern, same tier as BotCoverage above.
    CONNECTION: [
        ADMIN,
        OPERATIONS
    ],

    # Employee $ value/effectiveness is compensation-adjacent (Sam's explicit scoping
    # answer, session 37: ADMIN + OPERATIONS only -- not visible to a department
    # manager, unlike the leaderboard/workload dashboards).
    EMPLOYEE_VALUE_SNAPSHOT: [
        ADMIN,
        OPERATIONS
    ],

    # Compliance agent (session 38) -- same GM-level-oversight tier as BOT_TASK_EVENT.
    # Note this is the general entity-read list; a manager or the employee whose action
    # triggered a specific alert is additionally notified directly via
    # core/messaging.py regardless of this list, same "read access vs. who gets
    # notified" distinction ASSET/CAMPAIGN/WEBSITE already draw for approval routing.
    COMPLIANCE_ALERT: [
        ADMIN,
        OPERATIONS
    ],

    # Network intelligence layer (session 38) -- reuses Department Intelligence's exact
    # ACL tier (ADMIN/OPERATIONS/FINANCE) since it's built directly on top of the same
    # cross-department profit/margin data, just benchmarked against (simulated) peers.
    NETWORK_PEER_SNAPSHOT: [
        ADMIN,
        OPERATIONS,
        FINANCE
    ],

    # Knowledge base (session 38) -- broad structural read access, same tier as
    # VEHICLE/ASSET (every role can ask "how do I use NXTDeal"); which SPECIFIC
    # articles a role sees is a narrower per-article filter in
    # core/knowledge_base_api.py (an article's own `visible_roles` list), not this
    # general list -- same "general read access vs. narrower per-item gate" split
    # ASSET/CAMPAIGN/WEBSITE already draw between read access and approve access.
    KNOWLEDGE_ARTICLE: [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ]
}


# Per-department dashboard ACL (Phase 9 follow-up, added 2026-07-13). No department
# actually told us their access matrix — these are Sam-approved assumptions based on
# typical dealership role responsibilities, deliberately kept consistent with the
# ENTITY_ACCESS precedent above rather than invented from scratch: each dashboard's role
# list mirrors the ENTITY_ACCESS list for the entity type that dashboard is really about.
# ADMIN and OPERATIONS appear in every entry, matching ENTITY_ACCESS (dealer
# principal/GM-level oversight of the whole store). Revisit any of these with Sam if they
# turn out wrong in practice — this is a reasonable starting point, not a spec.
DASHBOARD_ACCESS = {

    # Aggregate counts across leads/customers/vehicles/finance — mirrors LEAD access
    # (sales works these, marketing generates/nurtures them).
    "sales": [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING
    ],

    # Mirrors SERVICE_RECORD access.
    "service": [
        ADMIN,
        OPERATIONS,
        SERVICE
    ],

    # Mirrors FINANCE_CONTRACT/LENDER access — F&I-specific.
    "finance": [
        ADMIN,
        OPERATIONS,
        FINANCE
    ],

    # Whole-company rollup touching every entity type — only the two roles present in
    # every ENTITY_ACCESS list get it, same reasoning as the rollup itself.
    "executive": [
        ADMIN,
        OPERATIONS
    ],

    # Lead/pipeline funnel — sales works the funnel, marketing feeds and cares about it,
    # BDC sets the appointments that move leads through it.
    "pipeline": [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        BDC
    ],

    "followup": [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        BDC
    ],

    # Sales team/rep performance management — marketing doesn't manage sales reps, so
    # excluded here even though it's lead-adjacent (unlike pipeline/followup above).
    "salesperson": [
        ADMIN,
        OPERATIONS,
        SALES
    ],

    "manager": [
        ADMIN,
        OPERATIONS,
        SALES
    ],

    "leaderboard": [
        ADMIN,
        OPERATIONS,
        SALES
    ],

    "workload": [
        ADMIN,
        OPERATIONS,
        SALES
    ],

    "velocity": [
        ADMIN,
        OPERATIONS,
        SALES
    ],

    # Escalated/stalled leads needing management action — same tier as the
    # rep-performance dashboards above, not marketing's job to act on.
    "escalations": [
        ADMIN,
        OPERATIONS,
        SALES
    ],

    # Who-did-what audit log — stays ADMIN-only, already enforced separately in
    # api/app.py via _require_admin (listed here too for completeness/documentation).
    "audit": [
        ADMIN
    ],

    # Customer Journey Engine (2026-07-22, slice 1) — the cross-department
    # lifecycle stage view (Awareness -> Lead -> Appointment -> Sale -> Service
    # -> Loyalty -> Repeat). Journey state lives on the existing CUSTOMER entity
    # (core/customer_journey.py), which already grants all six roles read access
    # in ENTITY_ACCESS above, so this dashboard mirrors that same broad tier —
    # every real role can see and act on a customer's journey (the same
    # VIEW_ROLES tuple core/customer_journey_api.py enforces). Marketing owns
    # Awareness/Lead, Sales owns Appointment/Sale, Service owns Service, and
    # everyone shares Loyalty/Repeat.
    "customer_journey": [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE,
        FINANCE
    ],

    # Newly-built modules (2026-07-23 integration pass).
    # Accessories (Sales dept) — accessories upsell desk.
    "accessories": [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING
    ],

    # Equity Center (Sales dept) — equity/upgrade offers.
    "equity_center": [
        ADMIN,
        OPERATIONS,
        SALES,
        FINANCE
    ],

    # Inventory Advertising (Marketing dept).
    "inventory_advertising": [
        ADMIN,
        OPERATIONS,
        MARKETING
    ],

    # Loyalty (Marketing dept) — no AI feature.
    "loyalty": [
        ADMIN,
        OPERATIONS,
        SALES,
        MARKETING,
        SERVICE
    ],

    # Success Center (NXTDeal-internal, Administration) — portfolio-wide.
    "success_center": [
        ADMIN,
        OPERATIONS
    ],

    # AI Consulting Engine (Network dept, 2026-07-23) — executive/manager-level
    # strategic consulting that composes whole-store, cross-department analysis
    # (peer benchmarks, dollar-opportunity sizing, Executive Recommendations),
    # scoped to the same executive tier NETWORK_ROLES already uses.
    "consulting_engine": [
        ADMIN,
        OPERATIONS
    ],

    # BDC dashboard (Bumper parity, 2026-07-25) — the speed-to-lead / untouched-queue /
    # appointment-setting surface (core/bdc.py). Scoped to the BDC team plus the roles
    # that already supervise it (SALES historically carried the BDC function). This is
    # the "role-scoped view" the new BDC role lands on at login.
    "bdc": [
        ADMIN,
        OPERATIONS,
        SALES,
        BDC
    ]
}
