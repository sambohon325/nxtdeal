"""
Campaign & customer-lifecycle engine (2026-07-13, session 31) -- phase 2 of folding
NXTDeal's product suite into NXTDeal, per Sam: "sales, marketing, and operations
together... the full suite of products that NXTDeal provides... routed through the same
graph knowledge." This is the Bumper-style product line (Retention, Inventory Ads,
Finance renewal pushes, Accessory Accelerator) modeled as ONE generic campaign engine
rather than four separate stacked tools -- same "streamline the workflows that have been
stacked on top of each other for decades" instruction that drove the asset workflow.

Same graph-native rule as everything else here: a Campaign is an ordinary Entity in the
same core.dealeros.ledger every other entity type lives in. The audience isn't a
freeform query language (matches the "template-fill, no freeform canvas" scoping
decision already made for assets, session 30) -- each campaign type has a small,
structured set of audience params, and build_audience() answers them by walking the
graph's existing relationships (AUTHORIZED for service history, FINANCED_BY for finance
contracts, OWNS for vehicle ownership, INTERESTED_IN for lead interest) exactly the way
core/queries.py's get_customer_360()/get_vehicle_360() already do -- no new query engine.

A campaign can optionally reference an Asset (core/assets.py) via linked_asset_id -- the
creative the campaign is actually sending. core/campaigns_api.py's activate rule requires
that asset be 'approved' first if one is attached, which is what ties this new module to
the asset design/approval workflow built last session rather than leaving them as two
disconnected features.

No real send integrations exist (no email/SMS/direct-mail provider wired up) --
activating a campaign SIMULATES a send: it stamps sent_at/sent_count from the audience
snapshot taken at creation time. See BUILD_QUEUE.md for the explicit note on what a real
send integration would need.
"""

from datetime import datetime, timezone, date, timedelta

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import CAMPAIGN, CUSTOMER, LEAD, VEHICLE, FINANCE_CONTRACT, SERVICE_RECORD, RECURRING_SCHEDULE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Real, pre-existing data-loss bug found and fixed (2026-07-18, Marketing Growth
# Platform, Email/SMS upgrades slice) -- same class of bug session 105 already
# found and fixed in core/deals.py and core/marketing_lists.py: this entire
# module (create/activate/complete/cancel/update_campaign) had never once
# called save_graph() on any mutation since it shipped (session 31). Every real
# Campaign action taken through the live app was silently discarded on server
# restart. Fixed by adding save_graph(GRAPH_PATH) to every mutating function
# below, same right-before-`return` placement session 105's fix used.

# Individual sends (session 79 -- Sam: "a fully functional email builder (for mass and
# individual campaigns)... Both pull from the CRM"). A one-off email/SMS to a single
# Customer or Lead reuses this exact same Campaign entity/audience-builder engine
# rather than inventing a parallel "individual message" data model -- its "audience" is
# just a one-member list resolved from a target_id, same shape build_audience() already
# returns for every other campaign type, so every downstream consumer (activate/
# complete/cancel, the CRM Campaigns tab, employee_value.py's attribution if it's ever
# extended here) keeps working with zero special-casing.


CHANNELS = ["email", "sms", "direct_mail", "ringless_voicemail"]


# Fixed starter catalog, one entry per Bumper-style product line -- mirrors
# core/assets.py's ASSET_TEMPLATES shape (fixed catalog + a small `audience_fields`
# schema the frontend renders as a form, not a management screen). Add new campaign
# types here rather than inventing an admin UI to manage them.
CAMPAIGN_TYPES = {
    "retention": {
        "key": "retention",
        "name": "Service Retention",
        "category": "service",
        "description": "Win back customers who haven't been in for service in a while (or never have).",
        "default_channel": "email",
        "audience_fields": [
            {"key": "months_since_service", "label": "Months since last service (or never serviced)", "type": "number", "required": True, "default": 6},
        ],
    },
    "inventory_ads": {
        "key": "inventory_ads",
        "name": "Inventory Ads / Conquest",
        "category": "sales",
        "description": "Target leads interested in specific inventory (by make/model) with fresh ads.",
        "default_channel": "sms",
        "audience_fields": [
            {"key": "make", "label": "Make (optional)", "type": "text", "required": False},
            {"key": "model", "label": "Model (optional)", "type": "text", "required": False},
        ],
    },
    "finance_renewal": {
        "key": "finance_renewal",
        "name": "Finance Renewal / Payoff",
        "category": "finance",
        "description": "Target customers approaching the end of their loan or lease term.",
        "default_channel": "email",
        "audience_fields": [
            {"key": "months_to_maturity", "label": "Months until contract maturity", "type": "number", "required": True, "default": 3},
        ],
    },
    "accessory_accelerator": {
        "key": "accessory_accelerator",
        "name": "Accessory Accelerator",
        "category": "sales",
        "description": "Upsell accessories and protection products to recent buyers.",
        "default_channel": "sms",
        "audience_fields": [
            {"key": "days_since_sale", "label": "Days since purchase (max)", "type": "number", "required": True, "default": 30},
        ],
    },
    "general": {
        "key": "general",
        "name": "General Announcement",
        "category": "marketing",
        "description": "Broadcast to every customer -- store events, holiday hours, recalls.",
        "default_channel": "email",
        "audience_fields": [],
    },
    "individual": {
        "key": "individual",
        "name": "Individual Message",
        "category": "marketing",
        "description": "A one-off email or text to a single customer or lead -- pulled from the CRM, not a segment.",
        "default_channel": "email",
        "audience_fields": [
            {"key": "target_id", "label": "Customer or Lead ID", "type": "text", "required": True},
        ],
    },
    "event_promo": {
        "key": "event_promo",
        "name": "Event Promotion",
        "category": "marketing",
        "description": "Promote one specific dealership Event to its real invite/RSVP roster -- never a blanket broadcast.",
        "default_channel": "email",
        "audience_fields": [
            {"key": "event_id", "label": "Event ID", "type": "text", "required": True},
        ],
    },
}


def list_campaign_types():
    return list(CAMPAIGN_TYPES.values())


def get_campaign_type(campaign_type_key):
    return CAMPAIGN_TYPES.get(campaign_type_key)


def list_channels():
    return CHANNELS


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today():
    return datetime.now(timezone.utc).date()


def _parse_date(value):
    """Seed/imported data stores dates as plain ISO strings (see
    imports/generate_seed_data.py's DateSold/ContractDate/ServiceDate) -- tolerate
    missing/malformed values rather than raising, since audience segmentation should
    degrade gracefully on messy real-world data instead of 500ing the whole campaign."""

    if not value:
        return None

    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _relationships_from(entity_id, relationship_type):
    return [
        r for r in ledger.get_relationships()
        if r.source_id == entity_id and r.relationship_type == relationship_type
    ]


def _all_of_type(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _customer_last_service_date(customer_id):

    dates = []

    for rel in _relationships_from(customer_id, "AUTHORIZED"):

        record = ledger.get_entity(rel.target_id)

        if record and record.entity_type == SERVICE_RECORD:

            parsed = _parse_date(record.attributes.get("ServiceDate"))

            if parsed:
                dates.append(parsed)

    return max(dates) if dates else None


def _customer_finance_contracts(customer_id):

    contracts = []

    for rel in _relationships_from(customer_id, "FINANCED_BY"):

        contract = ledger.get_entity(rel.target_id)

        if contract and contract.entity_type == FINANCE_CONTRACT:
            contracts.append(contract)

    return contracts


def _customer_vehicles(customer_id):
    """Customer -OWNS-> Vehicle, per core/queries.py's get_vehicle_360() (which reads
    OWNS from the vehicle side) -- same relationship, read from the customer side here."""

    vehicles = []

    for rel in ledger.get_relationships():

        if rel.source_id == customer_id and rel.relationship_type == "OWNS":

            vehicle = ledger.get_entity(rel.target_id)

            if vehicle and vehicle.entity_type == VEHICLE:
                vehicles.append(vehicle)

    return vehicles


def _lead_interested_vehicles(lead_id):

    vehicles = []

    for rel in _relationships_from(lead_id, "INTERESTED_IN"):

        vehicle = ledger.get_entity(rel.target_id)

        if vehicle and vehicle.entity_type == VEHICLE:
            vehicles.append(vehicle)

    return vehicles


def _build_retention_audience(params):

    months = float(params.get("months_since_service") or 0)
    cutoff = _today() - timedelta(days=int(months * 30))

    matches = []

    for customer in _all_of_type(CUSTOMER):

        last_service = _customer_last_service_date(customer.id)

        if last_service is None or last_service <= cutoff:
            matches.append(customer)

    return matches


def _build_inventory_ads_audience(params):

    make = (params.get("make") or "").strip().lower()
    model = (params.get("model") or "").strip().lower()

    matches = []

    for lead in _all_of_type(LEAD):

        vehicles = _lead_interested_vehicles(lead.id)

        if not make and not model:

            if vehicles:
                matches.append(lead)

            continue

        for vehicle in vehicles:

            vehicle_make = str(vehicle.attributes.get("Make", "")).strip().lower()
            vehicle_model = str(vehicle.attributes.get("Model", "")).strip().lower()

            if (not make or vehicle_make == make) and (not model or vehicle_model == model):
                matches.append(lead)
                break

    return matches


def _build_finance_renewal_audience(params):

    months = float(params.get("months_to_maturity") or 0)
    horizon = _today() + timedelta(days=int(months * 30))

    matches = []

    for customer in _all_of_type(CUSTOMER):

        for contract in _customer_finance_contracts(customer.id):

            contract_date = _parse_date(contract.attributes.get("ContractDate"))
            term_months = contract.attributes.get("TermMonths")

            if not contract_date or not term_months:
                continue

            try:
                term_months = int(term_months)
            except (TypeError, ValueError):
                continue

            maturity = contract_date + timedelta(days=term_months * 30)

            if _today() <= maturity <= horizon:
                matches.append(customer)
                break

    return matches


def _build_accessory_accelerator_audience(params):

    days = float(params.get("days_since_sale") or 0)
    cutoff = _today() - timedelta(days=int(days))

    matches = []

    for customer in _all_of_type(CUSTOMER):

        for vehicle in _customer_vehicles(customer.id):

            sold_date = _parse_date(vehicle.attributes.get("DateSold"))

            if sold_date and sold_date >= cutoff:
                matches.append(customer)
                break

    return matches


def _build_general_audience(params):
    return _all_of_type(CUSTOMER)


def _build_individual_audience(params):
    """A one-member "audience" resolved from a real Customer or Lead id -- the
    individual-send path. Returns an empty list (not an error) for a missing/unknown/
    wrong-type id, same "degrade gracefully" rule _build_finance_renewal_audience etc.
    already follow for messy real-world input; core/campaigns_api.py's
    create_campaign_api surfaces a real error to the caller when the resulting
    audience is empty."""

    target_id = (params.get("target_id") or "").strip()

    if not target_id:
        return []

    entity = ledger.get_entity(target_id)

    if entity and entity.entity_type in (CUSTOMER, LEAD):
        return [entity]

    return []


def _build_event_promo_audience(params):
    """Audience = the real Event's own invite/RSVP roster (session 84's
    core/dealership_events.py) -- never a blanket 'every customer' broadcast, since
    this promotes ONE specific event to people actually connected to it. Prefers the
    Event's linked MarketingList (the real snapshot publish_event() already creates)
    and falls back to whoever has a real RSVP on file (walk-ins/self-registrations
    with no list membership, or a linked list that resolved to zero real members).
    Imports deferred to avoid a circular import -- core/dealership_events.py doesn't
    import core/campaigns.py, but keeping this import local matches the rest of this
    module's own "no top-level cross-department imports beyond what's always needed"
    convention."""

    from core.dealership_events import get_event, list_event_rsvps
    from core.marketing_lists import get_list

    event_id = (params.get("event_id") or "").strip()

    if not event_id:
        return []

    event = get_event(event_id)

    if not event:
        return []

    linked_list_id = event.attributes.get("linked_list_id")

    if linked_list_id:

        mlist = get_list(linked_list_id)

        if mlist:

            members = []

            for member_id in mlist.attributes.get("member_ids") or []:

                member = ledger.get_entity(member_id)

                if member and member.entity_type in (CUSTOMER, LEAD):
                    members.append(member)

            if members:
                return members

    members = []
    seen_ids = set()

    for rsvp in list_event_rsvps(event_id):

        target_id = rsvp.attributes.get("customer_id") or rsvp.attributes.get("lead_id")

        if not target_id or target_id in seen_ids:
            continue

        entity = ledger.get_entity(target_id)

        if entity and entity.entity_type in (CUSTOMER, LEAD):
            members.append(entity)
            seen_ids.add(target_id)

    return members


_AUDIENCE_BUILDERS = {
    "retention": _build_retention_audience,
    "inventory_ads": _build_inventory_ads_audience,
    "finance_renewal": _build_finance_renewal_audience,
    "accessory_accelerator": _build_accessory_accelerator_audience,
    "general": _build_general_audience,
    "individual": _build_individual_audience,
    "event_promo": _build_event_promo_audience,
}


def audience_entity_type(campaign_type_key):
    """inventory_ads targets Leads (they haven't bought yet); everything else targets
    existing Customers. "individual"/"event_promo" can target either, so it's an
    honest None here -- exposed so callers can label results correctly without
    hardcoding the exception inline. The audience member's own real entity_type is
    still always in _serialize_audience_member()'s output either way."""

    if campaign_type_key == "inventory_ads":
        return LEAD

    if campaign_type_key in ("individual", "event_promo"):
        return None

    return CUSTOMER


def build_audience(campaign_type_key, params):

    builder = _AUDIENCE_BUILDERS.get(campaign_type_key)

    if not builder:
        return []

    return builder(params or {})


def _serialize_audience_member(entity):

    if entity.entity_type == CUSTOMER:

        name = f"{entity.attributes.get('FirstName', '')} {entity.attributes.get('LastName', '')}".strip()

        return {"id": entity.id, "entity_type": CUSTOMER, "name": name or entity.id}

    if entity.entity_type == LEAD:

        return {"id": entity.id, "entity_type": LEAD, "name": entity.attributes.get("LeadID", entity.id)}

    return {"id": entity.id, "entity_type": entity.entity_type, "name": entity.id}


def preview_audience(campaign_type_key, params):

    members = build_audience(campaign_type_key, params)

    return {
        "campaign_type": campaign_type_key,
        "entity_type": audience_entity_type(campaign_type_key),
        "count": len(members),
        "sample": [_serialize_audience_member(m) for m in members[:10]],
    }


def _all_campaigns():
    return [e for e in ledger.get_all().values() if e.entity_type == CAMPAIGN]


def create_campaign(campaign_type_key, name, channel, created_by, params, linked_asset_id=None, linked_template_id=None):

    campaign_id = id_generator.generate("CAMP")

    audience = build_audience(campaign_type_key, params)

    entity = Entity(
        id=campaign_id,
        entity_type=CAMPAIGN,
        attributes={
            "campaign_type": campaign_type_key,
            "name": name,
            "channel": channel,
            "status": "draft",
            "params": params or {},
            "audience_ids": [m.id for m in audience],
            "audience_entity_type": audience_entity_type(campaign_type_key),
            "audience_count": len(audience),
            "linked_asset_id": linked_asset_id,
            # Email/SMS builder tie-in (session 79) -- the composed message (subject/
            # blocks or sms_body) this campaign actually sends, same optional-linked-
            # creative shape linked_asset_id already established for the Bumper-style
            # asset workflow. See core/email_templates.py.
            "linked_template_id": linked_template_id,
            # Editable campaign detail (session 82) -- Sam: "the campaigns should be
            # editable." Name and notes are the only free-text fields a campaign
            # owns outside its structured audience params, so they're what
            # update_campaign() below allows changing after creation.
            "notes": "",
            "created_by": created_by,
            "created_at": _now(),
            "updated_at": _now(),
            "activated_at": None,
            "completed_at": None,
            "sent_count": 0,
        },
    )

    ledger.add_entity(entity)

    save_graph(GRAPH_PATH)

    return entity


def get_campaign(campaign_id):

    entity = ledger.get_entity(campaign_id)

    if entity and entity.entity_type == CAMPAIGN:
        return entity

    return None


def activate_campaign(campaign_id):
    """Simulates a send -- see module docstring. Stamps sent_count from the audience
    snapshot taken at creation time (not re-queried), since a real campaign send
    shouldn't silently grow/shrink its target list after launch."""

    campaign = get_campaign(campaign_id)

    if not campaign:
        return None

    campaign.attributes["status"] = "active"
    campaign.attributes["activated_at"] = _now()
    campaign.attributes["sent_count"] = campaign.attributes.get("audience_count", 0)
    campaign.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return campaign


def complete_campaign(campaign_id):

    campaign = get_campaign(campaign_id)

    if not campaign:
        return None

    campaign.attributes["status"] = "completed"
    campaign.attributes["completed_at"] = _now()
    campaign.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return campaign


def cancel_campaign(campaign_id):

    campaign = get_campaign(campaign_id)

    if not campaign:
        return None

    campaign.attributes["status"] = "cancelled"
    campaign.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return campaign


_CAMPAIGN_EDITABLE_FIELDS = {"name", "notes"}


def update_campaign(campaign_id, patch):
    """Session 82 -- Sam: "the campaigns should be editable." Whole-object-patch
    semantics for just the two free-text fields a campaign owns outside its structured
    (type-specific) audience params -- name and notes. Status changes still only ever
    happen through activate_campaign()/complete_campaign()/cancel_campaign(), not this
    generic patch, so a campaign can't be silently pushed into an invalid lifecycle
    state through the edit form."""

    campaign = get_campaign(campaign_id)

    if not campaign:
        return None

    for key, value in (patch or {}).items():
        if key in _CAMPAIGN_EDITABLE_FIELDS:
            campaign.attributes[key] = value

    campaign.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return campaign


def get_campaign_members(campaign_id, page=1, page_size=25, entity_type_filter=None):
    """Real server-side pagination over the audience snapshot taken at creation time
    (campaign.attributes['audience_ids']) -- same 25/50/100-adjustable pagination Sam
    asked for on Lists (session 82), reused here rather than building a second
    pagination engine, since a campaign's audience and a list's membership are both
    just "an ordered array of real Customer/Lead ids" underneath."""

    campaign = get_campaign(campaign_id)

    if not campaign:
        return None

    member_ids = campaign.attributes.get("audience_ids") or []
    members = [ledger.get_entity(mid) for mid in member_ids]
    members = [m for m in members if m is not None]

    if entity_type_filter:
        members = [m for m in members if m.entity_type == entity_type_filter]

    total = len(members)
    page_size = max(1, min(int(page_size or 25), 200))
    page = max(1, int(page or 1))
    start = (page - 1) * page_size
    page_members = members[start:start + page_size]

    return {
        "campaign_id": campaign_id,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
        "members": [_serialize_audience_member(m) for m in page_members],
    }


def get_campaign_stats(campaign_id):
    """Session 82 -- Sam: "when you click on [a campaign] they should show... all the
    information that has been included as well as active measurements / analytics."
    Real stats computed from what this campaign actually has (status, audience/sent
    counts, real timestamps, real elapsed days-active) -- open/click engagement is
    honestly not_yet_tracked rather than fabricated, since core/campaigns.py's
    activate_campaign() SIMULATES a send (module docstring) and no real email/SMS
    delivery or tracking pipeline exists anywhere in this codebase to measure
    engagement from."""

    campaign = get_campaign(campaign_id)

    if not campaign:
        return None

    attrs = campaign.attributes
    activated_at = attrs.get("activated_at")
    completed_at = attrs.get("completed_at")

    days_active = None

    if activated_at:

        try:
            start = datetime.fromisoformat(str(activated_at))
            end = datetime.fromisoformat(str(completed_at)) if completed_at else datetime.now(timezone.utc)
            days_active = round((end - start).total_seconds() / 86400, 1)
        except ValueError:
            days_active = None

    return {
        "status": attrs.get("status"),
        "campaign_type": attrs.get("campaign_type"),
        "channel": attrs.get("channel"),
        "audience_count": attrs.get("audience_count", 0),
        "sent_count": attrs.get("sent_count", 0),
        "created_at": attrs.get("created_at"),
        "activated_at": activated_at,
        "completed_at": completed_at,
        "days_active": days_active,
        "not_yet_tracked": {
            "open_rate": "No real email/SMS delivery or tracking pipeline exists yet -- activating a campaign simulates a send (see this module's docstring), so open/click engagement can't be computed from real data.",
            "click_rate": "Same as open_rate -- no real delivery/tracking pipeline exists yet.",
        },
    }


def list_campaigns(status=None, created_by=None, campaign_type=None):

    campaigns = _all_campaigns()

    if status:
        campaigns = [c for c in campaigns if c.attributes.get("status") == status]

    if created_by:
        campaigns = [c for c in campaigns if c.attributes.get("created_by") == created_by]

    if campaign_type:
        campaigns = [c for c in campaigns if c.attributes.get("campaign_type") == campaign_type]

    # Same (created_at, id) tiebreaker as core/assets.py's list_assets() -- avoids
    # flaky "most recent first" ordering when two campaigns share a timestamp.
    campaigns.sort(key=lambda c: (c.attributes.get("created_at", ""), c.id), reverse=True)

    return campaigns


def list_pending_campaigns():
    return list_campaigns(status="draft")


# =====================================================================================
# Bumper parity: Duplication Station, Recurring Schedule, Multi-Planner (2026-07-25)
# =====================================================================================

def duplicate_campaign(campaign_id, created_by, new_name=None):
    """Duplication Station -- clone an existing campaign (its type, channel, params, and linked
    creative) into a fresh DRAFT the user can tweak and launch. The audience is rebuilt live from
    the same params (create_campaign re-runs build_audience), so a clone targets who qualifies NOW
    rather than the original's frozen snapshot."""
    original = get_campaign(campaign_id)
    if not original:
        return {"error": "Campaign not found"}
    a = original.attributes
    name = (new_name or "").strip() or f"{a.get('name', 'Campaign')} (Copy)"
    clone = create_campaign(
        a.get("campaign_type"),
        name,
        a.get("channel"),
        created_by,
        dict(a.get("params") or {}),
        linked_asset_id=a.get("linked_asset_id"),
        linked_template_id=a.get("linked_template_id"),
    )
    clone.attributes["notes"] = a.get("notes", "")
    clone.attributes["duplicated_from"] = campaign_id
    save_graph(GRAPH_PATH)
    return clone


def bulk_create_campaigns(specs, created_by):
    """Multi-Planner -- create several campaigns at once from one planner form. `specs` is a list
    of dicts {campaign_type, name, channel, params}. Each is validated independently; a bad row is
    reported without aborting the good ones (all-or-nothing would be a worse UX for a planner)."""
    created, errors = [], []
    for i, spec in enumerate(specs or []):
        ctype = (spec or {}).get("campaign_type")
        name = ((spec or {}).get("name") or "").strip()
        channel = (spec or {}).get("channel")
        if not get_campaign_type(ctype):
            errors.append({"index": i, "error": f"Unknown campaign_type '{ctype}'"})
            continue
        if not name:
            errors.append({"index": i, "error": "name is required"})
            continue
        if channel not in list_channels():
            errors.append({"index": i, "error": f"Unknown channel '{channel}'"})
            continue
        entity = create_campaign(ctype, name, channel, created_by, dict((spec or {}).get("params") or {}))
        created.append(entity.id)
    return {"created": created, "created_count": len(created), "errors": errors}


# ---- Recurring Schedule ----

RECURRING_CADENCES = ("daily", "weekly", "monthly")


def _add_cadence(d, cadence, interval):
    """Advance a date by one cadence step (interval multiplier)."""
    interval = max(1, int(interval or 1))
    if cadence == "daily":
        return d + timedelta(days=interval)
    if cadence == "weekly":
        return d + timedelta(days=7 * interval)
    # monthly -- add months, clamping the day to the target month's length.
    month_index = (d.year * 12 + (d.month - 1)) + interval
    year, month = divmod(month_index, 12)
    month += 1
    # last day of target month
    if month == 12:
        last = 31
    else:
        last = (date(year, month + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(d.day, last))


def _get_recurring_schedule(schedule_id):
    e = ledger.get_entity(schedule_id)
    return e if e and e.entity_type == RECURRING_SCHEDULE else None


def get_recurring_schedule(schedule_id):
    """Public accessor (used by the API layer)."""
    return _get_recurring_schedule(schedule_id)


def create_recurring_schedule(base_campaign_id, cadence, start_date, created_by, end_date=None, interval=1, name=None):
    """Set up a cadence that auto-clones + launches a base campaign. On-demand evaluation (see
    run_due_recurring_schedules) -- no background scheduler, same posture as workflow automation."""
    base = get_campaign(base_campaign_id)
    if not base:
        return {"error": "Base campaign not found"}
    if cadence not in RECURRING_CADENCES:
        return {"error": f"cadence must be one of {RECURRING_CADENCES}"}
    start = _parse_date(start_date)
    if not start:
        return {"error": "start_date must be a valid ISO date"}
    end = _parse_date(end_date) if end_date else None
    if end and end < start:
        return {"error": "end_date cannot be before start_date"}
    try:
        interval = max(1, int(interval or 1))
    except (TypeError, ValueError):
        return {"error": "interval must be a positive integer"}

    entity = Entity(
        id=id_generator.generate("RSCH"),
        entity_type=RECURRING_SCHEDULE,
        attributes={
            "base_campaign_id": base_campaign_id,
            "name": (name or "").strip() or f"Recurring: {base.attributes.get('name', 'Campaign')}",
            "cadence": cadence,
            "interval": interval,
            "start_date": start.isoformat(),
            "end_date": end.isoformat() if end else None,
            "next_run_date": start.isoformat(),
            "active": True,
            "created_by": created_by,
            "created_at": _now(),
            "updated_at": _now(),
            "runs": [],
        },
    )
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return entity


def list_recurring_schedules(active_only=False):
    out = [e for e in ledger.get_all().values() if e.entity_type == RECURRING_SCHEDULE]
    if active_only:
        out = [e for e in out if e.attributes.get("active")]
    return out


def set_recurring_schedule_active(schedule_id, active):
    sched = _get_recurring_schedule(schedule_id)
    if not sched:
        return {"error": "Recurring schedule not found"}
    sched.attributes["active"] = bool(active)
    sched.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return sched


def delete_recurring_schedule(schedule_id):
    sched = _get_recurring_schedule(schedule_id)
    if not sched:
        return {"error": "Recurring schedule not found"}
    # Soft-stop rather than deleting the audit trail of runs.
    sched.attributes["active"] = False
    sched.attributes["deleted"] = True
    sched.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"ok": True, "schedule_id": schedule_id}


def run_due_recurring_schedules(today=None):
    """On-demand pass (no background scheduler): for every active schedule whose next_run_date is
    due, clone + activate the base campaign and advance next_run_date by the cadence until it's in
    the future or past the end_date. Returns a summary of what launched."""
    today = _parse_date(today) if today else _today()
    launched, errors = [], []
    for sched in list_recurring_schedules(active_only=True):
        if sched.attributes.get("deleted"):
            continue
        a = sched.attributes
        cadence = a.get("cadence")
        interval = a.get("interval", 1)
        end = _parse_date(a.get("end_date")) if a.get("end_date") else None
        next_run = _parse_date(a.get("next_run_date"))
        if not next_run:
            continue
        guard = 0
        while next_run <= today and (end is None or next_run <= end) and guard < 60:
            guard += 1
            base = get_campaign(a.get("base_campaign_id"))
            if not base:
                errors.append({"schedule_id": sched.id, "error": "base campaign missing"})
                a["active"] = False
                break
            clone = duplicate_campaign(
                a.get("base_campaign_id"),
                created_by=a.get("created_by"),
                new_name=f"{base.attributes.get('name', 'Campaign')} — {next_run.isoformat()}",
            )
            if isinstance(clone, dict) and clone.get("error"):
                errors.append({"schedule_id": sched.id, "error": clone["error"]})
                break
            activate_campaign(clone.id)
            a.setdefault("runs", []).append({"campaign_id": clone.id, "run_date": next_run.isoformat(), "at": _now()})
            launched.append({"schedule_id": sched.id, "campaign_id": clone.id, "run_date": next_run.isoformat()})
            next_run = _add_cadence(next_run, cadence, interval)
        a["next_run_date"] = next_run.isoformat()
        if end is not None and next_run > end:
            a["active"] = False
        a["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    return {"launched": launched, "launched_count": len(launched), "errors": errors}
