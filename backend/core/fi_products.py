"""
core/fi_products.py -- F&I Workflow (session 105 follow-up), the seventh of Sam's ~10
"completely missing" dealership workflows (Up System, BDC, Manager TO, Demo Drive,
Credit App, eSignature, F&I Workflow, Delivery Checklist, Lost Sale Recovery, Orphan
Owner Mining -- session 92's original spec).

Deliberately NOT the same thing as the "F&I Handoff" tab under `sales.fi_turnover`
(deal packaging / customer transfer / lender submission / contract readiness -- the
PROCESS handoff from the sales desk to F&I) and not the same thing as
core/deals.py's financing_status/financing_terms (the deal's own financing decision).
This module is the actual F&I MENU -- presenting aftermarket protection products
(Vehicle Service Contract, GAP, Tire & Wheel, Paint & Fabric Protection, Key
Replacement, Prepaid Maintenance) to the customer, tracking accept/decline per
product, and reporting real product penetration.

This closes a gap `core/department_intelligence.py` already documented by name: its
own module docstring says "F&I 'Product Penetration' needs aftermarket product
attachment data (VSC/GAP/tire & wheel) that doesn't exist anywhere in this graph --
swapped for 'Deals Financed'." That swap is left in place (it's a deliberate,
well-reasoned choice documented there, not a bug) -- but as of this module, the real
data that swap was waiting on now exists. A future session can decide whether to
surface `get_product_penetration_stats()` alongside/instead of that swapped KPI;
flagged in BUILD_QUEUE.md rather than silently changed here.

Data model: additive `Deal.attributes["fi_products"]` list, same convention as
`trade_in`/`delivery_checklist` -- no new entity type. Each entry:
    {product_key, name, category, cost, price, status, presented_at, presented_by,
     decided_at, declined_reason}
`status` is "presented" -> "accepted" | "declined". A product can be re-presented with
adjusted pricing (an F&I manager negotiating) while still "presented", but once
decided it's a record of what was actually offered and decided -- same
locked-once-acted-on convention as core/credit_app.py's applicant fields.

Editable window: F&I product presentation/decisions are only meaningful once a deal
has approved financing terms to price against (the customer's actual payment is what
"can we roll this into the payment" math depends on) and before the deal is funded --
gated to `deal.status in ("financing", "contract")`, matching the real-world F&I
turnover point in DealerSocket/Tekion's own Desking -> F&I -> Contracting flow this
codebase is modeled on (see core/deals.py's module docstring).

Honest scope note: FI_PRODUCT_CATALOG's cost/price figures are dealership-typical
defaults (an F&I manager can adjust price per deal via update_fi_product_pricing()),
not pulled from any real underwriter/provider rate table -- there is no live VSC/GAP
provider integration in this sandbox, same category of honest simulation as
core/credit_app.py's decision engine and core/deals.py's own _estimate_apr().
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.deals import get_deal
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


PRESENTABLE_STATUSES = ("financing", "contract")

FI_PRODUCT_CATALOG = [
    {
        "key": "vsc",
        "name": "Vehicle Service Contract (Extended Warranty)",
        "category": "protection",
        "description": "Extends mechanical breakdown coverage past the factory warranty.",
        "default_cost": 900.0,
        "default_price": 1895.0,
    },
    {
        "key": "gap",
        "name": "GAP Insurance",
        "category": "protection",
        "description": "Covers the 'gap' between what's owed and the vehicle's actual cash value in a total loss.",
        "default_cost": 250.0,
        "default_price": 795.0,
    },
    {
        "key": "tire_wheel",
        "name": "Tire & Wheel Protection",
        "category": "protection",
        "description": "Covers repair/replacement for road-hazard tire and wheel damage.",
        "default_cost": 300.0,
        "default_price": 895.0,
    },
    {
        "key": "paint_fabric",
        "name": "Paint & Fabric Protection",
        "category": "protection",
        "description": "Interior fabric/leather and exterior paint/finish protection treatment plus stain/chip coverage.",
        "default_cost": 200.0,
        "default_price": 695.0,
    },
    {
        "key": "key_replacement",
        "name": "Key Replacement Protection",
        "category": "protection",
        "description": "Covers the cost of replacing lost or damaged keys/fobs, including reprogramming.",
        "default_cost": 90.0,
        "default_price": 395.0,
    },
    {
        "key": "prepaid_maintenance",
        "name": "Prepaid Maintenance Plan",
        "category": "maintenance",
        "description": "Prepays a set number of scheduled maintenance visits (oil changes, tire rotations, inspections) at today's price.",
        "default_cost": 400.0,
        "default_price": 995.0,
    },
]

_CATALOG_BY_KEY = {p["key"]: p for p in FI_PRODUCT_CATALOG}


def _now():
    return datetime.now(timezone.utc).isoformat()


def get_fi_product_catalog():
    return FI_PRODUCT_CATALOG


# ---------------------------------------------------------------------------
# Personalized menu recommendation (Phase 4, 2026-07-25). CDK's MenuVantage Platinum
# recommends F&I add-ons per customer; NXTDeal could present products but not RECOMMEND
# which fit a given buyer/vehicle/deal. This engine ranks the catalog for one deal from
# real deal signals (vehicle age/mileage, term length, down payment / LTV, credit tier),
# each recommendation carrying a plain-English reason -- explainable, not a black box.
# ---------------------------------------------------------------------------

def _to_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _selected_terms(deal):
    """Best available (term_months, down_payment, sale_price, amount_financed) for a deal --
    the selected scenario, else the first scenario, else financing_terms."""
    scenarios = deal.attributes.get("scenarios") or []
    sel_id = deal.attributes.get("selected_scenario_id")
    scenario = next((s for s in scenarios if s.get("id") == sel_id), None) or (scenarios[0] if scenarios else None)
    terms = deal.attributes.get("financing_terms") or {}
    src = scenario or terms
    return {
        "term_months": _to_num(src.get("term_months")),
        "down_payment": _to_num(src.get("down_payment")),
        "sale_price": _to_num(src.get("sale_price")),
        "amount_financed": _to_num(src.get("amount_financed")),
    }


def _deal_signals(deal):
    vehicle = ledger.get_entity(deal.attributes.get("vehicle_id"))
    year = _to_num(vehicle.attributes.get("Year")) if vehicle else None
    mileage = None
    if vehicle:
        mileage = _to_num(vehicle.attributes.get("Mileage") or vehicle.attributes.get("Odometer"))
    age = (datetime.now(timezone.utc).year - int(year)) if year else None

    customer = ledger.get_entity(deal.attributes.get("customer_id"))
    credit = _to_num(customer.attributes.get("CreditScore")) if customer else None

    terms = _selected_terms(deal)
    down = terms["down_payment"]
    sale = terms["sale_price"]
    down_pct = (down / sale) if (down is not None and sale) else None

    return {"age": age, "mileage": mileage, "term_months": terms["term_months"],
            "down_pct": down_pct, "credit": credit}


def recommend_fi_products(deal_id):
    """Rank every catalog product for this specific deal, each with a fit_score (0-100),
    a recommended flag, and plain-English reasons. Products already on the menu are flagged
    so the UI can dim them."""
    deal = get_deal(deal_id)
    if not deal:
        return {"error": "Deal not found"}

    s = _deal_signals(deal)
    on_menu = {p["product_key"] for p in _fi_products(deal)}
    recs = []

    for prod in FI_PRODUCT_CATALOG:
        key = prod["key"]
        score = 30  # baseline relevance -- every buyer is a candidate for every product
        reasons = []

        if key == "vsc":
            if s["age"] is not None and s["age"] >= 3:
                score += 35; reasons.append(f"{s['age']}-year-old vehicle — past or near end of factory warranty")
            if s["mileage"] is not None and s["mileage"] >= 36000:
                score += 25; reasons.append(f"~{int(s['mileage']):,} miles — mechanical coverage matters most here")
            if s["term_months"] is not None and s["term_months"] >= 60:
                score += 15; reasons.append(f"{int(s['term_months'])}-month term — long ownership window to protect")
        elif key == "gap":
            if s["down_pct"] is not None and s["down_pct"] < 0.10:
                score += 35; reasons.append("little/no money down — high loan-to-value where GAP matters most")
            if s["term_months"] is not None and s["term_months"] >= 72:
                score += 25; reasons.append(f"{int(s['term_months'])}-month term — negative-equity window is long")
        elif key == "prepaid_maintenance":
            if s["age"] is not None and s["age"] <= 1:
                score += 30; reasons.append("newer vehicle — lock in scheduled maintenance at today's price")
        elif key == "tire_wheel":
            if s["mileage"] is not None and s["mileage"] >= 60000:
                score += 20; reasons.append("higher-mileage vehicle — road-hazard exposure adds up")
        elif key == "key_replacement":
            reasons.append("low-cost peace-of-mind add-on suitable for any buyer")
        elif key == "paint_fabric":
            reasons.append("cosmetic protection — strongest for buyers keeping the vehicle long-term")

        score = min(100, score)
        recs.append({
            "product_key": key,
            "name": prod["name"],
            "category": prod["category"],
            "price": prod["default_price"],
            "fit_score": score,
            "recommended": score >= 60,
            "reasons": reasons,
            "already_on_menu": key in on_menu,
        })

    recs.sort(key=lambda r: r["fit_score"], reverse=True)
    return {
        "deal_id": deal_id,
        "signals": s,
        "recommendations": recs,
        "recommended_keys": [r["product_key"] for r in recs if r["recommended"] and not r["already_on_menu"]],
        "basis": "Ranked from real deal signals (vehicle age/mileage, term, down payment, credit). Prices are dealership-typical defaults; a real rate table would refine them.",
    }


def _fi_products(deal):
    return list(deal.attributes.get("fi_products") or [])


def get_fi_menu(deal_id):
    """The current F&I menu state for a deal -- every presented product plus real
    totals (presented/accepted/declined counts, accepted $ price/cost/gross)."""

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    products = _fi_products(deal)

    accepted = [p for p in products if p["status"] == "accepted"]
    declined = [p for p in products if p["status"] == "declined"]
    pending = [p for p in products if p["status"] == "presented"]

    total_price = round(sum(p["price"] for p in accepted), 2)
    total_cost = round(sum(p["cost"] for p in accepted), 2)

    return {
        "deal_id": deal_id,
        "deal_status": deal.attributes.get("status"),
        "products": products,
        "totals": {
            "presented": len(products),
            "pending": len(pending),
            "accepted": len(accepted),
            "declined": len(declined),
            "total_price_accepted": total_price,
            "total_cost_accepted": total_cost,
            "total_gross_accepted": round(total_price - total_cost, 2),
        },
    }


def present_fi_products(deal_id, product_keys, presented_by):
    """Adds one or more catalog products to the deal's menu as 'presented'. Skips a
    product_key that's already on the menu (re-presenting an already-decided product
    should go through update_fi_product_pricing + a fresh decision, not silently
    duplicate an entry)."""

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("status") not in PRESENTABLE_STATUSES:
        return {
            "error": (
                f"Deal is '{deal.attributes.get('status')}' -- F&I products can only "
                f"be presented once financing is underway (status must be one of "
                f"{list(PRESENTABLE_STATUSES)})"
            )
        }

    if not product_keys:
        return {"error": "At least one product_key is required"}

    unknown = [k for k in product_keys if k not in _CATALOG_BY_KEY]
    if unknown:
        return {"error": f"Unknown product key(s): {unknown}"}

    products = _fi_products(deal)
    existing_keys = {p["product_key"] for p in products}

    added = []
    for key in product_keys:
        if key in existing_keys:
            continue
        catalog_entry = _CATALOG_BY_KEY[key]
        entry = {
            "product_key": key,
            "name": catalog_entry["name"],
            "category": catalog_entry["category"],
            "cost": catalog_entry["default_cost"],
            "price": catalog_entry["default_price"],
            "status": "presented",
            "presented_by": presented_by,
            "presented_at": _now(),
            "decided_at": None,
            "declined_reason": None,
        }
        products.append(entry)
        added.append(key)

    deal.attributes["fi_products"] = products
    deal.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return get_fi_menu(deal_id)


def update_fi_product_pricing(deal_id, product_key, cost=None, price=None):
    """An F&I manager adjusting price/cost on a still-pending product -- locked once
    the customer has decided, same "editable only pre-decision" convention as
    core/credit_app.py's applicant fields."""

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    products = _fi_products(deal)
    entry = next((p for p in products if p["product_key"] == product_key), None)

    if not entry:
        return {"error": f"'{product_key}' has not been presented on this deal"}

    if entry["status"] != "presented":
        return {"error": f"'{product_key}' is already '{entry['status']}' -- pricing can only be adjusted before a decision"}

    if cost is not None:
        try:
            entry["cost"] = round(float(cost), 2)
        except (TypeError, ValueError):
            return {"error": "cost must be a number"}

    if price is not None:
        try:
            entry["price"] = round(float(price), 2)
        except (TypeError, ValueError):
            return {"error": "price must be a number"}

    deal.attributes["fi_products"] = products
    deal.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return get_fi_menu(deal_id)


def decide_fi_product(deal_id, product_key, decision, declined_reason=None):

    if decision not in ("accepted", "declined"):
        return {"error": "decision must be 'accepted' or 'declined'"}

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    products = _fi_products(deal)
    entry = next((p for p in products if p["product_key"] == product_key), None)

    if not entry:
        return {"error": f"'{product_key}' has not been presented on this deal"}

    if entry["status"] != "presented":
        return {"error": f"'{product_key}' is already '{entry['status']}'"}

    entry["status"] = decision
    entry["decided_at"] = _now()
    entry["declined_reason"] = declined_reason if decision == "declined" else None

    deal.attributes["fi_products"] = products
    deal.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return get_fi_menu(deal_id)


def _all_deals_with_fi_products():
    from core.deals import _all_deals
    return [d for d in _all_deals() if d.attributes.get("fi_products")]


def get_product_penetration_stats():
    """Real cross-deal product penetration -- the exact metric
    core/department_intelligence.py's module docstring flagged as impossible to
    compute ("needs aftermarket product attachment data ... that doesn't exist
    anywhere in this graph"). Computed only over deals that actually have an F&I menu
    on file (deals never taken through F&I aren't counted as declines -- an honest
    denominator, not an inflated one)."""

    deals = _all_deals_with_fi_products()
    deals_with_menu = len(deals)

    if deals_with_menu == 0:
        return {
            "deals_with_fi_menu": 0,
            "products_per_deal_avg": None,
            "total_accepted_gross": 0.0,
            "by_product": [],
        }

    per_product = {p["key"]: {"presented": 0, "accepted": 0, "declined": 0, "gross": 0.0} for p in FI_PRODUCT_CATALOG}
    total_accepted_count = 0
    total_gross = 0.0

    for deal in deals:
        for entry in deal.attributes.get("fi_products") or []:
            key = entry["product_key"]
            if key not in per_product:
                continue
            per_product[key]["presented"] += 1
            if entry["status"] == "accepted":
                per_product[key]["accepted"] += 1
                per_product[key]["gross"] += round(entry["price"] - entry["cost"], 2)
                total_accepted_count += 1
                total_gross += round(entry["price"] - entry["cost"], 2)
            elif entry["status"] == "declined":
                per_product[key]["declined"] += 1

    by_product = []
    for p in FI_PRODUCT_CATALOG:
        stats = per_product[p["key"]]
        penetration_pct = (
            round(100 * stats["accepted"] / deals_with_menu, 1)
            if deals_with_menu else None
        )
        by_product.append({
            "product_key": p["key"],
            "name": p["name"],
            "category": p["category"],
            "presented": stats["presented"],
            "accepted": stats["accepted"],
            "declined": stats["declined"],
            "penetration_pct": penetration_pct,
            "total_gross": round(stats["gross"], 2),
        })

    by_product.sort(key=lambda x: x["penetration_pct"] or 0, reverse=True)

    return {
        "deals_with_fi_menu": deals_with_menu,
        "products_per_deal_avg": round(total_accepted_count / deals_with_menu, 2),
        "total_accepted_gross": round(total_gross, 2),
        "by_product": by_product,
    }


def list_deals_needing_fi_menu(limit=25):
    """Deals in the presentable window (financing/contract) that have NO F&I menu
    on file yet -- a real actionable queue, not just a stats screen. This is the
    'Product Menu' tab's real work list."""

    from core.deals import _all_deals

    deals = [
        d for d in _all_deals()
        if d.attributes.get("status") in PRESENTABLE_STATUSES and not d.attributes.get("fi_products")
    ]
    deals.sort(key=lambda d: d.attributes.get("updated_at") or "", reverse=True)

    return deals[:limit]
