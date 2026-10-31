"""
core/inventory_menu.py -- real data behind Inventory's 8-item Top Menu
(core/menu_catalog.py), session 63 continuation. inventory.pdf's own framing: the
department is asset-driven -- "What do I own? Where is it? How much is it worth? How
fast can I move it?" -- and its Menu Bar (Overview | Inventory | Acquisitions | Lot
Management | Pricing | Merchandising | Wholesale | Reporting) maps directly onto those
four questions plus command-center/reporting bookends.

Same discipline as core/operations_menu.py/core/sales_menu.py/core/service_menu.py/
core/marketing_menu.py: reuse an already-built function wherever it's a genuine match,
compute a small new real aggregate where the graph has the underlying data but nobody
had queried it this way yet, and use an honest `not_yet_tracked` note (never a
fabricated number) wherever inventory.pdf asks for something this data model doesn't
back at all. The two biggest structural gaps, confirmed against the live graph before
writing this module: Vehicle has no acquisition/stock-date field (so no real
day-based aging, turn rate, or holding cost can be computed -- price-band distribution,
already built for the Operations rollout as `inventory_aging_pricing_bands`, is the
real signal available today) and zero Image entities exist in the seed despite the
HAS_IMAGE relationship type existing (so "Missing Photos" is a real, honest 100% --
not fabricated, just the true state of this data).

core/operations_menu.py already has `vehicles()`/`inventory()`/`scheduling()` items
that touch the same underlying Vehicle/AuctionTransaction data -- this module reuses
the SAME underlying functions but frames them through Inventory's distinct lens
(acquisitions sourcing, physical lot control, the pricing desk, merchandising/photo
health, wholesale disposition) rather than duplicating Operations' command-center
framing.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import VEHICLE, DEAL, DOCUMENT, AUCTION_TRANSACTION

from core.workflow_tab_data import (
    inventory_auction_acquisition,
    inventory_lot_audit,
    inventory_wholesale_disposition,
    inventory_aging_pricing_bands,
    operations_recon_queue,
)
from core.data_connections_api import readiness_predictions_api
from core.ai_tools import search_entities, get_entity_by_id, get_related_entities
from core.vehicle_lifecycle_api import get_vehicle_workspace_api
from core.acquisitions_api import get_acquisitions_summary_api, get_factory_allocations_api, list_acquisition_requests_api
from core.pricing_desk_api import get_pricing_queue_api
from core.inventory_overview import get_inventory_overview_enrichment
from core.lot_control_api import get_lot_map_api, get_key_board_api, get_showroom_board_api, list_damage_reports_api
from core.merchandising_api import get_merchandising_queue_api, get_featured_vehicles_api
from core.wholesale_desk_api import get_wholesale_desk_summary_api, get_sold_wholesale_units_api
from core.inventory_syndication_api import get_syndication_overview_api
from core.vehicle_lifecycle import get_cost_breakdown
from core.pricing_desk import get_market_pricing
from core.merchandising import get_vdp_health

# Reporting = Department Intelligence integration (Sam: "the dynamic reporting is
# supposed to be integrated in the reporting section of each department"). Department
# Intelligence's real KPI engine (core/department_intelligence.py) only has 5 keys --
# sales/service/parts/fi/executive -- not one per menu department, so this is an honest
# gap for Inventory rather than a stretch mapping onto an unrelated key.
_DI_GAP_NOTE = {
    "available": False,
    "note": (
        "No 1:1 Department Intelligence key exists for Inventory -- the 5 real keys "
        "are sales/service/parts/fi/executive (see core/department_intelligence.py)."
    ),
}


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _unsold_vehicles():
    return [v for v in _entities(VEHICLE) if not v.attributes.get("DateSold")]


def _vehicle_has_image(vehicle_id):
    return any(
        rel.source_id == vehicle_id and rel.relationship_type == "HAS_IMAGE"
        for rel in ledger.get_relationships()
    )


def _primary_photo(vehicle_id):
    """The first real photo URL for a vehicle (App Suite roadmap Phase 2 -- close the photo
    gap). Walks the HAS_IMAGE relationship to real Image entities (core/merchandising.py).
    Returns None when the vehicle has no photos on file -- never a fabricated URL, so the UI
    shows its placeholder honestly until the dealer's photo feed populates."""
    for rel in ledger.get_relationships():
        if rel.source_id == vehicle_id and rel.relationship_type == "HAS_IMAGE":
            img = ledger.get_entity(rel.target_id)
            if img:
                url = img.attributes.get("URL") or img.attributes.get("ImageURL") or img.attributes.get("url")
                if url:
                    return url
    return None


def overview(role):
    """inventory.pdf's "Overview" item: the Inventory command center. Total
    Inventory Value, Wholesale Candidates, and the (price-banded) aging
    distribution are real. Average Days in Stock, Aged Units (30/60/90+),
    Inventory Turn Rate, and Market Days Supply were honest `not_yet_tracked`
    gaps as of session 109 -- closed in session 110's Overview slice
    (core/inventory_overview.py) per Sam's direct instruction to simulate
    genuine data gaps rather than leave them blank; all four are now real
    (SIMULATED) figures, clearly labeled basis="simulated_market_data".
    Frontline Ready Units is the one genuinely REAL figure closed this same
    slice -- a real count off core/vehicle_lifecycle.py's lifecycle_status,
    not simulated at all.

    readiness_score (added 2026-07-17, Inventory rebuild wishlist item #1) is
    a single 0-100 composite Readiness Score -- see
    core/inventory_overview.py's get_readiness_score() docstring for the full
    70% real / 30% simulated weighting."""

    unsold = _unsold_vehicles()
    total_value = sum(_safe_float(v.attributes.get("Price")) for v in unsold)

    aging = inventory_aging_pricing_bands(role)
    wholesale = inventory_wholesale_disposition(role)
    auctions = inventory_auction_acquisition(role)
    recon = operations_recon_queue(role)

    incoming = [
        t for t in auctions.get("transactions", [])
        if t.get("transport_status") != "delivered"
    ]

    funded_deals = [d for d in _entities(DEAL) if d.attributes.get("status") == "funded"]

    enrichment = get_inventory_overview_enrichment()

    return {
        "total_inventory_value": round(total_value, 2),
        "active_inventory_count": len(unsold),
        "incoming_vehicles": {"count": len(incoming)},
        "wholesale_candidates": {"count": wholesale.get("count", 0)},
        "inventory_aging_by_price_band": aging.get("by_price_band"),
        "average_days_in_stock": enrichment["aging_summary"],
        "aged_units_30_60_90": enrichment["aging_summary"].get("aged_units_by_band"),
        "inventory_turn_rate": enrichment["turn_rate"],
        "market_days_supply": enrichment["market_days_supply"],
        "lifecycle_stage_counts": enrichment["lifecycle_stage_counts"],
        "readiness_score": enrichment["readiness_score"],
        "vehicle_pipeline": {
            "purchased": auctions.get("count", 0),
            "in_transit": auctions.get("by_transport_status", {}).get("in_transit", 0),
            "recon": recon.get("used_unsold_count", 0),
            "merchandising": enrichment["lifecycle_stage_counts"].get("Merchandising"),
            "frontline_ready": enrichment["frontline_ready_units"],
            "sold_or_wholesale": len(funded_deals) + wholesale.get("count", 0),
        },
    }


def inventory(role, query=None):
    """inventory.pdf's "Inventory" item: the master inventory explorer -- the Single
    Vehicle Record / Vehicle Detail Workspace. Search by VIN/stock number/free text
    (year/make/model/status all match via the existing search_entities tokenizer).
    Recon Status and Activity Timeline are now REAL, as of the Inventory department's
    Master Vehicle Workspace slice (core/vehicle_lifecycle.py's lifecycle_status/
    recon_checklist/cost_breakdown/ownership/activity_feed) -- this Top Menu path
    reuses that same real engine rather than duplicating it, matching the established
    "the dedicated board talks directly to the real routes, the plain chat/menu path
    stays consistent with what it shows" convention (session 106's vehicles()
    enrichment did the same for Operations). Market Value and Day Supply remain real
    gaps -- no market-valuation feed and no acquisition-date field exist anywhere in
    this codebase. Photos is real (and, honestly, always zero right now -- no Image
    entity has ever been created in this seed)."""

    if not query:
        unsold = _unsold_vehicles()
        return {
            "default_view": "unsold_inventory",
            "count": len(unsold),
            "vehicles": [
                {
                    "id": v.id, "vin": v.attributes.get("VIN"), "stock_number": v.attributes.get("StockNumber"),
                    "year": v.attributes.get("Year"), "make": v.attributes.get("Make"), "model": v.attributes.get("Model"),
                    "condition": v.attributes.get("Condition"), "lot": v.attributes.get("Lot"),
                    "price": v.attributes.get("Price"),
                    "photo_url": _primary_photo(v.id),
                    "mileage": v.attributes.get("Mileage"),
                }
                for v in unsold[:50]
            ],
        }

    if query.upper().startswith("VEH-"):
        entity = get_entity_by_id(role, query.upper())
        if "error" in entity:
            return entity
        related = get_related_entities(role, query.upper())
        attrs = entity.get("attributes", {}) if isinstance(entity, dict) else {}
        price = _safe_float(attrs.get("Price"))
        cost = _safe_float(attrs.get("Cost"))
        workspace = get_vehicle_workspace_api(role, query.upper())
        return {
            "vehicle": entity,
            "related_entities": related,
            "vehicle_profile": {
                "cost_basis": attrs.get("Cost"),
                "current_price": attrs.get("Price"),
                "margin": round(price - cost, 2) if price and cost else None,
                "has_photos": _vehicle_has_image(query.upper()),
            },
            "lifecycle": None if "error" in workspace else {
                "lifecycle_status": workspace.get("lifecycle_status"),
                "status_history": workspace.get("status_history"),
                "recon_checklist": workspace.get("recon_checklist"),
                "vendor_assignments": workspace.get("vendor_assignments"),
            },
            "cost_breakdown": None if "error" in workspace else workspace.get("cost_breakdown"),
            "ownership": None if "error" in workspace else workspace.get("ownership"),
            "activity_feed": None if "error" in workspace else workspace.get("activity_feed"),
            "not_yet_tracked": {
                "market_value": "No market-valuation data feed exists yet.",
                "day_supply": "No acquisition-date field exists to compute this yet.",
            },
        }

    results = [r for r in search_entities(role, query) if r["entity_type"] == VEHICLE]
    # Phase 2: attach the primary photo URL to each search hit (null when none on file).
    for r in results:
        vid = r.get("id") or r.get("entity_id")
        if vid:
            r["photo_url"] = _primary_photo(vid)
    return {"query": query, "count": len(results), "results": results}


def acquisitions(role):
    """inventory.pdf's "Acquisitions" item: the sourcing center. Auction Purchases /
    Transportation Tracking / Incoming Inventory / Vehicles In Transit are all real,
    reused directly from inventory_auction_acquisition (seeded AuctionTransaction
    entities). Trade Acquisitions is real (Deals with a trade_in on file).

    Factory Allocations, Purchase Requests, and Acquisition Approvals were honest
    `not_yet_tracked` gaps as of session 109's first Inventory slice -- closed in
    this same session's follow-up (core/acquisitions.py) per Sam's direct
    instruction to simulate genuine data gaps rather than leave them blank.
    Purchase Requests and Acquisition Approvals are now REAL (a real
    AcquisitionRequest evaluation/approval-chain workflow, distinct from an
    AuctionTransaction). Factory Allocations is SIMULATED (no real OEM allocation
    feed exists anywhere in this codebase) -- clearly labeled
    basis="simulated_market_data" on every figure, not silently presented as real."""

    auctions = inventory_auction_acquisition(role)

    trade_deals = [d for d in _entities(DEAL) if d.attributes.get("trade_in")]

    vehicles_by_id = {v.id: v for v in _entities(VEHICLE)}
    variances = []
    for t in auctions.get("transactions", []):
        vehicle = vehicles_by_id.get(t.get("vehicle_id"))
        bid = _safe_float(t.get("bid_amount"))
        if vehicle and bid:
            cost = _safe_float(vehicle.attributes.get("Cost"))
            if cost:
                variances.append(cost - bid)

    cost_analysis = {
        "matched_transactions": len(variances),
        "avg_cost_vs_bid_variance": round(sum(variances) / len(variances), 2) if variances else None,
        "note": "Real comparison of AuctionTransaction bid_amount to the eventual Vehicle.Cost, where both exist on the same unit.",
    }

    acq_summary = get_acquisitions_summary_api(role)
    pending = list_acquisition_requests_api(role, stage="pending_approval") if not isinstance(acq_summary, dict) or "error" not in acq_summary else {"requests": []}
    factory_allocations = get_factory_allocations_api(role)

    return {
        "auction_purchases": {"count": auctions.get("count", 0), "by_transport_status": auctions.get("by_transport_status")},
        "vehicles_in_transit": {"count": auctions.get("by_transport_status", {}).get("in_transit", 0)},
        "incoming_inventory": {
            "count": len([t for t in auctions.get("transactions", []) if t.get("transport_status") != "delivered"]),
            "transactions": [t for t in auctions.get("transactions", []) if t.get("transport_status") != "delivered"][:25],
        },
        "trade_acquisitions": {"count": len(trade_deals)},
        "cost_analysis": cost_analysis,
        "purchase_requests": acq_summary,
        "acquisition_approvals": {
            "pending_approval": pending.get("requests", []) if isinstance(pending, dict) else [],
        },
        "factory_allocations": factory_allocations,
    }


def lot_management(role, query=None):
    """inventory.pdf's "Lot Management" item: physical inventory control. Vehicle
    Locations (by-lot counts) and a real data-integrity check (Vehicles marked sold
    with no PURCHASED relationship -- the closest real proxy this data model has to
    "Missing Units") both reuse inventory_lot_audit directly.

    Lot Map, Key Management, Damage Reports, Showroom Assignments, and QR/check-in
    scans were honest `not_yet_tracked` gaps as of session 109 -- closed in session
    110's Lot Management slice (core/lot_control.py). Unlike Pricing/Acquisitions,
    these are internal tracking capabilities this codebase simply hadn't built yet,
    not data that requires an external feed -- built as REAL features, not
    simulated. Geofencing remains an honest gap even under the simulate-data policy
    (a simulated GPS coordinate with no real map behind it would be misleading, not
    a useful stand-in)."""

    if query:
        results = [r for r in search_entities(role, query) if r["entity_type"] == VEHICLE]
        return {"query": query, "count": len(results), "results": results}

    audit = inventory_lot_audit(role)

    return {
        "vehicle_locations_by_lot": audit.get("unsold_by_lot"),
        "total_vehicles": audit.get("total_vehicles"),
        "ownership_mismatches": {
            "count": audit.get("sold_without_purchase_relationship"),
            "discrepancies": audit.get("discrepancies"),
            "note": "The real proxy this data model has for 'Missing Units' -- a Vehicle marked sold with no real PURCHASED relationship on file.",
        },
        "lot_map": get_lot_map_api(role),
        "key_management": get_key_board_api(role),
        "damage_reports": list_damage_reports_api(role, status="open"),
        "showroom_assignments": get_showroom_board_api(role),
        "qr_scans": {
            "note": "Real, per-vehicle check-in scan logging is available -- see /lot-control/{vehicle_id}/scan. No fleet-wide scan aggregate is surfaced here since scans are inherently a per-vehicle event log, not a lot-wide KPI.",
        },
        "not_yet_tracked": {
            "geofencing": "No geofencing integration exists yet -- a simulated GPS coordinate with no real map/geofence rendering would be misleading, not a useful stand-in.",
        },
    }


def pricing(role, query=None):
    """inventory.pdf's "Pricing" item: the pricing desk. Price-band distribution and
    the zero-price pricing queue (units missing a price entirely -- a real, actionable
    gap) are real. Margin Analysis is a genuinely new aggregate: average price-to-cost
    margin across ALL unsold inventory (not just the thin-margin wholesale
    candidates).

    Market Pricing, Pricing Recommendations, Age-Based Adjustments, and Competitor
    Comparisons were honest `not_yet_tracked` gaps as of session 109 -- closed in
    session 110's Pricing Desk slice (core/pricing_desk.py) per Sam's direct
    instruction to simulate genuine data gaps rather than leave them blank. All four
    are now real (SIMULATED) responses, clearly labeled basis="simulated_market_data"
    on every figure, not silently presented as real -- surfaced here via a real
    worklist (`pricing_desk_queue`, unsold inventory ranked by worst real margin
    first, each with a real blended recommendation attached), not just per-vehicle on
    request."""

    if query:
        results = [r for r in search_entities(role, query) if r["entity_type"] == VEHICLE]
        return {"query": query, "count": len(results), "results": results}

    aging = inventory_aging_pricing_bands(role)
    unsold = _unsold_vehicles()

    zero_price = [
        {"vehicle_id": v.id, "vin": v.attributes.get("VIN"), "stock_number": v.attributes.get("StockNumber")}
        for v in unsold
        if not v.attributes.get("Price") or _safe_float(v.attributes.get("Price")) <= 0
    ]

    margins = []
    for v in unsold:
        price = _safe_float(v.attributes.get("Price"))
        cost = _safe_float(v.attributes.get("Cost"))
        if price:
            margins.append((price - cost) / price)

    margin_analysis = {
        "unsold_with_margin_data": len(margins),
        "avg_margin_pct": round(sum(margins) / len(margins), 3) if margins else None,
        "min_margin_pct": round(min(margins), 3) if margins else None,
        "max_margin_pct": round(max(margins), 3) if margins else None,
    }

    pricing_desk_queue = get_pricing_queue_api(role, limit=25)

    return {
        "aging_by_price_band": aging.get("by_price_band"),
        "pricing_queue": {"count": len(zero_price), "vehicles": zero_price},
        "margin_analysis": margin_analysis,
        "pricing_desk_queue": pricing_desk_queue,
        "not_yet_tracked": {
            "price_change_history": "Real as of the Pricing Desk slice on any vehicle whose price has been changed through it -- Vehicle.price_history is now populated going forward, but pre-existing units have no history entries retroactively.",
        },
    }


def merchandising(role):
    """inventory.pdf's "Merchandising" item: digital inventory presentation. Missing
    Photos was already real. Missing Comments, VDP Health Scores, Inventory Feed
    Status, Featured Vehicles, Frontline Ready Units, Upload Assets, and Publish
    Listings were honest `not_yet_tracked` gaps as of session 109 -- closed in
    session 110's Merchandising slice (core/merchandising.py). A deliberate MIX:
    photo upload, description, featured flag, and frontline-ready are all REAL
    (internal capabilities nobody had built, same "build it real" call Lot
    Management made); VDP Health Score and Inventory Feed Status are SIMULATED (a
    genuine external gap -- no real VDP-analytics platform or third-party listing
    feed is connected anywhere in this system), clearly labeled."""

    unsold = _unsold_vehicles()
    missing_photos = [v for v in unsold if not _vehicle_has_image(v.id)]
    missing_comments = [v for v in unsold if not (v.attributes.get("description") or "").strip()]

    frontline_ready = get_inventory_overview_enrichment()["frontline_ready_units"]

    return {
        "missing_photos": {
            "count": len(missing_photos),
            "pct_of_unsold": round(len(missing_photos) / len(unsold), 3) if unsold else None,
            "note": "Real -- upload real photos via the Merchandising board's real image-upload action (core/merchandising.py's add_vehicle_image()) to close this gap for real, not by fabricating a count.",
        },
        "missing_comments": {
            "count": len(missing_comments),
            "pct_of_unsold": round(len(missing_comments) / len(unsold), 3) if unsold else None,
        },
        "frontline_ready_units": frontline_ready,
        "featured_vehicles": get_featured_vehicles_api(role),
        "merchandising_queue": get_merchandising_queue_api(role, limit=25),
        "not_yet_tracked": {},
    }


def wholesale(role, query=None):
    """inventory.pdf's "Wholesale" item: the disposition center. Wholesale Candidates
    and the Auction Queue both reuse inventory_wholesale_disposition directly (same
    real thin-margin population, framed as the actionable queue). Title Status is a
    genuinely new real check -- cross-referencing wholesale candidates against the
    categorized Document vault (session 60's seed_documents()) for a 'Title' document
    on file.

    Open Offers, Sold Wholesale Units, and Fund Collection were honest
    `not_yet_tracked` gaps as of session 109 -- closed in session 110's Wholesale
    slice (core/wholesale_desk.py). Same "internal tracking gap, not external data
    gap" call Lot Management/Merchandising already made -- built REAL, not
    simulated: a real WholesaleOffer entity backs Open Offers, a real
    disposition_channel flag on Vehicle (set by mark_wholesale_sold()) backs Sold
    Wholesale Units, and a real append-only settlement record backs Fund
    Collection."""

    if query:
        results = [r for r in search_entities(role, query) if r["entity_type"] == VEHICLE]
        return {"query": query, "count": len(results), "results": results}

    disposition = inventory_wholesale_disposition(role)

    title_docs_by_vehicle = {
        doc.attributes.get("EntityID")
        for doc in _entities(DOCUMENT)
        if doc.attributes.get("EntityType") == VEHICLE and doc.attributes.get("DocumentType") == "Title"
    }

    candidates = disposition.get("candidates", [])
    with_title = [c for c in candidates if c.get("vehicle_id") in title_docs_by_vehicle]
    without_title = [c for c in candidates if c.get("vehicle_id") not in title_docs_by_vehicle]

    desk = get_wholesale_desk_summary_api(role)

    return {
        "wholesale_candidates": disposition,
        "auction_queue": {"count": disposition.get("count", 0), "candidates": candidates[:25]},
        "title_status": {
            "candidates_with_title_on_file": len(with_title),
            "candidates_missing_title": len(without_title),
            "missing_title_vehicle_ids": [c["vehicle_id"] for c in without_title][:25],
        },
        "open_offers": desk.get("open_offers") if isinstance(desk, dict) else None,
        "sold_wholesale_units": desk.get("sold_wholesale_units") if isinstance(desk, dict) else None,
        "fund_collection": desk.get("fund_collection") if isinstance(desk, dict) else None,
        "not_yet_tracked": {},
    }


def syndication(role):
    """A new 9th Inventory Top Menu item (2026-07-19) -- Inventory Syndication.
    Composes core/merchandising.py's real per-vehicle simulated feed-sync status
    into a dealership-wide rollup (core/inventory_syndication.py), plus real
    Lead.Source-based cross-platform lead/revenue performance
    (core/marketing_attribution.py's get_channel_mix(), filtered to syndication
    platforms). A thin pass-through -- the real generate/apply actions live
    behind their own dedicated /inventory-syndication/* routes, not this menu
    dispatch, same "bespoke board bypasses /menu/data for its own extra views"
    precedent every other rebuild in this codebase established."""

    return get_syndication_overview_api(role)


def reporting(role):
    """inventory.pdf's "Reporting" item: formal inventory analytics -- the eighth and
    final item of Sam's original 8-item Inventory spec. Aging (price-band), Wholesale,
    and Pricing reports reuse the same real functions the other items already surface.
    Acquisition Reports' Source Performance is a genuinely new aggregate (auction
    transactions grouped by auction_house).

    Turn Rate, Holding Cost, Auction/Trade ROI, Market Position, VDP/lead-conversion,
    Capital Utilization, and Forecasted Aging Risk were honest `not_yet_tracked` gaps
    as of session 109 -- closed this session via the same real+simulated engines this
    Inventory rebuild already built: Turn Rate reuses `core/inventory_overview.py`'s
    SIMULATED figure (built for Overview, not recomputed a second way here). Holding
    Cost and Capital Utilization are REAL, off `core/vehicle_lifecycle.py`'s real
    per-vehicle Cost Breakdown (session 109) -- floorplan_interest honestly defaults
    to 0 for units nobody has entered a real figure against yet, not fabricated.
    Disposition ROI is REAL, off this session's own Wholesale Desk (realized
    wholesale sale price minus cost) and funded Deals (realized retail Price minus
    cost) -- an honest substitute for Sam's literal "Auction ROI/Trade ROI," since
    this data model can't cleanly attribute a specific historical unit's ROI back to
    its original acquisition channel (source_type on AcquisitionRequest is only
    tracked going forward from this session, not retroactively). Market Position and
    VDP/Lead Conversion are SIMULATED, aggregating the same per-vehicle simulated
    signals Pricing and Merchandising already compute (never a third, independently-
    seeded number). Forecasted Aging Risk is SIMULATED, off the same aging-band
    distribution Overview already established. Executive inventory value reuses the
    real total from overview(); forecasting reuses core/prediction.py's real
    ledger-based units_sold forecast (readiness_predictions_api's "sales" entry)."""

    unsold = _unsold_vehicles()
    total_value = sum(_safe_float(v.attributes.get("Price")) for v in unsold)

    aging = inventory_aging_pricing_bands(role)
    wholesale_data = inventory_wholesale_disposition(role)
    auctions = inventory_auction_acquisition(role)
    merch = merchandising(role)

    by_auction_house = {}
    for t in auctions.get("transactions", []):
        house = t.get("auction_house") or "Unknown"
        by_auction_house[house] = by_auction_house.get(house, 0) + 1

    wholesale_loss_total = round(
        sum(c["margin"] for c in wholesale_data.get("candidates", []) if c["margin"] < 0), 2
    )

    readiness = readiness_predictions_api()
    sales_forecast = next((d for d in readiness.get("departments", []) if d["department"] == "sales"), None)

    # --- Turn Rate (SIMULATED, reused from Overview) + Forecasted Aging Risk (SIMULATED) ---
    overview_enrichment = get_inventory_overview_enrichment()
    aging_summary = overview_enrichment["aging_summary"]
    aged_units = aging_summary.get("aged_units_by_band", {})
    at_risk = aged_units.get("91+ days", 0)
    forecasted_aging_risk = {
        "units_at_risk_91_plus_days": at_risk,
        "pct_of_unsold": round(at_risk / len(unsold), 3) if unsold else None,
        "basis": aging_summary.get("basis"),
        "disclaimer": "SIMULATED -- projected off the same simulated aging-band distribution Overview computes, not a real day-based projection.",
    }

    # --- Holding Cost + Capital Utilization (REAL, off Cost Breakdown) ---
    total_investment = 0.0
    floorplan_total = 0.0
    for v in unsold:
        cb = get_cost_breakdown(v.id)
        if "error" in cb:
            continue
        total_investment += cb.get("total_investment") or 0
        floorplan_total += _safe_float(cb.get("breakdown", {}).get("floorplan_interest"))

    holding_cost = {
        "total_floorplan_interest": round(floorplan_total, 2),
        "note": "Real -- sums each unsold vehicle's real floorplan_interest field (core/vehicle_lifecycle.py's Cost Breakdown). Honestly near-zero until managers record real per-unit floorplan interest through the Inventory board.",
    }
    capital_utilization = {
        "total_investment": round(total_investment, 2),
        "total_inventory_value": round(total_value, 2),
        "utilization_ratio": round(total_investment / total_value, 3) if total_value else None,
        "note": "Real -- total real cost-basis investment (Cost Breakdown's total_investment, summed) as a share of total real inventory value (Price, summed).",
    }

    # --- Disposition ROI (REAL, wholesale + retail realized) ---
    sold_wholesale = get_sold_wholesale_units_api(role, limit=1000)
    wholesale_roi_total = 0.0
    wholesale_roi_count = 0
    if isinstance(sold_wholesale, dict) and "error" not in sold_wholesale:
        for entry in sold_wholesale.get("vehicles", []):
            sale = entry.get("wholesale_sale") or {}
            cost = _safe_float(entry.get("cost"))
            sale_price = _safe_float(sale.get("sale_price"))
            if sale_price:
                wholesale_roi_total += sale_price - cost
                wholesale_roi_count += 1

    funded_deals = [d for d in _entities(DEAL) if d.attributes.get("status") == "funded"]
    vehicles_by_id = {v.id: v for v in _entities(VEHICLE)}
    retail_roi_total = 0.0
    retail_roi_count = 0
    for d in funded_deals:
        vehicle = vehicles_by_id.get(d.attributes.get("vehicle_id"))
        if vehicle:
            price = _safe_float(vehicle.attributes.get("Price"))
            cost = _safe_float(vehicle.attributes.get("Cost"))
            if price:
                retail_roi_total += price - cost
                retail_roi_count += 1

    disposition_roi = {
        "wholesale": {"units": wholesale_roi_count, "total_roi": round(wholesale_roi_total, 2)},
        "retail": {"units": retail_roi_count, "total_roi": round(retail_roi_total, 2)},
        "note": (
            "Real realized ROI (sale price minus Vehicle.Cost) by disposition channel -- "
            "an honest substitute for a literal Auction-vs-Trade split, since this data "
            "model can't retroactively attribute a historical unit's ROI back to its "
            "original acquisition source."
        ),
    }

    # --- Market Position + VDP/Lead Conversion (SIMULATED, aggregated from Pricing/Merchandising) ---
    market_positions = {"below_market": 0, "at_market": 0, "above_market": 0}
    total_views = 0
    total_lead_rate = 0.0
    vdp_sample = 0
    for v in unsold:
        mp = get_market_pricing(v.id)
        if mp.get("price_position") in market_positions:
            market_positions[mp["price_position"]] += 1

        vdp = get_vdp_health(v.id)
        if "error" not in vdp:
            total_views += vdp.get("simulated_page_views", 0)
            total_lead_rate += vdp.get("simulated_lead_conversion_rate", 0)
            vdp_sample += 1

    market_position_report = {
        "distribution": market_positions,
        "basis": "simulated_market_data",
        "disclaimer": "SIMULATED -- aggregates each unsold vehicle's own simulated market position (core/pricing_desk.py's Market Pricing), not a real competitor-listing feed.",
    }
    vdp_lead_conversion_report = {
        "avg_simulated_page_views": round(total_views / vdp_sample, 1) if vdp_sample else None,
        "avg_simulated_lead_conversion_rate": round(total_lead_rate / vdp_sample, 4) if vdp_sample else None,
        "sample_size": vdp_sample,
        "basis": "simulated_market_data",
        "disclaimer": "SIMULATED -- aggregates each unsold vehicle's own simulated VDP engagement figures (core/merchandising.py's VDP Health Score), not a real VDP-analytics platform.",
    }

    return {
        "aging_reports": {"by_price_band": aging.get("by_price_band"), "forecasted_aging_risk": forecasted_aging_risk},
        "acquisition_reports": {
            "source_performance_by_auction_house": by_auction_house,
            "total_acquisitions": auctions.get("count", 0),
        },
        "pricing_reports": {"margin_analysis": pricing(role).get("margin_analysis"), "market_position": market_position_report},
        "merchandising_reports": {"photo_completion": merch.get("missing_photos"), "vdp_lead_conversion": vdp_lead_conversion_report},
        "wholesale_reports": {
            "candidate_count": wholesale_data.get("count", 0),
            "loss_total_on_negative_margin_candidates": wholesale_loss_total,
        },
        "disposition_roi": disposition_roi,
        "capital_reports": {"holding_cost": holding_cost, "capital_utilization": capital_utilization},
        "turn_rate": overview_enrichment["turn_rate"],
        "executive_reports": {
            "total_inventory_value": round(total_value, 2),
            "active_inventory_count": len(unsold),
        },
        "forecasting": sales_forecast,
        "department_intelligence": _DI_GAP_NOTE,
        "not_yet_tracked": {},
    }
