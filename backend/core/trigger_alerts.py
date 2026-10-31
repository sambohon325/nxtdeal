"""
Trigger Alerts -- the AutoAlert / automotiveMastermind half of the Events dash
(session 84). Sam: "build out the event dash. we want to style it after nxtdeal
bumper, automotivemastermind.com, and auto alert. this part we absolutely have to
nail, and has to tightly integrate into the CRM."

AutoAlert's own product is built around a live "Timeline" of individually actionable
signals -- positive equity, an approaching lease/loan maturity, a customer who's gone
quiet on service, an open recall on a car someone still owns, an in-market lead who
hasn't been worked yet -- each one urgency-ranked and one-click-actionable, not a
buried aggregate count. automotiveMastermind's own pitch is the same idea pushed
further with a predictive score per customer. This module is that Timeline, built on
real graph data this codebase already computes in aggregate:

- core/campaigns.py's build_audience() already answers "who qualifies for a
  finance_renewal/retention/inventory_ads campaign" as a POOL. run_scan() below reuses
  the exact same relationship walks (FINANCED_BY/AUTHORIZED/INTERESTED_IN/OWNS) but
  keeps each match as its own dated, individually-actionable TriggerAlert record
  instead of collapsing them into one count.
- core/workflow_tab_data.py's marketing_database_mining() already computes the
  HEURISTIC equity-mining candidate list (elapsed-term-as-%-of-total-term, since no
  live amortization engine exists in this codebase) -- reused directly rather than
  reimplemented.
- Open OEM recalls (core/entity_types.py's RECALL, session 59) crossed against real
  vehicle ownership (the OWNS relationship) is a genuinely new signal no other menu
  item in this codebase surfaces per-customer yet.

Promoting an alert is the literal Marketing -> Sales handoff, closing the loop the
same way core/opportunities_actions.py already does for CRM pools, just at the
individual-alert level instead of the whole-pool level:
  - Customer-typed alert -> a real new Lead via core/lead_intake.py's create_lead()
    (source="Trigger Alert"), tied back to the originating Customer via a real
    GENERATED_LEAD relationship (defined in core/relationship_types.py from the
    original vision-doc pass, never actually used in this codebase until now).
  - Lead-typed alert (conquest) -> the exact same core/lead_assignment.py
    ASSIGNED_TO mechanism assign_opportunity_to_sales() already established.

Deduplication matches core/compliance.py's run_full_scan() precedent exactly: only an
already-OPEN ("new") alert for the same (target id, alert_type, source_reference) key
blocks a re-scan from creating a duplicate. A promoted or dismissed alert is a closed
decision that stays in the graph permanently (the append-only-graph rule everywhere
else in this codebase), but a fresh scan CAN create a new alert against the same key
later if the underlying signal still holds -- an honest, documented scoping choice,
not an oversight.

Real data-loss bug found and fixed (2026-07-18, Marketing Growth Platform data-gap-fill
follow-up) -- same bug class as core/compliance.py/core/dealership_events.py/
core/lead_conversion.py: this module had ZERO save_graph() calls anywhere. Every
dismissed/promoted alert, and every alert run_scan() ever created, had been silently
discarded on server restart. Fixed: dismiss_alert() and promote_alert() each save
directly. _create_alert() deliberately does NOT save itself -- a first pass that did
was live-tested and timed out, since run_scan() (called on every GET /alerts/feed
fetch) can call _create_alert() many times in one pass on a never-before-scanned
graph, and a save_graph() per alert (this codebase's own established several-seconds-
per-call cost) made a single feed fetch take far too long. run_scan() instead does one
real save at the end, and only when it actually created something -- covering
everything _create_alert() added in that pass with a single call, and adding zero
extra cost to the common case where a re-fetch finds nothing new.
"""

from datetime import datetime, timezone, date, timedelta

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import TRIGGER_ALERT, CUSTOMER, LEAD, VEHICLE, FINANCE_CONTRACT, SERVICE_RECORD, RECALL
from core.relationship_types import GENERATED_LEAD
from core.lead_intake import create_lead
from core.lead_assignment import assign_lead
from core.workflow_tab_data import marketing_database_mining
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

ALERT_TYPES = {
    "lease_maturity": "Loan/Lease Maturity",
    "service_win_back": "Service Win-Back",
    "equity_mining": "Equity Position",
    "recall_open": "Open Recall",
    "conquest_match": "In-Market Conquest",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today():
    return datetime.now(timezone.utc).date()


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _all_of_type(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _relationships_from(entity_id, relationship_type):
    return [
        r for r in ledger.get_relationships()
        if r.source_id == entity_id and r.relationship_type == relationship_type
    ]


def _customer_name(customer):
    return f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip() or customer.id


def _customer_vehicles(customer_id):
    return [
        ledger.get_entity(r.target_id)
        for r in ledger.get_relationships()
        if r.source_id == customer_id and r.relationship_type == "OWNS"
        and ledger.get_entity(r.target_id) and ledger.get_entity(r.target_id).entity_type == VEHICLE
    ]


def _open_alert_exists(target_id, alert_type, source_reference):
    """core/compliance.py's run_full_scan() dedup precedent -- only an already-OPEN
    ("new") alert blocks a duplicate; a promoted/dismissed alert is a closed decision
    and doesn't block a later, fresh scan from re-flagging the same underlying signal
    if it still holds."""

    for a in ledger.get_all().values():

        if a.entity_type != TRIGGER_ALERT:
            continue

        attrs = a.attributes

        if (
            attrs.get("status") == "new"
            and attrs.get("target_entity_id") == target_id
            and attrs.get("alert_type") == alert_type
            and attrs.get("source_reference") == source_reference
        ):
            return True

    return False


def _create_alert(alert_type, target_entity_type, target_entity_id, target_name, headline, urgency, basis, source_reference=None, vehicle_id=None, notes=None):

    if _open_alert_exists(target_entity_id, alert_type, source_reference):
        return None

    alert_id = id_generator.generate("ALERT")

    alert = Entity(
        id=alert_id,
        entity_type=TRIGGER_ALERT,
        attributes={
            "alert_type": alert_type,
            "alert_type_label": ALERT_TYPES.get(alert_type, alert_type),
            "target_entity_type": target_entity_type,
            "target_entity_id": target_entity_id,
            "target_name": target_name,
            "vehicle_id": vehicle_id,
            "headline": headline,
            "urgency": urgency,
            "basis": basis,
            "notes": notes,
            "source_reference": source_reference,
            "status": "new",
            "created_at": _now(),
            "updated_at": _now(),
            "promoted_to_lead_id": None,
            "promoted_by": None,
            "promoted_at": None,
            "dismissed_by": None,
            "dismissed_at": None,
            "dismissal_notes": None,
        },
    )

    ledger.add_entity(alert)

    # Deliberately NOT saved here -- run_scan() below can call this many times in one
    # pass on a graph that's never been scanned before (a save_graph() per new alert
    # was tried and timed out a live smoke test: this codebase's own established
    # several-seconds-per-save cost, multiplied by dozens of new alerts in a single
    # GET /alerts/feed request, is a real regression). run_scan() does one real,
    # conditional save at the end covering everything this function created.

    return alert


def _scan_lease_maturity(horizon_days=90):

    created = []

    for customer in _all_of_type(CUSTOMER):

        for rel in _relationships_from(customer.id, "FINANCED_BY"):

            contract = ledger.get_entity(rel.target_id)

            if not contract or contract.entity_type != FINANCE_CONTRACT:
                continue

            contract_date = _parse_date(contract.attributes.get("ContractDate"))
            term_months = contract.attributes.get("TermMonths")

            if not contract_date or not term_months:
                continue

            try:
                term_months = int(term_months)
            except (TypeError, ValueError):
                continue

            maturity = contract_date + timedelta(days=term_months * 30)
            days_out = (maturity - _today()).days

            if 0 <= days_out <= horizon_days:

                urgency = "high" if days_out <= 30 else "medium" if days_out <= 60 else "low"

                alert = _create_alert(
                    "lease_maturity",
                    CUSTOMER,
                    customer.id,
                    _customer_name(customer),
                    f"Loan/lease matures in {days_out} day(s) ({maturity.isoformat()})",
                    urgency,
                    "ledger",
                    source_reference=contract.id,
                )

                if alert:
                    created.append(alert)

    return created


def _scan_service_win_back(months_threshold=6):

    cutoff = _today() - timedelta(days=int(months_threshold * 30))
    created = []

    for customer in _all_of_type(CUSTOMER):

        dates = []

        for rel in _relationships_from(customer.id, "AUTHORIZED"):

            record = ledger.get_entity(rel.target_id)

            if record and record.entity_type == SERVICE_RECORD:

                parsed = _parse_date(record.attributes.get("ServiceDate"))

                if parsed:
                    dates.append(parsed)

        last_service = max(dates) if dates else None

        if last_service is None:
            headline = "Never serviced at this dealership"
            urgency = "high"
        elif last_service <= cutoff:
            months_ago = int((_today() - last_service).days / 30)
            headline = f"No service visit in {months_ago} month(s) (last: {last_service.isoformat()})"
            urgency = "high" if months_ago >= 12 else "medium"
        else:
            continue

        alert = _create_alert(
            "service_win_back",
            CUSTOMER,
            customer.id,
            _customer_name(customer),
            headline,
            urgency,
            "ledger",
            source_reference="service_history",
        )

        if alert:
            created.append(alert)

    return created


def _scan_equity_mining():
    """Reuses core/workflow_tab_data.py's marketing_database_mining() candidate list
    directly rather than reimplementing the same HEURISTIC elapsed-term-as-%-of-total
    walk -- one real computation, two consumers (the CRM's database-mining view and
    this Timeline)."""

    result = marketing_database_mining("ADMIN")
    created = []

    for c in result.get("candidates", []):

        customer_id = c.get("customer_id")

        if not customer_id:
            continue

        customer = ledger.get_entity(customer_id)

        if not customer or customer.entity_type != CUSTOMER:
            continue

        pct = c.get("pct_term_elapsed", 0)
        urgency = "high" if pct >= 0.75 else "medium" if pct >= 0.6 else "low"

        alert = _create_alert(
            "equity_mining",
            CUSTOMER,
            customer.id,
            _customer_name(customer),
            f"Estimated {round(pct * 100)}% of loan term elapsed on {c.get('vin', 'a financed vehicle')} -- likely equity position",
            urgency,
            "heuristic",
            source_reference=c.get("finance_contract_id"),
            notes="HEURISTIC: estimated from elapsed contract term, not a real amortization payoff quote.",
        )

        if alert:
            created.append(alert)

    return created


def _scan_recall_open():

    open_recalls = [r for r in _all_of_type(RECALL) if r.attributes.get("open")]

    if not open_recalls:
        return []

    created = []

    for customer in _all_of_type(CUSTOMER):

        vehicles = _customer_vehicles(customer.id)

        if not vehicles:
            continue

        for recall in open_recalls:

            recall_make = str(recall.attributes.get("make", "")).strip().lower()
            recall_model = str(recall.attributes.get("model", "")).strip().lower()

            for vehicle in vehicles:

                vehicle_make = str(vehicle.attributes.get("Make", "")).strip().lower()
                vehicle_model = str(vehicle.attributes.get("Model", "")).strip().lower()

                if vehicle_make == recall_make and vehicle_model == recall_model:

                    alert = _create_alert(
                        "recall_open",
                        CUSTOMER,
                        customer.id,
                        _customer_name(customer),
                        f"Open recall on your {vehicle.attributes.get('Year', '')} {vehicle.attributes.get('Make', '')} "
                        f"{vehicle.attributes.get('Model', '')}: {recall.attributes.get('description', '')}",
                        "high",
                        "ledger",
                        source_reference=recall.id,
                        vehicle_id=vehicle.id,
                    )

                    if alert:
                        created.append(alert)

                    break

    return created


def _scan_conquest_match():

    created = []

    for lead in _all_of_type(LEAD):

        pipeline_state = lead.attributes.get("PipelineState")

        if pipeline_state not in ("NEW", "CONTACTED"):
            continue

        for rel in _relationships_from(lead.id, "INTERESTED_IN"):

            vehicle = ledger.get_entity(rel.target_id)

            if not vehicle or vehicle.entity_type != VEHICLE:
                continue

            name = f"{lead.attributes.get('FirstName', '')} {lead.attributes.get('LastName', '')}".strip() or lead.attributes.get("LeadID", lead.id)

            alert = _create_alert(
                "conquest_match",
                LEAD,
                lead.id,
                name,
                f"Interested in {vehicle.attributes.get('Year', '')} {vehicle.attributes.get('Make', '')} "
                f"{vehicle.attributes.get('Model', '')} -- still {pipeline_state.replace('_', ' ').title()}, no appointment set",
                "medium",
                "ledger",
                source_reference=vehicle.id,
                vehicle_id=vehicle.id,
            )

            if alert:
                created.append(alert)

            break

    return created


_SCANNERS = [
    _scan_lease_maturity,
    _scan_service_win_back,
    _scan_equity_mining,
    _scan_recall_open,
    _scan_conquest_match,
]


def run_scan():
    """Re-runs every real trigger check against the live graph, upserting new
    TriggerAlert records where a fresh, non-duplicate signal is found. Called on every
    GET /alerts/feed fetch (same "compute live off the real graph" convention as most
    of this codebase) rather than on a background scheduler -- always fresh, no extra
    asyncio hook needed.

    Saves once, only when something was actually created -- not once per alert (see
    _create_alert()'s own comment) and not on every call regardless of whether anything
    changed (this runs on every single feed fetch; an unconditional save would cost
    several real seconds on every page load once the graph reaches this size)."""

    created = []

    for scanner in _SCANNERS:
        created.extend(scanner())

    if created:
        save_graph(GRAPH_PATH)

    return created


def get_alert(alert_id):

    entity = ledger.get_entity(alert_id)

    if entity and entity.entity_type == TRIGGER_ALERT:
        return entity

    return None


def list_alerts(alert_type=None, status=None, target_entity_type=None):

    alerts = [e for e in ledger.get_all().values() if e.entity_type == TRIGGER_ALERT]

    if alert_type:
        alerts = [a for a in alerts if a.attributes.get("alert_type") == alert_type]

    if status:
        alerts = [a for a in alerts if a.attributes.get("status") == status]

    if target_entity_type:
        alerts = [a for a in alerts if a.attributes.get("target_entity_type") == target_entity_type]

    urgency_rank = {"high": 0, "medium": 1, "low": 2}

    alerts.sort(key=lambda a: (urgency_rank.get(a.attributes.get("urgency"), 3), a.attributes.get("created_at", "")), reverse=False)

    return alerts


def dismiss_alert(alert_id, dismissed_by, notes=None):

    alert = get_alert(alert_id)

    if not alert:
        return {"error": "Alert not found"}

    if alert.attributes.get("status") != "new":
        return {"error": f"Alert is already '{alert.attributes.get('status')}'"}

    alert.attributes["status"] = "dismissed"
    alert.attributes["dismissed_by"] = dismissed_by
    alert.attributes["dismissed_at"] = _now()
    alert.attributes["dismissal_notes"] = notes
    alert.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return alert


def promote_alert(alert_id, promoted_by, assign_to_employee_id=None):
    """The literal Marketing -> Sales handoff for one Timeline item. Customer-typed
    alerts get a real new Lead (source="Trigger Alert") tied back to the originating
    Customer via a real GENERATED_LEAD relationship; Lead-typed alerts (conquest) are
    assigned directly via the existing ASSIGNED_TO mechanism -- no duplicate Lead
    created since one already exists. Optionally assigns the resulting/existing Lead
    to a specific salesperson in the same call, a true one-click promote-and-assign."""

    alert = get_alert(alert_id)

    if not alert:
        return {"error": "Alert not found"}

    if alert.attributes.get("status") != "new":
        return {"error": f"Alert is already '{alert.attributes.get('status')}'"}

    target_type = alert.attributes.get("target_entity_type")
    target_id = alert.attributes.get("target_entity_id")

    if target_type == CUSTOMER:

        customer = ledger.get_entity(target_id)

        if not customer or customer.entity_type != CUSTOMER:
            return {"error": f"Customer '{target_id}' not found"}

        vehicle_id = alert.attributes.get("vehicle_id")
        vin = None

        if vehicle_id:
            vehicle = ledger.get_entity(vehicle_id)
            if vehicle and vehicle.entity_type == VEHICLE:
                vin = vehicle.attributes.get("VIN")

        lead = create_lead(
            promoted_by,
            customer.attributes.get("FirstName", ""),
            customer.attributes.get("LastName", ""),
            "Trigger Alert",
            phone=customer.attributes.get("Phone"),
            email=customer.attributes.get("Email"),
            city=customer.attributes.get("City"),
            state=customer.attributes.get("State"),
            vin=vin,
        )

        ledger.add_relationship(
            Relationship(source_id=customer.id, target_id=lead.id, relationship_type=GENERATED_LEAD)
        )

        if assign_to_employee_id:
            assign_lead(lead.id, assign_to_employee_id)

        alert.attributes["promoted_to_lead_id"] = lead.id

    elif target_type == LEAD:

        lead = ledger.get_entity(target_id)

        if not lead or lead.entity_type != LEAD:
            return {"error": f"Lead '{target_id}' not found"}

        if assign_to_employee_id:
            assign_lead(lead.id, assign_to_employee_id)

        alert.attributes["promoted_to_lead_id"] = lead.id

    else:
        return {"error": f"Unknown target_entity_type '{target_type}'"}

    alert.attributes["status"] = "promoted"
    alert.attributes["promoted_by"] = promoted_by
    alert.attributes["promoted_at"] = _now()
    alert.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return alert
