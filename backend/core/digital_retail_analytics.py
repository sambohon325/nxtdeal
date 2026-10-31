"""
core/digital_retail_analytics.py -- NXTDeal Digital Retail KPI dashboard (slice DR-8,
2026-07-24). Sam's Reporting spec: a Digital Retail KPI Dashboard (digital leads/deals/
deliveries/closings/gross), AI Performance (deals assisted/negotiated/closed, revenue
influenced), and Workflow Drop-Off (verification -> trade -> finance -> contracting ->
delivery, to find friction points).

This is a pure READ/COMPOSE layer over everything DR-1..7 already record -- it introduces no
new storage. "Digital" means self-service: a deal whose created_by is the
digital_retail.CUSTOMER_SENTINEL marker (the customer drove it, not staff). Digital gross is
computed from the REAL Vehicle Cost/Price on funded digital deals, same honesty bar as
core/deals_api.py's own gross view -- nothing fabricated.
"""

from core.dealeros import ledger
from core.entity_types import DELIVERY

from core.digital_retail import CUSTOMER_SENTINEL
from core.deals import list_deals
from core.dealeros_verify import verification_summary, TIER_ORDER
from core.negotiation_engine import negotiation_summary
from core.delivery_fulfillment import fulfillment_dashboard
from core.ai_worker import workforce_summary


def _num(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def _digital_deals():
    return list_deals(created_by=CUSTOMER_SENTINEL)


def _deal_front_gross(deal):
    """Front gross on a deal from the real numbers: the selected scenario's sale price (or the
    vehicle's asking price) minus the vehicle's cost. Returns 0 when cost is unknown."""
    a = deal.attributes
    vehicle = ledger.get_entity(a.get("vehicle_id"))
    cost = _num(vehicle.attributes.get("Cost")) if vehicle else 0.0
    scenarios = a.get("scenarios") or []
    sel = next((s for s in scenarios if s.get("id") == a.get("selected_scenario_id")),
               scenarios[-1] if scenarios else None)
    sale = _num(sel.get("sale_price")) if sel else (_num(vehicle.attributes.get("Price")) if vehicle else 0.0)
    return round(sale - cost, 2)


# ------------------------------------------------------------------------------------
# The KPI blocks.
# ------------------------------------------------------------------------------------

_CLOSED_STATUSES = ("funded",)
_FINANCE_STATUSES = ("financing", "contract", "funded")
_CONTRACT_STATUSES = ("contract", "funded")


def digital_deal_kpis():
    deals = _digital_deals()
    by_status = {}
    closed = 0
    digital_gross = 0.0
    for d in deals:
        st = d.attributes.get("status")
        by_status[st] = by_status.get(st, 0) + 1
        if st in _CLOSED_STATUSES:
            closed += 1
            digital_gross += _deal_front_gross(d)
    return {
        "digital_deals": len(deals),
        "by_status": by_status,
        "digital_closings": closed,
        "digital_gross": round(digital_gross, 2),
    }


def digital_delivery_kpis():
    """Deliveries tied to a digital (self-service) deal."""
    digital_ids = {d.id for d in _digital_deals()}
    total = 0
    completed = 0
    for e in ledger.get_all().values():
        if e.entity_type != DELIVERY:
            continue
        if e.attributes.get("deal_id") in digital_ids:
            total += 1
            if e.attributes.get("status") == "completed":
                completed += 1
    return {"digital_deliveries": total, "completed": completed}


def ai_performance():
    """The AI Workforce's contribution. deals_assisted = self-service deals the AI workforce
    surface touched (all digital deals here), deals_negotiated = negotiation sessions,
    deals_closed = funded digital deals, revenue_influenced = digital gross on them."""
    deals = _digital_deals()
    neg = negotiation_summary()
    dk = digital_deal_kpis()
    wf = workforce_summary()
    return {
        "deals_assisted": len(deals),
        "deals_negotiated": neg["total_sessions"],
        "deals_closed": dk["digital_closings"],
        "revenue_influenced": dk["digital_gross"],
        "workforce": {
            "active_workers": wf.get("active_workers", 0),
            "actions_executed": wf.get("total_actions_executed", 0),
            "actions_drafted": wf.get("total_actions_drafted", 0),
            "interactions": wf.get("total_interactions", 0),
        },
    }


def journey_funnel():
    """The self-service journey drop-off. Each stage counts how many got that far; the
    conversion is stage / previous stage. Surfaces where customers fall out."""
    vsum = verification_summary()
    by_tier = vsum["by_tier"]
    verified = vsum["verified_humans_or_above"]

    deals = _digital_deals()
    started = len(deals)
    finance = sum(1 for d in deals if d.attributes.get("status") in _FINANCE_STATUSES)
    contracting = sum(1 for d in deals if d.attributes.get("status") in _CONTRACT_STATUSES
                      or d.attributes.get("contract"))
    delivered = digital_delivery_kpis()["digital_deliveries"]

    stages = [
        {"stage": "verification", "label": "Verified", "count": verified},
        {"stage": "deal", "label": "Deal Started", "count": started},
        {"stage": "finance", "label": "Financing", "count": finance},
        {"stage": "contracting", "label": "Contracting", "count": contracting},
        {"stage": "delivery", "label": "Delivery", "count": delivered},
    ]
    prev = None
    for s in stages:
        if prev is None or prev == 0:
            s["conversion_from_prev"] = None
        else:
            s["conversion_from_prev"] = round(s["count"] / prev, 3)
        s["dropped_from_prev"] = (prev - s["count"]) if (prev is not None and prev >= s["count"]) else 0
        prev = s["count"]
    return {"stages": stages, "verification_by_tier": {t: by_tier.get(t, 0) for t in TIER_ORDER}}


def get_digital_retail_dashboard():
    """The whole picture: KPIs + AI performance + the drop-off funnel + the underlying
    verification / negotiation / delivery summaries."""
    fulfil = fulfillment_dashboard()
    return {
        "kpis": {
            **digital_deal_kpis(),
            **digital_delivery_kpis(),
            "verifications": verification_summary()["total"],
        },
        "ai_performance": ai_performance(),
        "funnel": journey_funnel(),
        "verifications": verification_summary(),
        "negotiations": negotiation_summary(),
        "deliveries": fulfil["delivery"],
        "try_before_you_buy": fulfil["try_before_you_buy"],
        "note": "Digital = self-service (created by the customer via the Verify portal); gross "
                "is computed from real Vehicle Cost/Price on funded digital deals.",
    }
