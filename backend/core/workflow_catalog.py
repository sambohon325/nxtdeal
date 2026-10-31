"""
Department job-workflow catalog (session 53; restructured session 68).

Sam, after seeing the first cut of per-department buttons: "the buttons above the
workspace across the platform is not what I meant... we need 4 unique buttons for each
department/dash [Operations/Sales/Marketing/Inventory/Service/Finance/Administration/
Readiness/Network]... a work modal for the jobs that can't be done via chat for each
department that are unique to that department." Sam attached a document (a real job-
responsibilities writeup per department, 4 core responsibilities each with an explicit
"Workflow Steps" sequence and a "why it needs a process" rationale) and asked for that
to be baked directly into the button modals, not just used as background reading.

This module is that document, encoded as data -- one catalog entry per responsibility
(36 total, 4 x 9 departments), each with an ordered `stages` list. Deliberately
data-driven (one catalog + one generic engine in core/workflow_tracking.py) rather than
36 bespoke modules, matching this codebase's established pattern for large structured
catalogs (core/bot_tasks.py's TASK_CATALOG, core/compliance_rules.py's RULES,
core/knowledge_base.py's seed articles).

`entity_type` is a UI hint (which graph entity type this job is naturally about, so the
frontend can show the right placeholder/label on the "linked entity" field) -- it is
NOT a hard constraint enforced by the backend. core/workflow_tracking.py's
start_workflow_instance() accepts any linked_entity_id (or none), same permissive
"any role, no hard entity requirement" precedent as core/field_notes.py.

Session 68 (Sam, once the Top Menu rollout finished across all 9 departments: "we need
to rebuild the existing 4 modals for each department/dash to fit more inline with the
menus -- please see the attached doc and rework all modals to fit the new workflow")
replaced session 56's two-document layout ("deparment dash modals.docx" -- variable-
length `tabs` + two hand-written `core_functionality` preview cards per workflow) with
a single, uniform structure sourced from a new attached spec ("new modal layout.pdf"),
whose own closing framing is the standard now: "Top Menu = Navigation; Workflow Buttons
= Jobs To Be Done; Modal Tabs = Process Stages; Record/Dashboard Views = Data Layer."

Concretely, every one of the 36 workflows below now has EXACTLY 5 `stages` (a short
verb-chain naming the process, e.g. "Acquire -> Inspect -> Repair -> Merchandise ->
Frontline") and EXACTLY 5 `tabs` (the [Tab 1]..[Tab 5] left-hand navigation labels,
positionally paired with `stages` -- tabs[i] is the doc's fuller name for stages[i]).
This replaces the old variable-length stages/tabs pairing (Operations' Inventory
Reconciliation and Interdepartmental SLA workflows had only 4 of each, for instance) and
drops the `core_functionality` field entirely -- the new doc doesn't define aspirational
per-workflow widgets the way the old one did, and frontend/components/
DepartmentWorkflowButtons.tsx's core_functionality rendering is already optional
(`workflow.core_functionality?.length > 0`), so omitting the key is a no-op there, not a
breaking change. `tabs` was previously undefined for all 4 Sales workflows (the old doc
didn't cover Sales) -- the new doc does, so Sales gets real tabs for the first time.

Every workflow `key` is UNCHANGED from session 53/56/57 with one deliberate exception
(Marketing, below) -- core/workflow_tab_data.py's REAL_SOURCES map and
core/workflow_tracking.py both key off this string, and get_tab_data() (session 57)
already renders its sources once per workflow window, not per tab, so a tab-shape
change requires zero changes to real-data wiring as long as the key is stable.

Marketing is the one department where the new doc doesn't map 1:1 onto the old 4
workflows -- "Website Merchandising" and "Reputation Management" (two old, separate
workflows) are merged into one new "Website & Reputation" workflow, and a genuinely new
"Events & Activations" workflow (NXTDeal/Bumper-style, matching the placeholder already
flagged in core/marketing_menu.py's events() since session 62 -- no Event entity exists
anywhere in this codebase yet) fills the resulting fourth slot. Rather than delete a
key, the old `marketing.reputation` key is REPURPOSED to carry Events & Activations
(its `entity_type`/`entity_label` changed from Customer to None/"Notes (optional)" to
match), and the old `marketing.website_merchandising` key absorbs the review-related
content under its new "Website & Reputation" title. core/workflow_tab_data.py's
REAL_SOURCES was updated the same session to match: the review-summary source that used
to live under `marketing.reputation` moved to `marketing.website_merchandising`
alongside its existing pending-website-approvals source, and `marketing.reputation`'s
REAL_SOURCES list is now empty (Events has no real backing data yet, same honest-gap
treatment as every other not-yet-modeled concept in this codebase, e.g.
Simulations/Playbooks under Readiness/Network).
"""

DEPARTMENTS = [
    "Operations",
    "Sales",
    "Marketing",
    "Inventory",
    "Service",
    "Finance",
    "Administration",
    "Readiness",
    "Network",
]

WORKFLOW_CATALOG = {

    "Operations": [
        {
            "key": "operations.recon",
            "title": "Vehicle Intake & Recon",
            "entity_type": "Vehicle",
            "entity_label": "VIN",
            "description": (
                "A vehicle can't go straight to the lot -- inspection, repair, "
                "detailing, photography, and listing all have to happen in order to "
                "minimize holding costs."
            ),
            "why_it_matters": (
                "Without a clear workflow, cars get stuck in limbo between the service "
                "bay and the detail shop, delaying time to market."
            ),
            "stages": ["Acquire", "Inspect", "Repair", "Merchandise", "Frontline"],
            "tabs": [
                "Stock Assignment & Source",
                "Inspection & Condition Report",
                "Repair & Recon Management",
                "Media & Merchandising",
                "Frontline Readiness",
            ],
        },
        {
            "key": "operations.deal_jacket_audit",
            "title": "Compliance & Deal Jacket",
            "entity_type": "Deal",
            "entity_label": "Deal ID",
            "description": (
                "The Deal Jacket contains all the paperwork for a vehicle sale and must "
                "be flawless before it goes to the lender or is archived."
            ),
            "why_it_matters": (
                "Missing a single signature or failing a compliance check can result in "
                "a bank rejecting a deal or a fine during an audit."
            ),
            "stages": ["Collect", "Verify", "Audit", "Resolve", "Approve"],
            "tabs": [
                "Customer Verification",
                "Contract Audit",
                "Lender Requirements",
                "Registration & Insurance",
                "Compliance Approval",
            ],
        },
        {
            "key": "operations.inventory_reconciliation",
            "title": "Inventory Reconciliation",
            "entity_type": "Vehicle",
            "entity_label": "VIN",
            "description": (
                "Operations managers oversee the lifecycle of the millions of dollars "
                "of physical inventory on the lot."
            ),
            "why_it_matters": (
                "If a vehicle goes missing, is damaged, or sits too long without a "
                "price drop, it depreciates rapidly."
            ),
            "stages": ["Locate", "Audit", "Evaluate", "Adjust", "Reconcile"],
            "tabs": [
                "Floorplan Ledger",
                "Physical Lot Audit",
                "Aging Analysis",
                "Pricing Adjustments",
                "Reconciliation Review",
            ],
        },
        {
            "key": "operations.interdept_sla",
            "title": "Interdepartmental SLA",
            "entity_type": None,
            "entity_label": "Related Deal/VIN (optional)",
            "description": (
                "Operations designs how Sales, Service, Parts, and Finance hand work to "
                "each other -- e.g. an accessory install request."
            ),
            "why_it_matters": (
                "Friction between sales and service is a classic dealership problem; a "
                "clear workflow keeps parts billed correctly and delivery on schedule."
            ),
            "stages": ["Request", "Assign", "Execute", "Bill", "Close"],
            "tabs": [
                "Request Intake",
                "Parts Allocation",
                "Service Scheduling",
                "Financial Routing",
                "Completion Verification",
            ],
        },
    ],

    "Sales": [
        {
            "key": "sales.lead_cadence",
            "title": "Lead Management",
            "entity_type": "Lead",
            "entity_label": "Lead ID",
            "description": (
                "From the moment a customer inquires online, calls, or walks in, a "
                "strict workflow dictates how they're handled."
            ),
            "why_it_matters": (
                "Without a standardized follow-up cadence, leads go cold -- a workflow "
                "ensures every prospect is nurtured systematically."
            ),
            "stages": ["Lead", "Contact", "Qualify", "Appointment", "Showroom"],
            "tabs": [
                "Lead Assignment",
                "Communication Timeline",
                "Needs Analysis",
                "Appointment Scheduling",
                "Opportunity Creation",
            ],
        },
        {
            "key": "sales.desking",
            "title": "Desking & Trade Evaluation",
            "entity_type": "Deal",
            "entity_label": "Deal ID",
            "description": (
                "Once a customer is ready to talk numbers, the sales manager "
                "structures pricing, financing options, and trade-in value."
            ),
            "why_it_matters": (
                "Without structure, reps might over-promise on a trade-in value or "
                "miscalculate tax/title fees, hurting the dealership's bottom line."
            ),
            "stages": ["Appraise", "Structure", "Present", "Negotiate", "Approve"],
            "tabs": [
                "Customer Financial Profile",
                "Trade Appraisal",
                "Deal Structuring",
                "Payment Presentation",
                "Management Approval",
            ],
        },
        {
            "key": "sales.fi_turnover",
            "title": "F&I Handoff",
            "entity_type": "Deal",
            "entity_label": "Deal ID",
            "description": (
                "Once a customer agrees to buy, the deal must cleanly transition from "
                "the sales rep to the Finance & Insurance manager."
            ),
            "why_it_matters": (
                "The Sales-to-Finance handoff is a notorious bottleneck where "
                "customers get impatient -- a seamless workflow minimizes wait times."
            ),
            "stages": ["Prepare", "Transfer", "Present", "Submit", "Contract"],
            "tabs": [
                "Deal Packaging",
                "Customer Transfer",
                "Product Presentation",
                "Lender Submission",
                "Contract Readiness",
            ],
        },
        {
            "key": "sales.delivery",
            "title": "Delivery Experience",
            "entity_type": "Deal",
            "entity_label": "Deal ID",
            "description": (
                "The sale isn't complete until the keys are handed over and the "
                "customer leaves happy."
            ),
            "why_it_matters": (
                "A car delivered dirty or missing an accessory results in a poor "
                "review -- bad CSI scores cost thousands in monthly manufacturer "
                "incentives."
            ),
            "stages": ["Prepare", "Inspect", "Educate", "Deliver", "Follow Up"],
            "tabs": [
                "Vehicle Preparation",
                "Delivery Quality Control",
                "Technology Setup",
                "Delivery Documentation",
                "CSI & Review Trigger",
            ],
        },
        {
            "key": "sales.up_system",
            "title": "Up System",
            "entity_type": "Lead",
            "entity_label": "Lead ID",
            "description": (
                "Every walk-in or phone-up gets logged and handed to whoever's next "
                "in the floor rotation -- a fair, first-come-first-served line, not "
                "whoever happens to be closest to the door."
            ),
            "why_it_matters": (
                "An unlogged or unfairly-skipped up is a lost opportunity and a "
                "morale problem -- a real rotation keeps the floor honest and makes "
                "sure nobody walks out without being greeted."
            ),
            "stages": ["Greet", "Log", "Assign", "Work", "Outcome"],
            "tabs": [
                "Floor Rotation",
                "Log an Up",
                "Working Ups",
                "Be-Back Board",
                "Outcome Tracking",
            ],
        },
        {
            "key": "sales.bdc",
            "title": "BDC (Internet Leads)",
            "entity_type": "Lead",
            "entity_label": "Lead ID",
            "description": (
                "Internet-sourced leads live and die on speed -- the Business "
                "Development Center's job is first contact within minutes, not hours."
            ),
            "why_it_matters": (
                "Response time is the single biggest predictor of whether an "
                "internet lead ever shows up -- a stale, untouched queue is money "
                "already spent on marketing with nothing to show for it."
            ),
            "stages": ["Intake", "Triage", "Contact", "Qualify", "Handoff"],
            "tabs": [
                "Untouched Queue",
                "Response-Time Scorecard",
                "First Contact",
                "Qualification",
                "Handoff to Floor",
            ],
        },
        {
            "key": "sales.demo_drive",
            "title": "Demo Drive",
            "entity_type": "Lead",
            "entity_label": "Lead ID",
            "description": (
                "Getting a customer behind the wheel is the single biggest step "
                "toward a sale -- every drive gets logged with a verified license, "
                "the vehicle, and the odometer before the keys leave the desk."
            ),
            "why_it_matters": (
                "A test drive without a verified license is an insurance and "
                "liability problem, and an untracked one is a lost follow-up -- a "
                "real log protects the store and captures the buying signal."
            ),
            "stages": ["Qualify", "Verify License", "Drive", "Return", "Follow Up"],
            "tabs": [
                "Keys-Out Board",
                "Log a Drive",
                "License Verification",
                "Return & Odometer",
                "Interest & Follow-Up",
            ],
        },
        {
            "key": "sales.credit_app",
            "title": "Credit Application",
            "entity_type": "Customer",
            "entity_label": "Customer ID",
            "description": (
                "Knowing what a customer can qualify for -- before or after a "
                "vehicle is picked -- turns a maybe into a real deal. Capture "
                "income and consent, run a decision, and see exactly what "
                "terms and conditions come back."
            ),
            "why_it_matters": (
                "A credit decision without documented consent and specific "
                "reasons is a compliance exposure, and a customer who never "
                "finds out what they qualify for is a customer who walks -- a "
                "real application record protects both the store and the sale."
            ),
            "stages": ["Prequalify", "Consent", "Capture Info", "Decision", "Next Steps"],
            "tabs": [
                "Application Queue",
                "Applicant Information",
                "Consent & Submit",
                "Decision Results",
                "Application History",
            ],
        },
        {
            "key": "sales.esignature",
            "title": "eSignature",
            "entity_type": "Deal",
            "entity_label": "Deal ID",
            "description": (
                "A deal isn't done until it's actually signed. Build a real "
                "signing envelope against the generated contract, capture "
                "consent, and get every required signature on file before "
                "it heads to funding."
            ),
            "why_it_matters": (
                "A verbal agreement isn't a contract -- funding a deal with "
                "no signature on file is a real compliance and collections "
                "risk, and a lost signing link is a lost deal."
            ),
            "stages": ["Prepare", "Consent", "Send", "Sign", "Complete"],
            "tabs": [
                "Envelope Queue",
                "Signer Setup",
                "Send for Signature",
                "Sign & Consent",
                "Completed Envelopes",
            ],
        },
        {
            "key": "sales.fi_products",
            "title": "F&I Workflow",
            "entity_type": "Deal",
            "entity_label": "Deal ID",
            "description": (
                "The F&I menu -- present protection products (VSC, GAP, Tire & "
                "Wheel, Paint & Fabric, Key Replacement, Prepaid Maintenance), "
                "track what the customer accepts or declines, and see real "
                "product penetration across every deal."
            ),
            "why_it_matters": (
                "F&I product income is real gross profit on every deal, not "
                "just the vehicle sale -- and unpresented products are gross "
                "profit that was never even offered, not just declined."
            ),
            "stages": ["Present", "Select", "Structure", "Verify", "Finalize"],
            "tabs": [
                "Product Menu",
                "Customer Selections",
                "Deal F&I Summary",
                "Product Penetration",
                "Compliance & Disclosures",
            ],
        },
        {
            "key": "sales.lost_sale_recovery",
            "title": "Lost Sale Recovery",
            "entity_type": "Lead",
            "entity_label": "Lead ID or Deal ID (optional)",
            "description": (
                "A combined recovery queue over every lost Lead and cancelled "
                "Deal -- capture a real reason code, log outreach attempts, "
                "reactivate a lead that comes back around, and roll a whole "
                "lost/cancelled pool into a real Marketing win-back List."
            ),
            "why_it_matters": (
                "A lost lead or a cancelled deal isn't gone -- it's a real "
                "prospect who said no once, for a reason worth recording, not "
                "a dead record with no path back into the pipeline."
            ),
            "stages": ["Identify", "Diagnose", "Re-Engage", "Reactivate", "Recover"],
            "tabs": [
                "Recovery Queue",
                "Lost Reason Capture",
                "Outreach Log",
                "Reactivation",
                "Win-Back Lists & Stats",
            ],
        },
        {
            "key": "sales.orphan_owner_mining",
            "title": "Orphan Owner Mining",
            "entity_type": "Customer",
            "entity_label": "Customer ID",
            "description": (
                "Real vehicle owners with no salesperson currently attributed to "
                "their ownership -- a genuine gap in the graph, not a hunch. "
                "Claim one to spin up a real, assigned Lead and start working "
                "them as a reconquest opportunity."
            ),
            "why_it_matters": (
                "An owned vehicle with nobody assigned to the relationship is a "
                "trade-in, a service customer, and a next sale sitting unworked "
                "-- every unclaimed owner here is prospecting inventory that "
                "already exists in the graph."
            ),
            "stages": ["Identify", "Prioritize", "Claim", "Re-Engage", "Convert"],
            "tabs": [
                "Orphan Queue",
                "Customer Detail",
                "Claim & Assign",
                "Claimed Owners",
                "Mining Stats",
            ],
        },
    ],

    "Marketing": [
        {
            "key": "marketing.oem_incentive",
            "title": "Campaigns & Advertising",
            "entity_type": "Campaign",
            "entity_label": "Campaign ID (optional)",
            "description": (
                "Dealership marketing hinges on monthly OEM incentives, lease "
                "specials, and finance rates that change every month."
            ),
            "why_it_matters": (
                "An ad live with an outdated price or a co-op compliance violation can "
                "cost thousands in lost manufacturer reimbursement funds."
            ),
            "stages": ["Offer", "Build", "Launch", "Measure", "Optimize"],
            "tabs": [
                "OEM Incentives & Offers",
                "Campaign Builder",
                "Channel Deployment",
                "Attribution & Analytics",
                "Optimization Center",
            ],
        },
        {
            "key": "marketing.database_mining",
            "title": "Audiences & Opportunities",
            "entity_type": None,
            "entity_label": "Campaign ID (optional)",
            "description": (
                "Some of the most profitable leads come from the existing database -- "
                "previous buyers, equity positions, expiring leases -- scored and "
                "segmented Mastermind-style rather than blasted as one flat list."
            ),
            "why_it_matters": (
                "Blasting the whole database with generic spam leads to high "
                "unsubscribe rates -- precise scoring and targeting hits the right "
                "customer at the right moment."
            ),
            "stages": ["Analyze", "Score", "Segment", "Assign", "Convert"],
            "tabs": [
                "Customer Intelligence",
                "Opportunity Scoring",
                "Equity & Lease Mining",
                "Outreach Assignment",
                "Conversion Tracking",
            ],
        },
        {
            "key": "marketing.website_merchandising",
            "title": "Website & Reputation",
            "entity_type": "Website",
            "entity_label": "Website ID (optional)",
            "description": (
                "The dealership's website is its digital showroom, and the reviews "
                "customers leave after visiting it shape whether the next shopper ever "
                "walks in the door -- both need the same continuous workflow."
            ),
            "why_it_matters": (
                "If a customer sees a price online sales can't honor, or a negative "
                "review sits unanswered for a week, trust erodes immediately -- and "
                "local SEO ranking with it."
            ),
            "stages": ["Build", "Capture", "Convert", "Review", "Recover"],
            "tabs": [
                "Website Builder",
                "Landing Pages & Forms",
                "Conversion Optimization",
                "Review Management",
                "Reputation Recovery",
            ],
        },
        {
            "key": "marketing.reputation",
            "title": "Events & Activations",
            "entity_type": None,
            "entity_label": "Notes (optional)",
            "description": (
                "NXTDeal/Bumper-style in-person and virtual events -- test-drive "
                "nights, service clinics, owner-appreciation days -- need their own "
                "operational workflow from concept through post-event follow-up."
            ),
            "why_it_matters": (
                "An event with no registration tracking or follow-up plan burns "
                "marketing spend without ever converting attendees into leads or "
                "showroom traffic."
            ),
            "stages": ["Build Event", "Invite", "Register", "Operate", "Follow Up"],
            "tabs": [
                "Event Configuration",
                "Audience & Invitations",
                "RSVP Management",
                "Event Operations",
                "Revenue & Follow-Up",
            ],
        },
    ],

    "Inventory": [
        {
            "key": "inventory.auction_acquisition",
            "title": "Acquisition & Transport",
            "entity_type": "Vehicle",
            "entity_label": "VIN (optional)",
            "description": (
                "When inventory is purchased at wholesale auction, it must be tracked "
                "from the block to the dealership lot."
            ),
            "why_it_matters": (
                "Every day a purchased vehicle sits at a distant auction yard or on a "
                "truck is a day it isn't making money while interest accrues."
            ),
            "stages": ["Source", "Purchase", "Transport", "Receive", "Fund"],
            "tabs": [
                "Acquisition Source",
                "Purchase Management",
                "Transport Tracking",
                "Arrival Processing",
                "Floorplan Funding",
            ],
        },
        {
            "key": "inventory.lot_audit",
            "title": "Lot Control",
            "entity_type": "Vehicle",
            "entity_label": "VIN",
            "description": (
                "Managing a sprawling lot means knowing exactly where assets are and "
                "securing their access points."
            ),
            "why_it_matters": (
                "If a rep can't find a vehicle or its keys for a waiting customer, the "
                "sale is compromised."
            ),
            "stages": ["Assign", "Locate", "Audit", "Report", "Resolve"],
            "tabs": [
                "Vehicle Placement",
                "Key Management",
                "Lot Audits",
                "Damage & Exception Tracking",
                "Resolution Center",
            ],
        },
        {
            "key": "inventory.aging_pricing",
            "title": "Pricing & Velocity",
            "entity_type": "Vehicle",
            "entity_label": "VIN",
            "description": (
                "Vehicles lose value the longer they sit -- especially used cars -- and "
                "need aggressive monitoring."
            ),
            "why_it_matters": (
                "A vehicle sitting past 60-90 days without a price adjustment eats up "
                "capital that could turn faster cars."
            ),
            "stages": ["Monitor", "Compare", "Reprice", "Merchandise", "Evaluate"],
            "tabs": [
                "Aging Management",
                "Market Pricing",
                "Price Adjustments",
                "Merchandising Refresh",
                "Velocity Analysis",
            ],
        },
        {
            "key": "inventory.wholesale_disposition",
            "title": "Wholesale & Liquidation",
            "entity_type": "Vehicle",
            "entity_label": "VIN",
            "description": (
                "Trade-ins unsuitable for retail (high mileage, mechanical issues, "
                "off-brand) need to be offloaded to wholesale immediately."
            ),
            "why_it_matters": (
                "Wholesale units take up valuable lot space and hold up cash -- a swift "
                "exit workflow keeps cash flow fluid."
            ),
            "stages": ["Assign", "Inspect", "List", "Sell", "Reconcile"],
            "tabs": [
                "Wholesale Assignment",
                "Condition Reports",
                "Auction Management",
                "Bid Tracking",
                "Settlement & Titles",
            ],
        },
    ],

    "Service": [
        {
            "key": "service.intake",
            "title": "Service Intake",
            "entity_type": "ServiceRecord",
            "entity_label": "VIN",
            "description": (
                "The moment a customer arrives on the service drive, a structured "
                "check-in sets the tone for the whole visit."
            ),
            "why_it_matters": (
                "Missing pre-existing damage or an open recall during intake can mean "
                "unexpected liability or lost warranty revenue."
            ),
            "stages": ["Schedule", "Check-In", "Inspect", "Authorize", "Dispatch"],
            "tabs": [
                "Appointment Intake",
                "Customer & Vehicle Review",
                "Walkaround Inspection",
                "Authorization & Signatures",
                "Dispatch Assignment",
            ],
        },
        {
            "key": "service.mpi",
            "title": "MPI & Repair Approval",
            "entity_type": "ServiceRecord",
            "entity_label": "VIN",
            "description": (
                "The technician conducts a Multi-Point Inspection to identify "
                "immediate safety issues and future maintenance needs."
            ),
            "why_it_matters": (
                "This is the primary driver of service profitability -- without a fast "
                "digital workflow, vehicles sit on lifts waiting on quotes."
            ),
            "stages": ["Inspect", "Document", "Quote", "Present", "Approve"],
            "tabs": [
                "MPI Checklist",
                "Photos & Videos",
                "Parts & Pricing",
                "Recommendation Builder",
                "Approval Tracking",
            ],
        },
        {
            "key": "service.warranty_claims",
            "title": "Warranty Administration",
            "entity_type": "ServiceRecord",
            "entity_label": "VIN",
            "description": (
                "Manufacturers have strict guidelines for how warranty repairs must be "
                "documented before they'll pay the dealership."
            ),
            "why_it_matters": (
                "Manufacturers routinely audit and will claw back thousands if "
                "documentation, signatures, or time punches don't line up."
            ),
            "stages": ["Diagnose", "Document", "Verify", "Submit", "Track"],
            "tabs": [
                "Warranty Eligibility",
                "Technician Documentation",
                "Labor Verification",
                "Claim Submission",
                "Claim Tracking",
            ],
        },
        {
            "key": "service.quality_control",
            "title": "QC & Delivery",
            "entity_type": "ServiceRecord",
            "entity_label": "VIN",
            "description": (
                "Before a customer gets their keys back, the dealership ensures the "
                "repair was fixed right the first time."
            ),
            "why_it_matters": (
                "An unresolved issue or a dirty car directly damages Fixed Operations "
                "CSI scores."
            ),
            "stages": ["Inspect", "Clean", "Explain", "Deliver", "Survey"],
            "tabs": [
                "Quality Control",
                "Valet & Detail",
                "Invoice Review",
                "Checkout & Delivery",
                "CSI Follow-Up",
            ],
        },
    ],

    "Finance": [
        {
            "key": "finance.cit_funding",
            "title": "Funding",
            "entity_type": "FinanceContract",
            "entity_label": "Deal/Contract ID",
            "description": (
                "Once a vehicle is sold and financed, the contract and supporting docs "
                "must be sent to the lender for the dealership to receive funds."
            ),
            "why_it_matters": (
                "If a deal is held up over a missing document, the dealership's "
                "capital stays trapped in that vehicle."
            ),
            "stages": ["Review", "Collect", "Submit", "Fund", "Reconcile"],
            "tabs": [
                "Lender Assignment",
                "Stipulation Tracking",
                "Paperwork Audit",
                "Submission Queue",
                "Funding Reconciliation",
            ],
        },
        {
            "key": "finance.compliance",
            "title": "Compliance",
            "entity_type": "Customer",
            "entity_label": "Customer ID (optional)",
            "description": (
                "Finance offices handle highly sensitive personal information and "
                "large cash transactions under intense federal regulation."
            ),
            "why_it_matters": (
                "Non-compliance or missed identity fraud can lead to severe federal "
                "fines or the lender backing out of the contract entirely."
            ),
            "stages": ["Verify", "Screen", "Archive", "File", "Approve"],
            "tabs": [
                "Identity Verification",
                "OFAC & Red Flags",
                "Secure Document Storage",
                "Regulatory Filings",
                "Compliance Approval",
            ],
        },
        {
            "key": "finance.floorplan_payoff",
            "title": "Floorplan & Payoffs",
            "entity_type": "Vehicle",
            "entity_label": "VIN",
            "description": (
                "When a customer trades in a car they still owe on, finance must clear "
                "that debt immediately, and floorplan lines must be paid down on sale."
            ),
            "why_it_matters": (
                "Delayed trade payoffs cause a terrible customer experience; failing to "
                "pay down floorplan on sale risks heavy interest or an out-of-trust "
                "violation."
            ),
            "stages": ["Calculate", "Authorize", "Pay", "Track", "Close"],
            "tabs": [
                "Payoff Requests",
                "Wire Authorization",
                "Title Tracking",
                "Floorplan Reduction",
                "Reconciliation",
            ],
        },
        {
            "key": "finance.deal_accounting",
            "title": "Accounting & Commissions",
            "entity_type": "Deal",
            "entity_label": "Deal ID",
            "description": (
                "The accounting office finalizes every deal, calculates true profit "
                "margins, and compensates employees on their pay plans."
            ),
            "why_it_matters": (
                "Dealership pay structures combine volume bonuses, gross percentages, "
                "and flat payouts -- a standardized workflow prevents payroll errors."
            ),
            "stages": ["Post", "Reconcile", "Calculate", "Approve", "Close"],
            "tabs": [
                "Deal Posting",
                "Gross Reconciliation",
                "Pay Plans",
                "Commission Approval",
                "Financial Close",
            ],
        },
    ],

    "Administration": [
        {
            "key": "administration.onboarding",
            "title": "User Access",
            "entity_type": "Employee",
            "entity_label": "Employee ID",
            "description": (
                "Employees need access to exactly the tools their job requires -- and "
                "nothing else -- with instant lockout on termination."
            ),
            "why_it_matters": (
                "A terminated manager who retains access can export the entire "
                "customer database to a competitor."
            ),
            "stages": ["Create", "Assign", "Enable", "Monitor", "Remove"],
            "tabs": [
                "Employee Profile",
                "Role Assignment",
                "System Access",
                "Activity Monitoring",
                "Offboarding",
            ],
        },
        {
            "key": "administration.audit_monitoring",
            "title": "Auditing",
            "entity_type": None,
            "entity_label": "Related Employee/System (optional)",
            "description": (
                "With every department processing sensitive data, admin needs a "
                "bird's-eye view of who is doing what across NXTDeal."
            ),
            "why_it_matters": (
                "IT admins can't manually watch every action -- structured monitoring "
                "automatically flags high-risk activity before it becomes liability."
            ),
            "stages": ["Monitor", "Detect", "Investigate", "Resolve", "Archive"],
            "tabs": [
                "Activity Logs",
                "Security Alerts",
                "Investigation Tools",
                "Resolution Workflow",
                "Audit Archive",
            ],
        },
        {
            "key": "administration.vendor_management",
            "title": "Integrations",
            "entity_type": "Connection",
            "entity_label": "Connection/Vendor Name",
            "description": (
                "Dealerships run on a massive web of software -- DMS, CRM, inventory, "
                "desking, marketing -- that all needs managing."
            ),
            "why_it_matters": (
                "SaaS creep is a major profit drain -- paying for former employees' "
                "seats or overlapping features."
            ),
            "stages": ["Connect", "Authenticate", "Sync", "Monitor", "Optimize"],
            "tabs": [
                "Connected Systems",
                "API Management",
                "Data Mapping",
                "Health Monitoring",
                "Optimization",
            ],
        },
        {
            "key": "administration.executive_approval",
            "title": "Governance",
            "entity_type": None,
            "entity_label": "Related Item (optional)",
            "description": (
                "Owners and GMs need high-level oversight for capital, marketing "
                "budget, and policy decisions without daily micro-management."
            ),
            "why_it_matters": (
                "When critical decisions happen over text or casual conversation, "
                "accountability is lost."
            ),
            "stages": ["Request", "Review", "Analyze", "Approve", "Document"],
            "tabs": [
                "Approval Queue",
                "Policy Review",
                "Impact Analysis",
                "Executive Decision",
                "Audit Trail",
            ],
        },
    ],

    "Readiness": [
        {
            "key": "readiness.data_connection",
            "title": "Data Connections",
            "entity_type": "Connection",
            "entity_label": "Connection Name",
            "description": (
                "Before NXTDeal can predict anything, it has to cleanly hook into the "
                "dealership's existing DMS, CRM, service ledgers, and marketing suites."
            ),
            "why_it_matters": (
                "A dropped or mis-mapped connection feeds the predictive engine dirty "
                "data, skewing readiness percentages."
            ),
            "stages": ["Connect", "Map", "Sync", "Verify", "Activate"],
            "tabs": [
                "Integration Setup",
                "Schema Mapping",
                "Pipeline Monitoring",
                "Data Validation",
                "Readiness Activation",
            ],
        },
        {
            "key": "readiness.data_maturity",
            "title": "Data Verification",
            "entity_type": None,
            "entity_label": "Department (optional)",
            "description": (
                "The system audits the volume and history of ingested data until it "
                "crosses the threshold needed to simulate day-to-day operations."
            ),
            "why_it_matters": (
                "This prevents forecasts too early, drawing a clear line between "
                "verified ledger baselines and speculative industry averages."
            ),
            "stages": ["Collect", "Audit", "Validate", "Verify", "Score"],
            "tabs": [
                "Historical Data Review",
                "Density Analysis",
                "Ledger Validation",
                "Verification Thresholds",
                "Confidence Scoring",
            ],
        },
        {
            "key": "readiness.forecasting",
            "title": "Forecasting",
            "entity_type": None,
            "entity_label": "Department (optional)",
            "description": (
                "Once verified, the engine calculates confidence that the dealership "
                "can execute across tomorrow / this week / this month / this quarter."
            ),
            "why_it_matters": (
                "Different decisions need different horizons -- micro-insights for "
                "daily staffing, macro-insights for quarterly capital allocation."
            ),
            "stages": ["Analyze", "Predict", "Simulate", "Compare", "Refine"],
            "tabs": [
                "Tomorrow",
                "This Week",
                "This Month",
                "This Quarter",
                "Scenario Modeling",
            ],
        },
        {
            "key": "readiness.exception_escalation",
            "title": "Exception Resolution",
            "entity_type": None,
            "entity_label": "Department (optional)",
            "description": (
                "When a department's readiness score drops below target, the system "
                "flags it for the administrative team."
            ),
            "why_it_matters": (
                "An intelligence screen is only useful if it drives action -- gaps and "
                "bottlenecks must be addressed before they hit tomorrow's performance."
            ),
            "stages": ["Detect", "Isolate", "Analyze", "Resolve", "Restore"],
            "tabs": [
                "Active Alerts",
                "Root Cause Analysis",
                "Impact Assessment",
                "Resolution Workflow",
                "Readiness Recovery",
            ],
        },
    ],

    "Network": [
        {
            "key": "network.peer_filtering",
            "title": "Peer Groups",
            "entity_type": None,
            "entity_label": "Notes (optional)",
            "description": (
                "A Twenty Group is only useful if you're comparing apples to apples -- "
                "the network needs filtering to match your dealership's profile."
            ),
            "why_it_matters": (
                "Comparing a high-volume metro store to a rural domestic dealer yields "
                "useless benchmarks."
            ),
            "stages": ["Filter", "Build", "Validate", "Compare", "Benchmark"],
            "tabs": [
                "Demographics",
                "Market Filters",
                "OEM Alignment",
                "Cohort Validation",
                "Benchmark Setup",
            ],
        },
        {
            "key": "network.gap_analysis",
            "title": "Gap Analysis",
            "entity_type": None,
            "entity_label": "Department (optional)",
            "description": (
                "Once peer groups are established, the system runs a gap analysis "
                "across operations to see where money is being left on the table."
            ),
            "why_it_matters": (
                "Raw numbers alone don't change behavior -- an automated audit turns "
                "benchmarks into prioritized directives."
            ),
            "stages": ["Analyze", "Compare", "Identify", "Prioritize", "Recommend"],
            "tabs": [
                "Department Analysis",
                "Variance Detection",
                "Opportunity Ranking",
                "AI Recommendations",
                "Action Planning",
            ],
        },
        {
            "key": "network.trend_forecasting",
            "title": "Market Trends",
            "entity_type": None,
            "entity_label": "Notes (optional)",
            "description": (
                "The network should warn you about where the local market is moving "
                "tomorrow based on aggregate data, not just where you stand today."
            ),
            "why_it_matters": (
                "Traditional Twenty Groups meet quarterly -- real-time forecasting lets "
                "principals adjust strategy before the shift hits the bottom line."
            ),
            "stages": ["Collect", "Monitor", "Forecast", "Alert", "Respond"],
            "tabs": [
                "Regional Trends",
                "OEM Trends",
                "Demand Forecasting",
                "Alert Center",
                "Strategy Deployment",
            ],
        },
        {
            "key": "network.playbook_syndication",
            "title": "Playbooks",
            "entity_type": None,
            "entity_label": "Metric (optional)",
            "description": (
                "When the network identifies a sustained 100th-percentile performer, "
                "the system captures the 'how' without exposing dealer identity."
            ),
            "why_it_matters": (
                "This closes the loop of a true Twenty Group -- proven workflows get "
                "shared across the network instead of staying a private scoreboard."
            ),
            "stages": ["Discover", "Analyze", "Simulate", "Import", "Measure"],
            "tabs": [
                "Top Performer Library",
                "Workflow Analysis",
                "Impact Simulation",
                "Playbook Deployment",
                "Performance Measurement",
            ],
        },
    ],
}


def get_catalog():
    """Returns the full catalog. A plain function (not a direct import of the dict)
    so callers go through one seam, matching core/compliance_rules.py's
    get_rules()-style convention."""

    return WORKFLOW_CATALOG


def get_workflow_def(workflow_key):
    """Looks up one workflow definition by its dotted key (e.g. "operations.recon")
    across every department. Returns None if not found."""

    for department_workflows in WORKFLOW_CATALOG.values():
        for workflow in department_workflows:
            if workflow["key"] == workflow_key:
                return workflow

    return None
