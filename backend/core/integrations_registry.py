"""
core/integrations_registry.py -- the external-provider seam (2026-07-24). NXTDeal depends on a
handful of real external services it can't reach in this sandbox: an SMS/email/push gateway,
a payment processor, an identity-verification provider, an insurance-verification API, and a
credit bureau. Everywhere those are needed, the platform has been HONESTLY SIMULATING the
effect (a real state change, a clear `simulated` marker, no fabricated real-world side effect).

2026-10-14 exception: signature delivery is release-gated. An adapter registration
does not enable it; only isolated demo simulation is allowed pending reviewed forms.

This module turns those scattered simulations into ONE swappable seam:

  * a catalog of the external capabilities NXTDeal needs, each naming the recommended provider
    and which NXTDeal modules consume it;
  * a per-capability adapter slot -- `register_adapter(capability, fn)` -- where real
    integration code plugs in later. No adapters are registered in this codebase yet, so every
    dispatcher below returns an honest simulated result; the day a Twilio/Stripe/etc. adapter is
    registered, the SAME call sites go live with zero changes;
  * thin dispatchers (`send_notification`, `charge_deposit`, `verify_insurance_policy`) that the
    consuming modules call instead of rolling their own simulation.

A per-dealer singleton (INTEGRATION_SETTINGS, prefix INTG) records which provider the dealer
intends to use per capability -- informational, for the admin dashboard. The RUNTIME truth is
simple and honest: a capability is "live" iff a real adapter is registered in code; otherwise
"simulated". Marking a provider name never fakes a live connection.
"""

from datetime import datetime, timezone

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import INTEGRATION_SETTINGS
from core.audit import audit_log
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

SIMULATION_NOTE = (
    "Provider mode describes adapter registration only. It does not verify delivery, settlement, "
    "dealer authorization, OEM certification, commercial approval or production readiness. "
    "Unregistered capabilities use sample behavior where the workflow permits it. "
    "Workflow release restrictions still apply when an adapter is registered."
)

# The external capabilities NXTDeal needs, the recommended provider to connect, and which
# NXTDeal modules consume each. Static -- this is a product fact, not per-dealer state.
CAPABILITIES = {
    "notifications": {
        "name": "Customer Notifications (SMS / Email / Push)",
        "description": "Outbound customer messages -- verification codes, delivery updates, reminders.",
        "recommended_provider": "Twilio",
        "consumed_by": ["dealeros_verify", "delivery_fulfillment", "ai_worker", "connect"],
    },
    "payments": {
        "name": "Payments / Deposits",
        "description": "Collecting a deposit or a customer payment.",
        "recommended_provider": "Stripe",
        "consumed_by": ["delivery_fulfillment", "payments"],
    },
    "identity": {
        "name": "Identity Verification",
        "description": "Driver-license + selfie identity check for NXTDeal Verify.",
        "recommended_provider": "Stripe Identity / Persona",
        "consumed_by": ["dealeros_verify"],
    },
    "insurance": {
        "name": "Insurance Verification",
        "description": "Confirming an active insurance policy (e.g. for Try Before You Buy).",
        "recommended_provider": "an insurance-verification API",
        "consumed_by": ["delivery_fulfillment"],
    },
    "credit_bureau": {
        "name": "Credit Bureau",
        "description": "Pulling a credit report to decision a financing application.",
        "recommended_provider": "Experian / Equifax / TransUnion",
        "consumed_by": ["credit_app"],
    },
    "banking": {
        "name": "Bank Account Linking",
        "description": "Linking a bank account to pull balances + transactions (MySales self-accounting).",
        "recommended_provider": "Plaid",
        "consumed_by": ["rep_finance"],
    },
    "ads": {
        "name": "Advertising Platforms (Meta / Google)",
        "description": "Publishing conquest/inventory ad campaigns to a real ad platform.",
        "recommended_provider": "Meta Ads / Google Ads",
        "consumed_by": ["advertising", "inventory_advertising"],
    },
    "enrichment": {
        "name": "Third-Party Data Enrichment (CDP)",
        "description": "Appending third-party household/vehicle-ownership data to enrich a customer record and sharpen buy-propensity scoring.",
        "recommended_provider": "a data-enrichment / CDP provider (e.g. Experian, Acxiom, a vehicle-ownership data vendor)",
        "consumed_by": ["data_enrichment", "buy_propensity"],
    },
    "telephony": {
        "name": "Voice / Telephony",
        "description": "Placing real outbound phone calls (and receiving inbound), with recording + transcription callbacks.",
        "recommended_provider": "Twilio / RingCentral",
        "consumed_by": ["call_center", "customer_comms"],
    },
    "esignature": {
        "name": "E-Signature",
        "description": "Sending a signature envelope to signers for a legally-binding electronic signature.",
        "recommended_provider": "DocuSign / Dropbox Sign / Adobe Sign",
        "consumed_by": ["esignature"],
    },
}

# App Suite roadmap Phase 5 -- the two integration layers. NXTDeal has DEALER-scoped
# provider connections (the "Dealer Marketplace" -- DMS/CRM, telephony, credit bureaus,
# enrichment, ads: shared by the whole store, what Readiness analyzes for a conversion case)
# vs PERSONAL, rep-scoped tools (MySales' Plaid bank-linking is the one today -- it powers
# MySales as a standalone product whether or not the rep's dealership is on NXTDeal). Every
# capability is tagged so the Connections UI and Readiness can treat the two layers distinctly.
CAPABILITY_SCOPE = {
    "banking": "personal",   # MySales rep Plaid self-accounting -- personal tools layer
    # everything else is dealer-scoped (Dealer Marketplace layer) -- see _capability_scope
}


def _capability_scope(capability):
    return CAPABILITY_SCOPE.get(capability, "dealer")


# Real adapters plug in here later. capability -> callable. Empty today (everything simulates).
_ADAPTERS = {}


def register_adapter(capability, fn):
    if capability not in CAPABILITIES:
        raise ValueError(f"Unknown capability '{capability}'")
    _ADAPTERS[capability] = fn


def is_live(capability):
    return capability in _ADAPTERS


def _now():
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------------------------
# Per-dealer settings (intended provider per capability) -- informational.
# ------------------------------------------------------------------------------------

def _find_settings():
    for e in ledger.get_all().values():
        if e.entity_type == INTEGRATION_SETTINGS:
            return e
    return None


def get_or_create_settings():
    existing = _find_settings()
    if existing:
        return existing
    settings = Entity(
        id=id_generator.generate("INTG"),
        entity_type=INTEGRATION_SETTINGS,
        attributes={"providers": {}, "created_at": _now(), "updated_at": _now()},
    )
    ledger.add_entity(settings)
    save_graph(GRAPH_PATH)
    return settings


def configure_provider(capability, provider_name, admin_id, note=None):
    """Record the provider the dealer intends to use for a capability. Informational only --
    it does NOT create a live connection (that requires a registered adapter in code)."""
    if capability not in CAPABILITIES:
        return {"error": f"Unknown capability '{capability}' -- valid: {list(CAPABILITIES)}"}
    settings = get_or_create_settings()
    settings.attributes["providers"][capability] = {
        "provider_name": provider_name, "note": note,
        "configured_by": admin_id, "configured_at": _now(),
    }
    settings.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)
    audit_log.record(
        event_type="integration_provider_configured",
        summary=f"{admin_id} set the {capability} provider to {provider_name}",
        entity_id=settings.id, actor=admin_id,
        details={"capability": capability, "provider_name": provider_name},
    )
    return {"capability": capability, "status": provider_status_one(capability)}


def _provider_label(capability):
    settings = _find_settings()
    cfg = settings.attributes.get("providers", {}).get(capability) if settings else None
    if cfg and cfg.get("provider_name"):
        return cfg["provider_name"]
    return CAPABILITIES[capability]["recommended_provider"]


def provider_status_one(capability):
    cap = CAPABILITIES[capability]
    settings = _find_settings()
    cfg = settings.attributes.get("providers", {}).get(capability, {}) if settings else {}
    return {
        "capability": capability,
        "name": cap["name"],
        "description": cap["description"],
        "recommended_provider": cap["recommended_provider"],
        "consumed_by": cap["consumed_by"],
        "mode": "live" if is_live(capability) else "simulated",
        "adapter_registered": is_live(capability),
        "authorization_evidence_status": "not_verified_by_registry",
        "oem_approval_status": "not_verified_by_registry",
        "production_readiness_status": "not_verified_by_registry",
        "scope": _capability_scope(capability),
        "layer": "Dealer Marketplace" if _capability_scope(capability) == "dealer" else "Personal Tools",
        "configured_provider": cfg.get("provider_name"),
        "note": cfg.get("note"),
    }


def provider_status():
    statuses = [provider_status_one(k) for k in CAPABILITIES]
    return {
        "providers": statuses,
        "live_count": sum(1 for s in statuses if s["mode"] == "live"),
        "simulated_count": sum(1 for s in statuses if s["mode"] == "simulated"),
        # Phase 5: group by integration layer so the UI can present Dealer Marketplace vs
        # Personal Tools distinctly (the roadmap's key strategic distinction).
        "by_layer": {
            "dealer": [s["capability"] for s in statuses if s["scope"] == "dealer"],
            "personal": [s["capability"] for s in statuses if s["scope"] == "personal"],
        },
        "disclaimer": SIMULATION_NOTE,
    }


# ------------------------------------------------------------------------------------
# Dispatchers -- the consuming modules call these. Live adapter if registered, else an honest
# simulated result carrying `simulated: True`.
# ------------------------------------------------------------------------------------

def send_notification(to, event, channels=("sms", "email", "push")):
    from core.contact_suppression import contact_suppression
    blocked = contact_suppression(to, channels=channels)
    if blocked:
        return blocked
    if is_live("notifications"):
        return _ADAPTERS["notifications"](to, event, channels)
    return {"capability": "notifications", "provider": _provider_label("notifications"),
            "simulated": True, "to": to, "event": event, "channels": list(channels), "at": _now()}


def charge_deposit(amount, reference=None):
    from math import isfinite
    from core.workflow_readiness import simulation_block
    blocked = simulation_block("electronic_payments", external_dispatch=is_live("payments"))
    if blocked:
        return blocked
    try:
        amount = float(amount)
    except (TypeError, ValueError, OverflowError):
        return {"error": "A finite positive deposit amount is required."}
    if not isfinite(amount) or amount <= 0:
        return {"error": "A finite positive deposit amount is required."}
    return {"capability": "payments", "provider": _provider_label("payments"),
            "simulated": True, "amount": amount, "status": "collected",
            "reference": reference, "at": _now()}


def verify_insurance_policy(policy_ref):
    from core.workflow_readiness import simulation_block
    blocked = simulation_block("insurance_verification", external_dispatch=is_live("insurance"))
    if blocked:
        return blocked
    return {"capability": "insurance", "provider": _provider_label("insurance"),
            "simulated": True, "policy_ref": policy_ref, "verified": True, "at": _now()}


def publish_ad(ad_spec):
    """Publish an ad campaign to a real ad platform if an adapter is registered; otherwise
    an honest simulated result. ad_spec is the platform-agnostic campaign dict."""
    if is_live("ads"):
        return _ADAPTERS["ads"](ad_spec)
    return {"capability": "ads", "provider": _provider_label("ads"),
            "simulated": True, "ad_spec": ad_spec, "published": True, "at": _now()}


def pull_credit(applicant):
    """Pull a credit report from a bureau if an adapter is registered; otherwise an honest
    simulated result (no real pull). `applicant` is a dict (name/ssn_last4/address). A live
    adapter returns at least `{score, bureau, ...}`; the simulated result carries no score
    so the caller falls back to its own honest decisioning."""
    from core.workflow_readiness import simulation_block
    blocked = simulation_block("credit_decisioning", external_dispatch=is_live("credit_bureau"))
    if blocked:
        return blocked
    return {"capability": "credit_bureau", "provider": _provider_label("credit_bureau"),
            "simulated": True, "pulled": False, "score": None,
            "note": "No credit-bureau provider connected -- no real pull performed.", "at": _now()}


def place_call(to, from_number=None, context=None):
    """Place a real outbound call if a telephony adapter is registered; otherwise an honest
    simulated result (no real call). A live adapter returns at least `{call_sid, status}`."""
    from core.contact_suppression import contact_suppression
    blocked = contact_suppression(to, channels=("voice",))
    if blocked:
        return blocked
    if is_live("telephony"):
        return _ADAPTERS["telephony"](to, from_number, context)
    return {"capability": "telephony", "provider": _provider_label("telephony"),
            "simulated": True, "placed": False, "to": to,
            "note": "No telephony provider connected -- call is simulated.", "at": _now()}


def send_signature(envelope):
    """Simulate delivery only in demo; reviewed production execution is unavailable.

    Registering an adapter alone must never enable external signature delivery.
    """
    from core.contracting_readiness import execution_block
    blocked = execution_block("signature_dispatch", external_dispatch=is_live("esignature"))
    if blocked:
        return blocked
    return {"capability": "esignature", "provider": _provider_label("esignature"),
            "simulated": True, "sent": False, "envelope": envelope,
            "note": "No e-signature provider connected -- send is simulated (typed-name signing still works in-app).", "at": _now()}


def enrich_record(record):
    """Append third-party data to a customer record if an enrichment adapter is registered;
    otherwise an honest simulated result that adds NO fabricated external data. `record` is
    a dict of the known fields (name/email/phone/address); a live adapter returns a dict of
    appended attributes under `appended`."""
    if is_live("enrichment"):
        return _ADAPTERS["enrichment"](record)
    return {"capability": "enrichment", "provider": _provider_label("enrichment"),
            "simulated": True, "appended": {}, "record": record,
            "note": "No enrichment provider connected -- no third-party data appended.", "at": _now()}
