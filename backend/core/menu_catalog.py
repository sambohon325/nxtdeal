"""
core/menu_catalog.py -- the "Top Menu" navigation layer (session 60), sitting between
the department color bar and the existing 4 Workflow Buttons (core/workflow_catalog.py).

Sam: "i want to create a menu under the color bar for each dash / page... lets move
everything down a little from the bottom of the color bar, well put a title over the 4
buttons and call that 'workflow' (like workspace)." Baked from a batch of 9 attached
PDFs (operations.pdf/sales.pdf/service.pdf/admin.pdf/finance.pdf/inventory.pdf/
marketing.pdf/network.pdf/readiness.pdf, one per department), each describing the same
structure: "Menu Bar = quick-access navigation like a traditional CRM/DMS" (Overview |
... | Reporting, always 8 items, always starting with Overview and ending with
Reporting) as a DISTINCT layer from the 4 job-workflow buttons underneath it -- "Top
Menu = Navigation & Fast Access (DMS style). 4 Buttons = Operational Workflows
(NXTDeal style)."

Same one-catalog/one-engine pattern as core/workflow_catalog.py (and
core/bot_tasks.py's TASK_CATALOG, core/compliance_rules.py's RULES before it) -- not 9
bespoke modules. Each department maps to a fixed list of {key, label, description}
dicts; core/operations_menu.py (+ core/sales_menu.py, core/service_menu.py etc.)
supplies the fetch function for each item's real data, wired together generically in
core/menu_data.py's MENU_SOURCES the same way core/workflow_tab_data.py's REAL_SOURCES
wires workflow tabs.

Scoped the first pass (Sam, when asked how deep to go given the size -- 9 departments x
8 items = 72 screens: "Operations first, fully realized") to Operations only; Sam's
direct follow-up ("lets move to sales") extended this to Sales the same session, and the
scheduled builder rolled it out to Service & Parts next (session 61, autonomous).
Marketing followed in session 62 (a new interactive session) after Sam uploaded an
updated spec, marketing2.pdf, replacing the original marketing.pdf -- see
core/marketing_menu.py's module docstring for what
changed (Content/Analytics dropped as standalone items, Events/Opportunities added,
framed as a Revenue Operations department rather than a narrow marketing-manager page).
Inventory followed in session 63 ("lets move onto inventory") -- see
core/inventory_menu.py's module docstring. Finance followed in session 64 ("lets move
to finance") -- see core/finance_menu.py's module docstring; it turned out to have the
deepest structural gaps of any department rolled out so far (no Commission entity, no
general-ledger/posting concept, no OFAC/IRS-8300 compliance rule). Administration
followed in session 65 ("lets move to Administration") -- see
core/administration_menu.py's module docstring; unlike every production department,
Admin isn't organized around customers/vehicles/deals at all -- it's the control layer
above the dealership (users, security, systems, integrations, vendors, governance).
Readiness followed in session 66 ("lets move to Readiness") -- see
core/readiness_menu.py's module docstring; unlike every other department, Readiness
doesn't manage work at all -- it measures whether the dealership is CAPABLE of
executing the work tomorrow/next week/next month/next quarter, leaning on
core/prediction.py's and core/network_audit.py's already-built engines more than any
department before it. Network followed in session 67 ("lets build the network") --
see core/network_menu.py's module docstring; the ninth and final department, closing
out this rollout across all of NXTDeal. Network isn't managing your dealership at
all -- it's managing your dealership's relationship to every other dealership in the
network, reusing core/network_benchmark.py/core/network_audit.py/
core/kpi_snapshots.py more heavily than any department before it. All 9
departments are now catalogued -- extending further would mean deepening an existing
department's real data coverage, not adding a new one.
"""

MENU_CATALOG = {

    "Operations": [
        {
            "key": "overview",
            "label": "Overview",
            "description": (
                "The Operations home screen -- units in recon, aging inventory, "
                "compliance exceptions, cross-department bottlenecks, and today's "
                "delivery-ready deals at a glance."
            ),
        },
        {
            "key": "tasks",
            "label": "Tasks",
            "description": (
                "Universal task queue for Operations -- derived from real actionable "
                "gaps on the graph (wholesale disposition candidates, lot-audit "
                "discrepancies, unresolved compliance exceptions, open escalations, "
                "pending cross-department approvals)."
            ),
        },
        {
            "key": "vehicles",
            "label": "Vehicles",
            "description": (
                "Vehicle-centric search -- search any VIN or stock number and get its "
                "full record plus everything one hop away on the graph (deal, "
                "customer, finance contract, service history)."
            ),
        },
        {
            "key": "inventory",
            "label": "Inventory",
            "description": (
                "Inventory command center -- active/aging/incoming inventory, "
                "wholesale candidates, and the pricing queue."
            ),
        },
        {
            "key": "scheduling",
            "label": "Scheduling",
            "description": (
                "Operations coordination -- the recon board, transport schedule, "
                "delivery calendar, and cross-department capacity."
            ),
        },
        {
            "key": "documents",
            "label": "Documents",
            "description": (
                "Centralized document vault -- deal jackets, titles, recon forms, "
                "inspection reports, buyer orders, and compliance files, searchable "
                "by the vehicle/deal/customer they're attached to."
            ),
        },
        {
            "key": "alerts",
            "label": "Alerts",
            "description": (
                "Exception management -- compliance violations, lot-audit "
                "discrepancies, and unfunded deals, severity-ranked."
            ),
        },
        {
            "key": "communications",
            "label": "Communications",
            "description": (
                "Composes TWO real, distinct views: (1) the pre-existing Unified "
                "Communications Hub -- a real, company-wide, filterable feed of "
                "every logged customer-facing touch across Sales' Communication "
                "Hub, Service's RO Communication Center, and Finance's "
                "Collections contact log; and (2) the newer Communications Hub "
                "engine -- real Phone/Text/Email/Chat/Social logging, "
                "honestly-simulated call recording/transcript/sentiment, real "
                "embedded follow-up tasks, and a real AI-generated call/message "
                "summary (isolated OpenAI call with a deterministic fallback)."
            ),
        },
        {
            "key": "customer_journey",
            "label": "Customer Journey",
            "description": (
                "The Customer Journey Engine -- every customer's real lifecycle "
                "stage (Awareness -> Lead -> Appointment -> Sale -> Service -> "
                "Loyalty -> Repeat), tracked graph-natively on the Customer "
                "entity: per-stage counts, a visual journey designer, and an "
                "AI next-best-action recommendation (isolated OpenAI call with "
                "a deterministic fallback)."
            ),
        },
        {
            "key": "workforce",
            "label": "Workforce",
            "description": (
                "Staff Directory with real seniority tiers, real Shift "
                "Scheduling and Time-Off Requests (a real manager-tier "
                "approval gate), a computed-live Coverage view flagging "
                "shift/approved-time-off conflicts for any date, and a "
                "Workforce Performance panel reusing the real lead-workload "
                "and employee $ effectiveness engines."
            ),
        },
        {
            "key": "workflows",
            "label": "Workflows",
            "description": (
                "The real Operations Workflow Engine (v2) -- ~21 trackable "
                "workflow instances across Vehicle, Compliance, Operational, "
                "and Employee categories, each a real numbered Step "
                "Progression (not a tab bar) with Tasks/Evidence/Approvals/"
                "Comments per step, live blocked/waiting-approval/escalated "
                "state, and SLA-stall detection. This is the pilot for "
                "NXTDeal's eventual Workflow -> Step -> Task -> Approval -> "
                "Automation -> Completion standard -- see "
                "core/workflow_engine_v2.py's module docstring."
            ),
        },
        {
            "key": "payroll",
            "label": "Payroll",
            "description": (
                "Payroll processing (competitive roadmap Phase 5) -- a self-service "
                "time clock, per-employee pay plans (hourly/salary/commission), "
                "deal-commission attribution from funded deals, and payroll runs that "
                "generate real paychecks with simplified gross-to-net withholding."
            ),
        },
        {
            "key": "reporting",
            "label": "Reporting",
            "description": (
                "Department-specific reporting -- operational, inventory, "
                "compliance, and personnel performance rollups."
            ),
        },
    ],

    "Sales": [
        {
            "key": "overview",
            "label": "Overview",
            "description": (
                "The Sales command center -- active opportunities, leads awaiting "
                "response, deliveries scheduled, F&I pending, and funded-deal gross "
                "profit at a glance."
            ),
        },
        {
            "key": "prospects",
            "label": "Prospects",
            "description": (
                "CRM-style lead center -- real leads bucketed by source (internet, "
                "phone, walk-in, referral), lost opportunities, unsold showroom "
                "traffic, and equity-mining candidates."
            ),
        },
        {
            "key": "customers",
            "label": "Customers",
            "description": (
                "Customer-centric search -- search by name/email/phone/VIN and get "
                "the full record plus everything one hop away on the graph (deals, "
                "finance contracts, service history)."
            ),
        },
        {
            "key": "deals",
            "label": "Deals",
            "description": (
                "The deal desk shortcut -- working deals, pending delivery, deals "
                "awaiting credit approval, and delivered deals."
            ),
        },
        {
            "key": "appointments",
            "label": "Appointments",
            "description": (
                "Sales calendar and showroom traffic center -- delivery schedule and "
                "real showroom-visit activity from the lead pipeline."
            ),
        },
        {
            "key": "inventory",
            "label": "Inventory",
            "description": (
                "A sales-facing inventory browser -- available/incoming/recently-sold "
                "units, text search, and payment-based search."
            ),
        },
        {
            "key": "communications",
            "label": "Communications",
            "description": (
                "The unified communication hub -- the real follow-up cadence queue "
                "and marketing-compliance (CAN-SPAM/TCPA) alerts."
            ),
        },
        {
            "key": "workflows",
            "label": "Workflows",
            "description": (
                "The real Sales Workflow Engine (v2) -- 18 trackable workflow "
                "instances across Prospecting, Engagement, Deals, Finance, and "
                "Retention categories (Lead Management, BDC Workflow, Up System, "
                "Orphan Owner Mining, Appointment Workflow, Showroom Workflow, "
                "Demo Drive, Trade Appraisal, Desking, Credit Application, "
                "Manager TO, F&I Handoff, F&I Workflow, eSignature, Delivery "
                "Experience, Equity Mining, Lease Maturity, Lost Sale Recovery), "
                "each a real numbered Step Progression (not a tab bar) with "
                "Tasks/Evidence/Approvals/Comments per step, live blocked/"
                "waiting-approval/escalated state, and SLA-stall detection -- "
                "the same core/workflow_engine_v2.py engine Operations' own "
                "pilot uses, now serving a second department."
            ),
        },
        {
            "key": "accessories",
            "label": "Accessories",
            "description": (
                "The Accessories upsell desk -- per-customer accessory interest, "
                "packages, and an AI-generated accessory pitch (isolated OpenAI "
                "call with a deterministic fallback)."
            ),
        },
        {
            "key": "equity_center",
            "label": "Equity Center",
            "description": (
                "The Equity Center -- each customer's loan/equity position and "
                "eligible upgrade inventory, with an AI-generated upgrade offer "
                "(isolated OpenAI call with a deterministic fallback)."
            ),
        },
        {
            "key": "propensity",
            "label": "Buy Signals",
            "description": (
                "Buy-Propensity scoring (competitive roadmap Phase 1) -- every "
                "customer and lead ranked 0-100 on likelihood to buy, composed from "
                "real engagement, estimated equity, loan/lease maturity, and service "
                "recency, with an explainable factor breakdown, one-click outreach "
                "drafts, and third-party data enrichment."
            ),
        },
        {
            "key": "reporting",
            "label": "Reporting",
            "description": (
                "Sales-specific reporting -- lead, sales, and deal performance, "
                "salesperson scorecards, and a real ledger-based sales forecast."
            ),
        },
    ],

    # service.pdf's Menu Bar: Overview | Appointments | Repair Orders | Customers |
    # Shop Control | Parts | Warranty | Reporting. Department key is "Service" (the
    # value app/workspace/page.tsx passes for the Service tab), not "Service & Parts".
    "Service": [
        {
            "key": "overview",
            "label": "Overview",
            "description": (
                "The Service & Parts home screen -- open/total repair orders, warranty "
                "claims, open recalls, parts inventory value, service revenue, and "
                "technician headcount at a glance."
            ),
        },
        {
            "key": "appointments",
            "label": "Appointments",
            "description": (
                "The service scheduling center -- the recent-intake queue and open OEM "
                "recalls that need proactive customer outreach and a booked visit."
            ),
        },
        {
            "key": "repair_orders",
            "label": "Repair Orders",
            "description": (
                "Repair-order center -- ROs by status and pay type, the most recent "
                "ROs, and full-record search by SRV id, VIN, or free text (customer, "
                "vehicle, and technician one hop away on the graph)."
            ),
        },
        {
            "key": "customers",
            "label": "Customers",
            "description": (
                "Service customer search -- search by CUST id or name/email/phone and "
                "get the full record plus service history, vehicles owned, and finance "
                "contracts one hop away on the graph."
            ),
        },
        {
            "key": "shop_control",
            "label": "Shop Control",
            "description": (
                "Shop loading and technician productivity -- labor hours and revenue "
                "by technician, the pay-type revenue mix, and the multi-point-"
                "inspection summary."
            ),
        },
        {
            "key": "parts",
            "label": "Parts",
            "description": (
                "The parts department -- inventory value and units on hand, a category "
                "breakdown, out-of-stock SKUs, and part-sale revenue/gross, searchable "
                "by part number, description, or category."
            ),
        },
        {
            "key": "warranty",
            "label": "Warranty",
            "description": (
                "Warranty and recall management -- real warranty claims (ServiceRecord "
                "PayType = Warranty) and open OEM recall campaigns."
            ),
        },
        {
            "key": "reporting",
            "label": "Reporting",
            "description": (
                "Service & Parts reporting -- service and parts revenue/gross, labor "
                "hours, warranty cost, technician effectiveness, and a real ledger-"
                "based repair-order and parts-sales forecast."
            ),
        },
    ],

    # marketing2.pdf's original Menu Bar (replacing the original marketing.pdf spec,
    # per Sam: "lets replace the marketing pdf with this updated one"): Overview |
    # Campaigns | Audiences | Events | Website | Opportunities | Reputation |
    # Reporting. Content and Analytics (the original spec's items) are gone -- folded
    # in as embedded features rather than standalone menu items.
    #
    # Reworked session 79 (Sam: "combine campaigns, audiences, and opportunities into
    # one Hubspot style workflow dash called CRM... add an Email/SMS dash"): Campaigns/
    # Audiences/Opportunities merged into one "crm" item, a new "email_sms" item added.
    # Campaigns split back OUT into its own item session 113 follow-up (Sam's later
    # 12-item Growth Platform menu spec) -- "crm" keeps Pipeline/Lists/Opportunities/
    # Customer 360/Smart Audiences, "campaigns" is the same real campaign data as its
    # own focused item. Current Menu Bar: Overview | CRM | Campaigns | Email/SMS |
    # PURLs | Events | Website | Social/Reputation | Advertising | Analytics |
    # Reporting. Department key is "Marketing" (the value app/workspace/page.tsx
    # passes for the Marketing tab).
    "Marketing": [
        {
            "key": "overview",
            "label": "Overview",
            "description": (
                "The Marketing & Revenue command center -- lead volume, showroom "
                "traffic, funded-deal revenue, and the real revenue funnel and "
                "opportunity pipeline at a glance."
            ),
        },
        {
            "key": "crm",
            "label": "CRM",
            "description": (
                "A HubSpot-style CRM workspace -- Pipeline, Lists, Opportunities, "
                "Customer 360, and Smart Audiences in one place. Campaigns also "
                "still has its own tab here for anyone working inside the broader "
                "CRM workspace, but has its own dedicated 'Campaigns' Top Menu "
                "item too (split back out session 113 follow-up, per Sam's later "
                "12-item Growth Platform menu spec) for a focused, lighter view."
            ),
        },
        {
            "key": "campaigns",
            "label": "Campaigns",
            "description": (
                "Session 113 follow-up -- Campaigns split back out of the merged "
                "CRM item into its own dedicated, focused Top Menu item, per Sam's "
                "later 12-item Growth Platform menu spec. Same real data/actions "
                "as the CRM workspace's own Campaigns tab (core/campaigns.py) -- "
                "create/activate/complete/cancel, real per-campaign stats and "
                "member browser, A/B testing, and revenue correlation -- just "
                "without needing to load Pipeline/Lists/Opportunities alongside "
                "it. See core/marketing_menu.py's campaigns()."
            ),
        },
        {
            "key": "email_sms",
            "label": "Email / SMS",
            "description": (
                "The Email/SMS builder -- an AI drafting wizard and a drag-and-drop "
                "block editor for mass or individual sends, with a toggle between "
                "email and SMS. Recipients pull straight from the CRM."
            ),
        },
        {
            "key": "purls",
            "label": "PURLs",
            "description": (
                "Session 113 follow-up -- the Personalized URL Platform: "
                "dealer.com/john-smith, a real per-customer/per-lead landing page "
                "with four offer types (Current Vehicle, Trade Equity, Inventory "
                "Matches, Payment Reduction), a real Mail Piece + QR code for "
                "direct mail, and real Visits/Leads-Generated analytics. See "
                "core/purls.py."
            ),
        },
        {
            "key": "events",
            "label": "Events",
            "description": (
                "Session 84 -- two real engines behind one toggle: a live, "
                "urgency-ranked Timeline of individually actionable trigger signals "
                "(lease maturity, service win-back, equity position, open recalls, "
                "in-market conquest -- styled after AutoAlert/automotiveMastermind), "
                "and real scheduled dealership events with a CRM-list-backed invite "
                "audience + RSVP tracking (styled after NXTDeal Bumper). Both "
                "one-click promote into a real new Lead tied back into the CRM. See "
                "core/trigger_alerts.py/core/dealership_events.py."
            ),
        },
        {
            "key": "website",
            "label": "Website",
            "description": (
                "The native website builder -- layout templates (independent + OEM), "
                "drag-and-drop sections with per-section AI writing, an image "
                "library, per-page SEO, DNS/admin controls, real preview + analytics, "
                "personal URL microsites for reps, and live chat wired into the CRM."
            ),
        },
        {
            "key": "social_reputation",
            "label": "Social / Reputation",
            "description": (
                "Session 83 -- a Hootsuite-style social suite (multi-platform post "
                "builder with inventory drop-in, a content calendar, simulated "
                "competitor tracking) merged with reputation management (real seeded "
                "reviews by platform, average rating, per-review response, and a bad-"
                "review alert/auto-respond bot). Replaces the standalone 'Reputation' "
                "item -- see core/marketing_menu.py's social_reputation()."
            ),
        },
        {
            "key": "advertising",
            "label": "Advertising",
            "description": (
                "Session 83 -- Meta/Google ad campaign builder with inventory "
                "integration, AI-recommended or fully manual targeting/budget/creative, "
                "and a real (simulated) launch/pause/complete lifecycle. See "
                "core/advertising.py."
            ),
        },
        {
            "key": "analytics",
            "label": "Analytics",
            "description": (
                "Session 113 follow-up -- the Attribution Engine capstone: real, "
                "honest first-touch Channel Mix & ROI by Lead Source, a Marketing "
                "ROI Dashboard rolling up real Campaign and PURL revenue "
                "correlation, and Vehicle Attribution (which real Make/Model "
                "combinations are actually being marketed vs actually selling). "
                "See core/marketing_attribution.py."
            ),
        },
        {
            "key": "inventory_advertising",
            "label": "Inventory Advertising",
            "description": (
                "Inventory advertising campaigns -- per-vehicle ad campaigns "
                "across channels with AI-generated ad copy (isolated OpenAI "
                "call with a deterministic fallback)."
            ),
        },
        {
            "key": "loyalty",
            "label": "Loyalty",
            "description": (
                "The Loyalty program -- points ledgers and redemptions across "
                "customers (real, no AI)."
            ),
        },
        # Bumper-parity Growth Tools (2026-07-25). Placed before Reporting to preserve
        # the "Overview first, Reporting last" menu invariant.
        {
            "key": "campaign_library",
            "label": "Campaign Library",
            "description": (
                "A browsable library of prebuilt campaign templates (Bumper "
                "parity) -- pick one and it becomes a draft campaign you can "
                "review, tweak, and activate."
            ),
        },
        {
            "key": "campaign_scheduler",
            "label": "Campaign Tools",
            "description": (
                "Duplication Station, Recurring Schedule, and Multi-Planner "
                "(Bumper parity) -- clone a campaign, repeat one on a cadence, "
                "or plan several at once."
            ),
        },
        {
            "key": "lead_import",
            "label": "Import",
            "description": (
                "Bulk-import a book of leads or customers from a CSV (Bumper "
                "parity) -- map your columns, preview new vs. duplicate, then "
                "commit."
            ),
        },
        {
            "key": "file_manager",
            "label": "File Manager",
            "description": (
                "A general digital-asset library across image/video/audio/"
                "document (Bumper parity) -- categories, tags, and search."
            ),
        },
        {
            "key": "reporting",
            "label": "Reporting",
            "description": (
                "Marketing & Revenue reporting -- campaign, website, and "
                "opportunity-pipeline rollups plus a real ledger-based lead-"
                "generation forecast."
            ),
        },
    ],

    # inventory.pdf's Menu Bar: Overview | Inventory | Acquisitions | Lot Management |
    # Pricing | Merchandising | Wholesale | Reporting. Department key is "Inventory".
    "Inventory": [
        {
            "key": "overview",
            "label": "Overview",
            "description": (
                "The Inventory command center -- total inventory value, active/"
                "incoming/wholesale-candidate counts, price-band aging, and the "
                "real vehicle pipeline (auction purchase through delivery)."
            ),
        },
        {
            "key": "inventory",
            "label": "Inventory",
            "description": (
                "The master inventory explorer -- the Single Vehicle Record. "
                "Search by VIN/stock number/free text and get cost basis, current "
                "price, margin, and photo status."
            ),
        },
        {
            "key": "acquisitions",
            "label": "Acquisitions",
            "description": (
                "The sourcing center -- real auction purchases, transport status, "
                "trade acquisitions, and a bid-vs-cost variance check."
            ),
        },
        {
            "key": "lot_management",
            "label": "Lot Management",
            "description": (
                "Physical inventory control -- real vehicle locations by lot and "
                "an ownership-mismatch data-integrity check."
            ),
        },
        {
            "key": "pricing",
            "label": "Pricing",
            "description": (
                "The pricing desk -- price-band aging, the zero-price queue, and "
                "margin analysis across all unsold inventory."
            ),
        },
        {
            "key": "merchandising",
            "label": "Merchandising",
            "description": (
                "Digital inventory presentation -- a real missing-photos check "
                "against the graph's Image relationships."
            ),
        },
        {
            "key": "wholesale",
            "label": "Wholesale",
            "description": (
                "The disposition center -- real wholesale candidates, the "
                "auction queue, and a title-on-file check against the document "
                "vault."
            ),
        },
        {
            "key": "syndication",
            "label": "Syndication",
            "description": (
                "Cross-platform listing health -- a dealership-wide feed sync "
                "rollup (Cars.com/AutoTrader/CarGurus/CarFax, simulated) plus "
                "real Lead.Source-based revenue and conversion performance per "
                "platform, and a bulk republish action."
            ),
        },
        {
            "key": "reporting",
            "label": "Reporting",
            "description": (
                "Formal inventory analytics -- aging, acquisition source "
                "performance, pricing, merchandising, and wholesale rollups plus "
                "a real ledger-based sales forecast."
            ),
        },
    ],

    # finance.pdf's original Menu Bar: Overview | Deals | Funding | Compliance |
    # Accounting | Floorplan | Commissions | Reporting. "Portfolio" was added
    # 2026-07-17 (session 111 follow-up) as the first slice of Sam's "Retail
    # Automotive Lending Platform" expansion (Lead -> Deal -> Credit -> Approval ->
    # Contract -> Funding -> Loan Servicing -> Collections -> Repossession -> Recovery
    # -> Payoff) -- Payments/Collections/Assets/GPS & Devices/Repossessions are
    # separately scoped future additions to this same menu, not built yet. Department
    # key is "Finance".
    "Finance": [
        {
            "key": "overview",
            "label": "Overview",
            "description": (
                "The Finance command center -- contracts in transit, unfunded "
                "deals, funding aging, floorplan balance, and open compliance "
                "issues at a glance."
            ),
        },
        {
            "key": "deals",
            "label": "Deals",
            "description": (
                "The master deal board -- pending, submitted, funded, unfunded, "
                "and delivered deals, plus gross analysis on funded units."
            ),
        },
        {
            "key": "funding",
            "label": "Funding",
            "description": (
                "The Contracts-in-Transit command center -- the real CIT queue, "
                "lender-response breakdown, and daily funding activity."
            ),
        },
        {
            "key": "compliance",
            "label": "Compliance",
            "description": (
                "The dealership risk center -- open compliance exceptions, deal "
                "jacket audits, and the real cited rule catalog (TILA/Reg Z, "
                "FACTA Red Flags, ECOA, and more)."
            ),
        },
        {
            "key": "accounting",
            "label": "Accounting",
            "description": (
                "The controller's home screen -- a real ownership-variance "
                "check standing in for the general-ledger/posting concept this "
                "codebase doesn't model yet."
            ),
        },
        {
            "key": "floorplan",
            "label": "Floorplan",
            "description": (
                "Inventory financing management -- real floorplan exposure "
                "derived from unsold Vehicle cost."
            ),
        },
        {
            "key": "portfolio",
            "label": "Portfolio",
            "description": (
                "Loan servicing -- the master Loan record for every funded "
                "FinanceContract: borrower, collateral, real amortization "
                "schedule, loan timeline, and delinquency-bucket dashboard. "
                "The first slice of Sam's Retail Automotive Lending Platform "
                "expansion (Payments/Collections/GPS & Devices/Repossessions "
                "are separately scoped future additions to this menu)."
            ),
        },
        {
            "key": "payments",
            "label": "Payments",
            "description": (
                "The real payment ledger -- record a payment (real balance/"
                "delinquency computation once real payments exist for a "
                "loan, replacing Portfolio's own simulated estimate), "
                "manage Auto Drafts, track Promises To Pay, and issue a "
                "real Customer Payment Portal link. The second slice of "
                "Sam's Retail Automotive Lending Platform expansion."
            ),
        },
        {
            "key": "collections",
            "label": "Collections",
            "description": (
                "The Collections work queue -- a real bucketed (3/7/15/30/60-"
                "day) delinquency queue, an Agent Workspace per loan with a "
                "real rules-based risk score/priority recommendation "
                "('AI Collection Prioritization', transparently rules-based, "
                "not machine learning), a real collection-stage path "
                "(Friendly Reminder -> Late Notice -> Demand Notice -> "
                "Recovery Review -> Repossession Referral), and real "
                "call/text/email contact logging. The third slice of Sam's "
                "Retail Automotive Lending Platform expansion, built "
                "entirely on top of Payments' real ledger and Portfolio's "
                "delinquency computation."
            ),
        },
        {
            "key": "repossessions",
            "label": "Repossessions",
            "description": (
                "The Repossession Case lifecycle -- a real Referral Queue off "
                "Collections' own repossession_referral stage, agent "
                "assignment, location/recovery/storage tracking, a real "
                "Deficiency Balance calculation (Sam's own 'Recovery' stage), "
                "auction/private-sale disposition, and a customer redemption "
                "path -- all cascading real loan_status updates back onto "
                "Portfolio. The fourth slice of Sam's Retail Automotive "
                "Lending Platform expansion, the direct continuation of "
                "Collections' own repossession_referral stage and Sam's "
                "stated lifecycle (...Collections -> Repossession -> "
                "Recovery -> Payoff)."
            ),
        },
        {
            "key": "gps_devices",
            "label": "GPS & Devices",
            "description": (
                "The installed-device registry -- register/remove a real "
                "GPS or GPS+Starter-Interrupt unit per loan, plus honestly "
                "SIMULATED location telemetry (no real GPS hardware/"
                "telematics API is connected in this sandbox, clearly "
                "disclosed on every reading). The fifth slice of Sam's "
                "Retail Automotive Lending Platform expansion -- shares one "
                "real engine with the Starter Interrupt Management item "
                "below, since both are one real physical device with two "
                "operational lenses."
            ),
        },
        {
            "key": "starter_interrupt",
            "label": "Starter Interrupt",
            "description": (
                "Real, stored starter-interrupt control -- arm a device, "
                "send a required customer warning, then disable/re-enable "
                "the starter, with a real enforced rule that a warning must "
                "be on file before a disable command will run. Not a cited "
                "statute -- an honest, real consumer-protection-shaped "
                "business rule (see the NOT_LEGAL_ADVICE_NOTICE on every "
                "response). Same real engine as GPS & Devices above."
            ),
        },
        {
            "key": "assets",
            "label": "Assets",
            "description": (
                "Collateral / Asset Management -- real Title status (reusing "
                "the categorized Document vault), real Lien tracking (a "
                "release gated on the loan actually being paid off), real "
                "dealer-entered Insurance/loss-payee tracking with a real "
                "lapsed-expiration check, and a Collateral Valuation & Loan-"
                "to-Value ratio blending the vehicle's real on-file Price "
                "with core/pricing_desk.py's SIMULATED current market value. "
                "The sixth slice of Sam's Retail Automotive Lending Platform "
                "expansion -- lives at the /collateral/* route prefix, "
                "distinct from Marketing's own /assets/* creative-asset "
                "workflow, to avoid a real route collision found while "
                "wiring this in."
            ),
        },
        {
            "key": "commissions",
            "label": "Commissions",
            "description": (
                "Employee compensation management -- industry-estimate $ "
                "tiers per employee, honestly labeled as a stand-in for real "
                "commission data."
            ),
        },
        {
            "key": "lender_intelligence",
            "label": "Lender Intelligence",
            "description": (
                "Real per-lender scorecards (approval rate, average offered "
                "APR, average decision turnaround) and a transparent, "
                "rules-based recommendation for which lender to submit a "
                "deal to next -- all computed off Deal Desk's own real "
                "outside-lender submission history, never a fabricated AI "
                "score."
            ),
        },
        {
            "key": "reporting",
            "label": "Reporting",
            "description": (
                "Formal financial reporting -- funding, F&I, accounting, "
                "floorplan, and executive rollups plus a real ledger-based "
                "contracts-funded forecast."
            ),
        },
    ],

    # admin.pdf's Menu Bar: Overview | Users | Security | Systems | Integrations |
    # Vendors | Governance | Reporting. Department key is "Administration" (the value
    # /admin passes, per session 53's notes).
    "Administration": [
        {
            "key": "overview",
            "label": "Overview",
            "description": (
                "The Admin command center -- active users, connected platforms, "
                "the real cross-department approval queue, and user activity by "
                "department."
            ),
        },
        {
            "key": "users",
            "label": "Users",
            "description": (
                "The central employee directory -- real employee/login-credential "
                "coverage by department, role assignments, and search by "
                "employee/department."
            ),
        },
        {
            "key": "roles_permissions",
            "label": "Roles & Permissions",
            "description": (
                "The real granular permission catalog and per-employee "
                "overrides on top of the platform's 6 core roles, field-level "
                "security on sensitive fields like credit score, and a real "
                "Employee/Manager/Executive approval-hierarchy engine "
                "(off each employee's own real Title)."
            ),
        },
        {
            "key": "security",
            "label": "Security",
            "description": (
                "The dealership SOC -- real login activity and failed-login "
                "events pulled from the audit log, plus credential-lifecycle "
                "events."
            ),
        },
        {
            "key": "systems",
            "label": "Systems",
            "description": (
                "Admin control over the platform -- the real audit log and "
                "active workflow-instance counts by status."
            ),
        },
        {
            "key": "integrations",
            "label": "Integrations",
            "description": (
                "The dealership technology stack -- real data connections by "
                "type, status, and department."
            ),
        },
        {
            "key": "vendors",
            "label": "Vendors",
            "description": (
                "Software and contract management -- real vendor/contract "
                "records (monthly cost, renewal dates, auto-renew) alongside "
                "the real data-connection records reused as a related proxy."
            ),
        },
        {
            "key": "organizations",
            "label": "Organizations",
            "description": (
                "This dealership's own profile and locations/rooftops -- "
                "name, address, EIN, business hours, currency/timezone "
                "defaults, and feature flags."
            ),
        },
        {
            "key": "data_management",
            "label": "Data Management",
            "description": (
                "Real per-entity-type CSV export, plus real graph.json "
                "backup and restore."
            ),
        },
        {
            "key": "identity_access",
            "label": "Identity & Access",
            "description": (
                "Real per-employee API keys for programmatic access, "
                "already wired into the platform's own authentication as a "
                "genuine bearer-token fallback."
            ),
        },
        {
            "key": "governance",
            "label": "Compliance & Governance",
            "description": (
                "The executive control center -- the real cross-department "
                "content approval queue, escalation rules, a real "
                "compliance-alert summary (resolution rate, avg resolution "
                "time, per-law violation breakdown), a real cross-department "
                "approval-hierarchy summary (permission/role/policy/expense "
                "requests by status and tier), a real blended governance-"
                "health figure, and a governance-scoped audit trail."
            ),
        },
        {
            "key": "audit_center",
            "label": "Audit Center",
            "description": (
                "The real investigative workspace over the audit log -- "
                "filterable/searchable across every real event this platform "
                "logs, a real per-actor activity summary, and a real, "
                "transparent rules-based suspicious-activity flag list (no "
                "ML/AI -- lockouts, IP-allowlist blocks, off-hours logins, "
                "recent permission grants, overridden compliance alerts)."
            ),
        },
        {
            "key": "workflow_automation",
            "label": "Workflow Automation",
            "description": (
                "A real, admin-configurable rule engine -- 'if this real "
                "condition, then this real action' (auto-create an "
                "Operations Task or send a notification DM) against real "
                "Deal/Lead/Vehicle signals, evaluated on demand (a 'Run "
                "Rules Now' action or on every dashboard fetch, not a "
                "background scheduler), with a real, deduped execution log."
            ),
        },
        {
            "key": "ai_management",
            "label": "AI Management",
            "description": (
                "A real catalog of every OpenAI-backed feature in this "
                "platform, with real per-feature enable/disable kill switches "
                "actually wired into each feature's own consumer function -- "
                "not just stored settings -- plus honest, in-memory call-"
                "attempt counters (attempted/succeeded/fell back/blocked)."
            ),
        },
        {
            "key": "fleet",
            "label": "AI Agents",
            "description": (
                "The agentic-bot fleet -- the nine NXTDeal team agents (one per "
                "section), each recording its team's real, observed workflow steps "
                "and surfacing the recurring workflows it has actually seen. ADMIN "
                "can activate an agent in draft or auto mode (auto gated by the same "
                "default-deny capability as Bot Coverage) or deactivate it. Viewing "
                "is open to any authenticated role; recognized workflows are never "
                "fabricated -- only shown once a step sequence has genuinely repeated."
            ),
        },
        {
            "key": "ai_workforce",
            "label": "Workforce Automation",
            "description": (
                "The customer-facing AI workforce -- an AI worker for every role "
                "(Receptionist, BDC, Sales, Service, Marketing, Finance, Collections, "
                "Operator, plus the Digital Retail roles: Product Specialist, Trade "
                "Manager, Negotiator, Delivery Coordinator, Ownership Concierge), each "
                "handling inbound touches across phone/SMS/email/chat and working an "
                "outbound queue. ADMIN can activate a worker in draft, assisted, or "
                "autonomous mode (autonomous gated by the AI kill switch and the "
                "default-deny ai.worker.autonomous capability) or deactivate it, and run "
                "its queue. Nothing financial or contractual ever auto-executes -- only "
                "informational safe actions can run autonomously; everything else drafts."
            ),
        },
        {
            "key": "connect",
            "label": "Connect",
            "description": (
                "NXTDeal Connect -- the unified customer-engagement surface. One inbox "
                "across every channel (phone/SMS/email/chat/social), a per-customer "
                "timeline that merges communications with the appointments booked off "
                "them, and analytics that split AI-handled from human-handled touches with "
                "rules-based sentiment and conversation scoring on every channel. Read-"
                "only -- it composes the communications already logged; nothing fabricated."
            ),
        },
        {
            "key": "digital_retail",
            "label": "Digital Retail",
            "description": (
                "The Digital Retail KPI dashboard -- how the self-service purchase journey is "
                "performing. Digital deals/closings/gross (deals the customer drove themselves "
                "via the Verify portal), AI Workforce performance (assisted/negotiated/closed, "
                "revenue influenced), and the journey drop-off funnel (verification -> deal -> "
                "finance -> contracting -> delivery) that surfaces where customers fall out. A "
                "read-only roll-up over the Verify/negotiation/delivery records; gross is "
                "computed from real vehicle cost on funded digital deals, nothing fabricated."
            ),
        },
        {
            "key": "success_center",
            "label": "Success Center",
            "description": (
                "NXTDeal-internal Success Center -- the portfolio-wide dealer "
                "roster with QBRs, objectives, initiatives, and recommendations, "
                "including AI-generated QBR insights (isolated OpenAI call with a "
                "deterministic fallback)."
            ),
        },
        # Bumper-parity administration (2026-07-25). Placed before Reporting to preserve
        # the "Overview first, Reporting last" menu invariant.
        {
            "key": "team_management",
            "label": "User Management",
            "description": (
                "Create a user (Employee record + login + role) in one action, "
                "manage the roster, and assign roles -- including the new BDC "
                "(Business Development Center) role (Bumper parity)."
            ),
        },
        {
            "key": "lead_routing",
            "label": "Leads Configuration",
            "description": (
                "Named lead-distribution rules (Bumper parity) -- route "
                "incoming leads by source to a team via round-robin/least-busy "
                "or to a specific rep, with optional ADF/HTTP endpoints."
            ),
        },
        {
            "key": "connections",
            "label": "Connections",
            "description": (
                "External provider integrations (Track B) -- see which "
                "capabilities (SMS/email, payments, ads, etc.) are live vs "
                "simulated, and connect a provider to take one live. The built-in "
                "http_webhook notifications provider works today with any endpoint "
                "you control; named providers (Twilio, Stripe, Meta) are slots that "
                "need credentials + a builder."
            ),
        },
        # Freemium Platform / Foundation-plus-Modules (2026-08-03). Placed before Reporting to
        # preserve the "Overview first, Reporting last" menu invariant.
        {
            "key": "modules",
            "label": "Modules & Plan",
            "description": (
                "NXTDeal Foundation (free) plus paid Modules -- the tenant-side "
                "entitlement record the running product actually enforces. See which "
                "Modules are active and at what level (Free/Professional/Enterprise), "
                "switch the whole dealer between the full-build reference profile and "
                "Tier-0 Foundation, add an individual Module, and set the Foundation "
                "usage caps (contacts, inventory units, report window, seats)."
            ),
        },
        {
            "key": "ai_spend",
            "label": "AI Spend",
            "description": (
                "The AI Spend Governor for a bring-your-own-key model -- NXTDeal is "
                "model-agnostic, so the dealer supplies their own AI key and the cost "
                "sits with them. Set a per-user monthly AI-action limit so one user "
                "can't burn the whole key's budget, override it per user, and see the "
                "aggregate consumption view. Metering is by AI actions (not tokens/$)."
            ),
        },
        {
            "key": "reporting",
            "label": "Reporting",
            "description": (
                "Administrative reporting -- user/adoption, integration, and "
                "governance rollups."
            ),
        },
    ],

    # readiness.pdf's Menu Bar: Overview | Data Health | Readiness | Forecasts |
    # Simulations | Exceptions | Recommendations | Reporting. Department key is
    # "Readiness" (the value /readiness passes). Unlike every production department,
    # Readiness doesn't manage work -- it measures whether the dealership is capable
    # of executing the work tomorrow/next week/next month/next quarter.
    "Readiness": [
        {
            "key": "overview",
            "label": "Overview",
            "description": (
                "The Enterprise Readiness Dashboard -- a real, color-coded "
                "readiness heatmap across the 5 departments core/prediction.py "
                "actually covers (with an honest note on the 3 it doesn't), "
                "Today's Risks pulled straight from the Enterprise Risk Center, "
                "and a real, rules-based Executive Summary (with an optional "
                "AI phrasing polish that can never invent a fact)."
            ),
        },
        {
            "key": "business_health",
            "label": "Business Health",
            "description": (
                "The executive health layer above every department -- real "
                "Sales/Service/Finance/Marketing/Inventory KPIs (Lead Volume, "
                "Close Rate, Gross Profit, Technician Utilization, Collections, "
                "Portfolio Quality, ROI, Turn Rate, and more), each labeled "
                "real/heuristic/simulated, distinct from Data Health's data-"
                "confidence question below."
            ),
        },
        {
            "key": "data_health",
            "label": "Data Health",
            "description": (
                "The foundation layer -- real connected-system status/sync "
                "health, plus real historical-coverage completeness per "
                "department from the prediction engine."
            ),
        },
        {
            "key": "readiness",
            "label": "Performance Readiness",
            "description": (
                "Goal Tracking against real pace -- a real, ADMIN/OPERATIONS-"
                "settable monthly target per department (Sales units, Service "
                "labor $, Marketing leads) compared against a real current-"
                "month pace projection and core/prediction.py's own ledger "
                "forecast, plus the prior confidence-score content (current/"
                "target %, variance, risk factors against the 90% go-live "
                "threshold) kept alongside as a distinct, honestly-labeled "
                "section."
            ),
        },
        {
            "key": "forecasts",
            "label": "Forecasts",
            "description": (
                "The predictive analytics engine -- real Sales (Units/Gross/"
                "Closing Ratio/Revenue), Service (Labor Sales/Parts Sales/RO "
                "Count/Capacity), Inventory (Units Likely To Sell/Age, "
                "Wholesale Candidates), and Finance (Funding/Collections/"
                "Delinquencies/Portfolio Performance) forecasts, each labeled "
                "real/real-linear-projection/real-rules-heuristic, plus the "
                "Readiness Timeline (Last 7/30/90 Days, Year To Date) to spot "
                "real trends, and the prior generic tomorrow/week/month/"
                "quarter-per-department view kept alongside."
            ),
        },
        {
            "key": "simulations",
            "label": "Simulations",
            "description": (
                "The Digital Twin -- real what-if scenario modeling "
                "(core/readiness_scenarios.py): Marketing/Lead Volume, "
                "Inventory Pricing, Staffing, and Finance Portfolio "
                "scenarios, each a transparent formula over this "
                "dealership's own real current-data ratios (real close "
                "rate, real gross per sale, real per-technician revenue, "
                "real observed portfolio yield/delinquency), never an "
                "invented multiplier."
            ),
        },
        {
            "key": "exceptions",
            "label": "Exceptions",
            "description": (
                "The Enterprise Risk Center -- Critical Issues (missing titles/"
                "documents, unlocated inventory, data sync failures), Financial "
                "Exceptions (unfunded contracts, funding delays, negative gross "
                "deals), and Operational Exceptions (recon/service delays, open "
                "compliance issues), each with a real Low/Medium/High/Critical "
                "severity and a link back to where it's resolved."
            ),
        },
        {
            "key": "recommendations",
            "label": "Recommendations",
            "description": (
                "The action engine -- a real, transparent 12-rule engine over "
                "Sales/Service/Finance/Inventory/Marketing signals (inventory "
                "aging, funding delays, collections risk, service-type revenue "
                "trends, lead-source conversion), each recommendation traced to "
                "a real condition crossing a real threshold, plus a curated "
                "Executive feed and the Network intelligence audit's own real "
                "recommendation set alongside it."
            ),
        },
        {
            "key": "strategic_planning",
            "label": "Strategic Planning",
            "description": (
                "\"A completely new area\" -- real Quarterly Planning (Objectives, "
                "Goals, Budgets), Department Planning (Sales Goal, Inventory "
                "Target, Service Growth, Marketing Budget), and Initiative "
                "Tracking (New Website Launch, New Service Center, New BHPH "
                "Program, GPS Rollout) with real, live-computed status for "
                "Sales/Service/Marketing objectives and an honest manual "
                "self-report for every other department, plus a real one-way "
                "sync into Performance Readiness's own monthly goal."
            ),
        },
        {
            "key": "reporting",
            "label": "Reporting",
            "description": (
                "Formal predictive reporting -- data quality, readiness, "
                "forecast, risk, and executive rollups."
            ),
        },
    ],

    # network.pdf's Menu Bar: Overview | Peer Groups | Benchmarks | Gap Analysis |
    # Trends | Playbooks | Opportunities | Reporting. Department key is "Network"
    # (the value /network passes). Network isn't managing your dealership -- it's
    # managing your dealership's relationship to every other dealership in the
    # network.
    "Network": [
        {
            "key": "overview",
            "label": "Overview",
            "description": (
                "The network intelligence command center -- real department "
                "percentile rankings, peer comparison snapshot, a real "
                "dollar-denominated opportunity total + largest-opportunities "
                "list, and a real, rules-based Executive Summary against "
                "simulated peer data."
            ),
        },
        {
            "key": "peer_groups",
            "label": "Peer Groups",
            "description": (
                "The digital Twenty Group manager -- the real, fixed simulated "
                "peer set (blind-labeled Dealer B/C/D/E) this dealer is "
                "benchmarked against."
            ),
        },
        {
            "key": "benchmarks",
            "label": "Benchmarks",
            "description": (
                "Pure performance benchmarking -- real KPIs across sales, "
                "service, parts, F&I, and executive against simulated peers."
            ),
        },
        {
            "key": "gap_analysis",
            "label": "Gap Analysis",
            "description": (
                "The profit leakage center -- real peer-average-vs-your-store "
                "gaps across every benchmarked KPI, ranked by size of "
                "opportunity."
            ),
        },
        {
            "key": "trends",
            "label": "Trends",
            "description": (
                "The market intelligence center -- real day-over-day KPI "
                "trend deltas per department, plus a real 90-day snapshot "
                "history view (however many real days have actually been "
                "recorded), from the Department Intelligence snapshot "
                "engine -- now including the real 'bhph' portfolio "
                "department."
            ),
        },
        {
            "key": "forecasts",
            "label": "Forecasts",
            "description": (
                "This dealer's own real trend, projected forward -- a "
                "simple linear projection off actual recorded KPI history, "
                "compared against the (static, simulated) peer average to "
                "estimate whether a real gap is closing or widening. Not a "
                "true competitive forecast, since peer benchmarks are a "
                "fixed simulated snapshot with no trend of their own."
            ),
        },
        {
            "key": "playbooks",
            "label": "Playbooks",
            "description": (
                "A real curated best-practice library -- every entry "
                "grounded in a real NXTDeal screen/workflow, live-checked "
                "against this dealer's own data (is_currently_active), and "
                "scored (0/1/3-tier Automation Score) against the real "
                "Workflow Automation rule engine, alongside the real "
                "cross-department recommendation feed."
            ),
        },
        {
            "key": "ai_advisors",
            "label": "AI Advisors",
            "description": (
                "5 real, department-specific Q&A advisors (Sales/Service/"
                "Parts/F&I/BHPH) -- ask a plain-language question and get an "
                "answer composed strictly from this dealer's own real "
                "benchmark comparison, gap analysis, and curated playbook "
                "data. AI phrasing is optional polish over an always-real, "
                "topic-matched fallback answer, never load-bearing."
            ),
        },
        {
            "key": "consulting_engine",
            "label": "Consulting Engine",
            "description": (
                "The AI Consulting Engine -- ask a plain business question "
                "(\"Why are service sales down?\") and get a structured "
                "four-part consulting answer: Analysis, Root Cause, "
                "Opportunity, and a concrete Action Plan. Composes NXTDeal's "
                "own already-real analysis (business health, gap analysis, "
                "dollar-opportunity sizing, Executive Recommendations); AI "
                "phrasing is optional polish over an always-real, fact-"
                "grounded answer, never load-bearing."
            ),
        },
        {
            "key": "opportunities",
            "label": "Opportunities",
            "description": (
                "Action-oriented intelligence -- the real recommendation "
                "feed grouped into cost-reduction, operational, staffing, "
                "and process-improvement buckets, plus a real per-department "
                "dollar-denominated opportunity total and grand total."
            ),
        },
        {
            "key": "reporting",
            "label": "Reporting",
            "description": (
                "Formal network reporting -- benchmark, opportunity, "
                "competitive, and executive rollups, plus a real Growth "
                "Forecast report (this dealer's own projected trend), a "
                "real Historical Trend report (real day-over-day KPI "
                "coverage), a real Playbook Adoption report (automation-"
                "tier breakdown), and a real AI Advisor usage report."
            ),
        },
    ],

    # NXTDeal Marketplace (2026-07-24) -- a certified catalog of apps, integrations, and
    # connectors a dealer installs with one click while NXTDeal stays the system of record.
    # A top-level Platform surface (opened from the gear menu, after Network). Every item is a
    # bespoke board (core/marketplace.py via the /marketplace routes), rendered by
    # MarketplaceBoard.tsx -- so these carry no MENU_SOURCES entry.
    "Marketplace": [
        {"key":"browse","label":"Marketplace","description":"Find dealership tools by name, category and setup status. Review a listing before adding it."},
        {"key":"installed","label":"Installed tools","description":"Review added listings and identify tools that still need provider setup."},
        {"key":"oem","label":"OEM programs","description":"Explore manufacturer programs and review setup requirements."},
        {"key":"phase2","label":"Coming soon","description":"Preview planned skills, workflow packs, marketing packs and website themes. Not yet installable."},
        {"key":"partners","label":"Network partners","description":"Explore planned dealer playbooks and shared workflows."},
    ],

}


def get_department_menu(department):
    """The 8-item (or empty, for a department not catalogued yet) Top Menu for one
    department -- GET /menu/catalog's data source. An empty list is a valid, expected
    answer for any department beyond Operations/Sales/Service this pass; the frontend
    hides the menu bar entirely rather than showing an empty row."""

    return MENU_CATALOG.get(department, [])
