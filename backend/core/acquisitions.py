"""
core/acquisitions.py -- Inventory department's "Acquisitions" item, the second
slice of Inventory's rebuild (first was the Master Vehicle Workspace, session
109). Sam's own framing: "probably one of the most important modules... an
entire buying center." Covers Vehicle Sourcing (auction/trade/direct-purchase),
a real Evaluate -> Price Risk -> Estimate Recon -> Review Market -> Approve
workflow, a Buy Recommendation Engine, and a real 2-step Purchase Approval
chain (Inventory Manager -> GM/Admin).

`AcquisitionRequest` is a genuinely new entity, deliberately distinct from
`AuctionTransaction` (session 59, which only ever represents an ALREADY-
acquired auction unit) and from `Vehicle` itself (which may not exist yet at
evaluation time -- a walk-in seller's car or a trade appraisal is being
evaluated before it's ever added to inventory). Once a request is approved and
actually purchased, `mark_purchased()` links it to the real Vehicle entity
that gets created -- no parallel inventory copy.

Sam's direct instruction (2026-07-17, immediately after the first Inventory
slice shipped): "when a lack of data is a problem, lets simply make up
simulated data to accommodate it." This is the first module built under that
directive -- `get_market_signal()`/`get_buy_recommendation()` generate
deterministic SIMULATED market-demand/turn-rate/comparable-sales figures
(seeded off make/model/year, so the same vehicle always gets the same
simulated read rather than fresh random noise per call) and
`get_factory_allocations()` generates a SIMULATED monthly OEM allocation feed
scoped to the Makes actually present in this dealer's real inventory. Every
simulated figure carries `basis: "simulated_market_data"` plus an explicit
disclaimer string everywhere it's surfaced -- same disclosure convention
`core/network_benchmark.py`'s simulated peer dealers already established, not
a silent fabrication. No real market/competitor/OEM-allocation data feed
exists anywhere in this codebase (confirmed absent, same finding sessions
63/85/106/109 already made) -- simulation replaces an honest
`not_yet_tracked` note here specifically because Sam asked for it, not because
the underlying gap became real.
"""

import hashlib
import math
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import ACQUISITION_REQUEST, VEHICLE, DEAL, AUCTION_TRANSACTION
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

SOURCE_TYPES = ("auction", "trade", "direct_purchase")
DIRECT_PURCHASE_CHANNELS = ("we_buy_cars", "web_lead", "walk_in")

# Ordered evaluation stages a request moves through before approval; approved/
# rejected/purchased are reached via their own dedicated actions below, not by
# advancing through this list directly.
EVALUATION_STAGES = ("evaluate", "price_risk", "estimate_recon", "review_market", "pending_approval")
TERMINAL_STAGES = ("approved", "rejected", "purchased")
ALL_STAGES = EVALUATION_STAGES + TERMINAL_STAGES

_MARKET_DISCLAIMER = (
    "SIMULATED market signal -- no real market/competitor data feed exists in "
    "this system yet. Demand level, average turn rate, and comparable-sales "
    "count are deterministic placeholders seeded by make/model/year, not live "
    "market data. Per Sam's direct instruction, this fills a genuine data gap "
    "with clearly-labeled simulated figures rather than leaving it blank."
)

_ALLOCATION_DISCLAIMER = (
    "SIMULATED factory allocation feed -- no real OEM allocation entity or "
    "integration exists in this codebase. Scoped to Makes actually present in "
    "this dealer's real inventory; allocated_units and allotment_month are "
    "deterministic placeholders, not a live OEM data feed."
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _serialize(req):
    """Flattens the raw AcquisitionRequest Entity into {id, **attributes}
    before it ever crosses the API boundary -- built correctly from the start
    this time, matching the fix applied retroactively to
    core/operations_tasks_api.py after a real production bug."""
    return {"id": req.id, **req.attributes}


def _get_request(request_id):
    r = ledger.get_entity(request_id)
    if not r or r.entity_type != ACQUISITION_REQUEST:
        return None
    return r


def _seeded_int(seed_str, modulo, offset=0):
    """A deterministic pseudo-random int in [offset, offset+modulo) derived
    from seed_str -- the same seed always produces the same number, so a
    simulated market read for '2022 Silverado' looks the same on every call
    rather than flickering like a slot machine."""
    digest = hashlib.sha256(seed_str.encode()).hexdigest()
    return offset + (int(digest, 16) % modulo)


def get_market_signal(make, model, year):
    """SIMULATED. See module docstring."""

    seed = f"{make or ''}|{model or ''}|{year or ''}"

    demand_levels = ["Low", "Medium", "Medium", "High"]
    demand = demand_levels[_seeded_int(seed + "|demand", len(demand_levels))]
    turn_rate = _seeded_int(seed + "|turn", 45, offset=18)
    comp_sales = _seeded_int(seed + "|comps", 40, offset=5)

    return {
        "demand_level": demand,
        "avg_turn_rate_days": turn_rate,
        "comparable_sales_count": comp_sales,
        "basis": "simulated_market_data",
        "disclaimer": _MARKET_DISCLAIMER,
    }


def get_buy_recommendation(make, model, year, estimated_acv=None):
    """SIMULATED demand/turn-rate signal, anchored to a real dollar figure
    (estimated_acv, supplied by the caller from a real trade appraisal / auction
    estimate / recon-adjusted value) where one exists -- the recommended bid
    RANGE is still simulated overall, but not a fully fabricated price when a
    real anchor is available."""

    signal = get_market_signal(make, model, year)

    recommended_bid = None
    try:
        acv = float(estimated_acv) if estimated_acv not in (None, "") else None
    except (TypeError, ValueError):
        acv = None

    if acv:
        adj = {"High": 1.05, "Medium": 1.0, "Low": 0.92}[signal["demand_level"]]
        recommended_bid = {
            "low": round(acv * adj * 0.94, 2),
            "high": round(acv * adj * 1.02, 2),
            "anchor_acv": acv,
        }

    return {**signal, "recommended_bid": recommended_bid}


def get_factory_allocations():
    """SIMULATED. See module docstring."""

    vehicles = [e for e in ledger.get_all().values() if e.entity_type == VEHICLE]
    makes = sorted({v.attributes.get("Make") for v in vehicles if v.attributes.get("Make")})

    allocations = []
    for make in makes:
        models = sorted({v.attributes.get("Model") for v in vehicles if v.attributes.get("Make") == make and v.attributes.get("Model")})
        top_models = models[:3] if models else ["Various"]
        qty = _seeded_int(make + "|qty", 12, offset=3)
        month_offset = _seeded_int(make + "|month", 3, offset=1)
        allocations.append({
            "make": make,
            "allocated_units": qty,
            "models": top_models,
            "allotment_month_offset": month_offset,
            "basis": "simulated_market_data",
        })

    return {"allocations": allocations, "disclaimer": _ALLOCATION_DISCLAIMER}


def create_acquisition_request(
    source_type, requested_by, year=None, make=None, model=None, trim=None,
    mileage=None, vin=None, estimated_acv=None, direct_purchase_channel=None,
    linked_deal_id=None, linked_auction_transaction_id=None, notes="",
):
    if source_type not in SOURCE_TYPES:
        return {"error": f"source_type must be one of {list(SOURCE_TYPES)}"}

    if source_type == "direct_purchase" and direct_purchase_channel not in DIRECT_PURCHASE_CHANNELS:
        return {"error": f"direct_purchase_channel must be one of {list(DIRECT_PURCHASE_CHANNELS)} for a direct_purchase request"}

    # Validate before allocating an ID, decoding a VIN or persisting a request.
    # Missing facts remain supported for VIN-assisted/imported evaluations.
    for field, value, pattern, message in (
        ("year", year, r"[0-9]{4}", "Enter a four-digit model year or leave it blank."),
        ("mileage", mileage, r"[0-9]+", "Enter mileage as a whole number, zero or greater, without commas."),
    ):
        if value is not None and str(value).strip() and not re.fullmatch(pattern, str(value).strip()):
            return {"error": message}
    if estimated_acv is not None and str(estimated_acv).strip():
        try:
            amount = Decimal(str(estimated_acv).strip())
            if (not amount.is_finite() or amount < 0 or not math.isfinite(float(amount))
                    or amount != amount.quantize(Decimal("0.01"))):
                raise ValueError("invalid amount")
            estimated_acv = float(amount)
        except (InvalidOperation, ValueError, OverflowError):
            return {"error": "Enter estimated cash value as a nonnegative finite amount with up to two decimal places."}
    else:
        estimated_acv = None

    if linked_deal_id:
        deal = ledger.get_entity(linked_deal_id)
        if not deal or deal.entity_type != DEAL:
            return {"error": f"Deal '{linked_deal_id}' not found"}

    if linked_auction_transaction_id:
        t = ledger.get_entity(linked_auction_transaction_id)
        if not t or t.entity_type != AUCTION_TRANSACTION:
            return {"error": f"AuctionTransaction '{linked_auction_transaction_id}' not found"}

    req_id = id_generator.generate("ACQ")

    entity = Entity(
        id=req_id,
        entity_type=ACQUISITION_REQUEST,
        attributes={
            "source_type": source_type,
            "direct_purchase_channel": direct_purchase_channel,
            "year": year, "make": make, "model": model, "trim": trim,
            "mileage": mileage, "vin": vin,
            "estimated_acv": estimated_acv,
            "vin_decode": None,
            "stage": "evaluate",
            "requested_by": requested_by,
            "linked_deal_id": linked_deal_id,
            "linked_auction_transaction_id": linked_auction_transaction_id,
            "linked_vehicle_id": None,
            "notes": notes or "",
            "price_risk_level": None,
            "price_risk_notes": None,
            "recon_estimate": None,
            "recon_notes": None,
            "market_review": None,
            "inventory_manager_approval": None,
            "gm_approval": None,
            "rejection_reason": None,
            "rejected_by": None,
            "rejected_at": None,
            "created_by": requested_by,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "purchased_at": None,
        },
    )

    # NXTDeal VIN Intelligence, Phase 3 -- when a real VIN is supplied at
    # creation time and any of year/make/model/trim wasn't also given,
    # best-effort auto-decode it to prefill exactly those blanks, same
    # backfill-only / never-overwrite-a-supplied-value convention
    # core/vin_decoder.py's apply_decode_to_vehicle() already established for
    # Vehicle records -- a real VIN cross-check happening automatically the
    # moment a unit enters the Buying Center, not a second manual step.
    # Deferred import (same cross-module-reuse convention as
    # core/loan_servicing.py's get_loan_financials()). Non-blocking: a decode
    # failure never prevents the request itself from being created.
    if vin and not all([entity.attributes.get("year"), entity.attributes.get("make"), entity.attributes.get("model")]):
        try:
            from core.vin_decoder import decode_vin
            decode = decode_vin(vin, attempt_live=True)
            resolved = decode.get("resolved") or {}
            if not entity.attributes.get("year") and resolved.get("year"):
                entity.attributes["year"] = str(resolved["year"])
            if not entity.attributes.get("make") and resolved.get("make"):
                entity.attributes["make"] = resolved["make"]
            if not entity.attributes.get("model") and resolved.get("model"):
                entity.attributes["model"] = resolved["model"]
            if not entity.attributes.get("trim") and resolved.get("trim"):
                entity.attributes["trim"] = resolved["trim"]
            entity.attributes["vin_decode"] = decode
        except Exception:
            pass

    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    return _serialize(entity)


def decode_and_prefill_acquisition_vin(request_id, updated_by, attempt_live=True):
    """Manual re-decode/re-prefill action for a request's own on-file VIN --
    e.g. retrying with attempt_live=True once this runs in a real deployment
    with genuine outbound network access, after an earlier offline-only
    decode. Same backfill-only rule as creation-time auto-decode: never
    overwrites a field a human has since entered by hand."""

    req = _get_request(request_id)
    if not req:
        return {"error": f"AcquisitionRequest '{request_id}' not found"}
    if _finalized(req):
        return {"error": f"Request is already {req.attributes.get('stage')} -- no further evaluation allowed"}

    vin = (req.attributes.get("vin") or "").strip()
    if not vin:
        return {"error": "This request has no VIN on file to decode."}

    from core.vin_decoder import decode_vin
    decode = decode_vin(vin, attempt_live=attempt_live)
    resolved = decode.get("resolved") or {}

    backfilled = []
    if not str(req.attributes.get("year") or "").strip() and resolved.get("year"):
        req.attributes["year"] = str(resolved["year"])
        backfilled.append("year")
    if not str(req.attributes.get("make") or "").strip() and resolved.get("make"):
        req.attributes["make"] = resolved["make"]
        backfilled.append("make")
    if not str(req.attributes.get("model") or "").strip() and resolved.get("model"):
        req.attributes["model"] = resolved["model"]
        backfilled.append("model")
    if not str(req.attributes.get("trim") or "").strip() and resolved.get("trim"):
        req.attributes["trim"] = resolved["trim"]
        backfilled.append("trim")

    req.attributes["vin_decode"] = decode
    req.attributes["vin_decode_backfilled_fields"] = backfilled
    req.attributes["updated_at"] = _now_iso()

    save_graph(GRAPH_PATH)
    return _serialize(req)


def get_acquisition_request(request_id):
    req = _get_request(request_id)
    if not req:
        return {"error": f"AcquisitionRequest '{request_id}' not found"}
    return _serialize(req)


def list_acquisition_requests(source_type=None, stage=None):
    reqs = [e for e in ledger.get_all().values() if e.entity_type == ACQUISITION_REQUEST]
    if source_type:
        reqs = [r for r in reqs if r.attributes.get("source_type") == source_type]
    if stage:
        reqs = [r for r in reqs if r.attributes.get("stage") == stage]
    reqs.sort(key=lambda r: r.attributes.get("created_at") or "", reverse=True)
    return {"count": len(reqs), "requests": [_serialize(r) for r in reqs]}


def _finalized(req):
    return req.attributes.get("stage") in TERMINAL_STAGES


def record_price_risk(request_id, updated_by, risk_level, notes=""):
    req = _get_request(request_id)
    if not req:
        return {"error": f"AcquisitionRequest '{request_id}' not found"}
    if _finalized(req):
        return {"error": f"Request is already {req.attributes.get('stage')} -- no further evaluation allowed"}
    if risk_level not in ("low", "medium", "high"):
        return {"error": "risk_level must be one of ['low', 'medium', 'high']"}

    req.attributes["price_risk_level"] = risk_level
    req.attributes["price_risk_notes"] = notes or ""
    req.attributes["stage"] = "price_risk"
    req.attributes["updated_at"] = _now_iso()

    save_graph(GRAPH_PATH)
    return _serialize(req)


def record_recon_estimate(request_id, updated_by, recon_estimate, notes=""):
    req = _get_request(request_id)
    if not req:
        return {"error": f"AcquisitionRequest '{request_id}' not found"}
    if _finalized(req):
        return {"error": f"Request is already {req.attributes.get('stage')} -- no further evaluation allowed"}
    try:
        recon_estimate = float(recon_estimate)
    except (TypeError, ValueError):
        return {"error": "recon_estimate must be a number"}

    req.attributes["recon_estimate"] = recon_estimate
    req.attributes["recon_notes"] = notes or ""
    req.attributes["stage"] = "estimate_recon"
    req.attributes["updated_at"] = _now_iso()

    save_graph(GRAPH_PATH)
    return _serialize(req)


def record_market_review(request_id, updated_by, notes=""):
    """Computes and stores the Buy Recommendation (SIMULATED demand signal,
    anchored to estimated_acv if on file) as the real payload for this stage,
    rather than just a free-text note."""

    req = _get_request(request_id)
    if not req:
        return {"error": f"AcquisitionRequest '{request_id}' not found"}
    if _finalized(req):
        return {"error": f"Request is already {req.attributes.get('stage')} -- no further evaluation allowed"}

    recommendation = get_buy_recommendation(
        req.attributes.get("make"), req.attributes.get("model"), req.attributes.get("year"),
        estimated_acv=req.attributes.get("estimated_acv"),
    )

    req.attributes["market_review"] = {
        "recommendation": recommendation,
        "notes": notes or "",
        "reviewed_by": updated_by,
        "reviewed_at": _now_iso(),
    }
    req.attributes["stage"] = "review_market"
    req.attributes["updated_at"] = _now_iso()

    save_graph(GRAPH_PATH)
    return _serialize(req)


def submit_for_approval(request_id, updated_by):
    req = _get_request(request_id)
    if not req:
        return {"error": f"AcquisitionRequest '{request_id}' not found"}
    if _finalized(req):
        return {"error": f"Request is already {req.attributes.get('stage')}"}
    if not req.attributes.get("market_review"):
        return {"error": "A market review (Buy Recommendation) is required before submitting for approval"}

    req.attributes["stage"] = "pending_approval"
    req.attributes["updated_at"] = _now_iso()

    save_graph(GRAPH_PATH)
    return _serialize(req)


def approve_by_inventory_manager(request_id, approved_by, notes=""):
    req = _get_request(request_id)
    if not req:
        return {"error": f"AcquisitionRequest '{request_id}' not found"}
    if req.attributes.get("stage") != "pending_approval":
        return {"error": "Request must be pending_approval before an Inventory Manager can approve it"}

    req.attributes["inventory_manager_approval"] = {
        "approved_by": approved_by, "approved_at": _now_iso(), "notes": notes or "",
    }
    req.attributes["updated_at"] = _now_iso()

    save_graph(GRAPH_PATH)
    return _serialize(req)


def approve_by_gm(request_id, approved_by, notes=""):
    req = _get_request(request_id)
    if not req:
        return {"error": f"AcquisitionRequest '{request_id}' not found"}
    if req.attributes.get("stage") != "pending_approval":
        return {"error": "Request must be pending_approval before final approval"}
    if not req.attributes.get("inventory_manager_approval"):
        return {"error": "Inventory Manager approval is required before GM sign-off"}

    req.attributes["gm_approval"] = {
        "approved_by": approved_by, "approved_at": _now_iso(), "notes": notes or "",
    }
    req.attributes["stage"] = "approved"
    req.attributes["updated_at"] = _now_iso()

    save_graph(GRAPH_PATH)
    return _serialize(req)


def reject_request(request_id, rejected_by, reason):
    req = _get_request(request_id)
    if not req:
        return {"error": f"AcquisitionRequest '{request_id}' not found"}
    if _finalized(req):
        return {"error": f"Request is already {req.attributes.get('stage')}"}
    if not reason or not reason.strip():
        return {"error": "A rejection reason is required"}

    req.attributes["stage"] = "rejected"
    req.attributes["rejection_reason"] = reason.strip()
    req.attributes["rejected_by"] = rejected_by
    req.attributes["rejected_at"] = _now_iso()
    req.attributes["updated_at"] = _now_iso()

    save_graph(GRAPH_PATH)
    return _serialize(req)


def mark_purchased(request_id, updated_by, vehicle_id=None):
    req = _get_request(request_id)
    if not req:
        return {"error": f"AcquisitionRequest '{request_id}' not found"}
    if req.attributes.get("stage") != "approved":
        return {"error": "Request must be approved (both Inventory Manager and GM sign-off) before it can be marked purchased"}

    if vehicle_id:
        v = ledger.get_entity(vehicle_id)
        if not v or v.entity_type != VEHICLE:
            return {"error": f"Vehicle '{vehicle_id}' not found"}
        req.attributes["linked_vehicle_id"] = vehicle_id

    req.attributes["stage"] = "purchased"
    req.attributes["purchased_at"] = _now_iso()
    req.attributes["updated_at"] = _now_iso()

    save_graph(GRAPH_PATH)
    return _serialize(req)


def get_acquisitions_summary():
    reqs = [e for e in ledger.get_all().values() if e.entity_type == ACQUISITION_REQUEST]

    by_stage = {}
    by_source = {}
    for r in reqs:
        stage = r.attributes.get("stage")
        source = r.attributes.get("source_type")
        by_stage[stage] = by_stage.get(stage, 0) + 1
        by_source[source] = by_source.get(source, 0) + 1

    pending_approval = [r for r in reqs if r.attributes.get("stage") == "pending_approval"]
    awaiting_gm = [
        r for r in pending_approval
        if r.attributes.get("inventory_manager_approval") and not r.attributes.get("gm_approval")
    ]

    return {
        "total_requests": len(reqs),
        "by_stage": by_stage,
        "by_source_type": by_source,
        "pending_approval_count": len(pending_approval),
        "awaiting_gm_signoff_count": len(awaiting_gm),
    }
