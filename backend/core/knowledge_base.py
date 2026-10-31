"""
core/knowledge_base.py -- the role-gated, cross-dashboard knowledge base
(2026-07-13, session 38). Sam: "we need to include a knowledge base thats accessable
from each dash... obviously sections of it will be closed off to non admin/managers,
etc - so roles based - and there it needs to have Getting started guides, How to build
a deal, basically the how to use NXTDeal for each department and everything they can
use it for, and how to do it."

A KnowledgeArticle is an ordinary graph entity (same no-separate-store rule as every
other module in this codebase), seeded once with REAL, specific content describing
NXTDeal's actual built features (Sam's explicit scoping answer, session 38: "I author
real starter guides now" rather than placeholder stubs) -- every article below
references real buttons/pages/chat phrases that exist in this codebase today, not
aspirational ones. `visible_roles` on an article is the role gate: an empty list means
every authenticated role can see it; a populated list restricts it (e.g. admin/
operations-only guides for roster, compliance overrides, employee value). Content is
editable later like any other entity -- this module just seeds a real starting set,
it isn't the only way articles can ever be added.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import KNOWLEDGE_ARTICLE
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


CATEGORY_GETTING_STARTED = "getting_started"
CATEGORY_HOW_TO = "how_to"

# department -> the section a KnowledgeSidebar-style article list groups under. "all"
# means cross-department (e.g. the bot, the network, admin-only guides).
DEPARTMENTS = ["sales", "service", "finance", "marketing", "operations", "administration", "all"]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _article(key, title, department, category, body, visible_roles=None):
    return {
        "key": key,
        "title": title,
        "department": department,
        "category": category,
        "body": body,
        "visible_roles": visible_roles or [],
    }


# Real, specific starter content -- one Getting Started guide per department, plus
# How-To guides for every major feature built across sessions 30-38. `visible_roles`
# empty = every role; populated = only those roles (ADMIN always effectively has
# access via the same "ADMIN always passes" rule used everywhere else in this
# codebase, enforced in knowledge_base_api.py rather than repeated in every list here).
SEED_ARTICLES = [

    _article(
        "getting_started_sales", "Getting Started: Sales", "sales", CATEGORY_GETTING_STARTED,
        "NXTDeal is chat-first: everything you need shows up by asking, in the chat box "
        "at the bottom of /workspace, /admin, /readiness, or /network. As a sales role you "
        "can: ask \"sell a car\" or \"start a deal\" to open the Deal Desk (desk multiple "
        "pricing scenarios side by side, choose in-house or outside-lender financing); ask "
        "\"my deals\" to see deals you're working; ask \"my tasks\" or click the turquoise "
        "robot button next to Send to see what the agentic bot suggests for you today "
        "(overdue leads to follow up, deals stuck in financing, etc.); ask about a lead or "
        "customer by ID (e.g. \"pull up CUST-00042\") to see their full 360 profile. Every "
        "sale you fund runs through a real compliance check (Reg Z disclosure, identity "
        "completeness) before it's allowed to fund -- if it's blocked, the compliance "
        "alert tells you exactly what's missing.",
    ),

    _article(
        "getting_started_service", "Getting Started: Service", "service", CATEGORY_GETTING_STARTED,
        "As a service role, ask \"service dashboard\" or \"service overview\" for your "
        "department's numbers, or \"show service intelligence\" for real "
        "gross profit, average repair order, customer-pay %, and effective labor rate "
        "computed from actual ServiceRecord data (not estimates). Click the turquoise bot "
        "button for tasks like service records missing cost/labor data that need to be "
        "filled in so KPIs stay accurate. Ask about a customer or vehicle by ID to see "
        "their full service history in one profile.",
    ),

    _article(
        "getting_started_finance", "Getting Started: Finance", "finance", CATEGORY_HOW_TO,
        "As a finance/F&I role, you're one of the roles that can move a deal's financing "
        "forward in the Deal Desk (choose in-house/BHPH financing or submit to an outside "
        "lender, record approve/decline/counter decisions, generate the on-screen "
        "contract, and fund the deal). Ask \"finance dashboard\" or \"funding status\" for "
        "real funded-contract numbers, or \"show f&i intelligence\" for "
        "reserve income, income per contract, deals financed, and average APR. Every "
        "funded deal and every declined financing decision runs through a real compliance "
        "check (Reg Z disclosure on funding, ECOA adverse-action documentation on a "
        "decline) -- a decline without a documented reason is blocked until you add one.",
    ),

    _article(
        "getting_started_marketing", "Getting Started: Marketing", "marketing", CATEGORY_GETTING_STARTED,
        "As a marketing role, ask \"create a flyer\" or \"design a flyer\" to open the "
        "asset design workflow (inventory flyers, social posts, sold announcements, "
        "service specials, finance offers -- template-fill, no freeform canvas), and "
        "\"pending approvals\" to review assets other roles have submitted (marketing and "
        "admin approve). Ask \"run a campaign\" or name a campaign type (\"retention "
        "campaign\", \"inventory ads\", \"finance renewal\", \"accessory accelerator\") to "
        "build a real, audience-segmented campaign, then \"pending campaigns\" to activate "
        "one. Ask \"build a website\" for the website/inventory builder. Every asset "
        "approval, campaign activation, and website publish runs through a real "
        "compliance check (advertising disclosure on rate/APR mentions, CAN-SPAM/TCPA "
        "consent on campaign audiences) before it goes live.",
    ),

    _article(
        "getting_started_operations", "Getting Started: Operations", "operations", CATEGORY_GETTING_STARTED,
        "Operations has the broadest access in NXTDeal -- the same tier as Admin on "
        "almost every feature. Ask \"executive dashboard\" for the cross-department "
        "rollup, \"show department intelligence\" for every department's KPIs, \"show my tasks\" for the "
        "operations-tier bot suggestions, and use the Readiness page to connect data "
        "sources (CSV upload or API connection) department by department. You can also "
        "review compliance alerts (\"compliance alerts\"), see employee value/"
        "effectiveness (\"employee value\"), and open the network benchmark/audit.",
    ),

    _article(
        "getting_started_administration", "Getting Started: Administration", "administration", CATEGORY_GETTING_STARTED,
        "As an admin, you have every feature above plus admin-only views: \"employee "
        "roster\" (who has a login and what role), \"audit log\" (a full who-did-what "
        "trail), \"bot coverage\" (run the bot as an absent employee for a set window), "
        "and \"reset password for EMP-00003\" (generates a new temp password, requires "
        "explicit confirmation). Admin is also the only role that can override a "
        "compliance block (bypass with a documented, audited reason) rather than just "
        "resolving one once it's actually fixed.",
    ),

    _article(
        "how_to_build_a_deal", "How To: Build a Deal", "sales", CATEGORY_HOW_TO,
        "1) Ask \"start a deal\" or \"sell a car\" in chat. 2) Pick a customer and vehicle "
        "to create the deal (desking stage). 3) Add one or more pricing scenarios "
        "side-by-side (sale price, down payment, term) -- NXTDeal estimates an APR from "
        "the customer's credit score and computes the monthly payment for each. 4) Select "
        "the scenario you want to move forward with. 5) Choose financing: in-house/BHPH "
        "(self-approved instantly) or submit to an outside lender (approve/decline/"
        "counter). 6) Once financing is approved, generate the on-screen contract. 7) "
        "Fund the deal -- this is the point a real compliance check runs (contract "
        "disclosures, customer identity completeness); if it's blocked, fix the flagged "
        "issue and try again. Funding creates a real FinanceContract and marks the "
        "vehicle sold, identical in shape to historically-imported data.",
    ),

    _article(
        "how_to_run_a_campaign", "How To: Run a Marketing Campaign", "marketing", CATEGORY_HOW_TO,
        "1) Ask for a campaign type by name (\"retention campaign\", \"inventory ads\", "
        "\"finance renewal\", \"accessory accelerator\", or \"general announcement\"). 2) "
        "Fill in the audience parameters (e.g. months since last service) -- NXTDeal "
        "builds a real, live audience from the graph and shows you a preview with a "
        "sample of who's included. 3) Optionally link an approved marketing asset. 4) "
        "Marketing or admin activates the campaign (\"pending campaigns\") -- this is "
        "where the CAN-SPAM/TCPA compliance check runs against the audience, and where a "
        "linked asset must already be approved. Activating simulates the send and stamps "
        "a sent count from the audience snapshot.",
    ),

    _article(
        "how_to_design_an_asset", "How To: Design and Approve a Marketing Asset", "marketing", CATEGORY_HOW_TO,
        "1) Ask \"create a flyer\" or name a template (inventory flyer, social post, sold "
        "announcement, service special, finance offer). 2) Fill in the template's fields "
        "and submit it for approval. 3) Marketing or admin reviews it via \"pending "
        "approvals\" and approves or rejects with notes. Approval is where the "
        "advertising-disclosure compliance check runs -- if the asset mentions a rate or "
        "percentage, it needs a disclaimer filled in or it will be blocked.",
    ),

    _article(
        "how_to_build_a_website", "How To: Build the Dealership Website", "marketing", CATEGORY_HOW_TO,
        "1) Ask \"build a website\" to start a draft with a fixed four-page structure "
        "(Home/Inventory/About/Contact). 2) Add sections to each page from the fixed "
        "template catalog (hero banner, text block, image gallery, inventory grid, "
        "contact info) -- every image is a URL you supply, there's no AI image "
        "generation. The Inventory page's grid is always live, pulled from real current "
        "inventory, not a stored copy. 3) Submit for approval; marketing or admin "
        "publishes it. Publishing runs the same advertising-disclosure compliance check "
        "as assets -- a page mentioning a rate/APR needs a disclaimer text block on the "
        "same page.",
    ),

    _article(
        "how_to_read_department_intelligence", "How To: Read Department Intelligence", "all", CATEGORY_HOW_TO,
        "Ask \"show department intelligence\" (or name a department -- sales, service, parts, F&I) for "
        "real KPI dashboards computed from the graph: gross profit, units sold, average "
        "repair order, inventory turns, reserve income, and more, each with a day-over-day "
        "trend where enough history exists. The Executive Overview rolls every "
        "department's gross profit into one number and calls out recoverable profit "
        "(like obsolete parts inventory) as an explicit alert. Visible to Admin, "
        "Operations, and Finance.",
    ),

    _article(
        "how_to_use_the_bot", "How To: Use the Agentic Bot", "all", CATEGORY_HOW_TO,
        "The square turquoise robot button next to Send shows tasks tailored to your "
        "role, department/section, and seniority tier (staff/manager/executive, inferred "
        "from your title) -- real gap-checks against the graph, like overdue leads or "
        "deals stuck in financing, not generic reminders. Click \"Run it in chat\" to load "
        "a task's prompt straight into chat, or dismiss it if it's not relevant (dismiss "
        "the same task three times and it stops resurfacing). Admins can additionally "
        "activate \"coverage\" -- running the bot as a specific absent employee for a set "
        "window, either as draft suggestions or fully automatic for a narrow, whitelisted "
        "set of safe actions.",
    ),

    _article(
        "how_to_read_readiness", "How To: Read Readiness & Connect Data", "all", CATEGORY_HOW_TO,
        "The Readiness page shows, for every department, a percentage-certainty "
        "prediction for tomorrow/this week/this month/this quarter -- blended from real "
        "ledger history where it exists and clearly-labeled industry estimates where it "
        "doesn't. A department is \"ready to go live\" once its tomorrow-horizon "
        "confidence clears 90%. Admin and Operations can also connect real data sources "
        "here: upload a CSV (reuses the same importers as the seed pipeline) or configure "
        "an API connection and test it -- each real data point you add raises that "
        "department's confidence, so you don't have to fully deploy everything at once.",
        visible_roles=[],
    ),

    _article(
        "how_to_review_compliance", "How To: Review Compliance Alerts", "administration", CATEGORY_HOW_TO,
        "Every deal funding, campaign activation, asset/website publish, and data "
        "connection is checked against a real starting set of federal compliance rules "
        "(Truth in Lending/Reg Z, ECOA/Reg B, FACTA Red Flags, CAN-SPAM/TCPA, GLBA "
        "Safeguards, Reg Z advertising) before it's allowed to proceed -- a failure blocks "
        "the action and creates a compliance alert, notifying Admin/Operations and any "
        "manager/executive-tier employee by direct message. Ask \"compliance alerts\" to "
        "see the open list. Mark one Resolved once the underlying issue is actually "
        "fixed, or (Admin only) Override it with a documented reason if you're "
        "consciously choosing to proceed anyway -- an override is fully audited, never "
        "silent. This ruleset is a starting compliance framework covering a small set of "
        "well-known federal rules -- not exhaustive, not a substitute for your own "
        "compliance officer or attorney.",
        visible_roles=[ADMIN, OPERATIONS],
    ),

    _article(
        "how_to_use_the_network", "How To: Use the Network Benchmark & Audit", "all", CATEGORY_HOW_TO,
        "The Network page benchmarks each department's real KPIs against a blind-labeled "
        "peer set (Dealer B/C/D/E) and shows a percentile rank, plus an AI-driven "
        "self-audit that ties together low-percentile departments, real profit leaks "
        "(like obsolete parts inventory), automation opportunities from employee/bot "
        "data, and department prediction confidence -- every recommendation is derived "
        "from a real number, not a fabricated narrative. Peer data is currently SIMULATED "
        "(clearly labeled) since no second real NXTDeal dealer is connected yet -- it "
        "activates with real data the moment one joins. Visible to Admin, Operations, and "
        "Finance.",
        visible_roles=[ADMIN, OPERATIONS, FINANCE],
    ),

    _article(
        "how_to_review_employee_value", "How To: Review Employee Value & Effectiveness", "administration", CATEGORY_HOW_TO,
        "Ask \"employee value\" for a per-employee $ estimate of what they're bringing in "
        "or affecting, blended from real ledger attribution (sales via funded deals' "
        "gross profit, service via labor gross profit) where it exists, and honestly "
        "labeled industry estimates where a real attribution path doesn't exist yet "
        "(finance, marketing, operations, administration). This also shows automation "
        "coverage -- what fraction of an employee's recurring flagged tasks the bot could "
        "already handle. This is explicitly a decision-support figure for reassigning "
        "duties to where people are most effective, not a tool for reducing headcount.",
        visible_roles=[ADMIN, OPERATIONS],
    ),

    _article(
        "how_to_use_admin_roster_audit", "How To: Employee Roster & Audit Log", "administration", CATEGORY_HOW_TO,
        "Ask \"employee roster\" for who has a login and what role they're assigned, or "
        "\"audit log\" for a full who-did-what trail across the whole system (asset "
        "approvals, campaign activations, deal funding, compliance overrides, and more). "
        "Ask \"reset password for EMP-00003\" to start a password reset -- this only ever "
        "shows a confirmation card in the workspace panel; nothing changes until you "
        "explicitly confirm it.",
        visible_roles=[ADMIN],
    ),
]


def seed_articles():
    """Idempotent, same convention as core/messaging.py's seed_channels() -- creates
    every SEED_ARTICLES entry once if it doesn't already exist (by its stable `key`),
    and never overwrites an already-loaded (possibly edited) article. Called at API
    startup."""

    for article in SEED_ARTICLES:

        article_id = f"KB-{article['key']}"

        if ledger.get_entity(article_id):
            continue

        ledger.add_entity(Entity(
            id=article_id,
            entity_type=KNOWLEDGE_ARTICLE,
            attributes={
                "key": article["key"],
                "title": article["title"],
                "department": article["department"],
                "category": article["category"],
                "body": article["body"],
                "visible_roles": article["visible_roles"],
                "created_at": _now(),
                "updated_at": _now(),
            },
        ))


def _all_articles():
    return [e for e in ledger.get_all().values() if e.entity_type == KNOWLEDGE_ARTICLE]


def _visible_to(article, role):
    visible_roles = article.attributes.get("visible_roles") or []

    return not visible_roles or role == ADMIN or role in visible_roles


def list_articles(role, department=None, category=None):

    articles = [a for a in _all_articles() if _visible_to(a, role)]

    if department:
        articles = [a for a in articles if a.attributes.get("department") in (department, "all")]

    if category:
        articles = [a for a in articles if a.attributes.get("category") == category]

    articles.sort(key=lambda a: (a.attributes.get("department", ""), a.attributes.get("title", "")))

    return articles


def get_article(article_id, role):

    article = ledger.get_entity(article_id)

    if not article or article.entity_type != KNOWLEDGE_ARTICLE:
        return None

    if not _visible_to(article, role):
        return None

    return article
