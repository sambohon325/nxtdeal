"""
NXTDeal AI Demo Platform — backend foundation (2026-07-24, Sam: let a prospect experience the
product immediately instead of waiting for a sales rep. "The demo environment is simply a
special demo mode inside an existing NXTDeal tenant." Entered from dealeros.xyz's "Try AI
Guided Demo" form or a reserved demo login; invisible to real employees).

This module owns:
  • The demo GATE — demo entry only works in a DEALEROS_DEMO tenant (a separate, seeded, fully
    NON-PERSISTENT deployment; every saver no-ops — see core/storage.demo_persistence_disabled).
    On the real dealer backend the flag is off, so start_demo refuses: a regular employee can
    never enter demo mode, and the app just works normally.
  • The 15 role PERSONAS from the spec, each mapped to the NXTDeal role its tour needs, an
    entry department, and a focus list the AI guide walks through.
  • start_demo() → a DemoSession (analytics) + a normal employee-style session token for the
    persona's role, so every existing dashboard/read works against the seeded demo data with no
    per-route changes. Because the tenant can't persist, minting a session freely is safe.
  • Lightweight analytics: track_event() records pages viewed / questions asked / modules
    visited on the DemoSession, feeding end-of-demo AI lead qualification later.
"""

import os
import secrets
from datetime import datetime, timezone

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import DEMO_SESSION
from core.storage import save_graph, demo_persistence_disabled
from core.storage_paths import GRAPH_PATH
from core.auth import credential_store, issue_token
from core.auth_api import _allowed_dashboards
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


# The role picker from the spec. `role` is the NXTDeal auth role the persona's tour needs;
# `entry` is the department it should open on; `focus` seeds the AI guide's tour outline.
PERSONAS = [
    {"key": "dealer_principal", "label": "Dealer Principal", "role": ADMIN, "entry": "Operations",
     "focus": ["Readiness", "Network", "Opportunities", "Forecasting", "Profitability", "AI Workforce"]},
    {"key": "general_manager", "label": "General Manager", "role": ADMIN, "entry": "Operations",
     "focus": ["Store performance", "Sales + Service", "AI Workforce", "Forecasting"]},
    {"key": "sales_manager", "label": "Sales Manager", "role": SALES, "entry": "Sales",
     "focus": ["Leads", "BDC", "Pipeline", "Coaching", "AI Sales Agents"]},
    {"key": "salesperson", "label": "Salesperson", "role": SALES, "entry": "Sales",
     "focus": ["My day", "Follow-ups", "Inventory", "AI Coach"]},
    {"key": "service_director", "label": "Service Director", "role": SERVICE, "entry": "Service",
     "focus": ["ROs", "DVI", "Shop Control", "Technician Utilization", "Retention"]},
    {"key": "service_advisor", "label": "Service Advisor", "role": SERVICE, "entry": "Service",
     "focus": ["Appointments", "Repair Orders", "DVI", "Customer updates"]},
    {"key": "fixed_ops_director", "label": "Fixed Ops Director", "role": SERVICE, "entry": "Service",
     "focus": ["Shop Control", "Parts", "Technician Utilization", "Retention", "Profitability"]},
    {"key": "fi_manager", "label": "F&I Manager", "role": FINANCE, "entry": "Finance",
     "focus": ["Deals", "F&I menu", "Compliance", "Funding", "Lender submission"]},
    {"key": "bdc_manager", "label": "BDC Manager", "role": SALES, "entry": "Sales",
     "focus": ["Lead inbox", "AI BDC", "Appointments", "Response times"]},
    {"key": "marketing_director", "label": "Marketing Director", "role": MARKETING, "entry": "Marketing",
     "focus": ["CRM", "Email", "SMS", "Website Builder", "Events", "Advertising"]},
    {"key": "group_exec", "label": "Dealer Group Executive", "role": ADMIN, "entry": "Operations",
     "focus": ["Multi-store", "Network benchmarking", "Forecasting", "AI Workforce"]},
    {"key": "bhph_operator", "label": "BHPH Operator", "role": FINANCE, "entry": "Finance",
     "focus": ["Collections", "Payments", "GPS", "Starter Interrupt", "Repossession"]},
    {"key": "finance_company", "label": "Finance Company", "role": FINANCE, "entry": "Finance",
     "focus": ["Portfolio", "Servicing", "Collections", "Recovery"]},
    {"key": "independent_dealer", "label": "Independent Dealer", "role": ADMIN, "entry": "Operations",
     "focus": ["Inventory", "Sales", "Digital Retail", "AI Workforce", "Marketing"]},
    {"key": "oem_representative", "label": "OEM Representative", "role": OPERATIONS, "entry": "Operations",
     "focus": ["Network", "Benchmarking", "Program compliance", "Store readiness"]},
]

_PERSONA_BY_KEY = {p["key"]: p for p in PERSONAS}

# Demo tours (prebuilt story scenarios from the spec) — the AI guide will drive these.
SCENARIOS = [
    {"key": "sell_a_vehicle", "label": "Sell a vehicle",
     "steps": ["Lead", "Appointment", "Showroom", "Deal", "Finance", "Delivery"]},
    {"key": "run_service", "label": "Run service",
     "steps": ["Appointment", "RO", "DVI", "Parts", "Repair", "Delivery"]},
    {"key": "launch_campaign", "label": "Launch a marketing campaign",
     "steps": ["Audience", "Email", "SMS", "Landing Page", "Ads"]},
    {"key": "buy_online", "label": "Buy a vehicle online",
     "steps": ["Website", "Trade", "Negotiation", "Finance", "Delivery"]},
]

MODES = ("guided", "explore", "power")


def _now():
    return datetime.now(timezone.utc).isoformat()


def demo_enabled():
    """Demo entry is only available in a DEALEROS_DEMO tenant (which is also non-persistent)."""
    return demo_persistence_disabled()


def get_personas():
    return {
        "enabled": demo_enabled(),
        "personas": [{"key": p["key"], "label": p["label"], "focus": p["focus"], "entry": p["entry"]} for p in PERSONAS],
        "scenarios": SCENARIOS,
        "modes": list(MODES),
    }


def _access_ok(access_code):
    """Optional gate: if DEMO_ACCESS_CODE is set on the tenant, the launcher must present it
    (the 'unique demo credential'). Unset → the demo is open (e.g. straight from the website
    form)."""
    required = os.environ.get("DEMO_ACCESS_CODE", "").strip()
    if not required:
        return True
    return (access_code or "").strip() == required


def start_demo(persona_key, mode="guided", contact=None, access_code=None):
    if not demo_enabled():
        return {"error": "Demo mode isn't available here."}
    if not _access_ok(access_code):
        return {"error": "That demo access code isn't valid."}
    persona = _PERSONA_BY_KEY.get(persona_key)
    if persona is None:
        return {"error": f"Unknown persona '{persona_key}'."}
    if mode not in MODES:
        mode = "guided"

    session = Entity(
        id=id_generator.generate("DEMO"),
        entity_type=DEMO_SESSION,
        attributes={
            "persona": persona_key,
            "persona_label": persona["label"],
            "role": persona["role"],
            "mode": mode,
            "contact": contact or {},
            "started_at": _now(),
            "events": [],
            "modules_visited": [],
            "questions_asked": 0,
            "pages_viewed": 0,
        },
    )
    ledger.add_entity(session)
    save_graph(GRAPH_PATH)  # no-op in a demo tenant; kept for parity/audit shape

    # A normal employee-style token for the persona's role, so every existing authed dashboard
    # works with no per-route demo changes. employee_id encodes the demo session for analytics.
    # Demo persistence is disabled above; this random, undisclosed credential
    # exists only in memory so demo sessions follow normal revocation rules too.
    credential_store.set_credential(f"DEMO:{session.id}", secrets.token_urlsafe(32),
                                    persona["role"], must_change_password=False)
    token = issue_token(f"DEMO:{session.id}", persona["role"])

    return {
        "token": token,
        "session_id": session.id,
        "persona": {"key": persona_key, "label": persona["label"], "focus": persona["focus"], "entry": persona["entry"]},
        "role": persona["role"],
        "allowed_dashboards": _allowed_dashboards(persona["role"]),
        "mode": mode,
        "scenarios": SCENARIOS,
        "watermark": {"label": "NXTDeal Demonstration Environment", "session_id": session.id, "started_at": session.attributes["started_at"]},
    }


def _demo_session(session_id):
    e = ledger.get_entity(session_id)
    if e is None or e.entity_type != DEMO_SESSION:
        return None
    return e


def track_event(session_id, kind, detail=None):
    """Record a demo interaction for analytics (feeds end-of-demo AI lead qualification)."""
    e = _demo_session(session_id)
    if e is None:
        return {"error": "Demo session not found."}
    a = e.attributes
    a.setdefault("events", []).append({"kind": kind, "detail": detail, "at": _now()})
    if kind == "page_view":
        a["pages_viewed"] = a.get("pages_viewed", 0) + 1
        module = (detail or {}).get("module") if isinstance(detail, dict) else detail
        if module and module not in a.setdefault("modules_visited", []):
            a["modules_visited"].append(module)
    elif kind == "question":
        a["questions_asked"] = a.get("questions_asked", 0) + 1
    save_graph(GRAPH_PATH)  # no-op in demo tenant
    return {"ok": True}


def get_session(session_id):
    e = _demo_session(session_id)
    if e is None:
        return {"error": "Demo session not found."}
    a = e.attributes
    return {
        "session_id": e.id,
        "persona": a.get("persona"),
        "persona_label": a.get("persona_label"),
        "mode": a.get("mode"),
        "pages_viewed": a.get("pages_viewed", 0),
        "questions_asked": a.get("questions_asked", 0),
        "modules_visited": a.get("modules_visited", []),
        "started_at": a.get("started_at"),
    }


# A short "what to do next" line per top-interest department, used in the recommendation.
_FOCUS_PITCH = {
    "Sales": "growth automation — AI BDC, lead follow-up, and coaching",
    "Service": "fixed-ops throughput — DVI, shop control, and retention",
    "Marketing": "demand generation — CRM, campaigns, and the website studio",
    "Inventory": "inventory velocity — acquisition, recon, and merchandising",
    "Finance": "portfolio performance — F&I, collections, and servicing",
    "Operations": "store-wide readiness — the AI Workforce and Network benchmarking",
}


def summarize_session(session_id):
    """End-of-demo AI lead qualification (2026-07-24, Phase 3). Rules-based (deterministic, no
    LLM — like conversation_intelligence): from what the prospect actually explored, infer their
    interest areas + buying intent and produce a tailored recommendation + conversion CTAs."""
    e = _demo_session(session_id)
    if e is None:
        return {"error": "Demo session not found."}
    a = e.attributes
    events = a.get("events", [])

    # Rank the departments they navigated to (the strongest interest signal).
    dept_counts = {}
    for ev in events:
        if ev.get("kind") == "navigate":
            d = (ev.get("detail") or {}).get("department")
            if d:
                dept_counts[d] = dept_counts.get(d, 0) + 1
    ranked = sorted(dept_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    interests = [d for d, _ in ranked[:3]] or a.get("modules_visited", [])[:3]

    pages = a.get("pages_viewed", 0)
    questions = a.get("questions_asked", 0)
    score = pages + questions * 3 + len(dept_counts) * 2
    intent = "high" if (score >= 15 or questions >= 3) else "medium" if score >= 6 else "low"

    focus = interests[0] if interests else None
    pitch = _FOCUS_PITCH.get(focus, "the workflows you explored")
    if interests:
        recommendation = (
            f"Based on what you explored — {', '.join(interests)} — I'd set up a live demo focused on {pitch}."
        )
    else:
        recommendation = (
            f"You got a feel for how a {a.get('persona_label')} works in NXTDeal. A short live demo can go deep on the areas that matter most to your store."
        )
    if intent == "high":
        recommendation += " You dug in — a conversation now would be time well spent."

    return {
        "session_id": e.id,
        "persona": a.get("persona"),
        "persona_label": a.get("persona_label"),
        "role": a.get("role"),
        "mode": a.get("mode"),
        "pages_viewed": pages,
        "questions_asked": questions,
        "modules_visited": a.get("modules_visited", []),
        "interests": interests,
        "intent": intent,
        "score": score,
        "recommendation": recommendation,
        "ctas": [
            {"kind": "book", "label": "Book a live demo", "href": "/contact"},
            {"kind": "network", "label": "Install NXTDeal Network free", "href": "/dealeros-network"},
        ],
    }
