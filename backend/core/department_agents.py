"""Vendor-independent department definitions. No credentials or provider logic here."""
from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True)
class Capability:
    id: str
    kind: str
    risk: int = 0
    entity: str | None = None


CAPABILITIES: dict[str, Capability] = {}


def register_capability(capability: Capability):
    if capability.id in CAPABILITIES:
        raise ValueError("Capability already registered")
    if capability.kind not in {"READ", "ACTION", "EVENT"} or capability.risk not in range(6):
        raise ValueError("Invalid capability contract")
    CAPABILITIES[capability.id] = capability


for name, entity in {
    "customer.read": "Customer", "customer.timeline.read": "Customer",
    "customer.segment.read": "Customer", "lead.read": "Lead",
    "opportunity.read": "Lead", "inventory.read": "Vehicle", "deal.read": "Deal",
    "service.read": "ServiceRecord", "campaign.read": "Campaign",
    "employee.read": "Employee", "department.read": "Department",
    "analytics.read": None, "chrono.analyze": None,
    "inventory.match": "Vehicle", "sales.next_best_action": "Lead",
    "chrono.workspace.read": None, "chrono.history.read": None,
}.items():
    register_capability(Capability(name, "READ", entity=entity))
for name in ("lead.update", "task.create", "appointment.create", "message.generate",
             "sms.send", "email.send", "campaign.create", "campaign.publish", "crm.update",
             "crm.marketing_status.write", "deal.request_review", "manager.request_approval"):
    register_capability(Capability(name, "ACTION", 2 if name in {"message.generate", "campaign.create", "manager.request_approval", "deal.request_review"} else
                                  3 if name == "task.create" else 4))
for name in ("lead.created", "lead.no_activity", "customer.replied", "appointment.created",
             "appointment.missed", "vehicle.sold", "vehicle.aged", "repair_order.opened",
             "repair_order.closed", "deal.created", "deal.funded", "campaign.completed",
             "lead.updated", "task.created", "campaign.created"):
    register_capability(Capability(name, "EVENT"))


@dataclass(frozen=True)
class AgentPack:
    id: str
    department: str
    purpose: str
    responsibilities: tuple[str, ...]
    capabilities: tuple[str, ...]
    kpis: tuple[str, ...]
    roles: tuple[str, ...]
    maturity: str = "scaffold"
    version: int = 1
    prohibited_tools: tuple[str, ...] = (
        "payroll.read", "payroll.write", "banking.transfer", "deal.fund", "employee.compensation.read")
    policies: tuple[str, ...] = (
        "Explicit employee grants only", "Respect consent before communication",
        "Consequential actions require human approval", "Never infer missing consent")
    escalation_paths: tuple[str, ...] = ("gm", "compliance")
    chrono_access: str = "Authorized observations; predictions require an available engine"
    audit_requirements: str = "Record actor, origin, capability, record IDs and outcome; omit raw PII"


def pack(department, purpose, responsibilities, capabilities, kpis, roles, maturity="scaffold"):
    return AgentPack(f"nxtdeal.{department}", department, purpose, tuple(responsibilities.split(";")),
                     tuple(capabilities.split()), tuple(kpis.split(";")), tuple(roles.split()), maturity)


PACKS = {p.department: p for p in (
    pack("sales", "Move customer relationships forward with timely, accountable follow-up",
         "Lead management;Opportunity management;Appointments;Follow-up;Stale lead recovery;Task generation;Manager escalation;CRM updates;Inventory matching;Next-best-action and timeline analysis",
         "customer.read customer.timeline.read lead.read lead.update opportunity.read inventory.read inventory.match sales.next_best_action appointment.create task.create message.generate sms.send email.send crm.update manager.request_approval chrono.analyze",
         "Response time;Appointment show rate;Lead conversion;Overdue follow-ups", "SALES BDC ADMIN OPERATIONS", "reference"),
    pack("marketing", "Plan and measure consent-aware dealership marketing",
         "Campaign creation;Segmentation;Inventory marketing;Retention;Lifecycle marketing;Creative requests;Advertising;Attribution;Reputation;Measurement;OEM compliance;Timing analysis",
         "customer.segment.read customer.timeline.read inventory.read campaign.read campaign.create campaign.publish message.generate analytics.read crm.marketing_status.write email.send sms.send chrono.analyze",
         "Campaign conversion;Retention;Attribution coverage;Consent coverage", "MARKETING ADMIN OPERATIONS", "reference"),
    pack("gm", "Coordinate dealership performance, exceptions and decisions",
         "Operating overview;Department KPIs;Exceptions;Approvals;Escalation;Cross-department coordination;Forecasts;Trajectory;Decision support",
         "analytics.read department.read inventory.read lead.read deal.read campaign.read service.read manager.request_approval deal.request_review chrono.analyze chrono.workspace.read chrono.history.read",
         "Department exceptions;Aging inventory;Approval turnaround;Goal trajectory", "ADMIN OPERATIONS", "reference"),
    pack("bdc", "Respond, route and schedule", "Inbound leads;Responses;Appointments;Routing;Response-time monitoring",
         "lead.read customer.read appointment.create task.create", "Response SLA;Appointments", "BDC SALES ADMIN"),
    pack("fi", "Prepare compliant deals", "Deal readiness;Documents;Lender workflow;Follow-up;Compliance",
         "deal.read deal.request_review", "Readiness;Funding exceptions", "FINANCE ADMIN"),
    pack("accounting", "Resolve financial exceptions", "Reconciliation;AP/AR;Reporting",
         "analytics.read deal.read", "Open exceptions;Reconciliation time", "ADMIN"),
    pack("service", "Maintain customer and vehicle relationships", "Appointments;Reminders;Declined service;Maintenance;Retention;Capacity",
         "service.read customer.read appointment.create", "Retention;Capacity", "SERVICE ADMIN"),
    pack("parts", "Coordinate parts availability", "Low stock;Aging;Special orders;Service coordination",
         "service.read", "Fill rate;Aging stock", "SERVICE ADMIN"),
    pack("inventory", "Manage vehicle lifecycle", "Aging;Pricing signals;Merchandising;Acquisition;Disposition",
         "inventory.read analytics.read", "Days in stock;Merchandising completeness", "OPERATIONS ADMIN"),
    pack("operations", "Coordinate dealership execution", "SOPs;Bottlenecks;Tasks",
         "department.read analytics.read", "SLA attainment;Bottlenecks", "OPERATIONS ADMIN"),
    pack("hr", "Support employee workflows", "Onboarding;Training;Policies",
         "department.read", "Training completion;Onboarding time", "ADMIN"),
    pack("compliance", "Monitor consent, audit and policy exceptions", "Consent;Audit;Advertising;OEM requirements;Access escalation",
         "analytics.read manager.request_approval", "Unresolved exceptions;Consent coverage", "ADMIN"),
)}

# Native operating packs: scoped reports and accountable work, independent of providers.
for department, agent in list(PACKS.items()):
    additions = (f"{department}.workbench.read", f"{department}.work.create", f"{department}.work.update")
    for capability in additions:
        register_capability(Capability(capability, "READ" if capability.endswith(".read") else "ACTION",
                                       0 if capability.endswith(".read") else 4))
    PACKS[department] = replace(agent, capabilities=agent.capabilities + additions,
                               maturity="native", version=2)
register_capability(Capability("service.appointment.create", "ACTION", 4))
PACKS["service"] = replace(PACKS["service"], capabilities=tuple(
    c for c in PACKS["service"].capabilities if c != "appointment.create") + ("service.appointment.create",))

AUTOMATIONS = {
    "sales.stale_lead_recovery": {
        "id": "sales.stale_lead_recovery", "version": 1, "department": "sales",
        "trigger": "lead.no_activity", "duration_hours": 48, "risk": 3,
        "conditions": ["Observed open lead", "Observed last activity at least 48 hours ago"],
        "steps": ["lead.read", "task.create"],
        "description": "Prepare a follow-up task for a stale lead. Outreach remains a separately approved connector action.",
    },
    "marketing.inventory_review": {
        "id": "marketing.inventory_review", "version": 1, "department": "marketing",
        "trigger": "vehicle.aged", "risk": 0, "steps": ["inventory.read"],
        "description": "Review observed inventory before preparing a campaign.",
    },
    "marketing.aged_inventory_campaign": {
        "id": "marketing.aged_inventory_campaign", "version": 1, "department": "marketing",
        "trigger": "vehicle.aged", "risk": 2, "steps": ["inventory.read", "campaign.create"],
        "description": "Prepare an inventory campaign draft for a vehicle observed at 60+ days. No publishing or sending.",
    },
    "gm.operating_review": {
        "id": "gm.operating_review", "version": 1, "department": "gm",
        "trigger": "manual", "risk": 0, "steps": ["analytics.read"],
        "description": "Review authorized entity counts and operating readiness.",
    },
}

for department in PACKS:
    AUTOMATIONS[f"{department}.daily_review"] = {
        "id": f"{department}.daily_review", "version": 1, "department": department,
        "trigger": "manual", "risk": 0, "steps": [f"{department}.workbench.read"],
        "description": "Review observed department exceptions and assigned work. No records are changed.",
    }

PROVIDERS = ("nxtdeal", "api", "chatgpt", "claude", "copilot", "hermes", "openclaw")


def export_pack(department, provider, enabled):
    """Neutral manifest scaffold, not a claim of an installed provider app/MCP server."""
    if provider not in PROVIDERS:
        raise ValueError("Unknown interface")
    agent = PACKS[department]
    return {"schema_version": 1, "provider": provider, "transport": "nxtdeal-http",
            "adapter_status": "manifest_scaffold", "agent": asdict(agent),
            "tools": [{"name": c, "contract": asdict(CAPABILITIES[c]),
                       "endpoint": "/agent-fabric/invoke"} for c in sorted(enabled)],
            "authorization": "Authenticated NXTDeal employee; server evaluates every invocation"}
