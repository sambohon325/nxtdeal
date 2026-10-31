"""
core/workflow_definitions_v2.py -- Operations Workflow Engine v2, the static
catalog half (paired with core/workflow_engine_v2.py's runtime engine).

Sam's own reframe (2026-07-19/20), quoted directly because it's the design brief
this whole module is built against: a workflow must stop being "a report with
steps" and become "the primary way work gets done in NXTDeal" -- a real
operations manager should touch 20-50 workflow instances a day, not interact with
4 high-level categories. Every workflow must always answer: I have a problem ->
what are the steps to resolution -> who owns each step -> what can AI automate.

This is a DELIBERATELY PARALLEL catalog to core/workflow_catalog.py's existing
36-entry WORKFLOW_CATALOG (4 job-workflow buttons x 9 departments, session 53+),
not a replacement -- that catalog's flat 5-stage/5-tab shape still backs every
OTHER department's already-shipped job-workflow screens (Sales/Service/Inventory/
Finance/Marketing/Administration/Readiness/Network), all explicitly out of scope
for this pilot. Operations is the pilot department Sam named directly ("Ok, so
this is for the workflow tabs, starting with operations"). The long-term goal,
stated by Sam and preserved here rather than silently dropped: standardize every
workflow in NXTDeal around Workflow -> Step -> Task -> Approval -> Automation ->
Completion, with every department eventually using this same engine -- migrating
the other 8 departments is real, scoped future work, not attempted in this pass.

Each v2 workflow definition carries a real per-STEP structure -- something the
original catalog's flat `stages`/`tabs` lists never had:

  - `owner_role`: which of this codebase's real roles (core/permissions.py --
    ADMIN/OPERATIONS/SALES/MARKETING/SERVICE/FINANCE) typically owns this step.
  - `automation_tier`: one of TIER_HUMAN_ONLY / TIER_ASSISTED / TIER_AUTONOMOUS --
    mirroring core/ai_execution_tier.py's own Informational/Assisted/Autonomous
    convention (that module's own TIER_DESCRIPTIONS are quoted in spirit below),
    but scoped to a workflow STEP/action rather than a whole AI feature. Every
    tier assignment carries its own short, specific, checkable rationale string,
    matching this codebase's established "never a blanket assumption" convention
    for this kind of classification.
  - `automation_note`: the rationale for that tier, always present.
  - `sla_hours`: an honest, stated escalation threshold -- how long this specific
    step may sit before core/workflow_engine_v2.py's stalled-instance detection
    flags it. No fabricated per-step timing data exists anywhere in this
    codebase to derive these from; they are reasonable, stated defaults an
    Operations manager can tune later (a future admin-editable-threshold pass is
    explicitly not attempted here).
  - `real_source_hint`: a plain, human-readable pointer to which already-real
    Operations backend module/function this step's real data or action should
    come from (vehicle_lifecycle.py, document_workflows.py, lot_control.py,
    operations_tasks.py, operations_scheduling.py, vendor_management.py,
    workforce.py, operations_alerts.py, core/coaching.py's PerformanceReview) --
    documentation for a human/future session wiring real actions onto a step,
    not itself an executable dispatch table. core/workflow_engine_v2_api.py's
    own `get_instance_ai_state()` and a handful of steps below DO call directly
    into these real modules where the mapping is unambiguous and low-risk (see
    each workflow's own comment) -- everywhere else, this field is honest
    documentation of "where the real data lives," not a claim that this step
    already executes it.

TIER_HUMAN_ONLY steps are never candidates for core/workflow_automation.py's rule
engine or any unattended AI action -- a human must take the action themselves.
TIER_ASSISTED steps may have AI draft content (a message, a document request) but
a human must review and send/apply it. TIER_AUTONOMOUS steps may run unattended --
per core/ai_execution_tier.py's own established rule, any step actually wired to
run autonomously must still sit behind a real Approval Chain
(core/permissions_registry.py) before it's allowed to fire with no human reviewing
that specific instance; this catalog states the TIER, not a claim that autonomous
execution is already wired for every such step (see core/workflow_engine_v2.py's
own module docstring for exactly which steps have real automation behind them
today vs. which are catalog-only classification for now).
"""

CATEGORY_VEHICLE = "vehicle"
CATEGORY_COMPLIANCE = "compliance"
CATEGORY_OPERATIONAL = "operational"
CATEGORY_EMPLOYEE = "employee"

# Sales categories (added alongside the Sales Workflow Engine v2 rollout) --
# Sam's own explicit reframe: organize Sales workflows by customer LIFECYCLE
# (Lead -> Contact -> Appointment -> Showroom -> Demo -> Deal -> Finance ->
# Delivery -> Ownership -> Retention), not by flat department-task list. These
# 5 categories are that lifecycle collapsed into groups: Prospecting (finding/
# working leads before first appointment), Engagement (the in-person/scheduled
# visit), Deals (desking/trade/credit), Finance (F&I/contract execution),
# Retention (delivery through owning-the-relationship-after-the-sale).
CATEGORY_PROSPECTING = "prospecting"
CATEGORY_ENGAGEMENT = "engagement"
CATEGORY_DEALS = "deals"
CATEGORY_FINANCE = "finance"
CATEGORY_RETENTION = "retention"

CATEGORIES = (
    CATEGORY_VEHICLE,
    CATEGORY_COMPLIANCE,
    CATEGORY_OPERATIONAL,
    CATEGORY_EMPLOYEE,
    CATEGORY_PROSPECTING,
    CATEGORY_ENGAGEMENT,
    CATEGORY_DEALS,
    CATEGORY_FINANCE,
    CATEGORY_RETENTION,
)

CATEGORY_LABELS = {
    CATEGORY_VEHICLE: "Vehicle Workflows",
    CATEGORY_COMPLIANCE: "Compliance Workflows",
    CATEGORY_OPERATIONAL: "Operational Workflows",
    CATEGORY_EMPLOYEE: "Employee Workflows",
    CATEGORY_PROSPECTING: "Prospecting",
    CATEGORY_ENGAGEMENT: "Engagement",
    CATEGORY_DEALS: "Deals",
    CATEGORY_FINANCE: "Finance",
    CATEGORY_RETENTION: "Retention",
}

TIER_HUMAN_ONLY = "human_only"
TIER_ASSISTED = "assisted"
TIER_AUTONOMOUS = "autonomous"

STEP_AUTOMATION_TIERS = (TIER_HUMAN_ONLY, TIER_ASSISTED, TIER_AUTONOMOUS)

STEP_TIER_DESCRIPTIONS = {
    TIER_HUMAN_ONLY: "A person must take this action. Never a candidate for AI/automation execution.",
    TIER_ASSISTED: "AI may draft real content (a message, a document request, a summary) here, but a human must review and explicitly apply/send it before it has any real-world effect.",
    TIER_AUTONOMOUS: "May run unattended once a real Approval Chain covers it (core/permissions_registry.py) -- low-risk scheduling/notification actions only, never a financial or personnel decision.",
}

DEFAULT_SLA_HOURS = 48


def _step(key, label, owner_role, tier, note, sla_hours=DEFAULT_SLA_HOURS, real_source_hint=None):
    if tier not in STEP_AUTOMATION_TIERS:
        raise ValueError(f"invalid automation_tier '{tier}' for step '{key}'")
    return {
        "key": key,
        "label": label,
        "owner_role": owner_role,
        "automation_tier": tier,
        "automation_note": note,
        "sla_hours": sla_hours,
        "real_source_hint": real_source_hint,
    }


def _workflow(key, category, title, purpose, entity_type, steps, escalate_to_role="OPERATIONS"):
    return {
        "key": key,
        "category": category,
        "title": title,
        "purpose": purpose,
        "entity_type": entity_type,
        "steps": steps,
        "escalation_rules": {
            "default_stalled_hours": DEFAULT_SLA_HOURS,
            "escalate_to_role": escalate_to_role,
        },
    }


# ---------------------------------------------------------------------------
# VEHICLE WORKFLOWS (7)
# ---------------------------------------------------------------------------

_VEHICLE_INTAKE = _workflow(
    "operations.vehicle_intake_v2",
    CATEGORY_VEHICLE,
    "Vehicle Intake & Recon",
    "Move a newly acquired vehicle from acquisition through inspection, repair, "
    "detail, and merchandising to frontline-ready -- Sam's own literal example "
    "workflow (Acquire -> Inspect -> Repair -> Detail -> Photograph -> Merchandise "
    "-> Price -> Frontline).",
    "Vehicle",
    [
        _step("acquire", "Acquire", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real purchase/trade-in decision -- never automated.",
              real_source_hint="core.acquisitions (Inventory dept) / core.deals.trade_in"),
        _step("inspect", "Inspect", "SERVICE", TIER_ASSISTED,
              "AI can draft the inspection checklist and flag likely issues from the "
              "vehicle's own condition/mileage, but a technician performs and records it.",
              real_source_hint="core.vehicle_inspection (DVI)"),
        _step("repair", "Repair", "SERVICE", TIER_HUMAN_ONLY,
              "Physical mechanical/body work -- never automated.",
              real_source_hint="core.vehicle_lifecycle.assign_vendor/update_vendor_status"),
        _step("detail", "Detail", "OPERATIONS", TIER_ASSISTED,
              "AI can schedule/track the detail vendor assignment; a person confirms quality.",
              real_source_hint="core.vehicle_lifecycle.assign_vendor"),
        _step("photograph", "Photograph", "MARKETING", TIER_ASSISTED,
              "AI can flag a vehicle as missing photos and draft a merchandising task; "
              "a person takes and uploads the real photos.",
              real_source_hint="core.merchandising.add_vehicle_image"),
        _step("merchandise", "Merchandise", "MARKETING", TIER_ASSISTED,
              "AI can draft a listing description; a person reviews before it publishes.",
              real_source_hint="core.merchandising.get_vdp_health"),
        _step("price", "Price", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real pricing decision affecting gross profit -- never automated.",
              real_source_hint="core.pricing_desk"),
        _step("frontline", "Frontline Ready", "OPERATIONS", TIER_AUTONOMOUS,
              "Once every prior step is complete, marking the unit frontline-ready is a "
              "pure status update with no independent judgment call.",
              real_source_hint="core.vehicle_lifecycle.update_lifecycle_status"),
    ],
)

_RECON_COORDINATION = _workflow(
    "operations.recon_v2",
    CATEGORY_VEHICLE,
    "Recon Coordination",
    "Coordinate a vehicle's recon work across outside vendors (body shop, mechanical, "
    "detail) from assignment through quality check and return to the lot.",
    "Vehicle",
    [
        _step("assign_vendor", "Assign Vendor", "OPERATIONS", TIER_ASSISTED,
              "AI can suggest a vendor from real recon-queue data; a person confirms the assignment.",
              real_source_hint="core.vehicle_lifecycle.assign_vendor"),
        _step("body_work", "Body Work", "OPERATIONS", TIER_HUMAN_ONLY,
              "Physical vendor work -- never automated.",
              real_source_hint="core.vehicle_lifecycle.update_vendor_status"),
        _step("mechanical", "Mechanical", "SERVICE", TIER_HUMAN_ONLY,
              "Physical repair work -- never automated.",
              real_source_hint="core.vehicle_lifecycle.update_recon_item"),
        _step("detail", "Detail", "OPERATIONS", TIER_HUMAN_ONLY,
              "Physical detail work -- never automated.",
              real_source_hint="core.vehicle_lifecycle.update_recon_item"),
        _step("quality_check", "Quality Check", "OPERATIONS", TIER_ASSISTED,
              "AI can compile the real recon checklist completion state for a reviewer.",
              real_source_hint="core.vehicle_lifecycle.get_vehicle_lifecycle"),
        _step("return_to_lot", "Return To Lot", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure lot-position/status update once quality check passes.",
              real_source_hint="core.lot_control.set_lot_position"),
    ],
)

_VEHICLE_TRANSFER = _workflow(
    "operations.vehicle_transfer_v2",
    CATEGORY_VEHICLE,
    "Vehicle Transfer",
    "Move a unit between lots/locations -- request, approve, transport, and confirm "
    "arrival at the new location.",
    "Vehicle",
    [
        _step("request_transfer", "Request Transfer", "OPERATIONS", TIER_ASSISTED,
              "AI can draft the transfer request from a real lot/inventory signal; a person confirms it.",
              real_source_hint="core.lot_control.get_lot_map"),
        _step("approve_transfer", "Approve Transfer", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real logistics/cost decision -- never automated.",
              real_source_hint=None),
        _step("schedule_transport", "Schedule Transport", "OPERATIONS", TIER_ASSISTED,
              "AI can draft/propose a transport schedule; a person confirms the carrier.",
              real_source_hint="core.operations_scheduling.get_transport_schedule"),
        _step("in_transit", "In Transit", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure status update while the real transport record is tracked.",
              real_source_hint="core.operations_scheduling.update_transport_status"),
        _step("confirm_arrival", "Confirm Arrival", "OPERATIONS", TIER_ASSISTED,
              "AI can prompt for confirmation once the expected transit window elapses.",
              real_source_hint="core.operations_scheduling.update_transport_status"),
        _step("update_lot_position", "Update Lot Position", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure data-entry update once arrival is confirmed.",
              real_source_hint="core.lot_control.set_lot_position"),
    ],
)

_MERCHANDISING = _workflow(
    "operations.merchandising_v2",
    CATEGORY_VEHICLE,
    "Merchandising",
    "Get a frontline-ready vehicle fully merchandised -- photographed, described, "
    "priced, synced to listing feeds, and placed on the showroom floor if applicable.",
    "Vehicle",
    [
        _step("photograph", "Photograph", "MARKETING", TIER_ASSISTED,
              "AI flags missing photos from real merchandising-completeness data; a person shoots them.",
              real_source_hint="core.merchandising.get_merchandising_queue"),
        _step("write_description", "Write Description", "MARKETING", TIER_ASSISTED,
              "AI can draft real listing copy; a person reviews before publish.",
              real_source_hint="core.merchandising / core.website_wizard.generate_vehicle_description"),
        _step("price", "Price", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real pricing decision -- never automated.",
              real_source_hint="core.pricing_desk"),
        _step("feed_sync", "Feed Sync", "MARKETING", TIER_AUTONOMOUS,
              "Republishing to already-configured listing feeds is a pure sync action.",
              real_source_hint="core.merchandising.publish_to_feed / core.inventory_syndication"),
        _step("showroom_placement", "Showroom Placement", "OPERATIONS", TIER_ASSISTED,
              "AI can suggest a showroom slot from real availability; a person places the unit.",
              real_source_hint="core.lot_control.assign_showroom"),
    ],
)

_FRONT_LINE_READINESS = _workflow(
    "operations.front_line_readiness_v2",
    CATEGORY_VEHICLE,
    "Front Line Readiness",
    "Final gate before a vehicle is genuinely ready for sale -- inspection, missing "
    "parts, title on file, key assigned, and lot position all confirmed.",
    "Vehicle",
    [
        _step("final_inspection", "Final Inspection", "SERVICE", TIER_HUMAN_ONLY,
              "A physical, real safety/condition check -- never automated.",
              real_source_hint="core.vehicle_inspection"),
        _step("missing_parts_check", "Missing Parts Check", "OPERATIONS", TIER_ASSISTED,
              "AI can compile a real missing-parts list from the recon checklist.",
              real_source_hint="core.vehicle_lifecycle.get_vehicle_lifecycle"),
        _step("title_on_file", "Title On File", "OPERATIONS", TIER_ASSISTED,
              "AI checks real document status and can draft a request if missing.",
              real_source_hint="core.document_workflows.get_title_status"),
        _step("key_assigned", "Key Assigned", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure lot/key-board status check against real data.",
              real_source_hint="core.lot_control.get_key_status"),
        _step("lot_position_confirmed", "Lot Position Confirmed", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure data check against the real lot map.",
              real_source_hint="core.lot_control.get_lot_position"),
        _step("ready_for_sale", "Ready For Sale", "OPERATIONS", TIER_HUMAN_ONLY,
              "The final sign-off that the unit is genuinely sellable -- a real judgment call.",
              real_source_hint="core.vehicle_lifecycle.update_lifecycle_status"),
    ],
)

_DELIVERY_READINESS = _workflow(
    "operations.delivery_readiness_v2",
    CATEGORY_VEHICLE,
    "Delivery Readiness",
    "Prep a sold vehicle for customer delivery -- final detail, documentation, fuel/"
    "inspection, and a scheduled walkthrough.",
    "Deal",
    [
        _step("confirm_sale", "Confirm Sale", "SALES", TIER_AUTONOMOUS,
              "A pure status check against the real Deal record.",
              real_source_hint="core.deals.get_deal"),
        _step("final_detail", "Final Detail", "OPERATIONS", TIER_HUMAN_ONLY,
              "Physical detail work -- never automated.",
              real_source_hint="core.vehicle_lifecycle.update_recon_item"),
        _step("documentation_check", "Documentation Check", "OPERATIONS", TIER_ASSISTED,
              "AI checks the real delivery checklist and can draft missing-doc requests.",
              real_source_hint="core.deals.delivery_checklist / core.document_workflows"),
        _step("fuel_and_inspection", "Fuel & Inspection", "OPERATIONS", TIER_HUMAN_ONLY,
              "A physical pre-delivery check -- never automated.",
              real_source_hint="core.deals.delivery_checklist"),
        _step("walkthrough_scheduled", "Customer Walkthrough Scheduled", "SALES", TIER_AUTONOMOUS,
              "Scheduling a delivery appointment is a low-risk notification/calendar action.",
              real_source_hint="core.operations_scheduling.schedule_delivery / core.appointments"),
        _step("delivered", "Delivered", "SALES", TIER_HUMAN_ONLY,
              "Confirming a real customer handoff happened -- a human confirms it occurred.",
              real_source_hint="core.deals.delivery_checklist"),
    ],
)

_WHOLESALE_DISPOSAL = _workflow(
    "operations.wholesale_disposal_v2",
    CATEGORY_VEHICLE,
    "Wholesale Disposal",
    "Move an aging/low-margin unit out of retail inventory through wholesale -- "
    "flagging, bidding, approval, transport, and payment collection.",
    "Vehicle",
    [
        _step("flag_for_wholesale", "Flag For Wholesale", "OPERATIONS", TIER_ASSISTED,
              "AI flags real aging/margin candidates; a person confirms the wholesale decision.",
              real_source_hint="core.inventory_aging.get_pricing_desk_queue (Inventory dept)"),
        _step("get_bids", "Get Bids", "OPERATIONS", TIER_ASSISTED,
              "AI can draft outreach to wholesale buyers/auctions; a person negotiates.",
              real_source_hint="core.wholesale_desk (Inventory dept)"),
        _step("approve_sale", "Approve Sale", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real financial decision -- never automated.",
              real_source_hint="core.wholesale_desk.accept_offer"),
        _step("transport_arranged", "Transport Arranged", "OPERATIONS", TIER_ASSISTED,
              "AI can draft the transport request; a person confirms the carrier.",
              real_source_hint="core.operations_scheduling.get_transport_schedule"),
        _step("payment_collected", "Payment Collected", "FINANCE", TIER_HUMAN_ONLY,
              "A real financial confirmation -- never automated.",
              real_source_hint="core.wholesale_desk.record_funds_collected"),
        _step("removed_from_inventory", "Removed From Inventory", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure status update once payment is confirmed collected.",
              real_source_hint="core.wholesale_desk.mark_wholesale_sold"),
    ],
)

# ---------------------------------------------------------------------------
# COMPLIANCE WORKFLOWS (5)
# ---------------------------------------------------------------------------

_DEAL_JACKET_AUDIT = _workflow(
    "operations.deal_jacket_audit_v2",
    CATEGORY_COMPLIANCE,
    "Deal Jacket Audit",
    "Confirm every funded deal has a complete, compliant deal jacket -- identify "
    "missing documents, request them, verify, and close.",
    "Deal",
    [
        _step("identify_missing_documents", "Identify Missing Documents", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure, real completeness check against the categorized document vault.",
              real_source_hint="core.document_workflows.get_deal_jacket_status"),
        _step("request_documents", "Request Documents", "OPERATIONS", TIER_ASSISTED,
              "AI drafts the document request; a real Operations task is created for a person to follow up.",
              real_source_hint="core.document_workflows.request_document"),
        _step("verify_documents", "Verify Documents", "OPERATIONS", TIER_HUMAN_ONLY,
              "Confirming a real document is genuinely correct/compliant -- never automated.",
              real_source_hint="core.document_workflows.approve_document"),
        _step("manager_review", "Manager Review", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real management sign-off -- never automated.",
              real_source_hint=None),
        _step("close_audit", "Close Audit", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure status update once every prior step is complete.",
              real_source_hint=None),
    ],
)

_TITLE_EXCEPTION = _workflow(
    "operations.title_exception_v2",
    CATEGORY_COMPLIANCE,
    "Title Exception",
    "Resolve a vehicle with no title on file -- flag, request, escalate if needed, "
    "receive, and file.",
    "Vehicle",
    [
        _step("flag_missing_title", "Flag Missing Title", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure, real document-completeness check.",
              real_source_hint="core.document_workflows.get_title_status"),
        _step("request_title", "Request Title", "OPERATIONS", TIER_ASSISTED,
              "AI drafts the request; a real task is created for a person to send it.",
              real_source_hint="core.document_workflows.request_document"),
        _step("escalate_to_vendor_or_dmv", "Escalate To Vendor/DMV", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real outside-party escalation call -- never automated.",
              real_source_hint=None),
        _step("title_received", "Title Received", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure status update once the document is logged.",
              real_source_hint="core.document_workflows.request_document"),
        _step("verify_and_file", "Verify & File", "OPERATIONS", TIER_HUMAN_ONLY,
              "Confirming the real title is correct before filing -- never automated.",
              real_source_hint="core.document_workflows.approve_document"),
    ],
)

_COMPLIANCE_EXCEPTION = _workflow(
    "operations.compliance_exception_v2",
    CATEGORY_COMPLIANCE,
    "Compliance Exception",
    "Work a flagged compliance violation from identification through remediation "
    "and manager sign-off to close.",
    None,
    [
        _step("identify_violation", "Identify Violation", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure read of the real, already-cited compliance alert feed.",
              real_source_hint="core.compliance_api.list_alerts_api"),
        _step("notify_responsible_party", "Notify Responsible Party", "OPERATIONS", TIER_ASSISTED,
              "AI drafts the notification; a person sends it.",
              real_source_hint="core.messaging.send_direct_message"),
        _step("remediate", "Remediate", "OPERATIONS", TIER_HUMAN_ONLY,
              "The actual fix to a compliance violation -- never automated.",
              real_source_hint="core.compliance_api.resolve_alert_api"),
        _step("manager_review", "Manager Review", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real management sign-off -- never automated.",
              real_source_hint=None),
        _step("resolve_and_close", "Resolve & Close", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure status update once remediation and review are both complete.",
              real_source_hint="core.compliance_api.resolve_alert_api"),
    ],
)

_FUNDING_EXCEPTION = _workflow(
    "operations.funding_exception_v2",
    CATEGORY_COMPLIANCE,
    "Funding Exception",
    "Work a deal stalled in financing/funding -- identify the blocker, contact the "
    "lender or finance office, resolve it, and confirm funding.",
    "Deal",
    [
        _step("identify_stalled_deal", "Identify Stalled Deal", "FINANCE", TIER_AUTONOMOUS,
              "A pure, real staleness check (core.operations_alerts' stalled_deal signal).",
              real_source_hint="core.operations_alerts.get_alert_feed"),
        _step("contact_lender_or_finance", "Contact Lender/Finance", "FINANCE", TIER_ASSISTED,
              "AI drafts the outreach; a person sends it.",
              real_source_hint="core.lender_intelligence"),
        _step("resolve_blocker", "Resolve Blocker", "FINANCE", TIER_HUMAN_ONLY,
              "A real financing decision -- never automated.",
              real_source_hint="core.deals.record_lender_decision"),
        _step("confirm_funding", "Confirm Funding", "FINANCE", TIER_HUMAN_ONLY,
              "A real financial confirmation -- never automated.",
              real_source_hint="core.deals.fund_deal"),
        _step("close_exception", "Close Exception", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure status update once funding is confirmed.",
              real_source_hint=None),
    ],
)

_DOCUMENTATION_RECOVERY = _workflow(
    "operations.documentation_recovery_v2",
    CATEGORY_COMPLIANCE,
    "Documentation Recovery",
    "Track down a specific missing document from initial request through receipt "
    "and filing.",
    None,
    [
        _step("identify_missing_doc", "Identify Missing Doc", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure, real completeness check.",
              real_source_hint="core.document_workflows.get_document_packet"),
        _step("request_from_source", "Request From Source", "OPERATIONS", TIER_ASSISTED,
              "AI drafts the request; a person sends it.",
              real_source_hint="core.document_workflows.request_document"),
        _step("follow_up", "Follow Up", "OPERATIONS", TIER_ASSISTED,
              "AI can draft a follow-up reminder if the request is still open past its SLA.",
              real_source_hint="core.operations_tasks.escalate_task"),
        _step("receive_and_verify", "Receive & Verify", "OPERATIONS", TIER_HUMAN_ONLY,
              "Confirming a real received document is correct -- never automated.",
              real_source_hint="core.document_workflows.approve_document"),
        _step("file_and_close", "File & Close", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure status update once verification is complete.",
              real_source_hint=None),
    ],
)

# ---------------------------------------------------------------------------
# OPERATIONAL WORKFLOWS (5)
# ---------------------------------------------------------------------------

_INTERDEPT_SLA = _workflow(
    "operations.interdept_sla_v2",
    CATEGORY_OPERATIONAL,
    "Interdepartment SLA",
    "Track a cross-department request (e.g. Sales needs a unit ready by Friday) "
    "from logging through assignment, work, verification, and close.",
    None,
    [
        _step("log_request", "Log Request", "OPERATIONS", TIER_ASSISTED,
              "AI can draft the SLA request from a real cross-department message.",
              real_source_hint="core.unified_communications.get_unified_feed"),
        _step("assign_owning_department", "Assign Owning Department", "OPERATIONS", TIER_ASSISTED,
              "AI can suggest the owning department; a person confirms the assignment.",
              real_source_hint="core.operations_tasks.create_task"),
        _step("work_in_progress", "Work In Progress", "OPERATIONS", TIER_HUMAN_ONLY,
              "The actual work is done by a person in the owning department.",
              real_source_hint=None),
        _step("verify_completion", "Verify Completion", "OPERATIONS", TIER_HUMAN_ONLY,
              "Confirming the real work is actually done -- never automated.",
              real_source_hint=None),
        _step("close_sla", "Close SLA", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure status update once verified complete.",
              real_source_hint="core.operations_tasks.close_task"),
    ],
)

_BOTTLENECK_RESOLUTION = _workflow(
    "operations.bottleneck_resolution_v2",
    CATEGORY_OPERATIONAL,
    "Bottleneck Resolution",
    "Work a real, identified operational bottleneck (parts delay, approval delay, "
    "technician overload) from root-cause through a confirmed fix.",
    None,
    [
        _step("identify_bottleneck", "Identify Bottleneck", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure read of the real Shop Bottlenecks signal.",
              real_source_hint="core.shop_control.get_shop_bottlenecks (Service dept)"),
        _step("root_cause_analysis", "Root Cause Analysis", "OPERATIONS", TIER_ASSISTED,
              "AI can compile the real contributing signals; a person interprets them.",
              real_source_hint="core.network_root_cause"),
        _step("assign_resolution_owner", "Assign Resolution Owner", "OPERATIONS", TIER_ASSISTED,
              "AI can suggest an owner from real workload data.",
              real_source_hint="core.operations_tasks.create_task"),
        _step("implement_fix", "Implement Fix", "OPERATIONS", TIER_HUMAN_ONLY,
              "The actual operational fix -- never automated.",
              real_source_hint=None),
        _step("confirm_resolved", "Confirm Resolved", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure re-check of the same real signal that flagged the bottleneck.",
              real_source_hint="core.operations_overview.get_operations_overview"),
    ],
)

_VENDOR_ESCALATION = _workflow(
    "operations.vendor_escalation_v2",
    CATEGORY_OPERATIONAL,
    "Vendor Escalation",
    "Escalate an underperforming vendor (missed recon deadline, poor quality) from "
    "logging the issue through resolution and a vendor rating update.",
    "Vendor",
    [
        _step("log_issue", "Log Issue", "OPERATIONS", TIER_ASSISTED,
              "AI can draft the issue record from real vendor-status data.",
              real_source_hint="core.vehicle_lifecycle.update_vendor_status"),
        _step("notify_vendor", "Notify Vendor", "OPERATIONS", TIER_ASSISTED,
              "AI drafts the notification; a person sends it.",
              real_source_hint="core.vendor_management.update_vendor"),
        _step("escalate_to_manager", "Escalate To Manager", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real management escalation -- never automated.",
              real_source_hint=None),
        _step("vendor_response", "Vendor Response", "OPERATIONS", TIER_HUMAN_ONLY,
              "Recording a real outside party's response -- never automated.",
              real_source_hint=None),
        _step("resolve_and_rate_vendor", "Resolve & Rate Vendor", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real vendor-performance judgment call -- never automated.",
              real_source_hint="core.vendor_management.set_vendor_status"),
    ],
)

_INVENTORY_RECONCILIATION = _workflow(
    "operations.inventory_reconciliation_v2",
    CATEGORY_OPERATIONAL,
    "Inventory Reconciliation",
    "Run a lot audit, identify discrepancies between physical and system inventory, "
    "investigate, correct records, and sign off.",
    None,
    [
        _step("run_lot_audit", "Run Lot Audit", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure, real cross-reference of the lot map against inventory ownership.",
              real_source_hint="core.workflow_tab_data.inventory_lot_audit"),
        _step("identify_discrepancies", "Identify Discrepancies", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure read of the real audit output.",
              real_source_hint="core.lot_control.get_lot_map"),
        _step("investigate", "Investigate", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real physical/records investigation -- never automated.",
              real_source_hint=None),
        _step("correct_records", "Correct Records", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real correction to inventory ownership/position records -- never automated.",
              real_source_hint="core.lot_control.set_lot_position"),
        _step("sign_off", "Sign Off", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real management sign-off -- never automated.",
              real_source_hint=None),
    ],
)

_DELIVERY_COORDINATION = _workflow(
    "operations.delivery_coordination_v2",
    CATEGORY_OPERATIONAL,
    "Delivery Coordination",
    "Coordinate the logistics of a customer vehicle delivery -- scheduling, "
    "transport, customer availability, delivery, and post-delivery follow-up.",
    "Deal",
    [
        _step("schedule_delivery", "Schedule Delivery", "OPERATIONS", TIER_AUTONOMOUS,
              "A low-risk scheduling action against real calendar/appointment data.",
              real_source_hint="core.operations_scheduling.schedule_delivery"),
        _step("coordinate_transport", "Coordinate Transport", "OPERATIONS", TIER_ASSISTED,
              "AI can draft the transport coordination; a person confirms the carrier.",
              real_source_hint="core.operations_scheduling.get_transport_schedule"),
        _step("confirm_customer_availability", "Confirm Customer Availability", "SALES", TIER_AUTONOMOUS,
              "A low-risk confirmation/reminder action.",
              real_source_hint="core.appointment_scheduling.send_appointment_reminder"),
        _step("deliver_vehicle", "Deliver Vehicle", "SALES", TIER_HUMAN_ONLY,
              "A real customer handoff -- never automated.",
              real_source_hint="core.deals.delivery_checklist"),
        _step("post_delivery_follow_up", "Post-Delivery Follow Up", "SALES", TIER_AUTONOMOUS,
              "A low-risk follow-up notification once delivery is confirmed.",
              real_source_hint="core.lead_tasks.create_task"),
    ],
)

# ---------------------------------------------------------------------------
# EMPLOYEE WORKFLOWS (4)
# ---------------------------------------------------------------------------

_NEW_EMPLOYEE_ONBOARDING = _workflow(
    "operations.new_employee_onboarding_v2",
    CATEGORY_EMPLOYEE,
    "New Employee Onboarding",
    "Move a new hire from offer-accepted through paperwork, systems access, "
    "orientation, first shift, and a 30-day check-in.",
    "Employee",
    [
        _step("offer_accepted", "Offer Accepted", "ADMIN", TIER_HUMAN_ONLY,
              "A real HR/hiring decision -- never automated.",
              real_source_hint="core.workforce.get_directory"),
        _step("paperwork_complete", "Paperwork Complete", "ADMIN", TIER_ASSISTED,
              "AI can track real completion state; a person confirms the paperwork itself.",
              real_source_hint=None),
        _step("systems_access_granted", "Systems Access Granted", "ADMIN", TIER_HUMAN_ONLY,
              "Granting real credentials/access -- never automated (security-sensitive).",
              real_source_hint="core.auth.create_credential"),
        _step("orientation", "Orientation", "ADMIN", TIER_ASSISTED,
              "AI can schedule/draft orientation materials; a person delivers it.",
              real_source_hint=None),
        _step("first_shift_scheduled", "First Shift Scheduled", "OPERATIONS", TIER_AUTONOMOUS,
              "A low-risk scheduling action.",
              real_source_hint="core.workforce.schedule_shift"),
        _step("thirty_day_check_in", "30-Day Check-In", "ADMIN", TIER_ASSISTED,
              "AI can prompt the check-in on schedule; a person conducts it.",
              real_source_hint=None),
    ],
)

_TRAINING = _workflow(
    "operations.training_v2",
    CATEGORY_EMPLOYEE,
    "Training",
    "Track an employee through an assigned training program from assignment to "
    "manager sign-off. Honest gap: no dedicated training-content/LMS entity exists "
    "anywhere in this codebase -- this workflow tracks the real process (who's "
    "assigned, in progress, assessed, signed off) via its own Tasks/Evidence/"
    "Comments, not a training-content or scoring integration.",
    "Employee",
    [
        _step("assign_training", "Assign Training", "OPERATIONS", TIER_ASSISTED,
              "AI can suggest relevant training from real role/department context; a person assigns it.",
              real_source_hint="core.workforce.get_directory"),
        _step("in_progress", "In Progress", "OPERATIONS", TIER_HUMAN_ONLY,
              "The employee's own real progress -- tracked, not automated.",
              real_source_hint=None),
        _step("assessment", "Assessment", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real competency assessment -- never automated.",
              real_source_hint=None),
        _step("manager_sign_off", "Manager Sign-Off", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real management sign-off -- never automated.",
              real_source_hint=None),
        _step("complete", "Complete", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure status update once sign-off is recorded.",
              real_source_hint=None),
    ],
)

_CERTIFICATION = _workflow(
    "operations.certification_v2",
    CATEGORY_EMPLOYEE,
    "Certification",
    "Track an employee through a real certification process from enrollment to "
    "renewal scheduling. Honest gap: no certification-body integration exists "
    "anywhere in this codebase -- this workflow tracks the process manually.",
    "Employee",
    [
        _step("enroll", "Enroll", "OPERATIONS", TIER_ASSISTED,
              "AI can draft the enrollment record; a person confirms it.",
              real_source_hint=None),
        _step("complete_coursework", "Complete Coursework", "OPERATIONS", TIER_HUMAN_ONLY,
              "The employee's own real coursework -- tracked, not automated.",
              real_source_hint=None),
        _step("pass_exam", "Pass Exam", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real exam outcome -- never automated or fabricated.",
              real_source_hint=None),
        _step("certification_issued", "Certification Issued", "OPERATIONS", TIER_HUMAN_ONLY,
              "A real, consequential HR record -- never automated.",
              real_source_hint=None),
        _step("renewal_scheduled", "Renewal Scheduled", "OPERATIONS", TIER_AUTONOMOUS,
              "A low-risk scheduling reminder ahead of a known expiration.",
              real_source_hint=None),
    ],
)

_PERFORMANCE_REVIEW = _workflow(
    "operations.performance_review_v2",
    CATEGORY_EMPLOYEE,
    "Performance Review",
    "Run a real, data-grounded performance review -- schedule, gather real metrics, "
    "draft, discuss, and finalize. Directly wired to core/coaching.py's already-real "
    "AI Performance Review mechanism (a factual, numbers-only draft a manager "
    "reviews/edits before an employee ever sees it -- never AI-generated subjective "
    "judgment language, and never auto-shared).",
    "Employee",
    [
        _step("schedule_review", "Schedule Review", "OPERATIONS", TIER_AUTONOMOUS,
              "A low-risk scheduling action.",
              real_source_hint=None),
        _step("gather_metrics", "Gather Metrics", "OPERATIONS", TIER_AUTONOMOUS,
              "A pure, real read of the employee's own $ effectiveness/department scorecard.",
              real_source_hint="core.coaching.compose_review_metrics"),
        _step("manager_assessment", "Manager Assessment", "OPERATIONS", TIER_ASSISTED,
              "core.coaching.draft_review() composes a real, factual, numbers-only summary; "
              "a manager must review/edit it -- never AI-generated subjective judgment language.",
              real_source_hint="core.coaching.draft_review / update_review_notes"),
        _step("employee_discussion", "Employee Discussion", "OPERATIONS", TIER_HUMAN_ONLY,
              "The actual conversation -- never automated.",
              real_source_hint=None),
        _step("finalize_and_file", "Finalize & File", "OPERATIONS", TIER_HUMAN_ONLY,
              "core.coaching.finalize_review()/share_review() are real, enforced, manager-only "
              "actions -- a review is never auto-shared with the employee.",
              real_source_hint="core.coaching.finalize_review / share_review"),
    ],
)

# ---------------------------------------------------------------------------
# SALES WORKFLOWS (18)
# ---------------------------------------------------------------------------
# Sam's own reframe (2026-07-21): Sales should be organized by customer
# LIFECYCLE (Lead -> Contact -> Appointment -> Showroom -> Demo -> Deal ->
# Finance -> Delivery -> Ownership -> Retention), not as a flat list of
# department tasks. These 18 workflows are grouped into the 5 lifecycle
# categories above (Prospecting/Engagement/Deals/Finance/Retention) and,
# wherever a real backing function already exists in this codebase, every
# step's real_source_hint points straight at it -- no fabricated capability.
# A handful of steps (a live floor conversation, a needs-assessment
# discussion, presenting options to a customer) are honestly HUMAN_ONLY with
# no real_source_hint at all, since no backend module exists (or should
# exist) for them.

# --- Prospecting -----------------------------------------------------------

_LEAD_MANAGEMENT = _workflow(
    "sales.lead_management_v2",
    CATEGORY_PROSPECTING,
    "Lead Management",
    "Move a new Lead from creation through first contact, qualification, "
    "and pipeline advancement, using the real LEAD_WORKFLOW state chain and "
    "real next-best-action guidance -- not a generic task list.",
    "Lead",
    [
        _step("initial_contact", "Initial Contact", "SALES", TIER_ASSISTED,
              "core.lead_record.next_best_action() surfaces the real recommended "
              "next touch (overdue tasks, no-contact-logged signals, days-in-stage). "
              "core.email_wizard.py can draft the outreach, but a human sends it.",
              real_source_hint="core.lead_record.next_best_action"),
        _step("qualify_and_score", "Qualify & Score", "SALES", TIER_ASSISTED,
              "core.lead_scoring.py computes a real, observable-signal score "
              "(Credit App started, Deal desked, Test Drive completed, etc.) -- "
              "used to prioritize, never to auto-qualify.",
              real_source_hint="core.lead_scoring"),
        _step("advance_pipeline_stage", "Advance Pipeline Stage", "SALES", TIER_HUMAN_ONLY,
              "core.lead_workflows.advance_lead_workflow() enforces the real "
              "NEW -> CONTACTED -> APPOINTMENT_SET -> VISITED -> PROPOSAL -> "
              "NEGOTIATION state chain -- a person decides when a lead genuinely "
              "moves, never automated.",
              real_source_hint="core.lead_workflows.advance_lead_workflow"),
        _step("convert_or_close", "Convert or Close", "SALES", TIER_HUMAN_ONLY,
              "core.lead_conversion.convert_lead_to_customer() on a real sale; "
              "core.lost_sale_recovery.mark_lost() on a real loss -- both real, "
              "deliberate human decisions.",
              real_source_hint="core.lead_conversion.convert_lead_to_customer"),
    ],
)

_BDC_WORKFLOW = _workflow(
    "sales.bdc_workflow_v2",
    CATEGORY_PROSPECTING,
    "BDC Workflow (Internet Leads)",
    "Work the real untouched-internet-lead queue against genuine "
    "speed-to-lead measurement, through qualification and hand-off to the "
    "sales floor.",
    "Lead",
    [
        _step("log_new_internet_lead", "Log New Internet Lead", "SALES", TIER_ASSISTED,
              "core.bdc.py's real untouched-lead queue, off Lead.CreatedAt "
              "(precise where available; historical rows honestly report "
              "urgency='unknown' rather than a fabricated value).",
              real_source_hint="core.bdc.get_untouched_queue"),
        _step("speed_to_lead_response", "Speed-to-Lead Response", "SALES", TIER_ASSISTED,
              "core.bdc.get_response_time_stats() measures real elapsed time to "
              "first contact -- the core BDC KPI.",
              real_source_hint="core.bdc.get_response_time_stats"),
        _step("qualification", "Qualification", "SALES", TIER_HUMAN_ONLY,
              "core.bdc.get_qualification_queue() -- real CONTACTED-stage "
              "internet leads awaiting a real qualification call.",
              real_source_hint="core.bdc.get_qualification_queue"),
        _step("handoff_to_floor", "Hand Off to Floor", "SALES", TIER_HUMAN_ONLY,
              "core.bdc.get_handoff_candidates() -- real APPOINTMENT_SET-or-"
              "VISITED leads ready to move from BDC to a floor salesperson.",
              real_source_hint="core.bdc.get_handoff_candidates"),
    ],
)

_UP_SYSTEM_V2 = _workflow(
    "sales.up_system_v2",
    CATEGORY_PROSPECTING,
    "Up System",
    "Log a real walk-in/phone-up and run it through a genuine round-robin "
    "floor rotation for fairness, tracking outcome to a real be-back board.",
    "Lead",
    [
        _step("log_the_up", "Log the Up", "SALES", TIER_ASSISTED,
              "core.up_system.log_up() creates a real Lead (Source Walk-In/"
              "Phone-Up) and re-assigns it to whoever's next in the real floor "
              "rotation, not the logging rep.",
              real_source_hint="core.up_system.log_up"),
        _step("work_the_up", "Work the Up", "SALES", TIER_HUMAN_ONLY,
              "Real up_status/up_type lifecycle tracking on the created Lead.",
              real_source_hint="core.up_system"),
        _step("outcome_and_beback", "Outcome & Be-Back", "SALES", TIER_ASSISTED,
              "A terminal status is logged; unsold ups feed a real be-back "
              "board for follow-up.",
              real_source_hint="core.up_system"),
    ],
)

_ORPHAN_OWNER_MINING_V2 = _workflow(
    "sales.orphan_owner_mining_v2",
    CATEGORY_PROSPECTING,
    "Orphan Owner Mining",
    "Work the real queue of customers who own a vehicle but have no "
    "salesperson currently working that relationship (no traceable "
    "Deal-to-salesperson attribution on file).",
    "Customer",
    [
        _step("identify_orphan", "Identify Orphan Owner", "SALES", TIER_ASSISTED,
              "core.orphan_owner_mining.get_orphan_owners() -- a real queue, "
              "sorted by vehicles owned then service recency.",
              real_source_hint="core.orphan_owner_mining.get_orphan_owners"),
        _step("review_customer_detail", "Review Customer Detail", "SALES", TIER_ASSISTED,
              "core.orphan_owner_mining.get_orphan_owner_detail().",
              real_source_hint="core.orphan_owner_mining.get_orphan_owner_detail"),
        _step("claim_and_assign", "Claim & Assign", "SALES", TIER_HUMAN_ONLY,
              "core.orphan_owner_mining.claim_orphan_owner() creates a real Lead "
              "(Source Orphan Owner Mining) tied to the Customer via a real "
              "GENERATED_LEAD relationship, auto-assigned to the claiming rep.",
              real_source_hint="core.orphan_owner_mining.claim_orphan_owner"),
        _step("work_as_lead", "Work as Lead", "SALES", TIER_HUMAN_ONLY,
              "Once claimed, this drops straight into the standard Lead "
              "Management workflow.",
              real_source_hint="sales.lead_management_v2"),
    ],
)

# --- Engagement --------------------------------------------------------------

_APPOINTMENT_WORKFLOW = _workflow(
    "sales.appointment_workflow_v2",
    CATEGORY_ENGAGEMENT,
    "Appointment Workflow",
    "Move a scheduled appointment from booking through confirmation, "
    "arrival, and outcome -- the real bridge between a Lead and a Showroom "
    "Visit.",
    "Appointment",
    [
        _step("schedule", "Schedule", "SALES", TIER_ASSISTED,
              "core.appointments.schedule_appointment() -- a real, "
              "department-agnostic Appointment entity shared with Service.",
              real_source_hint="core.appointments.schedule_appointment"),
        _step("confirm_reminder", "Confirm / Reminder", "SALES", TIER_ASSISTED,
              "core.appointments.send_appointment_reminder() is a real, "
              "honestly-labeled SIMULATED send (no live SMS/email gateway); "
              "core.appointment_scheduling.generate_checkin_link() is a real "
              "customer-facing pre-visit check-in link.",
              real_source_hint="core.appointment_scheduling.generate_checkin_link"),
        _step("show_or_no_show", "Show or No-Show", "SALES", TIER_HUMAN_ONLY,
              "core.appointments.update_status() -- arrived/no_show/cancelled, "
              "a real enforced lifecycle.",
              real_source_hint="core.appointments.update_status"),
        _step("outcome_sold_or_followup", "Outcome: Sold or Follow-Up", "SALES", TIER_HUMAN_ONLY,
              "A shown appointment moves into Showroom Workflow toward a Deal; "
              "a missed one feeds the BDC/Lead Management follow-up cadence.",
              real_source_hint="sales.showroom_workflow_v2"),
    ],
)

_SHOWROOM_WORKFLOW = _workflow(
    "sales.showroom_workflow_v2",
    CATEGORY_ENGAGEMENT,
    "Showroom Workflow",
    "The in-person floor process from a guest walking in through a desked "
    "deal -- deliberately composes several already-real modules rather than "
    "building one new one.",
    "Lead",
    [
        _step("guest_arrival", "Guest Arrival", "SALES", TIER_HUMAN_ONLY,
              "core.appointments.update_status() to 'arrived', or a fresh Up "
              "via core.up_system.log_up() for a walk-in with no prior "
              "appointment.",
              real_source_hint="core.appointments.update_status"),
        _step("needs_assessment", "Needs Assessment", "SALES", TIER_HUMAN_ONLY,
              "No dedicated backend module exists for a structured needs-"
              "assessment questionnaire -- a real, human-only conversation "
              "step, honestly not backed by a specific function.",
              real_source_hint=None),
        _step("vehicle_selection", "Vehicle Selection", "SALES", TIER_ASSISTED,
              "core.sales_menu.inventory() -- real payment-search/browse/"
              "compare across live unsold inventory, plus "
              "core.vehicle_holds.place_hold() to reserve the unit.",
              real_source_hint="core.vehicle_holds.place_hold"),
        _step("manager_to", "Manager TO", "SALES", TIER_HUMAN_ONLY,
              "sales.manager_to_v2 -- a real timed hand-off to a manager-tier "
              "employee.",
              real_source_hint="core.manager_to.request_to"),
        _step("demo_drive", "Demo Drive", "SALES", TIER_ASSISTED,
              "sales.demo_drive_v2.",
              real_source_hint="core.demo_drive.start_drive"),
        _step("move_to_deal", "Move to Deal", "SALES", TIER_HUMAN_ONLY,
              "core.deals.create_deal() -- the real Deal Desk entry point.",
              real_source_hint="core.deals.create_deal"),
    ],
)

_DEMO_DRIVE_V2 = _workflow(
    "sales.demo_drive_v2",
    CATEGORY_ENGAGEMENT,
    "Demo Drive",
    "A real test-drive log with an enforced license-verification gate, "
    "odometer out/in, and a real out/returned lifecycle.",
    "DemoDrive",
    [
        _step("verify_license", "Verify License", "SALES", TIER_HUMAN_ONLY,
              "core.demo_drive.start_drive() refuses to start without "
              "license_verified -- an honestly-labeled captured flag, not a "
              "real DMV/AAMVA check.",
              real_source_hint="core.demo_drive.start_drive"),
        _step("log_odometer_out", "Log Odometer Out", "SALES", TIER_ASSISTED,
              "Real odometer_out capture at drive start.",
              real_source_hint="core.demo_drive.start_drive"),
        _step("conduct_drive", "Conduct Drive", "SALES", TIER_HUMAN_ONLY,
              "The drive itself -- never automated.",
              real_source_hint=None),
        _step("return_and_log", "Return & Log", "SALES", TIER_ASSISTED,
              "core.demo_drive.return_drive() computes real miles-driven/"
              "duration and closes the lifecycle (or cancels it).",
              real_source_hint="core.demo_drive.return_drive"),
    ],
)

# --- Deals -------------------------------------------------------------------

_TRADE_APPRAISAL = _workflow(
    "sales.trade_appraisal_v2",
    CATEGORY_DEALS,
    "Trade Appraisal",
    "Split out of Desking per Sam's own recommendation -- a structured "
    "trade-in appraisal with a manager-approval gate, now with real VIN "
    "decode support.",
    "Deal",
    [
        _step("capture_vin", "Capture VIN", "SALES", TIER_ASSISTED,
              "core.vin_decoder.decode_trade_in_vin() -- a real, read-only "
              "cross-check of the appraiser's entered year/make against the "
              "VIN's own decoded value; core.deals.update_trade_appraisal() "
              "stores the structured trade_in fields.",
              real_source_hint="core.vin_decoder.decode_trade_in_vin"),
        _step("condition_and_photos", "Condition & Photos", "SALES", TIER_HUMAN_ONLY,
              "Honestly hand-entered condition/photo fields on "
              "Deal.trade_in -- no real inspection-report/photo-upload "
              "integration for trade-ins specifically.",
              real_source_hint="core.deals.update_trade_appraisal"),
        _step("market_value_research", "Market Value Research", "SALES", TIER_ASSISTED,
              "core.pricing_desk.get_market_pricing() -- SIMULATED comparable-"
              "market data, clearly disclosed.",
              real_source_hint="core.pricing_desk.get_market_pricing"),
        _step("acv_and_approval", "ACV & Approval", "SALES", TIER_HUMAN_ONLY,
              "core.deals.approve_trade_appraisal() -- a real manager-"
              "approval gate; re-editing the appraisal resets approval.",
              real_source_hint="core.deals.approve_trade_appraisal"),
    ],
)

_DESKING = _workflow(
    "sales.desking_v2",
    CATEGORY_DEALS,
    "Desking",
    "The real multi-scenario Deal Desk Pencil Tool -- refined per Sam's own "
    "spec to make Vehicle Selection and Manager Review their own explicit "
    "steps.",
    "Deal",
    [
        _step("vehicle_selection", "Vehicle Selection", "SALES", TIER_ASSISTED,
              "core.deals.create_deal() against a real, selected, held unit "
              "(core.vehicle_holds).",
              real_source_hint="core.deals.create_deal"),
        _step("appraise_trade", "Appraise Trade", "SALES", TIER_HUMAN_ONLY,
              "sales.trade_appraisal_v2 -- a real linked workflow, not "
              "duplicated here.",
              real_source_hint="sales.trade_appraisal_v2"),
        _step("build_scenarios", "Build Scenarios", "SALES", TIER_ASSISTED,
              "core.deals.add_scenario() -- real multi-scenario Pencil Tool "
              "math.",
              real_source_hint="core.deals.add_scenario"),
        _step("present_options", "Present Options", "SALES", TIER_HUMAN_ONLY,
              "The actual customer presentation -- never automated.",
              real_source_hint=None),
        _step("manager_review", "Manager Review", "SALES", TIER_HUMAN_ONLY,
              "sales.manager_to_v2 -- a real timed hand-off to a manager-"
              "tier employee for deal review.",
              real_source_hint="sales.manager_to_v2"),
        _step("customer_selection", "Customer Selection", "SALES", TIER_HUMAN_ONLY,
              "core.deals.select_scenario() -- locks in the chosen scenario.",
              real_source_hint="core.deals.select_scenario"),
    ],
)

_CREDIT_APPLICATION_V2 = _workflow(
    "sales.credit_application_v2",
    CATEGORY_DEALS,
    "Credit Application",
    "A real applicant-level pre-qualification record, independent of or "
    "later linked to a Deal, gated by an enforced FCRA-consent check before "
    "any decision runs.",
    "CreditApplication",
    [
        _step("start_application", "Start Application", "SALES", TIER_ASSISTED,
              "core.credit_app.create_credit_application() -- employment/"
              "income/housing, optional co-applicant, SSN last-4 only.",
              real_source_hint="core.credit_app.create_credit_application"),
        _step("capture_consent", "Capture Consent", "SALES", TIER_HUMAN_ONLY,
              "core.credit_app.record_consent() -- a real, enforced FCRA-"
              "consent gate; submit_credit_application() refuses to run "
              "without it.",
              real_source_hint="core.credit_app.record_consent"),
        _step("run_decision", "Run Decision", "SALES", TIER_ASSISTED,
              "core.credit_app.submit_credit_application() -- an honestly-"
              "labeled deterministic, rules-based simulated decision engine, "
              "no live credit-bureau connection in this sandbox.",
              real_source_hint="core.credit_app.submit_credit_application"),
        _step("link_to_deal", "Link to Deal", "SALES", TIER_HUMAN_ONLY,
              "core.credit_app.link_to_deal() -- once a decision is on file, "
              "tie it to the real Deal it supports.",
              real_source_hint="core.credit_app.link_to_deal"),
    ],
)

_MANAGER_TO_V2 = _workflow(
    "sales.manager_to_v2",
    CATEGORY_DEALS,
    "Manager TO",
    "A real timed hand-off queue for a manager-tier employee to join a deal "
    "in progress -- request/claim/resolve, with real save-rate and claim-"
    "wait stats.",
    "ManagerTO",
    [
        _step("request_to", "Request TO", "SALES", TIER_ASSISTED,
              "core.manager_to.request_to() -- linkable to a Lead or a Deal, "
              "with a reason.",
              real_source_hint="core.manager_to.request_to"),
        _step("manager_claims", "Manager Claims", "OPERATIONS", TIER_HUMAN_ONLY,
              "core.manager_to.claim_to() -- gated to manager-tier only via "
              "core.bot_tasks.infer_tier() off the real Employee.Title.",
              real_source_hint="core.manager_to.claim_to"),
        _step("manager_joins_and_works_deal", "Manager Joins & Works Deal", "OPERATIONS", TIER_HUMAN_ONLY,
              "The actual floor conversation -- never automated.",
              real_source_hint=None),
        _step("outcome_recorded", "Outcome Recorded", "OPERATIONS", TIER_HUMAN_ONLY,
              "core.manager_to.resolve_to() -- a real outcome record feeding "
              "save-rate/resolution-time stats.",
              real_source_hint="core.manager_to.resolve_to"),
    ],
)

# --- Finance -------------------------------------------------------------------

_FI_HANDOFF = _workflow(
    "sales.fi_handoff_v2",
    CATEGORY_FINANCE,
    "F&I Handoff",
    "The real desking-to-financing handoff -- once a scenario is selected, "
    "the deal moves into Finance's own financing/contract pipeline.",
    "Deal",
    [
        _step("confirm_selected_scenario", "Confirm Selected Scenario", "SALES", TIER_HUMAN_ONLY,
              "core.deals.select_scenario() must already be complete -- the "
              "real precondition this handoff checks.",
              real_source_hint="core.deals.select_scenario"),
        _step("choose_financing_path", "Choose Financing Path", "FINANCE", TIER_HUMAN_ONLY,
              "core.deals.choose_in_house_financing() or "
              "core.deals.submit_to_lender() -- in-house BHPH vs. a real "
              "outside-lender submission.",
              real_source_hint="core.deals.choose_in_house_financing"),
        _step("lender_decision", "Lender Decision", "FINANCE", TIER_ASSISTED,
              "core.deals.record_lender_decision() -- approved/declined/"
              "countered, feeding core.lender_intelligence.py's real per-"
              "lender scorecards.",
              real_source_hint="core.deals.record_lender_decision"),
        _step("handoff_complete", "Handoff Complete", "FINANCE", TIER_HUMAN_ONLY,
              "The deal moves into sales.fi_workflow_v2 for product "
              "presentation.",
              real_source_hint="sales.fi_workflow_v2"),
    ],
    escalate_to_role="FINANCE",
)

_FI_WORKFLOW = _workflow(
    "sales.fi_workflow_v2",
    CATEGORY_FINANCE,
    "F&I Workflow",
    "The actual F&I product menu -- presenting VSC/GAP/Tire & Wheel/Paint & "
    "Fabric/Key Replacement/Prepaid Maintenance and tracking accept/decline "
    "-- distinct from the F&I Handoff above.",
    "Deal",
    [
        _step("present_menu", "Present Menu", "FINANCE", TIER_HUMAN_ONLY,
              "core.fi_products.py's real 6-product catalog, gated to "
              "deal.status in (financing, contract).",
              real_source_hint="core.fi_products"),
        _step("capture_selections", "Capture Selections", "FINANCE", TIER_ASSISTED,
              "Real per-product accept/decline with pending-price editing.",
              real_source_hint="core.fi_products"),
        _step("structure_pricing", "Structure Pricing", "FINANCE", TIER_HUMAN_ONLY,
              "Real per-product pricing adjustment on the deal's F&I menu.",
              real_source_hint="core.fi_products"),
        _step("summary_and_penetration", "Summary & Penetration", "FINANCE", TIER_ASSISTED,
              "core.fi_products.get_product_penetration_stats() -- the real "
              "cross-deal product-attachment metric this closed a long-"
              "standing gap in core.department_intelligence.py for.",
              real_source_hint="core.fi_products.get_product_penetration_stats"),
    ],
    escalate_to_role="FINANCE",
)

_ESIGNATURE_V2 = _workflow(
    "sales.esignature_v2",
    CATEGORY_FINANCE,
    "eSignature",
    "A real signing envelope tied to a funded-ready Deal, requiring a "
    "generated contract on file, with a real per-signer ESIGN-Act-style "
    "consent gate.",
    "Deal",
    [
        _step("prepare_envelope", "Prepare Envelope", "FINANCE", TIER_ASSISTED,
              "core.esignature.create_envelope() -- contract_snapshot is "
              "copied, not referenced, from Deal.attributes['contract'] at "
              "creation time.",
              real_source_hint="core.esignature.create_envelope"),
        _step("signer_setup", "Signer Setup", "FINANCE", TIER_ASSISTED,
              "core.esignature.add_signer().",
              real_source_hint="core.esignature.add_signer"),
        _step("send_for_signature", "Send for Signature", "FINANCE", TIER_ASSISTED,
              "core.esignature.send_envelope() -- an honestly-labeled "
              "SIMULATED dispatch, no real e-signature platform connected in "
              "this sandbox.",
              real_source_hint="core.esignature.send_envelope"),
        _step("sign_and_consent", "Sign & Consent", "SALES", TIER_HUMAN_ONLY,
              "core.esignature.sign()/decline() -- each signer requires a "
              "real esign_consent flag before signing; a typed-full-name "
              "capture is checked against the signer's name on file.",
              real_source_hint="core.esignature.sign"),
    ],
    escalate_to_role="FINANCE",
)

# --- Retention -----------------------------------------------------------------

_DELIVERY_EXPERIENCE = _workflow(
    "sales.delivery_experience_v2",
    CATEGORY_RETENTION,
    "Delivery Experience",
    "The real, already-shipped Delivery workflow -- vehicle prep, quality "
    "control, tech setup, documentation, and a CSI/review trigger -- "
    "confirmed by Sam to be the same real thing as 'Delivery Checklist.'",
    "Deal",
    [
        _step("vehicle_preparation", "Vehicle Preparation", "OPERATIONS", TIER_HUMAN_ONLY,
              "core.deals.update_delivery_checklist() -- vehicle_prep item.",
              real_source_hint="core.deals.update_delivery_checklist"),
        _step("quality_control", "Quality Control", "OPERATIONS", TIER_HUMAN_ONLY,
              "core.deals.update_delivery_checklist() -- quality_control item.",
              real_source_hint="core.deals.update_delivery_checklist"),
        _step("tech_setup", "Tech Setup", "SALES", TIER_HUMAN_ONLY,
              "core.deals.update_delivery_checklist() -- tech_setup item.",
              real_source_hint="core.deals.update_delivery_checklist"),
        _step("documentation_and_csi", "Documentation & CSI", "SALES", TIER_ASSISTED,
              "core.deals.update_delivery_checklist() -- documentation item; "
              "csi.review_requested is explicitly labeled NOT a real CSI-"
              "survey send, since no dispatch mechanism exists anywhere in "
              "this codebase.",
              real_source_hint="core.deals.update_delivery_checklist"),
    ],
)

_EQUITY_MINING = _workflow(
    "sales.equity_mining_v2",
    CATEGORY_RETENTION,
    "Equity Mining",
    "Sam's own 'one of your strongest opportunities' -- surfaces real, "
    "currently-visible positive-equity customers and moves them to a real "
    "appointment.",
    "TriggerAlert",
    [
        _step("identify_positive_equity", "Identify Positive Equity", "MARKETING", TIER_ASSISTED,
              "core.trigger_alerts._scan_equity_mining() -- real HEURISTIC "
              "candidates off elapsed loan term, resolved to the real "
              "Customer id via the CustomerID raw-key resolution fix.",
              real_source_hint="core.trigger_alerts._scan_equity_mining"),
        _step("vehicle_match", "Vehicle Match", "SALES", TIER_ASSISTED,
              "core.sales_menu.inventory() real payment-based inventory "
              "search against the customer's likely budget.",
              real_source_hint="core.sales_menu.inventory"),
        _step("present_offer", "Present Offer", "SALES", TIER_HUMAN_ONLY,
              "core.trigger_alerts.promote_alert() -- creates a real new Lead "
              "tied back to the Customer via GENERATED_LEAD.",
              real_source_hint="core.trigger_alerts.promote_alert"),
        _step("schedule_appointment", "Schedule Appointment", "SALES", TIER_ASSISTED,
              "sales.appointment_workflow_v2.",
              real_source_hint="core.appointments.schedule_appointment"),
    ],
)

_LEASE_MATURITY = _workflow(
    "sales.lease_maturity_v2",
    CATEGORY_RETENTION,
    "Lease Maturity",
    "A real lease-maturity signal from the Trigger Alert Timeline, walked "
    "through customer contact to a new Deal.",
    "TriggerAlert",
    [
        _step("lease_maturity_signal", "Lease Maturity Signal", "MARKETING", TIER_ASSISTED,
              "core.trigger_alerts._scan_lease_maturity() -- real, "
              "re-scanned-on-fetch lease-end matching.",
              real_source_hint="core.trigger_alerts._scan_lease_maturity"),
        _step("customer_contact", "Customer Contact", "SALES", TIER_HUMAN_ONLY,
              "core.field_notes.py's real call/text/email log, linked to the "
              "promoted Lead.",
              real_source_hint="core.field_notes"),
        _step("upgrade_offer", "Upgrade Offer", "SALES", TIER_ASSISTED,
              "core.sales_menu.inventory() real payment-based search for a "
              "comparable/upgraded unit.",
              real_source_hint="core.sales_menu.inventory"),
        _step("appointment_to_deal", "Appointment to Deal", "SALES", TIER_HUMAN_ONLY,
              "sales.appointment_workflow_v2 into sales.desking_v2.",
              real_source_hint="core.deals.create_deal"),
    ],
)

_LOST_SALE_RECOVERY_V2 = _workflow(
    "sales.lost_sale_recovery_v2",
    CATEGORY_RETENTION,
    "Lost Sale Recovery",
    "A combined recovery queue unifying a hard-terminal LOST lead state and "
    "a cancelled Deal, with real reason-code capture and a deliberate, "
    "logged state-machine bypass to reactivate.",
    "Lead",
    [
        _step("capture_lost_reason", "Capture Lost Reason", "SALES", TIER_HUMAN_ONLY,
              "core.lost_sale_recovery.mark_lost() -- real LOST_REASON_CODES "
              "capture on a Lead; a parallel cancel_reason capture exists for "
              "a cancelled Deal.",
              real_source_hint="core.lost_sale_recovery.mark_lost"),
        _step("log_recovery_attempts", "Log Recovery Attempts", "SALES", TIER_ASSISTED,
              "core.lost_sale_recovery.log_recovery_attempt() -- reuses "
              "core.field_notes.py via a real 'recovery_attempt' category.",
              real_source_hint="core.lost_sale_recovery.log_recovery_attempt"),
        _step("reactivate_or_close", "Reactivate or Close", "SALES", TIER_HUMAN_ONLY,
              "core.lost_sale_recovery.reactivate_lost_lead() -- a "
              "deliberate, logged bypass of the strict LEAD_WORKFLOW state "
              "machine, preserving prior-loss history.",
              real_source_hint="core.lost_sale_recovery.reactivate_lost_lead"),
        _step("win_back_or_permanently_close", "Win-Back or Permanently Close", "SALES", TIER_HUMAN_ONLY,
              "A reactivated lead re-enters sales.lead_management_v2; "
              "otherwise this instance is force-closed as genuinely lost.",
              real_source_hint="sales.lead_management_v2"),
    ],
)


WORKFLOW_CATALOG_V2 = [
    _VEHICLE_INTAKE,
    _RECON_COORDINATION,
    _VEHICLE_TRANSFER,
    _MERCHANDISING,
    _FRONT_LINE_READINESS,
    _DELIVERY_READINESS,
    _WHOLESALE_DISPOSAL,
    _DEAL_JACKET_AUDIT,
    _TITLE_EXCEPTION,
    _COMPLIANCE_EXCEPTION,
    _FUNDING_EXCEPTION,
    _DOCUMENTATION_RECOVERY,
    _INTERDEPT_SLA,
    _BOTTLENECK_RESOLUTION,
    _VENDOR_ESCALATION,
    _INVENTORY_RECONCILIATION,
    _DELIVERY_COORDINATION,
    _NEW_EMPLOYEE_ONBOARDING,
    _TRAINING,
    _CERTIFICATION,
    _PERFORMANCE_REVIEW,
    # -- Sales (18) --
    _LEAD_MANAGEMENT,
    _BDC_WORKFLOW,
    _UP_SYSTEM_V2,
    _ORPHAN_OWNER_MINING_V2,
    _APPOINTMENT_WORKFLOW,
    _SHOWROOM_WORKFLOW,
    _DEMO_DRIVE_V2,
    _TRADE_APPRAISAL,
    _DESKING,
    _CREDIT_APPLICATION_V2,
    _MANAGER_TO_V2,
    _FI_HANDOFF,
    _FI_WORKFLOW,
    _ESIGNATURE_V2,
    _DELIVERY_EXPERIENCE,
    _EQUITY_MINING,
    _LEASE_MATURITY,
    _LOST_SALE_RECOVERY_V2,
]

_CATALOG_BY_KEY = {w["key"]: w for w in WORKFLOW_CATALOG_V2}


def get_workflow_def_v2(key):
    return _CATALOG_BY_KEY.get(key)


def list_workflow_defs_v2(category=None):
    if category is None:
        return list(WORKFLOW_CATALOG_V2)
    return [w for w in WORKFLOW_CATALOG_V2 if w["category"] == category]


def get_step_def(workflow_key, step_key):
    workflow = get_workflow_def_v2(workflow_key)
    if not workflow:
        return None
    for step in workflow["steps"]:
        if step["key"] == step_key:
            return step
    return None
