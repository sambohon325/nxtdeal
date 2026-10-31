"""
Quick Lead intake (2026-07-13, session 47) -- the Sales/Marketing half of the
per-department "native quick-entry" ask: a walk-in or event lead needs to get into the
graph in seconds, not via a chat sentence or a CSV re-import. Produces a Lead entity
with the exact same attribute shape imports/lead_import.py's CSV path writes
(FirstName/LastName/Email/Phone/City/State/Source/Status/CreatedDate/VIN +
PipelineState/PipelineCreatedAt/PipelineStateSince), so a manually-created lead is
indistinguishable from an imported one to every dashboard (workload/leaderboard/
pipeline/escalation/followup) that already reads those exact keys. Auto-assigns to
whoever's logging it -- "I just took this walk-in" -- via a real ASSIGNED_TO
relationship (core/lead_assignment.py's mechanism), not the CSV path's business-key
resolution dance.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator, registry
from core.entities import Entity
from core.entity_types import LEAD
from core.relationships import Relationship
from core.relationship_types import INTERESTED_IN, ASSIGNED_TO
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Mirrors imports/lead_import.py's STATUS_TO_PIPELINE_STATE exactly -- a manually
# created lead should land in the same pipeline states the workflow engine already
# knows about.
STATUS_TO_PIPELINE_STATE = {
    "New": "NEW",
    "Contacted": "CONTACTED",
    "Qualified": "APPOINTMENT_SET",
    "Nurturing": "VISITED",
    "Lost": "LOST",
}

VALID_SOURCES = ["Walk-In", "Phone-Up", "Event", "Referral", "Website", "Autotrader", "Trigger Alert", "Orphan Owner Mining", "Service Handoff"]


def _now_date():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def create_lead(
    created_by,
    first_name,
    last_name,
    source,
    phone=None,
    email=None,
    city=None,
    state=None,
    vin=None,
    *,
    personal_site_id=None,
    message=None,
    website_id=None,
    contact_page=None,
    contact_section_index=None,
    website_request_id=None,
    inquiry_fingerprint=None,
    inquiry_intent=None,
    interested_vehicle_id=None,
):

    if interested_vehicle_id is not None:
        vehicle = ledger.get_entity(interested_vehicle_id)
        if not vehicle or vehicle.entity_type != "Vehicle":
            raise ValueError("The selected vehicle is unavailable")

    lead_id = id_generator.generate("LEAD")

    created_date = _now_date()

    attributes = {
        "LeadID": lead_id,
        "FirstName": first_name,
        "LastName": last_name,
        "Email": email or "",
        "Phone": phone or "",
        "City": city or "",
        "State": state or "",
        "Source": source,
        "Status": "New",
        "AssignedSalesperson": created_by,
        "CreatedDate": created_date,
        # Full-precision creation timestamp (session 100 follow-up) -- CreatedDate
        # above is date-only (always has been, matching imports/lead_import.py's CSV
        # shape), which makes a real "minutes since created" computation meaningless
        # for a lead logged five minutes ago. Historical CSV-imported leads have no
        # such precision and simply won't carry this field -- core/bdc.py's speed-to-
        # lead math checks for it explicitly rather than fabricating precision that
        # was never real.
        "CreatedAt": datetime.now(timezone.utc).isoformat(),
        "VIN": vin or "",
        "PipelineState": STATUS_TO_PIPELINE_STATE["New"],
        "PipelineCreatedAt": created_date,
        "PipelineStateSince": created_date,
    }

    # Personal-page provenance must accompany the first durable lead write.
    # Explicit fields keep callers from overriding canonical identity/ownership.
    if personal_site_id is not None:
        attributes["PersonalSiteID"] = personal_site_id
    if message is not None:
        attributes["Message"] = message

    if website_id is not None:
        attributes.update({
            "WebsiteID": website_id,
            "ContactPage": contact_page,
            "ContactSectionIndex": contact_section_index,
        })
        for key, value in {
            "WebsiteRequestID": website_request_id,
            "WebsiteInquiryFingerprint": inquiry_fingerprint,
            "WebsiteInquiryIntent": inquiry_intent,
            "WebsiteVehicleID": interested_vehicle_id,
        }.items():
            if value is not None:
                attributes[key] = value

    lead = Entity(id=lead_id, entity_type=LEAD, attributes=attributes)

    previous_entity = ledger.get_entity(lead_id)
    previous_registered = registry.lead_ids.get(lead_id)
    had_registration = lead_id in registry.lead_ids
    created_relationships = []

    def add_relationship(relationship):
        ledger.add_relationship(relationship)
        created_relationships.append(relationship)

    ledger.add_entity(lead)

    registry.register_lead(lead_id, lead_id)

    vehicle_id = interested_vehicle_id or (registry.find_vehicle(vin) if vin else None)
    if vehicle_id:
        add_relationship(Relationship(source_id=lead_id, target_id=vehicle_id, relationship_type=INTERESTED_IN))

    add_relationship(
        Relationship(
            source_id=created_by,
            target_id=lead_id,
            relationship_type=ASSIGNED_TO,
        )
    )

    try:
        save_graph(GRAPH_PATH)
    except Exception:
        if ledger.get_entity(lead_id) is lead:
            if previous_entity is None:
                ledger.entities.pop(lead_id, None)
            else:
                ledger.entities[lead_id] = previous_entity
        added_ids = {id(relationship) for relationship in created_relationships}
        ledger.relationships[:] = [r for r in ledger.relationships if id(r) not in added_ids]
        if registry.lead_ids.get(lead_id) == lead_id:
            if had_registration:
                registry.lead_ids[lead_id] = previous_registered
            else:
                registry.lead_ids.pop(lead_id, None)
        raise

    return lead
