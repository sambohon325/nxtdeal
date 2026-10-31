"""Accessories Accelerator (2026-07-23): a graph-native module for the
dealership accessories/upsell motion -- Vehicle Sold -> Recommend -> Install
-> Track Revenue. Turns the moment of sale into a structured accessory upsell
program (truck accessories, protection packages, OEM accessories, lift kits,
wheels, tint), the same "own lifecycle state on the customer" convention
core/customer_journey.py already established for a customer's lifecycle stage.

GRAPH-NATIVE, single source of truth: an accessory sale is stored DIRECTLY as
attributes on the existing Customer entity -- an `accessory_sales` list (one
dict per sale, each with its own id/line-items/total/installed state) plus a
rolled-up `accessory_revenue_total` -- exactly the way
core/customer_journey.py stores journey_history/journey_stage on a Customer and
core/pipeline_state.py stores pipeline state on a Lead. NOT a separate JSON
store, not a new entity type. The same core/storage.py save_graph() that
already persists everything else persists these too.

Follows the per-mutation save_graph() convention core/customer_journey.py/
core/communications_hub.py already established for low/moderate-frequency,
human-driven mutations (recording one accessory sale, or marking one install,
is a single human action, not a bulk job, so a direct save on every mutating
call is the right, safe choice).

Honest real-vs-simulated split, matching this codebase's own disclosure
convention: the accessory CATALOG (categories, item names, prices) is a real,
fixed, honestly-representative price list -- a reasonable default set, not
pulled from a live vendor feed (no accessories DMS/vendor catalog is connected
in this environment). Recording that a customer bought/installed an accessory
is 100% real (a genuine employee action, timestamped, persisted). The
overview's ATTACH-RATE is an honest ESTIMATE, clearly labeled: this codebase
has no single authoritative "vehicles delivered this month" counter wired to
this module, so attach rate is estimated against the count of Customer entities
(clearly marked estimated, never presented as a real audited delivery-based
attach rate).

The AI accessory pitch is an isolated, kill-switched OpenAI call following
core/customer_journey.py's generate_journey_recommendation() pattern exactly (a
dedicated no-tool-calling client, an is_feature_enabled()/record_call_attempt()
gate, a try/except around the real API call, and an honest, non-AI
fallback_accessory_pitch() for when the call can't be reached -- this sandbox
has consistently shown no outbound OpenAI network access, so the fallback path
is what actually fires here today).
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import CUSTOMER
from core.id_generator import IDGenerator
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# A dedicated IDGenerator instance owned by this module. The "ASALE" prefix
# (accessory sale) is registered on THIS instance's counters via setdefault so
# the module is self-contained and runnable today; the shared
# core/id_generator.py IDGenerator can register the same prefix permanently
# without changing this module's behavior.
id_generator = IDGenerator()
id_generator.counters.setdefault("ASALE", 0)

ACCESSORY_SALE_PREFIX = "ASALE"

# The six real accessory categories. Order is load-bearing for the overview's
# revenue_by_category seeding (every category is seeded to 0, same convention
# core/customer_journey.py's counts_by_stage / core/communications_hub.py's
# by_channel already established).
TRUCK_ACCESSORIES = "truck_accessories"
PROTECTION_PACKAGES = "protection_packages"
OEM_ACCESSORIES = "oem_accessories"
LIFT_KITS = "lift_kits"
WHEELS = "wheels"
TINT = "tint"

CATEGORIES = [
    TRUCK_ACCESSORIES,
    PROTECTION_PACKAGES,
    OEM_ACCESSORIES,
    LIFT_KITS,
    WHEELS,
    TINT,
]

# Real, fixed, honestly-representative default price list. Each item:
# id / category / name / price. Not pulled from a live vendor feed (none is
# connected here) -- a reasonable default catalog a dealer would refine, never
# presented as a real-time vendor-priced quote.
ACCESSORY_CATALOG = [
    # Truck accessories
    {"id": "ACC-TRUCK-BEDLINER", "category": TRUCK_ACCESSORIES, "name": "Spray-In Bed Liner", "price": 549.00},
    {"id": "ACC-TRUCK-TONNEAU", "category": TRUCK_ACCESSORIES, "name": "Hard Tri-Fold Tonneau Cover", "price": 899.00},
    {"id": "ACC-TRUCK-STEPS", "category": TRUCK_ACCESSORIES, "name": "Running Boards / Side Steps", "price": 749.00},
    {"id": "ACC-TRUCK-HITCH", "category": TRUCK_ACCESSORIES, "name": "Tow Hitch & Wiring Package", "price": 399.00},
    # Protection packages
    {"id": "ACC-PROT-PAINT", "category": PROTECTION_PACKAGES, "name": "Paint & Interior Protection Package", "price": 995.00},
    {"id": "ACC-PROT-PPF", "category": PROTECTION_PACKAGES, "name": "Paint Protection Film (Front)", "price": 1299.00},
    {"id": "ACC-PROT-CERAMIC", "category": PROTECTION_PACKAGES, "name": "Ceramic Coating", "price": 799.00},
    {"id": "ACC-PROT-MATS", "category": PROTECTION_PACKAGES, "name": "All-Weather Floor Liner Set", "price": 249.00},
    # OEM accessories
    {"id": "ACC-OEM-CARGO", "category": OEM_ACCESSORIES, "name": "OEM Cargo Organizer", "price": 199.00},
    {"id": "ACC-OEM-CROSSBARS", "category": OEM_ACCESSORIES, "name": "OEM Roof Cross Bars", "price": 349.00},
    {"id": "ACC-OEM-SPLASH", "category": OEM_ACCESSORIES, "name": "OEM Splash Guard Set", "price": 149.00},
    # Lift kits
    {"id": "ACC-LIFT-2IN", "category": LIFT_KITS, "name": "2\" Leveling Kit", "price": 649.00},
    {"id": "ACC-LIFT-4IN", "category": LIFT_KITS, "name": "4\" Suspension Lift Kit", "price": 1899.00},
    # Wheels
    {"id": "ACC-WHEEL-ALLOY", "category": WHEELS, "name": "Upgraded Alloy Wheel Set", "price": 1499.00},
    {"id": "ACC-WHEEL-OFFROAD", "category": WHEELS, "name": "Off-Road Wheel & Tire Package", "price": 2299.00},
    # Tint
    {"id": "ACC-TINT-STD", "category": TINT, "name": "Standard Window Tint", "price": 299.00},
    {"id": "ACC-TINT-CERAMIC", "category": TINT, "name": "Ceramic Window Tint", "price": 549.00},
]

_CATALOG_BY_ID = {item["id"]: item for item in ACCESSORY_CATALOG}

CATALOG_BASIS = "default_price_list"
CATALOG_DISCLAIMER = (
    "Representative default accessory price list -- not pulled from a live "
    "accessories vendor/DMS catalog (none is connected in this environment). "
    "Prices are reasonable defaults a dealer would refine, never presented as "
    "a real-time vendor-priced quote."
)

ATTACH_RATE_BASIS = "estimated_against_customer_count"
ATTACH_RATE_DISCLAIMER = (
    "ESTIMATED attach rate -- this module has no single authoritative "
    "'vehicles delivered' counter wired to it, so the denominator is the "
    "count of Customer entities, not an audited delivery count. A real "
    "delivery-based attach rate would come from a wired DMS delivery feed."
)


def _now():

    return datetime.now(timezone.utc).isoformat()


def _get_customer_or_raise(customer_id):

    entity = ledger.get_entity(customer_id)

    if not entity or entity.entity_type != CUSTOMER:
        raise ValueError(f"No customer found with id {customer_id}.")

    return entity


def _customer_name(customer):

    attrs = customer.attributes

    name = attrs.get("Name")
    if name:
        return name

    first = attrs.get("FirstName") or ""
    last = attrs.get("LastName") or ""
    full = f"{first} {last}".strip()

    return full or None


def list_accessory_catalog(category=None):
    """The real, fixed accessory catalog (id/category/name/price per item),
    optionally filtered to one category. Raises ValueError on an unknown
    category so callers get a clear error, same convention as the journey
    funcs' invalid-stage error."""

    if category is not None and category not in CATEGORIES:
        raise ValueError(
            f"Invalid accessory category '{category}'. Must be one of: "
            + ", ".join(CATEGORIES)
            + "."
        )

    items = [dict(item) for item in ACCESSORY_CATALOG if category is None or item["category"] == category]

    return {
        "categories": list(CATEGORIES),
        "items": items,
        "basis": CATALOG_BASIS,
        "disclaimer": CATALOG_DISCLAIMER,
    }


def _customer_sales(customer):

    return list(customer.attributes.get("accessory_sales") or [])


def _purchased_item_ids(customer):

    purchased = set()
    for sale in _customer_sales(customer):
        for line in sale.get("line_items") or []:
            purchased.add(line.get("item_id"))
    return purchased


def recommend_accessories(customer_id):
    """Rule-based accessory recommendations for one customer -- the single
    highest-value catalog item in each category the customer has NOT already
    purchased, one suggestion per category. Deliberately simple and
    deterministic (no source-data-dependent scoring exists yet); clearly a
    rule-based starter, not an ML model. Raises ValueError on an unknown
    customer / non-customer id, exactly like the journey funcs."""

    customer = _get_customer_or_raise(customer_id)
    already_owned = _purchased_item_ids(customer)

    recommendations = []
    for category in CATEGORIES:
        candidates = [
            item for item in ACCESSORY_CATALOG
            if item["category"] == category and item["id"] not in already_owned
        ]
        if not candidates:
            continue
        # Rule: lead with the highest-ticket item in the category the customer
        # doesn't already own -- the biggest revenue-per-attach opportunity.
        top = max(candidates, key=lambda i: i["price"])
        recommendations.append({
            "category": category,
            "item_id": top["id"],
            "name": top["name"],
            "price": top["price"],
            "reason": (
                f"Highest-value {category.replace('_', ' ')} option this "
                "customer hasn't purchased yet."
            ),
        })

    return {
        "customer_id": customer.id,
        "name": _customer_name(customer),
        "recommendations": recommendations,
        "basis": "rule_based",
        "disclaimer": (
            "Rule-based recommendations (top unpurchased item per category), "
            "not an ML/behavioral model -- a deterministic starter."
        ),
    }


def _sale_brief(sale):

    return dict(sale)


def create_accessory_sale(customer_id, item_ids):
    """Records a real accessory sale on the customer: validates every item_id
    against the catalog, builds priced line items, totals the revenue, appends
    the sale to the customer's own `accessory_sales` list and rolls it into
    `accessory_revenue_total`, then persists. Returns the sale brief.

    Raises ValueError on an unknown customer, an empty item list, or any
    unknown item_id -- clear errors, same convention as the journey funcs."""

    customer = _get_customer_or_raise(customer_id)

    if not item_ids:
        raise ValueError("An accessory sale must include at least one item.")

    line_items = []
    for item_id in item_ids:
        item = _CATALOG_BY_ID.get(item_id)
        if not item:
            raise ValueError(f"Unknown accessory item id '{item_id}'.")
        line_items.append({
            "item_id": item["id"],
            "category": item["category"],
            "name": item["name"],
            "price": item["price"],
        })

    total = round(sum(line["price"] for line in line_items), 2)

    sale_id = id_generator.generate(ACCESSORY_SALE_PREFIX)
    now = _now()

    sale = {
        "sale_id": sale_id,
        "customer_id": customer.id,
        "line_items": line_items,
        "total_revenue": total,
        "installed": False,
        "installed_at": None,
        "created_at": now,
    }

    sales = customer.attributes.get("accessory_sales") or []
    sales.append(sale)
    customer.attributes["accessory_sales"] = sales

    prior_total = customer.attributes.get("accessory_revenue_total") or 0
    customer.attributes["accessory_revenue_total"] = round(prior_total + total, 2)

    save_graph(GRAPH_PATH)

    return _sale_brief(sale)


def mark_installed(customer_id, sale_id):
    """Marks a recorded accessory sale as installed (installed=True,
    installed_at timestamp), persists, and returns the updated sale brief.

    Raises ValueError on an unknown customer, an unknown sale_id for that
    customer, or a sale already installed -- clear errors, same convention as
    the journey funcs."""

    customer = _get_customer_or_raise(customer_id)

    sales = customer.attributes.get("accessory_sales") or []
    target = None
    for sale in sales:
        if sale.get("sale_id") == sale_id:
            target = sale
            break

    if target is None:
        raise ValueError(
            f"No accessory sale found with id {sale_id} for customer {customer_id}."
        )

    if target.get("installed"):
        raise ValueError(f"Accessory sale {sale_id} is already marked installed.")

    target["installed"] = True
    target["installed_at"] = _now()
    customer.attributes["accessory_sales"] = sales

    save_graph(GRAPH_PATH)

    return _sale_brief(target)


def get_accessories_overview():
    """Real, live-computed accessories program overview: total revenue,
    revenue by category (every category seeded to 0), installed vs pending
    sale counts, and an ESTIMATED attach rate (clearly labeled -- see
    ATTACH_RATE_DISCLAIMER). Iterates every Customer entity's own
    graph-native accessory_sales."""

    revenue_by_category = {category: 0.0 for category in CATEGORIES}
    total_revenue = 0.0
    total_sales = 0
    installed_count = 0
    pending_count = 0

    total_customers = 0
    customers_with_sale = 0

    for entity in ledger.get_all().values():
        if entity.entity_type != CUSTOMER:
            continue

        total_customers += 1
        sales = entity.attributes.get("accessory_sales") or []
        if sales:
            customers_with_sale += 1

        for sale in sales:
            total_sales += 1
            if sale.get("installed"):
                installed_count += 1
            else:
                pending_count += 1
            for line in sale.get("line_items") or []:
                price = line.get("price") or 0
                total_revenue += price
                category = line.get("category")
                if category in revenue_by_category:
                    revenue_by_category[category] += price

    revenue_by_category = {c: round(v, 2) for c, v in revenue_by_category.items()}

    attach_rate_estimate = round(customers_with_sale / total_customers, 4) if total_customers else 0.0

    return {
        "total_accessory_revenue": round(total_revenue, 2),
        "revenue_by_category": revenue_by_category,
        "total_sales": total_sales,
        "installed_count": installed_count,
        "pending_count": pending_count,
        "customers_with_accessory_sale": customers_with_sale,
        "total_customers": total_customers,
        "attach_rate_estimate": attach_rate_estimate,
        "attach_rate_basis": ATTACH_RATE_BASIS,
        "attach_rate_disclaimer": ATTACH_RATE_DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# AI Accessory Pitch -- an isolated, kill-switched OpenAI call drafting a short
# upsell pitch for one customer, mirroring core/customer_journey.py's
# generate_journey_recommendation() pattern exactly (a dedicated no-tool-calling
# client, an is_feature_enabled()/record_call_attempt() gate, a try/except
# around the real API call, and an honest, non-AI fallback_accessory_pitch()
# for when the call can't be reached -- this sandbox has consistently shown no
# outbound OpenAI network access, so the fallback path is what actually fires
# here today).
# ---------------------------------------------------------------------------

import json
import os

from dotenv import load_dotenv
from core.optional_ai_client import LazyOpenAI

from core.ai_management import is_feature_enabled, record_call_attempt

load_dotenv()

client = LazyOpenAI(
    api_key=os.getenv(
        "OPENAI_API_KEY"
    )
)

PITCH_SYSTEM_PROMPT = (
    "You are an assistant drafting a short, friendly accessory upsell pitch for "
    "one dealership customer who just bought a vehicle. Given the customer's "
    "name and a list of recommended accessories (each with a category, name, "
    "and price), return ONLY a JSON object with exactly these keys: "
    "pitch (2-3 short sentences, warm and specific to the recommended items, "
    "never inventing an accessory or price not in the given list), "
    "highlighted_items (a JSON array of up to 3 short strings, each naming one "
    "recommended accessory worth leading with), and "
    "suggested_bundle_note (one short sentence suggesting a bundle/discount "
    "angle, or an empty string if none applies). Do not include any commentary "
    "outside the JSON object."
)


def _pitch_user_content(rec):

    name = rec.get("name") or "the customer"
    lines = [f"Customer: {name}", "Recommended accessories:"]

    recommendations = rec.get("recommendations") or []
    if recommendations:
        for item in recommendations:
            lines.append(
                f"- {item.get('name')} ({item.get('category')}) at "
                f"${item.get('price')}"
            )
    else:
        lines.append("- (none: the customer already owns an item in every category)")

    return "\n".join(lines) + "\n"


def fallback_accessory_pitch(rec):
    """Plain, non-AI placeholder pitch -- used when the AI call is disabled or
    fails, same pattern as core/customer_journey.py's
    fallback_journey_recommendation(). Grounded strictly in the real
    recommendations, never inventing an accessory or price."""

    name = rec.get("name") or "your new vehicle"
    recommendations = rec.get("recommendations") or []

    if recommendations:
        top = recommendations[:3]
        names = ", ".join(item.get("name") for item in top)
        pitch = (
            f"Congratulations on your purchase, {name}! To get the most out of "
            f"it, customers love adding {names}. Ask us about bundling them at "
            "delivery."
        )
        highlighted = [item.get("name") for item in top]
        bundle_note = (
            "Bundling these at the point of sale is usually the best value for "
            "the customer."
        )
    else:
        pitch = (
            "This customer already owns an accessory in every category -- no "
            "additional upsell is recommended right now."
        )
        highlighted = []
        bundle_note = ""

    return {
        "pitch": pitch,
        "highlighted_items": highlighted,
        "suggested_bundle_note": bundle_note,
    }


def generate_accessory_pitch(customer_id):
    """Real, isolated OpenAI call drafting a short accessory upsell pitch for
    one customer from their current rule-based recommendations. Returns a
    structured dict (pitch / highlighted_items / suggested_bundle_note, plus an
    ai_generated flag). On success the pitch is stored back onto the customer's
    own `accessory_pitch` attribute and persisted; on disabled/failure it
    returns an honest fallback (never stored, since it's not a real AI result)
    so the caller always has something usable.

    Raises ValueError on an unknown customer / non-customer id, exactly like the
    other accessory functions.

    AI Management: checks the real 'accessories_pitch' kill switch
    (core/ai_management.py, accessories_pitch_enabled flag) before attempting --
    mirrors core/customer_journey.py's generate_journey_recommendation()."""

    rec = recommend_accessories(customer_id)

    if not is_feature_enabled("accessories_pitch"):
        record_call_attempt("accessories_pitch", "blocked")
        fallback = fallback_accessory_pitch(rec)
        fallback["ai_generated"] = False
        fallback["disabled"] = True
        return fallback

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": PITCH_SYSTEM_PROMPT},
                {"role": "user", "content": _pitch_user_content(rec)},
            ],
            response_format={"type": "json_object"},
        )

        record_call_attempt("accessories_pitch", "succeeded")
        raw = json.loads(response.choices[0].message.content)

        # Parse STRICTLY from the model's JSON -- never invent a field it didn't
        # return (an absent key falls back to an empty value, not a guess).
        highlighted = raw.get("highlighted_items")
        if not isinstance(highlighted, list):
            highlighted = []

        pitch = {
            "pitch": str(raw.get("pitch") or ""),
            "highlighted_items": [str(item) for item in highlighted],
            "suggested_bundle_note": str(raw.get("suggested_bundle_note") or ""),
            "ai_generated": True,
        }

        entity = ledger.get_entity(customer_id)
        entity.attributes["accessory_pitch"] = pitch
        save_graph(GRAPH_PATH)

        return pitch

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back, never raises
        record_call_attempt("accessories_pitch", "fell_back", detail=str(exc))
        fallback = fallback_accessory_pitch(rec)
        fallback["ai_generated"] = False
        fallback["fallback_reason"] = str(exc)
        return fallback
