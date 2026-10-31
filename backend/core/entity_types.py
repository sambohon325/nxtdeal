VEHICLE = "Vehicle"

CUSTOMER = "Customer"

# A customer-facing login (email + password) that maps to a CUSTOMER/LEAD record — the
# non-secret profile half lives here in the graph; the password salt/hash live in a
# separate customer_credentials.json store (see core/customer_accounts.py).
CUSTOMER_ACCOUNT = "CustomerAccount"

LEAD = "Lead"

FINANCE_CONTRACT = "FinanceContract"

LENDER = "Lender"

SERVICE_RECORD = "ServiceRecord"

DOCUMENT = "Document"

IMAGE = "Image"

CAMPAIGN = "Campaign"

# A recurring cadence that auto-clones + launches a base campaign on a schedule (Bumper parity:
# "Recurring Schedule"). Evaluated on-demand like workflow automation, no background scheduler.
RECURRING_SCHEDULE = "RecurringSchedule"

# A named lead-distribution rule (Bumper parity: "Leads Configuration" / Distribution
# Configurations). Matches incoming leads by source/geography and routes them to a team via
# round-robin / least-busy / a specific rep, with optional ADF/HTTP endpoint config.
LEAD_ROUTING_RULE = "LeadRoutingRule"

# A prebuilt, browsable campaign template (Bumper parity: the Library of ~79 templates). A
# template instantiates into a real draft Campaign via campaigns.create_campaign.
CAMPAIGN_TEMPLATE = "CampaignTemplate"

# A catalogued digital asset in the general File Manager / DAM (Bumper parity). Unlike the
# image-only media_library, this catalogs multi-type files (image/video/audio/document) by
# metadata + a hosted URL or storage reference.
FILE_ASSET = "FileAsset"

# One per-recipient message-send record for a campaign (Track B delivery pipeline). Replaces
# the aggregate sent_count with a real, trackable per-message log (queued/sent/simulated/
# failed/no_contact + open/click tracking hooks). Routes through integrations_registry, so
# it's honestly simulated until a real notifications adapter is registered.
MESSAGE_SEND = "MessageSend"

# Per-tenant credentials for an external provider (Track B). Stored ADMIN-only; secrets are
# masked on read. Configuring one can register a live adapter via the adapter factory.
PROVIDER_CREDENTIAL = "ProviderCredential"

# Payroll (competitive roadmap Phase 5). A time-clock punch (actual hours worked), a
# generated paycheck, and a payroll run grouping the paychecks for one pay period.
TIME_ENTRY = "TimeEntry"
PAY_STATEMENT = "PayStatement"
PAYROLL_RUN = "PayrollRun"

# MySales adoption signal (App Suite roadmap Phase 6). One per rep using the standalone
# MySales app; tracks usage as a rep-level buy-in leading indicator, including at dealerships
# not yet on NXTDeal, which Readiness reads as a warm conversion-outreach signal.
MYSALES_ADOPTION = "MySalesAdoption"

EMPLOYEE = "Employee"

VENDOR = "Vendor"

# Graph-native communications (2026-07-13, session 28) -- channels/messages live as
# ordinary entities in the same graph ledger as everything else, tied to Employee
# entities, rather than a separate messaging store. See core/messaging.py.
CHANNEL = "Channel"

MESSAGE = "Message"

# Marketing asset design/approval workflow (2026-07-13, session 30 -- phase 1 of
# folding NXTDeal's product suite into NXTDeal: the previous sales design reference/
# admin.nxtdeal.design's "design an OEM/dealer asset, route it for approval" pattern).
# Same graph-native rule as everything else: an Asset is an ordinary entity in the same
# ledger, tied to the Employee who requested it and optionally the Vehicle/Campaign
# it's about, not a separate content-management system.
ASSET = "Asset"

# Website / inventory builder (2026-07-13, session 32 -- phase 3, the last piece of the
# NXTDeal suite integration before "DMS style systems"): a Glovebox Websites + a
# DriveFinder-lite, template-fill (no freeform canvas, no AI image generation -- OEM/
# dealer-supplied photos only, per Sam). A Website is an ordinary entity in the same
# ledger as everything else, tied to the Employee who built it; its inventory page is
# rendered live from the Vehicle entities already in the graph, not a static copy.
WEBSITE = "Website"

# DMS Deal Desk (2026-07-13, session 33 -- phase 1 of the DMS buildout Sam scoped after
# DealerSocket/Tekion, modeled on those platforms' Desking + F&I + Contracting modules).
# A Deal is an ordinary entity in the same ledger as everything else, tracking one
# vehicle sale from desking (multiple pricing/term scenarios) through financing
# (in-house/BHPH or an outside Lender already in the graph) through a generated contract
# to funding. Funding a Deal doesn't invent a new data shape -- it creates a
# FinanceContract entity and the exact FINANCED_BY/OWNS/PURCHASED/COVERS/FUNDED_BY
# relationships imports/finance_import.py already establishes for historical data, so a
# funded Deal is indistinguishable from imported data to every existing dashboard/
# profile view. Reuses the "DEAL" id-generator prefix that's existed since an earlier
# session but was never wired to an entity type until now.
DEAL = "Deal"

# Department Intelligence reporting layer (2026-07-13, session 35 -- Sam: "add this
# product functionality into the admin... its our product 'bumper bi' that creates
# dashboards across the dealership," modeled on a real cross-dealership KPI-dashboard
# product's Sales/Service/Parts/F&I/Accounting layout. Renamed session 68 (Sam: "i want
# to take out the term 'bumper bi'... What i do want to do is include that level of
# reporting for each reporting section of every department") -- the underlying real KPI
# computation is unchanged, only the branding is gone; see core/department_intelligence.py.
# Part/PartSale are new -- NXTDeal had ZERO parts-department data model before this
# session -- added so the Parts dashboard's KPIs (net profit, GP/unit, inventory turns,
# obsolete %) are computed from real (if synthetic) entities rather than fabricated
# numbers, same bar as everything else in this codebase. A DepartmentSnapshot is NOT a
# separate JSON store -- it's an ordinary graph entity (one per department per calendar
# day) so daily trend deltas ride on the same one-graph persistence as everything else,
# deliberately avoiding the exact separate-store-fragmentation pattern the "One Graph
# Unification" effort (session 17) spent real effort undoing. See
# core/department_intelligence.py.
PART = "Part"

PART_SALE = "PartSale"

# Session 68: renamed from BUMPER_SNAPSHOT/"BumperSnapshot". The stored string value
# changed, not just the Python name -- any existing graph.json entities with
# entity_type=="BumperSnapshot" from before this session won't match new lookups.
# Demo data, safe to re-seed (run_seed_import.py); no migration written since this
# is throwaway synthetic data, same convention as every other seed-data change in this
# codebase (e.g. session 39's ServiceRecord.Technician resolution fix).
DEPARTMENT_SNAPSHOT = "DepartmentSnapshot"

# Agentic bot layer (2026-07-13, session 36 -- Sam: "create a agentic bot for each
# section... it will prompt the user throughout the day with things that need to be
# done depending on their role"). Same graph-native rule as everything else in this
# file: a BotCoverage (an admin running the bot "as" an absent employee for a time
# window) and a BotTaskEvent (a real, explainable act/dismiss signal feeding the bot's
# heuristic prioritization -- see core/bot_learning.py) are both ordinary entities in
# the same ledger, not a new store. See core/bot_tasks.py/core/bot_coverage.py/
# core/bot_learning.py/core/bot_actions.py/core/bot_scheduler.py.
BOT_COVERAGE = "BotCoverage"

BOT_TASK_EVENT = "BotTaskEvent"

# Agentic-bot FLEET (2026-07-23, Pillar 4): a TeamAgent (one per section, admin-activated,
# holding its activation state) and a TeamWorkflowEvent (one real observed step in a
# team's workflow, mined into recurring workflows) are both ordinary entities in the same
# single ledger -- NOT a new store. See core/bot_fleet.py.
TEAM_AGENT = "TeamAgent"

TEAM_WORKFLOW_EVENT = "TeamWorkflowEvent"

# A single recorded RUN of a team agent's recognized workflow (Pillar 4 slice 4e, agentic
# auto-execution): a persisted, per-step record of what the agent executed (only ever a
# whitelisted safe action) vs drafted for a human. See core/bot_fleet.py.
TEAM_AGENT_RUN = "TeamAgentRun"

# Shared AI knowledge (2026-07-23, Pillar 5): one pool the whole agent fleet reads from and
# writes to. An entry is either a team's recognized workflow promoted for other agents to
# see, or a free-form insight a person contributed. An ordinary entity in the same single
# ledger -- NOT a new store. See core/shared_knowledge.py.
SHARED_KNOWLEDGE_ENTRY = "SharedKnowledgeEntry"

# Integration platform / employee value (2026-07-13, session 37 -- Sam: "the readiness
# page acts as the integration platform for dealerOS to pull data via api, csv, etc from
# various dealer platforms... and fill the knowledge ledger to a set point of prediction
# certainty." A Connection is an ordinary graph entity describing one configured data
# source (a CSV feed or an API endpoint) tied to a department, not a separate
# integrations database -- see core/data_connections.py. EmployeeValueSnapshot backs
# Sam's "assign monetary value to each employee... admin can measure the live employee
# over time" ask -- a point-in-time $ effectiveness estimate per employee, same
# graph-native/no-separate-store rule, blended from industry baselines and real ledger
# data as it accumulates -- see core/employee_value.py.
CONNECTION = "Connection"

EMPLOYEE_VALUE_SNAPSHOT = "EmployeeValueSnapshot"

# Compliance agent (2026-07-13, session 38 -- Sam: "there needs to be a complete
# compliance level baked into every part of this, and it needs to run through every
# sale, marketing push, etc... If it fails a compliance review it needs to be flagged,
# stopped, and not allowed to go through until the corrections are made... scan
# records/deals/etc at least twice a day and flag compliance issues and notify
# managers/admin"). A ComplianceAlert is an ordinary graph entity (what failed, which
# real federal rule, severity, who was notified, resolved/overridden status) -- same
# no-separate-store rule as DepartmentSnapshot/BotCoverage/Connection. See
# core/compliance_rules.py (the actual rule definitions) and core/compliance.py (the
# check/gate/scan engine).
COMPLIANCE_ALERT = "ComplianceAlert"

# Network intelligence layer (2026-07-13, session 38 -- Sam: "the network is a
# collection of other dealers... applying department intelligence and its kpi reports
# pulled from other NXTDeal dealers (blind labeled for anonymity)... this also needs to include
# the prediction scales... the entire idea of the network is to replace the twenty
# groups"). This environment is single-tenant (one dealer's graph) -- there's no real
# second NXTDeal dealer to pull from yet, so a NetworkPeerSnapshot is a clearly-labeled
# SIMULATED blind peer-dealer KPI record (basis="simulated_peer_data"), built the same
# graph-native way as everything else so it can be replaced by a real peer dealer's
# snapshot the moment one actually connects, with zero shape changes. See
# core/network_benchmark.py.
NETWORK_PEER_SNAPSHOT = "NetworkPeerSnapshot"

# Role-gated knowledge base (2026-07-13, session 38 -- Sam: "a knowledge base thats
# accessable from each dash... closed off to non admin/managers etc, role based...
# Getting started guides, How to build a deal... how to use NXTDeal for each
# department"). A KnowledgeArticle is an ordinary graph entity (title/body/department/
# visible_roles), authored once at seed time (real content, not placeholder stubs --
# Sam's scoping answer), editable later like any other entity. See
# core/knowledge_base.py.
KNOWLEDGE_ARTICLE = "KnowledgeArticle"

# Native per-department quick-entry (2026-07-13, session 47 -- Sam: "each section...
# needs to have their own buttons/callouts that are native to their department, and are
# functions that would be difficult to replicate in the chat feature... a way for jobs
# that require input / field work to add quicker to the knowledge graph"). A FieldNote
# is the generic, reusable half of that: a free-text log entry tagged with a department
# and category (incident, recon, maintenance, payment, general), optionally pointed at
# an existing entity (a Vehicle, Deal, etc.) -- same "ordinary entity in the same
# ledger" rule as everything else in this file. Backs Operations "Log Incident",
# Inventory "Recon Note", Finance "Payment Note". Sales/Inventory/Service's other new
# quick-entry actions (walk-in Lead, Vehicle intake, Service ticket) reuse the existing
# LEAD/VEHICLE/SERVICE_RECORD entity types above rather than this one, since those are
# structured business objects the rest of the app already knows how to read.
FIELD_NOTE = "FieldNote"

# Department job-workflow engine (session 53 -- Sam: "the buttons above the workspace
# across the platform is not what I meant... we need 4 unique buttons for each
# department that are unique to that department... a work modal for the jobs that
# can't be done via chat," baked directly from an attached job-responsibilities
# document covering all 9 departments/dashes). A WorkflowInstance is one in-progress
# (or completed) run of one of the 36 catalog workflows in core/workflow_catalog.py --
# an ordinary entity in the same ledger as everything else, same no-separate-store rule
# as DepartmentSnapshot/BotCoverage/ComplianceAlert. Optionally linked to whatever entity
# the job is actually about (a Vehicle mid-recon, a Deal awaiting F&I turnover, etc.)
# via a TRACKS relationship (core/relationship_types.py) rather than a foreign-key
# column, keeping this graph-native. See core/workflow_tracking.py
WORKFLOW_INSTANCE = "WorkflowInstance"

# Demo-data / workflow-tab-data gap closure (session 59 -- Sam: "lets go ahead and
# populate that data with demo data"). Three concepts core/workflow_tab_data.py's
# REAL_SOURCES map needed (review platform data, auction/transport acquisition
# tracking, OEM recall campaigns) had no entity type at all before this session --
# ordinary graph entities, same no-separate-store rule as everything else in this file.
# Seeded via imports/seed_demo_extras.py (40 Reviews / 25 AuctionTransactions / 15
# Recalls tied to real existing Vehicle/Customer entities) -- these string values are
# load-bearing: storage/graph.json already has entities persisted with these exact
# entity_type strings, so they must match verbatim, not just be internally consistent.
REVIEW = "Review"

AUCTION_TRANSACTION = "AuctionTransaction"

RECALL = "Recall"

# Shared Knowledge (session 72 -- Sam: "id like there to be a regular knowledge and a
# shared knowledge... if you want to share, you can select a department, multiple
# departments, or all, and it goes into 'Shared Knowledge'"). A KnowledgePin is an
# ordinary graph entity -- owner, visibility ("all" or a specific list of the 6 real
# roles), kind/ref_id/label/tag mirroring frontend/lib/pins.ts's existing private-pin
# shape. "My Knowledge" (the original private pin) is unchanged and stays entirely
# browser-local -- this entity type only ever exists for pins someone explicitly chose
# to share. See core/knowledge_pins.py.
KNOWLEDGE_PIN = "KnowledgePin"

# Customizable Reporting dashboards (session 73 -- Sam: "lets go ahead and set all the
# reporting to be graph based... they should also be able to snap them into place to
# create their own dashboards... hide the modules (deactivate)... this is for each
# department"). A DashboardLayout is an ordinary graph entity, one per (employee_id,
# department) pair -- "their own dashboards," not a shared department-wide layout --
# holding the employee's chosen module instances (which report-module catalog entry
# each one is sourced from, graph/text mode, chart type, color, column span, field
# selection, ordering). Same no-separate-store rule as everything else in this file.
# See core/dashboard_layouts.py and core/report_modules.py (the underlying module
# catalog, which needs no new entity type at all -- it's a live reshaping of each
# department's existing "reporting" Top Menu data, not a stored copy).
DASHBOARD_LAYOUT = "DashboardLayout"

# Account settings gear menu (session 74 -- Sam: "a gear icon on the far right at the
# top - when clicked, it should show user profile settings / password administration,
# notification settings"). A NotificationPreference is an ordinary graph entity, one
# per employee, holding a handful of real boolean toggles -- same no-separate-store
# rule as everything else in this file. Honest scope note: nothing downstream reads
# these yet to actually gate delivery (compliance-alert DMs, workflow-instance
# notifications, etc. all still fire unconditionally today) -- this is real, persisted
# preference *storage*, not yet a real preference *engine*. Flagged for a future pass
# to actually wire delivery code to check these. "Profile settings / password
# administration" needed no new entity type -- it reuses the existing Employee entity
# (read-only display) plus core/auth_api.py's already-built change_password().
NOTIFICATION_PREFERENCE = "NotificationPreference"

# Marketing CRM + Email/SMS builder (session 79 -- Sam: "combine campaigns, audiences,
# and opportunities into one Hubspot style workflow dash called CRM... add an Email/SMS
# dash with a fully functional email builder... Ai build an email wizard as well as a
# traditional drag and drop modual... toggle to switch to a texting/sms builder. Both
# pull from the CRM"). An EmailTemplate is one ordinary graph entity per composed
# message -- channel "email" (subject/preheader/blocks) or "sms" (plain sms_body) --
# tied to the Employee who built it and optionally to the Campaign it's attached to,
# same no-separate-store rule as everything else in this file. The CRM board itself
# needed no new entity type: the "Pipeline" tab is a real-time view over the Lead
# entities' existing PipelineState (core/pipeline_state.py, session 17) run through the
# existing LEAD_WORKFLOW state machine (core/workflows.py) -- validated server-side
# since session 17 but never rendered as a draggable kanban board until now. See
# core/email_templates.py.
EMAIL_TEMPLATE = "EmailTemplate"

# Marketing Lists (session 82 -- Sam: "under lists we need to be able to click on the
# list names and have them show as a list of names... really there you'd be able to
# start to curate marketing lists for campaigns," plus "this is actually a
# functionality that is going to appear on the sales side as well"). A MarketingList is
# an ordinary graph entity: a named, curated collection of real Customer/Lead ids
# (`member_ids`), same no-separate-store rule as everything else in this file. Built
# either manually, or seeded from one of the live audience-preview pools
# core/campaigns.py's build_audience() already computes -- once seeded, membership is a
# real, editable snapshot the marketer can hand-curate, not a live query. See
# core/marketing_lists.py.
MARKETING_LIST = "MarketingList"

# OneNote-style Workspace board (session 76 -- Sam: "the workspace needs to be dynamic
# in the sense that yes you can add graphs, but what other knowledge do you want to
# add?... You should be able to prompt 'in the workspace window'... and be able to add
# in a paragraph. The idea is something like microsoft OneNote"). A WorkspaceBoard is an
# ordinary graph entity, one per employee_id -- "your workspace," personal working
# notes, not a shared department board, same pattern as DashboardLayout above but keyed
# by employee only (not department) since a board can mix items pulled from any
# department. Holds an ordered `items` list, each either a live chart reference (department/
# item_key/field_path -- re-fetched at render time off core/menu_data.py, never a frozen
# snapshot, same "always reflects the current graph" rule DashboardLayout follows) or a
# freeform/AI-generated text note. See core/workspace_board.py.
WORKSPACE_BOARD = "WorkspaceBoard"

# Social / Reputation (session 83 -- Sam: "combine Reputation with Social media...
# post to facebook, instagram, X, LinkedIn, tiktok, etc with a social content
# calendar... a built in social media post builder that includes dropping in
# inventory"). A SocialPost is an ordinary graph entity, tied to the Employee who
# built it and optionally to one or more Vehicle entities it references (via
# `linked_vehicle_ids` -- the post stores only the id, never a copied snapshot of the
# vehicle's price/photo, same no-parallel-inventory-copy rule
# core/websites.py's inventory_grid section already established). This sandbox has no
# real path to the Facebook/Instagram/X/LinkedIn/TikTok APIs, so "publishing" a post
# is an honestly-labeled simulated action (same precedent as core/campaigns.py's
# activate_campaign() simulated send) -- it stamps real status/timestamps on a real
# graph record, it does not actually reach those platforms. See core/social_posts.py.
SOCIAL_POST = "SocialPost"

# Advertising (session 83 -- Sam: "an advertising tool to start meta and google ad
# campaigns that include inventory and allow ai recommendations / building, or
# granular control"). An AdCampaign is an ordinary graph entity, distinct from the
# existing Campaign entity type (core/campaigns.py's Campaign is NXTDeal's own
# email/SMS/direct-mail customer-lifecycle engine -- a Meta/Google ad campaign is a
# different real-world object with different fields: platform, budget, targeting,
# ad copy/creative -- kept as its own type rather than overloading Campaign, matching
# this codebase's "one entity type per real-world object" discipline). Same simulated-
# launch precedent as SocialPost/activate_campaign() -- no real Meta/Google Ads API
# access exists in this sandbox. See core/advertising.py.
AD_CAMPAIGN = "AdCampaign"

# Events dash (session 84 -- Sam: "build out the event dash... style it after nxtdeal
# bumper, automotivemastermind.com, and auto alert... has to tightly integrate into
# the CRM"). Two related but distinct real-world objects, scoped via AskUserQuestion
# (Sam picked "Both, unified" + "One-click promote"):
#
# TriggerAlert -- the AutoAlert/automotiveMastermind half: a real, individually
# actionable signal (lease maturity, service win-back, equity position, an open OEM
# recall on an owned vehicle, an in-market conquest match) computed by
# core/trigger_alerts.py's run_scan() off the same real graph data
# core/campaigns.py's audience builders and core/workflow_tab_data.py's
# marketing_database_mining() already compute in aggregate -- what's new here is
# surfacing each one as an individual, urgency-ranked, dismissable/promotable feed
# item (AutoAlert's own "Timeline" UI concept) rather than a pool count. Promoting an
# alert is the literal Marketing/Sales handoff: for a Customer-typed alert it creates
# a real new Lead (core/lead_intake.py's create_lead(), source="Trigger Alert") tied
# back to the originating Customer via a real GENERATED_LEAD relationship (defined in
# core/relationship_types.py since the original vision-doc pass but never actually
# used until now); for a Lead-typed alert (conquest) it reuses the exact
# core/lead_assignment.py ASSIGNED_TO mechanism core/opportunities_actions.py's
# assign_opportunity_to_sales() already established. Deduplicated per (target id,
# alert_type, vehicle id) so re-scanning never spams a second open alert for an
# already-flagged signal -- same dedup discipline as core/compliance.py's
# run_full_scan().
TRIGGER_ALERT = "TriggerAlert"

# DealershipEvent -- the NXTDeal Bumper half: a real, scheduled dealership event (test
# drive day, VIP sale, service clinic), tied into the CRM via an optional invite
# audience pulled from a real core/marketing_lists.py MarketingList -- not a
# standalone event calendar bolted onto the side. See core/dealership_events.py.
EVENT = "Event"

# EventRSVP -- tied to a real Customer/Lead id when the attendee is already in the
# graph, or a freeform name/phone/email snapshot for a genuine walk-in/self-registered
# prospect who isn't yet. Same promote-to-Lead mechanism as TriggerAlert (source=
# "Event" -- already a VALID_SOURCES entry in core/lead_intake.py before this session,
# now actually used for the first time here too).
EVENT_RSVP = "EventRSVP"

# EventTask -- Event Project Management (2026-07-18, Marketing Growth Platform, Events
# War Room/Project Management/Campaign Generator slice). A real planning checklist item
# tied to one Event (vendor coordination, staffing, day-of logistics) -- deliberately
# its own first-class entity, not a dict on Event, since a real event accumulates many
# distinct tasks over its planning lifecycle. See core/event_planning.py.
EVENT_TASK = "EventTask"

# Website Builder overhaul (session 85) -- Sam: "the last bit is the website... it
# needs to be a full website builder... personal url functionality that takes the look
# and feel of the website and can be deployed by the sales rep or marketing/events...
# live chat functionality (wired into the crm)."
#
# PersonalSite -- a single personal landing page for one Employee (sales/marketing/
# events), not a full site mirror -- borrows its parent core/websites.py Website's
# branding/colors/logo rather than duplicating it, at its own URL slug. See
# core/personal_sites.py.
PERSONAL_SITE = "PersonalSite"

# WebsiteChatSession / WebsiteChatMessage -- the live-chat half. Deliberately its own
# small store rather than overloading core/messaging.py's Channel/Message model: that
# system's whole design assumes both participants are authenticated Employees (fixed
# department channels + employee-to-employee DMs) -- a website visitor is anonymous,
# a fundamentally different trust boundary, so this is a new, narrowly-scoped pair of
# entity types rather than stretching an authenticated system to cover an
# unauthenticated one. REST + polling, not a new public WebSocket endpoint -- an
# explicit scoping choice (see core/website_chat.py's module docstring) to avoid
# opening a new unauthenticated realtime surface into this codebase's infrastructure.
WEBSITE_CHAT_SESSION = "WebsiteChatSession"

WEBSITE_CHAT_MESSAGE = "WebsiteChatMessage"

# WebsiteAnalyticsEvent -- real page-view events logged every time the real preview/
# render route is hit (see core/websites.py's record_page_view()), backing the
# Google-Analytics/Umami-style admin reporting Sam asked for. This sandbox has no
# live public domain actually serving traffic, so these are genuinely real events off
# whatever traffic this environment's own render/preview route receives (internal
# previews, personal-site visits) -- not fabricated numbers, just honestly limited to
# the traffic that's actually real here.
WEBSITE_ANALYTICS_EVENT = "WebsiteAnalyticsEvent"

# Sales department rebuild (session 92 follow-up) -- Sam's Prospects spec: "Task
# Management: Create: Call tomorrow, Send pricing, Schedule appraisal, Follow up
# after demo." No task/reminder entity tied to a Lead with a due date and completion
# state existed anywhere -- core/bot_tasks.py's tasks are a different concept
# (auto-generated per-role nudges, session 36), not user-created follow-ups. A
# LeadTask is deliberately its own small entity type rather than overloading
# FieldNote, since it has real state (due_at/completed/completed_at) FieldNote's
# plain body/category shape doesn't carry. See core/lead_tasks.py.
LEAD_TASK = "LeadTask"

# Sales/Service Appointments rebuild (session 96 follow-up) -- the single most-
# repeated "not_yet_tracked" gap across this codebase (sales_menu.py's overview()/
# appointments(), sales_overview.py's My Tasks/Daily Dashboard, service_menu.py's
# overview()/appointments(), marketing_menu.py's reporting()/website()). One generic
# entity, not a per-department one -- Sales and Service both book real appointments
# against the same real calendar concept (a customer/lead, a time, an assigned
# employee, a status lifecycle), distinguished by a `department` attribute the same
# way core/field_notes.py's FieldNote already is. See core/appointments.py.
APPOINTMENT = "Appointment"

# Sales Inventory rebuild (session 99 follow-up) -- sales.pdf's Inventory item asks
# for "Reservation/Hold" alongside the payment-based search that already existed
# (core/sales_menu.py's inventory()). A real gap this closes: nothing in this
# codebase previously prevented (or even surfaced) two salespeople desking separate
# Deals against the same unsold Vehicle at once -- a Vehicle only becomes
# unavailable once a Deal actually funds (DateSold gets set). A VehicleHold is a
# short-lived, ordinary graph entity (who placed it, which vehicle, an optional
# linked Customer/Lead, an expires_at) -- same no-separate-store rule as everything
# else in this file. Expiry is computed on read (now vs. expires_at), not a
# background scheduler, matching this codebase's "compute live" convention. See
# core/vehicle_holds.py.
VEHICLE_HOLD = "VehicleHold"

# Up System (session 100 follow-up) -- the first of Sam's ~10 "completely missing"
# dealership workflows. A real walk-in/phone-up log with a genuine round-robin floor
# rotation -- deliberately distinct from core/lead_routing.py's existing least-busy-
# employee auto-assignment (that algorithm optimizes total pipeline load; a real
# dealership "up board" instead rotates strictly through whoever's currently working
# the floor, in a fixed order, so every rep gets a fair shot regardless of how many
# older leads they're still carrying). A logged Up is NOT a new entity type -- it IS a
# real Lead (Source "Walk-In"/"Phone-Up", both already VALID_SOURCES entries in
# core/lead_intake.py since session 47 but never actually driven by anything but
# manual one-off quick-entry until now), tagged with a handful of extra floor-specific
# attributes rather than invented as a parallel object. An UpRotation is the one piece
# that IS a new entity -- a single ordinary graph entity holding the Sales floor's
# current board order + next-up pointer, same no-separate-store rule as everything
# else in this file. See core/up_system.py.
UP_ROTATION = "UpRotation"

# Manager TO / Turn-Over (session 101 follow-up) -- the third of Sam's ~10
# "completely missing" dealership workflows, and one both core/sales_menu.py's
# reporting() and core/sales_overview.py's get_manager_dashboard() had already
# independently flagged as not_yet_tracked. A real dealership "TO" is the moment a
# salesperson who can't close hands the customer to a manager for a second attempt --
# a distinct, timed event with its own lifecycle (requested -> claimed -> resolved),
# not something FieldNote's plain body/category shape carries. Linked to whatever
# entity the TO is actually about (a Lead mid-Up, a Deal mid-desking) via
# linked_entity_id rather than a foreign key, same convention as FieldNote/
# LeadTask/Appointment. Same no-separate-store rule as everything else in this file.
# See core/manager_to.py.
TURN_OVER = "ManagerTO"

# Demo Drive (session 102 follow-up) -- the fourth of Sam's ~10 "completely missing"
# dealership workflows. A real test-drive log: which prospect drove which vehicle,
# with which salesperson, driver's-license capture/verification (the real compliance
# gate before keys ever change hands), out/in odometer, and a start->out->returned
# lifecycle. Distinct from core/appointments.py's Appointment (a scheduled future
# slot) -- a DemoDrive is the live event of a vehicle actually leaving the lot, with
# its own license/odometer fields an Appointment doesn't carry. Linked to the Lead
# it's about and the Vehicle being driven via plain attribute ids, same convention as
# FieldNote/LeadTask/Appointment/ManagerTO -- not a foreign key, no parallel store.
# See core/demo_drive.py.
DEMO_DRIVE = "DemoDrive"

# Credit Application (session 104 follow-up) -- the fifth of Sam's ~10 "completely
# missing" dealership workflows. A real pre-qualification/application record, tied to
# a Customer and optionally a specific Deal (a customer can be pre-qualified before a
# vehicle is even picked, same "not everything needs a Deal first" shape
# core/lead_record.py's Opportunity Creation already established). Deliberately
# distinct from core/deals.py's financing_status/financing_terms fields on Deal --
# those describe ONE deal's outside-lender submission/decision for a specific
# scenario; a CreditApplication is the applicant-level record (income, employment,
# consent, a simulated decision) that can exist before, independent of, or attached
# to a Deal. See core/credit_app.py for the honest scope note on what "decision"
# means here (a deterministic simulated engine, not a real bureau pull).
CREDIT_APPLICATION = "CreditApplication"

# eSignature (session 104 follow-up, second of this session's two workflows) -- the
# sixth of Sam's ~10 "completely missing" dealership workflows. A real signing
# envelope: which signers (customer/co-signer/dealer rep), against a snapshot of a
# specific Deal's generated contract (core/deals.py's generate_contract() output,
# copied at envelope-creation time so what was actually signed doesn't silently
# drift if the Deal record changes later), each carrying a real ESIGN-Act-style
# consent gate before they can sign. See core/esignature.py for the honest scope
# note on what "signing" means here (a typed-name capture, not a cryptographic
# signature -- no DocuSign/HelloSign/Adobe Sign API is connected in this sandbox).
SIGNATURE_REQUEST = "SignatureRequest"

# Operations Tasks (session 106 follow-up #3, "keep going" autonomous continuation) --
# the "Universal Operations Work Queue" from Sam's Operations spec: a single real
# task/ticket store that Assign Owner (Inventory Manager/Title Clerk/Service Manager/
# Lot Manager/Accounting), SLA Tracking (hours-open + overdue computed live off
# created_at, same "compute live" convention as VehicleHold's expires_at -- no
# scheduler), Bulk Actions, and per-task-type Workflow Actions can all sit on top of.
# Deliberately a NEW real entity, not another additive-attribute dict on an existing
# one -- a task is its own first-class object with its own lifecycle (open ->
# in_progress -> closed), independent of whatever entity it's about (a Vehicle, a
# Deal, a ComplianceAlert, nothing at all). Some OperationsTasks are created directly
# by a person; others are synced (idempotently, deduped by source_entity_id, same
# dedup precedent as core/compliance.py's run_full_scan()) from signals this codebase
# already computes elsewhere (wholesale candidates, lot audit discrepancies, open
# compliance alerts) so those existing read-only dashboards gain a real, trackable,
# assignable action layer rather than staying pure reporting. See
# core/operations_tasks.py.
OPERATIONS_TASK = "OperationsTask"

# Inventory department's "Acquisitions" item (Inventory rebuild, second slice).
# Represents a vehicle BEING CONSIDERED for acquisition -- auction/trade/
# direct-purchase sourcing, an Evaluate -> Price Risk -> Estimate Recon ->
# Review Market -> Approve workflow, and a 2-step Purchase Approval chain
# (Inventory Manager -> GM/Admin). Deliberately distinct from AuctionTransaction
# (which only ever represents an ALREADY-acquired auction unit) and from
# Vehicle itself (which may not exist yet at evaluation time) -- this is the
# pre-acquisition decision record. Per Sam's direct instruction (2026-07-17):
# where this evaluation needs market-demand data that doesn't exist anywhere in
# this codebase, core/acquisitions.py's Buy Recommendation Engine now generates
# clearly-labeled SIMULATED market signals (basis="simulated_market_data"),
# same disclosure convention as core/network_benchmark.py's simulated peer
# dealers, rather than leaving it an honest not_yet_tracked gap. See
# core/acquisitions.py.
ACQUISITION_REQUEST = "AcquisitionRequest"

# Inventory department's "Lot Management" item (Inventory rebuild, fifth slice).
# Unlike Pricing/Acquisitions (which needed genuinely external market data that
# doesn't exist anywhere in this codebase), Lot Management's gaps -- Key
# Management, Damage Reports, Showroom Assignments, a real Lot Map -- are
# internal tracking capabilities this codebase simply hadn't built yet, not
# data this system can't ever have. Built as REAL features, not simulated, per
# the established "build it real wherever buildable, simulate only a genuine
# external-world gap" convention this whole rebuild otherwise follows. A
# DamageReport is a first-class entity (not another additive-attribute dict on
# Vehicle) since multiple reports can exist per vehicle over time, each with
# its own severity/status/resolution lifecycle -- same reasoning
# OperationsTask used for the same distinction. See core/lot_control.py.
DAMAGE_REPORT = "DamageReport"

# Inventory department's "Wholesale" item (Inventory rebuild, seventh slice).
# Open Offers, Sold Wholesale Units, and Fund Collection were honest
# not_yet_tracked gaps -- no Offer entity, no wholesale-vs-retail sale
# distinction on Vehicle, no settlement-tracking entity. Same "internal
# tracking gap, not external data gap" call Lot Management/Merchandising
# already made -- built REAL. A WholesaleOffer is a first-class entity (not
# an additive dict on Vehicle) since multiple competing offers can exist per
# vehicle over time (accept one, reject/counter the rest), each with its own
# status lifecycle -- same reasoning DamageReport/OperationsTask used for the
# same distinction. See core/wholesale_desk.py.
WHOLESALE_OFFER = "WholesaleOffer"

# Loaner & Shuttle Management (session 111 follow-up, third of Sam's
# "FEATURES COMPLETELY MISSING" Service list, after DVI and the
# Customer-Facing Approval Center). Three distinct real-world objects, not
# additive attributes on an existing entity -- a loaner vehicle is a
# dealership-owned fleet asset entirely separate from sale inventory (the
# existing Vehicle entity type is NXTDeal's for-sale stock; a loaner has no
# Price/Cost/DateSold, it has a availability/maintenance lifecycle instead),
# a loaner assignment is a first-class timed checkout/checkin event (same
# "own lifecycle, not a dict on something else" reasoning DamageReport/
# WholesaleOffer/OperationsTask already established), and a shuttle request
# is a separate real-world event (a ride, not a vehicle) with its own
# requested->assigned->en_route->completed/cancelled lifecycle. See
# core/loaner_shuttle.py.
LOANER_VEHICLE = "LoanerVehicle"

LOANER_ASSIGNMENT = "LoanerAssignment"

SHUTTLE_REQUEST = "ShuttleRequest"

# Finance's "Payments" item (2026-07-17, session 112 follow-up -- second slice of
# Sam's Retail Automotive Lending Platform expansion, after Portfolio / Loan
# Management). Three distinct real-world objects, each with its own real lifecycle,
# not additive-attribute dicts on FinanceContract -- a Payment is a first-class,
# timestamped ledger entry (many per loan over its life, same "own lifecycle, not a
# dict on something else" reasoning DamageReport/WholesaleOffer/OperationsTask/
# LoanerAssignment already established), an AutoDraft is a standing recurring
# configuration (active/paused, distinct from any one payment it eventually
# produces), and a PromiseToPay is a collections commitment record (kept/broken
# tracked against real payment history, not a payment itself). Processing itself
# (charging a card, pulling an ACH) is honestly SIMULATED -- no real payment
# gateway is connected in this sandbox, same disclosure convention as
# core/campaigns.py's activate_campaign()/core/social_posts.py's publish_post() --
# but a recorded, approved Payment is a REAL, first-class ledger entry that
# core/loan_servicing.py's balance/delinquency computation prefers over its own
# SIMULATED payment-status estimate the moment real payments exist for a loan. See
# core/payments.py.
PAYMENT = "Payment"

AUTO_DRAFT = "AutoDraft"

PROMISE_TO_PAY = "PromiseToPay"

# core/repossessions.py (added 2026-07-17, session 112 follow-up) -- Finance's
# "Repossessions" item, the fourth slice of Sam's "Retail Automotive Lending
# Platform" expansion, the direct continuation of Collections' own
# "repossession_referral" collection stage and Sam's own stated loan lifecycle
# (Lead -> Deal -> Credit -> Approval -> Contract -> Funding -> Loan Servicing ->
# Collections -> Repossession -> Recovery -> Payoff). A RepossessionCase is its own
# first-class, timed lifecycle (referred -> assigned -> located -> recovered ->
# stored -> disposed/redeemed) -- many real, distinct events happen over one case's
# life (agent assignment, recovery, storage, disposition), same "own lifecycle, not
# a dict on something else" reasoning Payment/DamageReport/OperationsTask/
# LoanerAssignment already established -- rather than a dict on the FinanceContract
# itself. Closing a case (repossessed/redeemed) calls core/loan_servicing.py's own
# set_loan_status(), the exact hook that module reserved for this slice since it
# shipped.
REPOSSESSION_CASE = "RepossessionCase"

# core/device_management.py (added 2026-07-17, session 112 follow-up) -- the fifth
# slice of Sam's "Retail Automotive Lending Platform" expansion, backing TWO Finance
# Top Menu items (GPS & Device Management + Starter Interrupt Management) off ONE
# real entity, since a GPS/starter-interrupt unit is one real physical device with
# two operational capabilities, not two separate objects. GPS location telemetry is
# honestly SIMULATED (no real GPS hardware/telematics API is connected in this
# sandbox, same disclosure precedent as core/pricing_desk.py/core/acquisitions.py);
# the starter-interrupt command lifecycle (arm/warn/disable/enable/remove) is real,
# stored state with a real advance-warning-required-before-disable business rule.
INSTALLED_DEVICE = "InstalledDevice"

# core/loan_accounting.py (added 2026-07-17, session 112 follow-up) -- the eighth
# slice of Sam's "Retail Automotive Lending Platform" expansion, closing the "loan
# accounting" half of the "broader Compliance/Accounting/Commissions/Reporting
# extensions" line from Sam's original message. A real cash-basis sub-ledger built
# entirely from core/payments.py's own real Payment records (principal_portion/
# interest_portion, already real once real payments exist) -- an AccountingPeriod is
# its own entity (not an attribute on something else) because a closed period is a
# dealership-wide fact, not owned by any single Loan/Deal/Payment. Real month-end
# close: once closed, no further payment may be posted to that period.
ACCOUNTING_PERIOD = "AccountingPeriod"

# core/general_ledger.py + core/bank_reconciliation.py (added 2026-07-17, session 112
# follow-up) -- Sam's direct instruction after the Retail Lending Platform arc's
# explicitly-named items all closed: "lets keep going, simply create the fake data
# that is needed to build them" -- General Ledger and Bank Reconciliation, previously
# left as honest not_yet_tracked gaps (no chart of accounts / bank-transaction feed
# exists anywhere in this codebase), now built with clearly-disclosed SIMULATED data
# filling exactly what's missing, blended with entries synced from already-real data
# (Loan Accounting's posted Payments, funded Deals' real Vehicle Price/Cost) wherever
# real data exists. A GlEntry is its own entity (not an attribute on something else)
# since many entries accumulate over time and aren't owned by any single Loan/Deal.
GL_ENTRY = "GlEntry"

# A BankTransaction is a simulated bank-feed row -- its own entity since many
# transactions accumulate over time, matched (or not) against real/simulated GlEntry
# cash postings via core/bank_reconciliation.py's real matching engine.
BANK_TRANSACTION = "BankTransaction"

# core/smart_audiences.py (added 2026-07-17, Marketing Growth Platform kickoff) --
# Sam's reframe of Marketing into a full "NXTDeal Growth Platform," first slice:
# CRM (Customer 360 + Smart Audiences + Lead Scoring). A SmartAudience is a saved,
# reusable, no-code segment DEFINITION (a condition tree over real Customer/Vehicle/
# FinanceContract/Deal attributes) -- its own entity, distinct from
# core/marketing_lists.py's MarketingList, because a List is a frozen membership
# snapshot while a SmartAudience is a live rule that gets re-evaluated against the
# graph on every read (same relationship MarketingList's own build_list_from_pool()
# already has to core/campaigns.py's build_audience() pools -- a SmartAudience can be
# saved into a List the same way, but isn't one itself).
SMART_AUDIENCE = "SmartAudience"

# PURL Platform (Marketing Growth Platform, PURLs slice): a personalized URL --
# dealer.com/john-smith -- generated for one specific Customer or Lead, carrying an
# unguessable token (same secrets.token_urlsafe() convention as
# core/approval_center.py/core/appointment_scheduling.py's public links). Distinct
# from a plain approval/checkin link because a PURL's public page renders a real,
# genuinely personalized OFFER (current vehicle, trade equity, inventory matches,
# payment reduction) rather than a single fixed action, and every visit/lead
# generated through it is tracked for real, closing this codebase's own honest
# "Website Activity" gap (core/customer_360.py's not_yet_tracked note) for the one
# channel where a visitor's identity is genuinely known up front.
PERSONALIZED_URL = "PersonalizedURL"

# core/permissions_registry.py (added 2026-07-18, Administration Control Center
# kickoff -- Sam's own framing: "Administration currently appears to monitor the
# system. It should run the platform," Roles & Permissions picked as the first
# slice). A PermissionOverride is a real, per-employee grant or revoke of one
# granular permission beyond that employee's role default -- its own entity (not a
# dict on Employee) since one employee can accumulate several overrides over time,
# each independently grantable/revocable/audited, same "own lifecycle" reasoning
# DamageReport/OperationsTask/RepossessionCase already established in this codebase.
PERMISSION_OVERRIDE = "PermissionOverride"

# An ApprovalRequest is the real, honest backing for Sam's "Employee -> Manager ->
# Director -> Executive" approval-hierarchy ask -- routed through a real 3-tier
# system (staff/manager/executive, core/bot_tasks.py's own already-real infer_tier()
# off Employee.Title, session 36) rather than a fabricated 4th "Director" tier this
# codebase has no Title-keyword data to honestly distinguish (director-titled
# employees already collapse into the "manager" tier via infer_tier()'s own
# _MANAGER_TITLE_PHRASES). Its own entity, not a dict on the thing being approved,
# since a request accumulates a real multi-step decision trail over its life.
APPROVAL_REQUEST = "ApprovalRequest"

# core/vendor_management.py (Administration Control Center rebuild, continued
# 2026-07-18/19) -- VENDOR (declared near the top of this file, "Vendor") has
# existed since early sessions but was never once instantiated by any importer/
# seed script (confirmed absent, core/administration_menu.py's vendors() reused
# Connection records as an honest proxy instead). This module is the first real
# Vendor record: contact info, a contract term, a monthly cost, a renewal date --
# genuine internal data this codebase simply never had a place to put, not an
# external-data gap.

# A real, per-employee API key for programmatic/integration access -- distinct
# from core/auth.py's session tokens (short-lived, issued at login) since an API
# key is meant to be long-lived and independently revocable without logging the
# employee out of their own interactive session. Its own entity (not a dict on
# Employee) since one employee can hold several keys over time, each independently
# revocable and auditable.
API_KEY = "ApiKey"

# One real, singleton settings record -- core/system_config.py -- covering both
# "Organizations" (dealership profile: name/address/EIN/locations) and "System
# Configuration" (business hours, default currency/timezone, feature toggles).
# Combined into one entity rather than two: this codebase is one NXTDeal
# instance per dealer (see the NXTDeal Hub / Multi-Tenant Architecture section of
# CLAUDE.md) -- "Organizations" here means this ONE dealer's own profile/locations,
# not multiple separate dealers, which is the Hub's job, not Administration's.
SYSTEM_CONFIG = "SystemConfig"

# core/data_backup.py -- real metadata for a real storage/graph.json snapshot
# (Data Management's "Backup" ask). The snapshot FILE itself lives in
# storage/backups/, this entity is just the real, listable/restorable record of
# it -- filename, size, who triggered it, when.
DATA_BACKUP = "DataBackup"

# core/workflow_automation.py (Administration Control Center rebuild,
# continued 2026-07-18/19) -- admin.pdf's "Workflow Automation" item: a real,
# admin-configurable "if this real condition, then this real action" rule
# engine, platform-wide, distinct from core/bot_tasks.py's per-employee
# suggested-task layer. AUTOMATION_RULE is the stored rule (trigger type +
# threshold + action type + params + active flag); AUTOMATION_EXECUTION is a
# first-class, own-lifecycle log entry per (rule, entity) firing -- not a
# dict on the rule, since one rule accumulates many real firings over its
# life, same "own lifecycle" reasoning OperationsTask/DamageReport/Payment
# already established elsewhere in this codebase.
AUTOMATION_RULE = "AutomationRule"
AUTOMATION_EXECUTION = "AutomationExecution"

# core/strategic_planning.py -- Readiness reframe, item #9, "A completely new
# area." STRATEGIC_OBJECTIVE is a real quarterly Objective/Goal/Budget record
# (department + quarter/year + target + optional budget), status computed
# LIVE on read rather than stored, same convention core/performance_
# readiness.py already established for readiness_pct -- never a manually-set
# status divorced from real progress. STRATEGIC_INITIATIVE is a real,
# separately-lifecycled Initiative ("New Website Launch," "GPS Rollout," "New
# Service Center," "New BHPH Program") -- its own entity, not a dict on the
# Objective, since an initiative accumulates its own real status/progress
# history independent of any one quarter's objective, same "own lifecycle"
# reasoning OperationsTask/DamageReport/Payment/AutomationExecution already
# established. See core/strategic_planning.py's own module docstring for the
# full real-vs-manual progress-tracking breakdown and how this relates to
# core/system_config.py's pre-existing department_goals mechanism.
STRATEGIC_OBJECTIVE = "StrategicObjective"
STRATEGIC_INITIATIVE = "StrategicInitiative"

# core/workforce.py -- Operations' new "Workforce" Top Menu item (2026-07-19,
# continuing Sam's six-pillar spec after the Customer Intelligence Layer and
# Unified Communications Hub). Nothing anywhere in this codebase previously
# modeled staff shift scheduling or time-off requests (confirmed absent via
# grep) -- both are real, first-class, own-lifecycle entities rather than a
# dict on Employee, since one employee accumulates many shifts/requests over
# time, same "own lifecycle" reasoning OperationsTask/DamageReport/Payment/
# AutomationExecution/StrategicInitiative already established.
EMPLOYEE_SHIFT = "EmployeeShift"
TIME_OFF_REQUEST = "TimeOffRequest"

# core/marketing_studio.py -- Marketing's new "AI Marketing Studio" Top Menu item
# (2026-07-19, continuing Sam's six-pillar spec after Workforce). Nothing anywhere in
# this codebase previously logged the real content drafts these already-real, already-
# kill-switched wizards (core/email_wizard.py, core/website_wizard.py,
# core/social_caption_wizard.py, core/advertising.py's generate_ad_recommendation)
# generate -- each one is called ad hoc from its own screen with no shared history.
# A MarketingContentDraft is a real, own-lifecycle entity (drafted -> applied/
# discarded) logging every generation made THROUGH the Studio -- one real
# cross-channel content library, same "own lifecycle" reasoning OperationsTask/
# DamageReport/Payment/AutomationExecution/StrategicInitiative already established.
# The Studio dispatches to the existing wizard functions rather than duplicating any
# generation logic -- see core/marketing_studio.py's own module docstring for the
# full per-content-type mapping and the honest note on what's deliberately excluded
# (Website's whole-site Setup Wizard bootstrap, Events' Campaign Generator -- both
# already have their own dedicated flows/UI).
MARKETING_CONTENT_DRAFT = "MarketingContentDraft"

# core/websites.py's Website Personalization (2026-07-19, closing the "AI Marketing
# Studio + Website Personalization" pillar). A PersonalizationVariant is NOT a
# separate entity -- it's an additive list on an existing WebsiteSection dict, same
# "additive attribute, not a new entity" convention core/deals.py's trade_in/
# delivery_checklist already established, since a variant is a small alternate-
# copy overlay tied 1:1 to the section it belongs to, not an independently
# trackable real-world event. The "PVAR" id-generator prefix backs each variant's
# own id within that list (so it can be referenced/removed), not a new entity type.

# core/coaching.py -- the fourth and final pillar of Sam's "NXTDeal Workforce AI"
# vision (2026-07-19), closing out Assistant ("Help Me With This Screen")/
# Automation/Coverage/Coaching. Scoped directly with Sam via AskUserQuestion before
# any code was written, given real employee-evaluation content is a materially
# higher HR/legal-risk category than the rest of this session's operational
# business-intelligence work: Intensity Tiers change bot nudge frequency/tone only
# (no new mutation capability), AI Performance Reviews are a data-grounded draft
# ONLY -- never auto-sent to the employee, no AI-generated subjective judgment
# language, real numbers plus factual templated framing only -- and AI Career
# Pathing surfaces a real internal-mobility signal off already-real performance
# data compared against core/bot_tasks.py's own infer_tier(), never fabricated
# career advice.
#
# CoachingIntensityOverride mirrors core/permissions_registry.py's
# PermissionOverride pattern exactly (a new override for the same scope+target
# deactivates, not deletes, the prior one -- full history stays inspectable).
# PerformanceReview is a real, own-lifecycle entity (draft -> finalized -> shared),
# same "own lifecycle" reasoning OperationsTask/DamageReport/Payment/
# AutomationExecution/StrategicInitiative/EmployeeShift/MarketingContentDraft
# already established -- a manager can edit/discard a draft before it's ever
# shown to the employee, matching the same "AI drafts, a human decides" contract
# core/marketing_studio.py's MarketingContentDraft already established for
# marketing copy, applied here to a much more sensitive content type.
COACHING_INTENSITY_OVERRIDE = "CoachingIntensityOverride"
PERFORMANCE_REVIEW = "PerformanceReview"

# core/ai_audit.py -- security-hardening pass (2026-07-20), Task #5 "Build
# comprehensive AI action audit trail." core/ai_management.py's own _CALL_STATS
# has been real but in-memory-only (attempted/succeeded/fell_back/blocked
# counters, reset on every process restart) since it shipped -- useful for a
# live dashboard, but not a durable record of WHICH call happened, on whose
# behalf, or what was actually asked/answered. AiActionLog is the real,
# persisted, per-call record on top of that -- own-lifecycle entity (many
# records accumulate over the life of one AI feature), same reasoning
# OperationsTask/Payment/AutomationExecution/MarketingContentDraft/
# PerformanceReview above already established, not a dict bolted onto
# something else. Deliberately bounded: prompt_summary/output_summary are
# truncated at write time (core/ai_audit.py's _MAX_SUMMARY_CHARS) so this can
# never grow into an unbounded transcript store -- a real, honest usage/audit
# trail, not a second copy of every conversation. See core/ai_audit.py's own
# module docstring for why this is added to the in-memory ledger on every
# call but deliberately NOT saved to disk on every call (a real
# save_graph()-scale cost on ai_assistant's hot chat path would repeat the
# exact mistake core/trigger_alerts.py's run_scan() already made and had to
# fix, per this file's own documented history).
AI_ACTION_LOG = "AiActionLog"

# core/bot_permissions.py -- security-hardening pass (2026-07-20), Task #7
# "Build Bot Permission Layer." A BotCapabilityGrant is a real, first-class,
# explicit grant (or deny) of one of the Bot's 4 real unattended-mutation
# capabilities at one of three scopes (employee/department/dealer_wide),
# most-specific-wins -- own entity, not a dict on Employee, same "own
# lifecycle" reasoning PermissionOverride/ApprovalRequest above already
# established, since one employee/department/dealer accumulates several
# grants over time, each independently grantable/revocable/audited.
# Deliberately the OPPOSITE default posture from PermissionOverride (which
# is default-ALLOW, a role gets a permission unless overridden): no bot
# capability is ever granted to anyone/anything until an explicit
# BotCapabilityGrant record says so -- see core/bot_permissions.py's own
# module docstring for the full default-deny design and exactly where each
# of the 4 capabilities is enforced.
BOT_CAPABILITY_GRANT = "BotCapabilityGrant"

# core/glba_program.py -- security-hardening pass (2026-07-20), Task #11
# "Add GLBA + PCI-DSS readiness controls." A single, real, cited-federal-law
# check already existed (core/compliance_rules.py's
# _check_glba_safeguards_encryption(), blocking a plaintext-HTTP Connection)
# but nothing tracked the broader GLBA Safeguards Rule (16 CFR 314)
# Information Security Program itself -- the 7 real named program
# components (Qualified Individual, Risk Assessment, Safeguards
# Implementation & Testing, Staff Training, Service Provider Oversight,
# Incident Response Plan, Board Reporting) a real dealership finance
# operation is expected to document and keep current. GlbaProgramItem is
# one real, first-class, per-component tracking record -- own entity, not a
# dict on some other module, since each of the 7 components has its own
# independent status/owner/review-date/notes lifecycle that accumulates
# real history over time, the same "own lifecycle" reasoning
# PermissionOverride/ApprovalRequest/BotCapabilityGrant above already
# established. See core/glba_program.py's own module docstring for the
# full component catalog and the honest, computed-not-fabricated
# readiness-percentage math.
GLBA_PROGRAM_ITEM = "GlbaProgramItem"

# core/sso_config.py + core/sso.py -- security-hardening pass (2026-07-20),
# Task #14 "SSO scaffolding (SAML/OIDC-ready)." A real OIDC authorization-
# code-flow client -- works against any standards-compliant IdP (Entra ID,
# Okta, Google Workspace, Auth0) with state/nonce CSRF protection and
# ID-token signature verification via the provider's real JWKS endpoint.
# SsoConfig is a real, per-dealer, fixed-id SINGLETON -- modeled directly on
# core/system_config.py's own _CONFIG_ID/_get_or_create()/additive-backfill
# pattern, since this codebase is one NXTDeal instance per dealer (see the
# NXTDeal Hub / Multi-Tenant Architecture section of CLAUDE.md) -- exactly
# one IdP configuration record per tenant, not a dict keyed by dealer_id. Own
# entity type rather than folding these fields onto SystemConfig itself:
# client_secret is a meaningfully more sensitive value than anything already
# on that record (business hours, feature flags, department goals), and
# keeping SSO's own admin-only read/write surface (core/sso_config_api.py)
# separate from SystemConfig's broader ADMIN/OPERATIONS-viewable one avoids
# accidentally widening who can see an OAuth client secret. Honest, stated
# gap: no live IdP client_id/secret/issuer exists in this sandbox to
# complete a real round-trip against, so this ships as real, wired code
# that's never been exercised against a live Entra/Okta/Auth0 tenant, not as
# a live-verified integration -- see core/sso.py's own module docstring.
SSO_CONFIG = "SsoConfig"

# core/communications_hub.py -- Unified Communications Hub (2026-07-21). Sam's own
# cross-cutting gap analysis of a competitor sales deck flagged "Communications
# Platform" as the single biggest missing area NXTDeal had: "Calling, Texting,
# Recording, Notes, Conversation History with: Recording, Transcription, AI
# Analysis, Coaching, Automation." core/unified_communications.py (session 19,
# Operations' "Communications" Top Menu item) already composes a real,
# read-only, cross-department FEED over three siloed FieldNote-backed logs
# (Sales/Service/Finance) -- but FieldNote's own generic {department, category,
# body, linked_entity_id} shape has no room for a real per-call recording/
# transcription/sentiment/follow-up/AI-summary record without breaking every
# existing FieldNote consumer. A Communication is therefore its own, new,
# first-class entity (not a FieldNote, not a dict on something else) -- many
# communications accumulate per Lead/Customer/Deal/ServiceRecord/
# FinanceContract over time, each with its own real channel/direction/
# transcript/sentiment/follow-up/AI-summary state, same "own lifecycle"
# reasoning OperationsTask/DamageReport/Payment/AutomationExecution/
# MarketingContentDraft/PerformanceReview above already established. Real
# phone-call recording/transcription/sentiment is honestly SIMULATED (no
# telephony/call-recording vendor is connected anywhere in this codebase),
# same disclosure convention as core/pricing_desk.py/core/acquisitions.py's
# own simulated-data policy (session 110) -- every simulated field carries a
# real `basis` label. The AI Summary is genuinely real (an isolated,
# kill-switched OpenAI call, same core/email_wizard.py pattern, with an
# honest non-AI fallback). See core/communications_hub.py's own module
# docstring for the full "compose with, don't replace, core/
# unified_communications.py" reasoning, and the explicit note that Sales'
# OWN, separate "communications" Top Menu item (core/sales_menu.py's
# communications(), components/CommunicationsBoard.tsx) is untouched by
# this module.
COMMUNICATION = "Communication"

# core/workflow_engine_v2.py -- Operations Workflow Engine v2 (2026-07-20/21). Sam's
# own reframe: a workflow must stop being "a report with steps" and become "the
# primary way work gets done in NXTDeal." Deliberately parallel to, not a
# replacement for, core/workflow_tracking.py's own WORKFLOW_INSTANCE entity (session
# 53) -- that flat, single-current_stage_index engine still backs every OTHER
# department's already-shipped job-workflow screens (Sales/Service/Inventory/
# Finance/Marketing/Administration/Readiness/Network), all explicitly out of scope
# for this pilot. WorkflowInstanceV2 tracks a real per-STEP structure (its own
# status/owner/tasks/evidence/approvals/comments/blocked-reason), not just a single
# stage pointer -- see core/workflow_definitions_v2.py for the v2 catalog schema and
# core/workflow_engine_v2.py's own module docstring for the full design.
WORKFLOW_INSTANCE_V2 = "WorkflowInstanceV2"

# core/call_center.py -- Phase 2: Communications Platform, Voice (2026-07-22). Sam's
# own kickoff: "Voice * Call Recording * Call Routing * Voicemail." A Call is its own
# first-class, own-lifecycle entity (ringing -> connected -> ended/missed/voicemail),
# not a dict on Employee/Lead/Customer, matching the "own lifecycle" reasoning
# OperationsTask/DamageReport/Payment/Communication already established -- a phone
# line accumulates many distinct call events over time, each with its own real
# routing decision, duration, and (simulated) recording. Voicemail, the Coaching
# Score (Phase 2's "AI Voice: Coaching"/"BDC Center: Call Scoring"), and the QA
# Review (BDC Center) are all embedded dicts directly on the Call itself -- each is
# real per-call state with no independent lifecycle of its own, following the
# opposite (embed, don't fork a new entity type) side of the same design test.
# Every terminal call (ended/missed/voicemail) synthesizes exactly one
# core/communications_hub.py Communication record via log_communication() rather
# than parallel-logging a second contact-history store.
CALL = "Call"

# NXTDeal AI Workforce (2026-07-24): a customer-facing AI worker (one per role -- AI
# Receptionist/BDC/Sales/Service/Marketing/Finance/Collections/Operator) that HANDLES
# customer interactions itself, and an AiWorkerAction (one proposed action per handled
# interaction, executed or drafted for a human). Both ordinary entities in the same
# single ledger -- NOT a new store. See core/ai_worker.py.
AI_WORKER = "AiWorker"

AI_WORKER_ACTION = "AiWorkerAction"

# NXTDeal Verify (2026-07-24): a Digital Retail identity-tier session -- one visitor's climb
# from anonymous -> verified_human (email+SMS) -> identity_verified (license+selfie) ->
# credit_verified (credit application). Gates the self-service purchase journey. Ordinary
# entity in the single ledger. See core/dealeros_verify.py.
VERIFICATION = "Verification"

# NXTDeal execution modes (2026-07-24, Digital Retail DR-2): a per-dealer singleton policy
# holding the active execution mode (human/ai/customer/hybrid) for each workflow. See
# core/execution_modes.py.
EXECUTION_POLICY = "ExecutionPolicy"

# AI Negotiation Engine (2026-07-24, Digital Retail DR-3): a per-dealer singleton
# NegotiationRules (the profit envelope -- gross floors, discount/trade/payment/loss ceilings)
# and a DealSession (one time-boxed negotiation per deal, with offer history + escalation).
# See core/negotiation_engine.py.
NEGOTIATION_RULES = "NegotiationRules"

DEAL_SESSION = "DealSession"

# Home Delivery + Try Before You Buy (2026-07-24, Digital Retail DR-6): a Delivery (store
# pickup / home delivery / third-party, with driver + window + status timeline), a
# TryBeforeYouBuy trial (identity/insurance/deposit/release/decision + return workflow), and a
# per-dealer singleton TbybProgram (max hours/miles, deposit, gates). See
# core/delivery_fulfillment.py.
DELIVERY = "Delivery"

TRY_BEFORE_YOU_BUY = "TryBeforeYouBuy"

TBYB_PROGRAM = "TbybProgram"

# Integration provider seam (2026-07-24): a per-dealer singleton recording the intended
# external provider per capability (notifications/payments/identity/insurance/credit_bureau).
# See core/integrations_registry.py.
INTEGRATION_SETTINGS = "IntegrationSettings"

# Marketplace (2026-07-24): a per-dealer record that a Marketplace listing is installed.
# Soft status (installed/removed) since the graph is append-only. See core/marketplace.py.
MARKETPLACE_INSTALL = "MarketplaceInstall"

# MySales rep referral/reward program (2026-07-24): a per-rep RepReferralProfile holds that
# salesperson's shareable referral code; a Referral is one tracked referral event — either
# the rep getting their dealership to book a NXTDeal demo / convert, or recruiting another
# salesperson onto MySales — with a status flow and an accrued reward. See core/rep_referrals.py.
REP_REFERRAL_PROFILE = "RepReferralProfile"

REFERRAL = "Referral"

# MySales light self-accounting (2026-07-24): a rep's linked BankAccount (balances +
# simulated transactions via the Plaid seam), a Budget (category monthly limit), and a
# Commission entry (projected/pending/paid) so a rep sees banking + earnings together. Keyed
# by employee_id. See core/rep_finance.py.
BANK_ACCOUNT = "BankAccount"

BUDGET = "Budget"

COMMISSION = "Commission"

# AI Demo Platform (2026-07-24): one prospect's guided demo session in a DEALEROS_DEMO tenant —
# persona, mode, and analytics (pages viewed, questions, modules, time). Non-persistent tenant,
# so this lives only in memory for the life of the demo process. See core/demo_mode.py.
DEMO_SESSION = "DemoSession"

# Freemium Platform / Foundation-plus-Modules enforcement (2026-08-03): a per-dealer singleton
# recording which paid Modules are entitled (and at what level: free/professional/enterprise) and
# the usage caps for metered Foundation features. This is the tenant-side ENFORCEMENT record the
# running product reads before serving a Module feature — the piece the Hub's Module Management /
# Licensing config could only ever *describe* before. Defaults to the full-build "reference"
# profile (everything on, caps unlimited) so an existing instance (Dealer1) is unchanged; a
# "foundation" profile gates down to Tier 0. Same fixed-id-singleton convention as
# core/system_config.py's SystemConfig. See core/entitlements.py.
ENTITLEMENT = "Entitlement"

# Freemium Platform / AI Spend Governor (2026-08-03, Phase 5): a per-dealer singleton holding the
# bring-your-own-key AI provider posture, per-user consumption limits (an admin-set default plus
# per-user overrides), and the per-user/per-month AI usage counters the governor meters against
# those limits. NXTDeal stays model-agnostic -- the dealer supplies their own key and the cost of
# consumption sits with them; this record is the spend governor on top of that. See core/ai_spend.py.
AI_SPEND_POLICY = "AiSpendPolicy"

# MySales personal AI config (2026-08-03, Freemium Phase 5+). One per rep (keyed by employee_id):
# the rep's own AI on/off, their optional bring-your-own-key (provider + masked hint; the raw key is
# never stored here), and their tiered-routing preferences (route routine tasks to a cheap model,
# premium tasks to a high-end one, and prefer on-device when the native app can). MySales is
# personal-account-scoped (personal-tools layer), so this is per-rep, not per-dealer. See
# core/mysales_ai.py.
MYSALES_AI_CONFIG = "MySalesAiConfig"

# Generalized per-user, per-app AI model-selector config (2026-10-24).
# One per (app_slug, user_id): the user's AI on/off, optional bring-your-own-key
# (provider + masked hint; raw key never stored), and tiered routing prefs.
# MySales personal uses app_slug="mysales" and delegates here from mysales_ai.py.
# Staff companion apps (salesapp, reception, serviceops) use their slug with the
# employee_id. Customer-facing apps (showroom, mygarage, kiosk) use dealer-level
# only — no per-customer entity. See core/ai_config.py.
AI_CONFIG = "AiConfig"

# Programming Schedule tracker (2026-10-24): work items for the NXTDeal production
# bridge. Tracks features, bugs, security issues, and tech debt with phases, priority,
# assignee, progress, estimated/logged hours, and dependencies. Keyed PS-{title-slug}.
# See core/programming_schedule.py.
PROGRAMMING_SCHEDULE = "ProgrammingSchedule"

# CI/CD pipeline integration (2026-10-25): tracks GitHub Actions CI runs,
# Coolify deployment runs, and a message channel for bidirectional communication
# between the desktop Hermes agent and the VPS Hermes agent (with Tailscale).
# All are ordinary entities in the same ledger — no separate store.
# See core/ci_deploy_pipeline.py.
CI_PIPELINE_RUN = "CIPipelineRun"
DEPLOYMENT_RUN = "DeploymentRun"
DEPLOYMENT_CHANNEL = "DeploymentChannel"

# Programming Schedule run + audit trail (2026-10-25, NXTDEAL-SCHEDULE-SOURCE-OF-TRUTH,
# Section 1). A ScheduleRun tracks one worker's execution of a PS item (which machine,
# which model, tokens, cost, outcome). A ScheduleEvent is an append-only audit log
# of status changes, claims, completions — who or what changed what, with evidence.
# Both are ordinary entities in the same single ledger — no separate store.
SCHEDULE_RUN = "ScheduleRun"
SCHEDULE_EVENT = "ScheduleEvent"
