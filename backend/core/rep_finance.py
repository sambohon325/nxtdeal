"""
MySales light self-accounting (2026-07-24, Sam: "a light self accounting app they can connect
their bank accounts to via plaid, set up budgets, so they can navigate their bank accounts and
commissions together. We should also have ai budget planners, advisors, etc").

A per-rep (keyed by employee_id) personal-finance layer:
  • Bank linking currently generates deterministic demo accounts and transactions.
    A registered banking capability does not make this flow live: no adapter is
    called here. Keep that distinction in responses, persisted provenance and audits.
  • Budgets — one monthly limit per category; spend is aggregated from this month's linked-
    account transactions.
  • Commissions — projected / pending / paid entries the rep logs, so banking and earnings sit
    on one screen. (There is no Commission model elsewhere in NXTDeal yet — this is it.)
  • A rules-based AI budget advisor (deterministic, never an LLM — like conversation_intelligence)
    that flags overages, near-limit categories, low savings, and pending commission income.

Scoping note: like rep_referrals, this is in the dealer backend keyed by the signed-in rep. If
MySales later supports reps not yet on a NXTDeal store, it would move to a central store.
"""

import hashlib
import random
from datetime import datetime, timezone, timedelta

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import BANK_ACCOUNT, BUDGET, COMMISSION
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.audit import audit_log
from core import integrations_registry

BANKING_CAPABILITY = "banking"

COMMISSION_STATUSES = ("projected", "pending", "paid")

# Categories the simulated transactions + default budgets share, so budget spend maps cleanly.
SPEND_CATEGORIES = ("Groceries", "Dining", "Transportation", "Shopping", "Bills", "Entertainment")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _seed(employee_id):
    return int(hashlib.sha256((employee_id or "").encode("utf-8")).hexdigest(), 16) % (2 ** 32)


# =====================================================================================
# Bank accounts (Plaid seam — simulated until a real adapter is registered)
# =====================================================================================

def _simulate_accounts(employee_id):
    """Deterministic per-rep sample: a checking + savings account, each with recent
    transactions across the shared spend categories. Stable so budgets don't jump around."""
    rng = random.Random(_seed(employee_id))
    checking_balance = round(rng.uniform(1500, 6500), 2)
    savings_balance = round(rng.uniform(2000, 18000), 2)

    def _txns(n):
        out = []
        today = datetime.now(timezone.utc)
        for _ in range(n):
            cat = rng.choice(SPEND_CATEGORIES)
            amt = -round(rng.uniform(12, 240), 2)
            day = rng.randint(0, 27)
            out.append({
                "date": (today - timedelta(days=day)).date().isoformat(),
                "name": f"{cat} purchase",
                "category": cat,
                "amount": amt,
            })
        return sorted(out, key=lambda t: t["date"], reverse=True)

    return [
        {"name": "Everyday Checking", "mask": f"{rng.randint(1000, 9999)}", "type": "checking",
         "balance": checking_balance, "transactions": _txns(14)},
        {"name": "Savings", "mask": f"{rng.randint(1000, 9999)}", "type": "savings",
         "balance": savings_balance, "transactions": []},
    ]


def _account_brief(entity):
    a = entity.attributes
    return {
        "id": entity.id,
        "institution": a.get("institution"),
        "name": a.get("name"),
        "mask": a.get("mask"),
        "type": a.get("type"),
        "balance": a.get("balance", 0.0),
        "source": a.get("source"),
    }


def list_accounts(employee_id):
    return [
        _account_brief(e)
        for e in ledger.get_all().values()
        if e.entity_type == BANK_ACCOUNT and e.attributes.get("employee_id") == employee_id
    ]


def _account_entities(employee_id):
    return [
        e for e in ledger.get_all().values()
        if e.entity_type == BANK_ACCOUNT and e.attributes.get("employee_id") == employee_id
    ]


def link_bank(employee_id, institution=None):
    """Load demo bank accounts idempotently. No provider adapter is executed here."""
    existing = _account_entities(employee_id)
    if existing:
        return {"accounts": [_account_brief(e) for e in existing],
                "simulated": True, "connection_verified": False,
                "already_linked": True}

    accounts = _simulate_accounts(employee_id)
    institution = institution or "Simulated Bank"

    created = []
    for acct in accounts:
        entity = Entity(
            id=id_generator.generate("BANK"),
            entity_type=BANK_ACCOUNT,
            attributes={
                "employee_id": employee_id,
                "institution": institution,
                "name": acct["name"],
                "mask": acct["mask"],
                "type": acct["type"],
                "balance": acct["balance"],
                "transactions": acct["transactions"],
                "source": "simulated",
                "linked_at": _now(),
            },
        )
        ledger.add_entity(entity)
        created.append(entity)
    save_graph(GRAPH_PATH)
    audit_log.record(
        event_type="rep_bank_linked",
        summary=f"{employee_id} loaded {len(created)} simulated bank account(s)",
        entity_id=created[0].id if created else None, actor=employee_id,
        details={"institution": institution, "simulated": True},
    )
    return {"accounts": [_account_brief(e) for e in created], "simulated": True, "connection_verified": False, "already_linked": False}


def _current_month_spend_by_category(employee_id):
    month_prefix = datetime.now(timezone.utc).date().isoformat()[:7]  # "YYYY-MM"
    spend = {}
    for e in _account_entities(employee_id):
        for t in e.attributes.get("transactions", []):
            if not str(t.get("date", "")).startswith(month_prefix):
                continue
            amt = t.get("amount", 0)
            if amt < 0:
                spend[t.get("category", "Other")] = round(spend.get(t.get("category", "Other"), 0) + (-amt), 2)
    return spend


# =====================================================================================
# Budgets
# =====================================================================================

def _budget_for(employee_id, category):
    for e in ledger.get_all().values():
        if (e.entity_type == BUDGET and e.attributes.get("employee_id") == employee_id
                and e.attributes.get("category") == category):
            return e
    return None


def set_budget(employee_id, category, limit):
    category = (category or "").strip()
    if not category:
        return {"error": "Choose a category."}
    try:
        limit = round(float(limit), 2)
    except (TypeError, ValueError):
        return {"error": "Enter a valid monthly limit."}
    if limit < 0:
        return {"error": "A budget can't be negative."}
    existing = _budget_for(employee_id, category)
    if existing:
        existing.attributes["limit"] = limit
        existing.attributes["updated_at"] = _now()
        entity = existing
    else:
        entity = Entity(
            id=id_generator.generate("BUDG"),
            entity_type=BUDGET,
            attributes={"employee_id": employee_id, "category": category, "limit": limit,
                        "period": "monthly", "created_at": _now(), "updated_at": _now()},
        )
        ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return {"category": category, "limit": limit}


def list_budgets(employee_id):
    spend = _current_month_spend_by_category(employee_id)
    out = []
    for e in ledger.get_all().values():
        if e.entity_type != BUDGET or e.attributes.get("employee_id") != employee_id:
            continue
        limit = e.attributes.get("limit", 0.0)
        cat = e.attributes.get("category")
        spent = spend.get(cat, 0.0)
        out.append({
            "id": e.id,
            "category": cat,
            "limit": limit,
            "spent": round(spent, 2),
            "remaining": round(limit - spent, 2),
            "pct": round((spent / limit) * 100, 1) if limit else 0.0,
            "over": spent > limit and limit > 0,
        })
    return sorted(out, key=lambda b: b["category"])


# =====================================================================================
# Commissions
# =====================================================================================

def record_commission(employee_id, amount, status="pending", source=None, deal_id=None, date=None):
    if status not in COMMISSION_STATUSES:
        return {"error": f"Status must be one of {', '.join(COMMISSION_STATUSES)}."}
    try:
        amount = round(float(amount), 2)
    except (TypeError, ValueError):
        return {"error": "Enter a valid amount."}
    entity = Entity(
        id=id_generator.generate("COMM"),
        entity_type=COMMISSION,
        attributes={
            "employee_id": employee_id,
            "amount": amount,
            "status": status,
            "source": source,
            "deal_id": deal_id,
            "date": date or datetime.now(timezone.utc).date().isoformat(),
            "created_at": _now(),
        },
    )
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return _commission_brief(entity)


def _commission_brief(entity):
    a = entity.attributes
    return {"id": entity.id, "amount": a.get("amount", 0.0), "status": a.get("status"),
            "source": a.get("source"), "deal_id": a.get("deal_id"), "date": a.get("date")}


def list_commissions(employee_id):
    return sorted(
        [_commission_brief(e) for e in ledger.get_all().values()
         if e.entity_type == COMMISSION and e.attributes.get("employee_id") == employee_id],
        key=lambda c: c["date"], reverse=True,
    )


def _commission_totals(commissions):
    totals = {s: 0.0 for s in COMMISSION_STATUSES}
    for c in commissions:
        totals[c["status"]] = round(totals.get(c["status"], 0) + c["amount"], 2)
    return totals


# =====================================================================================
# Overview + AI advisor
# =====================================================================================

def get_overview(employee_id):
    accounts = list_accounts(employee_id)
    budgets = list_budgets(employee_id)
    commissions = list_commissions(employee_id)
    comm_totals = _commission_totals(commissions)
    cash = round(sum(a["balance"] for a in accounts), 2)
    return {
        "linked": bool(accounts),
        "provider_live": False,
        "provider_available": integrations_registry.is_live(BANKING_CAPABILITY),
        "connection_verified": False,
        "cash_total": cash,
        "accounts": accounts,
        "budgets": budgets,
        "commissions": {"totals": comm_totals, "recent": commissions[:10]},
        "advisor": advisor(employee_id, accounts=accounts, budgets=budgets, comm_totals=comm_totals, cash=cash),
    }


def advisor(employee_id, accounts=None, budgets=None, comm_totals=None, cash=None):
    """Deterministic, rules-based budget advice — no LLM. Returns a ranked list of insights."""
    accounts = accounts if accounts is not None else list_accounts(employee_id)
    budgets = budgets if budgets is not None else list_budgets(employee_id)
    if comm_totals is None:
        comm_totals = _commission_totals(list_commissions(employee_id))
    if cash is None:
        cash = round(sum(a["balance"] for a in accounts), 2)

    insights = []

    if not accounts:
        insights.append({"type": "tip", "title": "Connect your bank",
                         "detail": "Link an account to see balances, track spending against budgets, and get tailored advice."})

    total_spent = round(sum(b["spent"] for b in budgets), 2)
    for b in budgets:
        if b["over"]:
            insights.append({"type": "warning", "title": f"Over budget on {b['category']}",
                             "detail": f"You've spent ${b['spent']:.0f} of your ${b['limit']:.0f} {b['category']} budget this month — ${b['spent'] - b['limit']:.0f} over."})
        elif b["limit"] and b["pct"] >= 80:
            insights.append({"type": "warning", "title": f"Close to your {b['category']} limit",
                             "detail": f"{b['pct']:.0f}% of your ${b['limit']:.0f} {b['category']} budget used — ${b['remaining']:.0f} left."})

    pending = comm_totals.get("pending", 0) + comm_totals.get("projected", 0)
    if pending > 0:
        insights.append({"type": "tip", "title": "Commission income on the way",
                         "detail": f"You have ${pending:.0f} in pending/projected commissions — plan for it, don't pre-spend it."})

    # Savings heuristic: savings balance vs a month of spend.
    savings = round(sum(a["balance"] for a in accounts if a["type"] == "savings"), 2)
    if accounts and total_spent > 0 and savings < total_spent:
        insights.append({"type": "tip", "title": "Build your cushion",
                         "detail": f"Savings (${savings:.0f}) is under a month of spending (${total_spent:.0f}). Auto-move a slice of each commission to savings."})

    # A win to reinforce good behavior.
    under = [b for b in budgets if b["limit"] and not b["over"] and b["pct"] < 60]
    if under:
        names = ", ".join(b["category"] for b in under[:3])
        insights.append({"type": "win", "title": "On track",
                         "detail": f"You're comfortably under budget on {names}. Nice work."})

    order = {"warning": 0, "tip": 1, "win": 2}
    return sorted(insights, key=lambda i: order.get(i["type"], 3))
