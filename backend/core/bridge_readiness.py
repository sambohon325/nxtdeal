"""Derived onboarding guidance from current facts, never an authorization gate."""
from collections import Counter


def summarize(system, runtime, mappings, jobs, event_profiles=(), event_jobs=(), sync_states=(), inbound=None, connector_health=None):
    scoped_mappings = [mapping for mapping in mappings if mapping["system_id"] == system["id"]]
    scoped_jobs = [job for job in jobs if job["system_id"] == system["id"]]
    mapping_counts = dict(Counter(mapping["status"] for mapping in scoped_mappings))
    job_counts = dict(Counter(job["status"] for job in scoped_jobs))
    event_profile_counts = dict(Counter(profile["status"] for profile in event_profiles if profile["system_id"] == system["id"]))
    event_job_counts = dict(Counter(job["status"] for job in event_jobs if job["system_id"] == system["id"]))
    scoped_states = [state for state in sync_states if state["system_id"] == system["id"]]
    blocked_states = [state for state in scoped_states if state.get("status") == "blocked"]
    sync_counts = dict(Counter(state["status"] for state in scoped_states))
    inbound = inbound if isinstance(inbound, dict) and inbound.get("system_id") == system["id"] else {}
    inbound_counts = dict(Counter(gateway["effective_status"] for gateway in inbound.get("gateways", [])))
    health_guidance = {
        "authentication_required": "The last check reported expired or missing source access. Ask the connector operator to review credentials, then check health again.",
        "permission_denied": "The last check reported denied source permissions. Ask the connector operator to verify the dealer-approved scope, then check health again.",
        "source_changed": "The last check reported a changed source. Inspect its schema and connector configuration before collecting another export.",
        "rate_limited": "The last check reported a source rate limit. Follow the provider's retry guidance before checking again; this diagnostic does not schedule a retry.",
        "unavailable": "The last check could not reach or verify the source. Ask the connector operator to inspect connectivity and configuration, then check health again.",
        "degraded": "The last check reported degraded source health. Review the connector with its operator before relying on a new collection.",
    }
    health = connector_health or {}
    health_message = health_guidance.get(health.get("status")) if health.get("current_binding") and runtime.get("status") == "bound" else None
    if system.get("paused"):
        code, label = "paused", "Review why this system is paused before resuming imports."
    elif job_counts.get("blocked"):
        code, label = "resolve_import", "Resolve the import rows or reconciliation checks that need review."
    elif event_job_counts.get("blocked"):
        code, label = "resolve_event_import", "Open ADF creation events to review blocked identities or source conflicts."
    elif job_counts.get("validated"):
        code, label = "review_activation", "Review the validated import before a human administrator activates it."
    elif event_job_counts.get("validated"):
        code, label = "review_event_activation", "Open ADF creation events and review the validated batch before activation."
    elif job_counts.get("staged"):
        code, label = "validate_import", "Validate the staged export and inspect its proposed changes."
    elif event_job_counts.get("staged"):
        code, label = "validate_event_import", "Open ADF creation events to validate the staged batch."
    elif any(state.get("last_error_code") == "authentication_required" for state in blocked_states):
        code, label = "renew_connector_access", "Ask the connector operator to renew source access, then review and explicitly retry the blocked collection."
    elif blocked_states:
        code, label = "review_blocked_collection", "Inspect the blocked collection and its error before an administrator requests a retry. Saved source positions have not advanced for failed reads."
    elif any(state.get("availability", {}).get("status") == "review_required" for state in scoped_states):
        code, label = "review_collection_configuration", "Review collection availability, connector scope and pending checkpoint evidence before reading this source again."
    elif inbound.get("delivery_evidence_issues"):
        code, label = "review_inbound_evidence", "Inspect signed-delivery evidence inconsistencies before relying on retained receipts."
    elif inbound_counts.get("review_required"):
        code, label = "review_inbound_policy", "Review the signed gateway binding, approved profile and authorizing administrator before resuming delivery."
    elif mapping_counts.get("proposed"):
        code, label = "review_mapping", "Test the proposed mapping; a different administrator must approve it."
    elif event_profile_counts.get("proposed"):
        code, label = "review_event_profile", "Test the proposed ADF profile; a different administrator must approve it."
    elif inbound_counts.get("ready"):
        code, label = "monitor_inbound_review", "Signed-delivery policy is ready. Inspect received batches for review; sender connectivity and signing credentials have not been probed."
    elif inbound_counts.get("disabled") and event_profile_counts.get("approved") and not mapping_counts.get("approved"):
        code, label = "review_inbound_options", "Signed delivery is disabled. Review gateway settings or upload an authorized ADF file for review."
    elif event_profile_counts.get("approved") and not mapping_counts.get("approved"):
        code, label = "review_event_export", "Review an authorized ADF file with the approved event profile."
    elif not mapping_counts.get("approved"):
        code, label = "discover_mapping", "Inspect an authorized export or connected schema, then propose a mapping."
    elif health_message:
        code, label = "review_connector_health", health_message
    elif runtime.get("status") == "bound":
        code, label = "review_collection", "Review the connector scope and prepare or inspect read-only collection."
    else:
        code, label = "review_export", "Review an authorized export using an approved mapping. Live access is separate."
    return {"next_step": code, "guidance": label, "mapping_counts": mapping_counts,
            "import_counts": job_counts, "collection_counts": sync_counts, "inbound_policy_counts": inbound_counts, "received_delivery_count": inbound.get("received_delivery_count", 0), "delivery_evidence_issues": inbound.get("delivery_evidence_issues", 0), "event_profile_counts": event_profile_counts, "event_import_counts": event_job_counts, "live_access": runtime.get("status") == "bound", "runtime_bound": runtime.get("status") == "bound",
            "notice": "Guidance reflects current records only; it does not approve access, mapping, collection or activation."}
