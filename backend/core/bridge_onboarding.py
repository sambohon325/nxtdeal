"""Dealer-reported setup evidence; never runtime authorization or certification."""
from copy import deepcopy

from core.bridge_contracts import FIELDS

EVIDENCE = ("dealer_authorization", "product_documentation", "sample_export", "stable_ids",
            "source_timestamps", "relationship_keys", "independent_totals")
STATES = ("unknown", "requested", "available", "not_applicable")
DEPLOYMENTS = ("unknown", "cloud", "on_premise", "hosted", "file_only")


def defaults():
    return {"product_version": "", "deployment": "unknown", "record_types": [],
            "evidence": {key: "unknown" for key in EVIDENCE}}


def validate(details):
    if not isinstance(details, dict) or set(details) != set(defaults()):
        raise ValueError("Complete onboarding details required")
    version = details["product_version"]
    if not isinstance(version, str) or len(version) > 120 or any(ord(c) < 32 for c in version):
        raise ValueError("Product version must be bounded plain text")
    if details["deployment"] not in DEPLOYMENTS:
        raise ValueError("Unknown deployment type")
    kinds = details["record_types"]
    if not isinstance(kinds, list) or len(kinds) > len(FIELDS) or any(not isinstance(k, str) or k not in FIELDS for k in kinds):
        raise ValueError("Known canonical record types required")
    if len(set(kinds)) != len(kinds):
        raise ValueError("Duplicate record types")
    evidence = details["evidence"]
    if not isinstance(evidence, dict) or set(evidence) != set(EVIDENCE) or any(value not in STATES for value in evidence.values()):
        raise ValueError("Known setup evidence states required")
    return {"product_version": version.strip(), "deployment": details["deployment"],
            "record_types": list(kinds), "evidence": dict(evidence)}


def describe(system):
    saved = system.get("onboarding", {})
    details = deepcopy(saved.get("details", defaults()))
    return {"revision": saved.get("revision", 0), "details": details,
            "updated_by": saved.get("updated_by"), "updated_at": saved.get("updated_at"),
            "evidence_states": list(STATES), "deployments": list(DEPLOYMENTS),
            "unresolved_evidence": [key for key in EVIDENCE if details["evidence"][key] in ("unknown", "requested")],
            "notice": "Dealer-reported planning only. Available evidence does not verify access, approve mappings, enable collection or permit external writes. Keep credentials and customer data out of setup details."}


def read(actor, system_id):
    from core import dealer_bridge as bridge
    bridge.authorize(actor)
    with bridge.LOCK:
        return describe(bridge.get(system_id, "BridgeSystem"))


def update(actor, system_id, revision, details):
    from core import dealer_bridge as bridge
    bridge.authorize(actor, human=True)
    if type(revision) is not int or revision < 0:
        raise ValueError("Current onboarding revision required")
    cleaned = validate(details)
    with bridge.mutation(actor, human=True):
        system = bridge.get(system_id, "BridgeSystem")
        current = system.get("onboarding", {})
        if current.get("revision", 0) != revision:
            raise ValueError("Setup details changed; reload before saving")
        system["onboarding"] = {"revision": revision + 1, "details": cleaned,
                                "updated_by": actor["employee_id"], "updated_at": bridge.now()}
        bridge.audit(actor, "system.onboarding.update", system_id)
        return describe(system)
