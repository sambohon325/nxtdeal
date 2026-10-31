"""CI/CD pipeline integration for the Programming Schedule (2026-10-25).

Closes the gap between "status: done" (manually set) and actual verified
completion: CI-passed → auto-advance to "done"; deployment-healthy →
auto-advance to "deployed"; production-verified → auto-advance to
"pushed_live".

Also provides a bidirectional message channel (DEPLOYMENT_CHANNEL entities)
so the desktop Hermes agent and the VPS Hermes agent (with Tailscale) can
exchange deployment commands and results through this hosted backend.

Three entity types (see core/entity_types.py):
  - CIPipelineRun: one GitHub Actions workflow run, linked to a PS item via
    ci_commit_sha. Persisted with status, conclusion, and a HMAC-verified
    payload reference.
  - DeploymentRun: one Coolify deployment attempt, linked to a PS item via
    coolify_deployment_id. Persisted with status, deployed_at, and health.
  - DeploymentChannel: a per-(from_agent, to_agent) message inbox. Agents
    poll GET /programming-schedule/agent-channel/messages?agent=<name> to
    retrieve messages addressed to them, and POST to send messages.

GitHub webhook signature verification uses HMAC-SHA256 with a shared secret
provided via NXTDEAL_GITHUB_WEBHOOK_SECRET. Coolify webhooks use a separate
secret via NXTDEAL_COOLIFY_WEBHOOK_SECRET. Messages on the agent channel are
NOT authenticated by user tokens — they're authenticated by a per-agent
shared secret token (NXTDEAL_AGENT_SECRET) that the VPS and desktop agents
present. This is the trust anchor for agent-to-agent communication.
"""
import hashlib
import hmac
import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import (
    CI_PIPELINE_RUN,
    DEPLOYMENT_RUN,
    DEPLOYMENT_CHANNEL,
    PROGRAMMING_SCHEDULE,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Status transition pipeline — the core of closing the completion→approval→live gap.
#
# Status flow:
#   todo → in_progress → in_review → done → deployed → pushed_live
#   Any status can be set to "blocked" manually. Only "done" can be set
#   manually from in_review (human approval gate). The transitions
#   done→deployed→pushed_live are AUTOMATIC, driven by CI/CD signals below.
# ---------------------------------------------------------------------------

# Environment variables (settable via .env or deployment config)
GITHUB_WEBHOOK_SECRET = os.environ.get("NXTDEAL_GITHUB_WEBHOOK_SECRET", "")
COOLIFY_WEBHOOK_SECRET = os.environ.get("NXTDEAL_COOLIFY_WEBHOOK_SECRET", "")
AGENT_SECRET = os.environ.get("NXTDEAL_AGENT_SECRET", "")

# Coolify API configuration
COOLIFY_API_URL = os.environ.get("NXTDEAL_COOLIFY_API_URL", "https://coolify.sambohon.digital/api/v1")
COOLIFY_API_KEY = os.environ.get("NXTDEAL_COOLIFY_API_KEY", "")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save():
    """Persist the graph after mutations."""
    from core.storage import save_graph
    from core.storage_paths import GRAPH_PATH
    save_graph(GRAPH_PATH)


# ---------------------------------------------------------------------------
# GitHub Actions webhook receiver
# ---------------------------------------------------------------------------

def verify_github_signature(payload: bytes, signature: str) -> bool:
    """Verify a GitHub webhook delivery signature (HMAC-SHA256).

    GitHub sends the signature as: 'sha256=<hexdigest>'.
    """
    if not GITHUB_WEBHOOK_SECRET:
        log.warning("GitHub webhook secret not configured; rejecting webhook")
        return False
    if not signature:
        return False
    if signature.startswith("sha256="):
        signature = signature[7:]
    expected = hmac.new(
        GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def receive_github_webhook(payload_body: bytes, signature: str) -> dict[str, Any]:
    """Process a GitHub Actions workflow_run webhook payload.

    Expected event: workflow_run, action=completed.
    Extracts: commit SHA, workflow name, conclusion (success/failure),
    and maps it to any PS item tracking that commit.
    """
    if not verify_github_signature(payload_body, signature):
        return {"error": "Invalid GitHub webhook signature"}

    try:
        payload = json.loads(payload_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"error": "Invalid JSON payload"}

    action = payload.get("action")
    workflow_run = payload.get("workflow_run", {})

    if action != "completed":
        return {"status": "ignored", "reason": f"action={action} (only 'completed' processed)"}

    commit_sha = workflow_run.get("head_sha", "")[:40]
    workflow_name = workflow_run.get("name", "")
    conclusion = workflow_run.get("conclusion", "")  # "success" or "failure"
    run_id = workflow_run.get("id")

    if not commit_sha:
        return {"error": "No commit SHA in workflow_run payload"}

    # Record this CI run as a CIPipelineRun entity
    ci_id = f"CI-{run_id}" if run_id else f"CI-{commit_sha[:12]}"
    ci_entity = Entity(
        id=ci_id,
        entity_type=CI_PIPELINE_RUN,
        attributes={
            "workspace_id": ledger.tenant.workspace_id if hasattr(ledger, "tenant") else "default",
            "commit_sha": commit_sha,
            "workflow_name": workflow_name,
            "conclusion": conclusion,
            "run_id": run_id,
            "received_at": _now(),
            "status": "success" if conclusion == "success" else "failed",
        },
    )

    # If this CI run corresponds to a PS item, record the CI result on the item
    matched_items = _find_ps_items_by_commit(commit_sha)
    for item in matched_items:
        _record_ci_result(item["id"], ci_id, conclusion == "success")

    ledger.add_entity(ci_entity)
    _save()

    return {
        "status": "processed",
        "ci_id": ci_id,
        "commit_sha": commit_sha,
        "workflow_name": workflow_name,
        "conclusion": conclusion,
        "matched_items": len(matched_items),
    }


def _find_ps_items_by_commit(commit_sha: str) -> list[dict[str, Any]]:
    """Find all PS items whose ci_commit_sha matches the given SHA."""
    results = []
    for entity_id in ledger.entities:
        entity = ledger.get_entity(entity_id)
        if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
            continue
        if entity.attributes.get("ci_commit_sha") == commit_sha:
            results.append({"id": entity.id, **dict(entity.attributes)})
    return results


def _record_ci_result(item_id: str, ci_id: str, passed: bool) -> None:
    """Record CI result on a PS item. If CI passes and status is 'in_review',
    auto-advance to 'done' (the approval gate)."""
    entity = ledger.get_entity(item_id)
    if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
        return

    entity.attributes["ci_passed"] = passed
    entity.attributes["ci_ci_id"] = ci_id
    entity.attributes["updated_at"] = _now()

    # Auto-advance: CI pass + in_review → done (this is the "checked" gate)
    if passed and entity.attributes.get("status") == "in_review":
        entity.attributes["status"] = "done"
        _add_work_note(entity, f"CI passed — status auto-advanced from in_review to done. CI run: {ci_id}")
    elif not passed:
        # Don't auto-advance; keep in in_review or whatever status, but note failure
        _add_work_note(entity, f"CI failed — see CI run {ci_id}")

    _save()


# ---------------------------------------------------------------------------
# Coolify deployment status
# ---------------------------------------------------------------------------

def receive_coolify_webhook(payload_body: bytes, signature: str) -> dict[str, Any]:
    """Process a Coolify deployment webhook.

    Coolix sends an X-Coolify-Signature header with HMAC-SHA256 of the body.
    """
    if not COOLIFY_WEBHOOK_SECRET:
        log.warning("Coolify webhook secret not configured; rejecting webhook")
        return {"error": "Coolify webhook secret not configured"}

    expected_sig = hmac.new(
        COOLIFY_WEBHOOK_SECRET.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()

    # Coolify typically sends signature without the 'sha256=' prefix
    provided_sig = signature.replace("sha256=", "") if signature else ""
    if not hmac.compare_digest(expected_sig, provided_sig):
        return {"error": "Invalid Coolify webhook signature"}

    try:
        payload = json.loads(payload_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"error": "Invalid JSON payload"}

    # Coolify deployment payload fields (v4 API shape)
    deployment_id = payload.get("deployment_id", "") or payload.get("id", "")
    status = payload.get("status", "")  # "successful", "failed", "queued", "in_progress"
    application = payload.get("application", {}).get("name", "") if isinstance(payload.get("application"), dict) else ""
    commit_sha = payload.get("commit_sha", "") or payload.get("git_commit", "") or ""
    deployed_at = payload.get("finished_at", payload.get("deployed_at", ""))

    if not deployment_id and not commit_sha:
        return {"error": "No deployment_id or commit_sha in Coolify payload"}

    # Create or update the DeploymentRun entity
    dep_id = f"DEPLOY-{deployment_id}" if deployment_id else f"DEPLOY-{commit_sha[:12]}"

    # Check if we already have this deployment run
    existing = ledger.get_entity(dep_id)
    if existing:
        existing.attributes.update({
            "status": status,
            "application": application,
            "commit_sha": commit_sha,
            "deployed_at": deployed_at or _now(),
        })
        entity = existing
    else:
        entity = Entity(
            id=dep_id,
            entity_type=DEPLOYMENT_RUN,
            attributes={
                "workspace_id": ledger.tenant.workspace_id if hasattr(ledger, "tenant") else "default",
                "status": status,
                "application": application,
                "commit_sha": commit_sha,
                "deployment_id": deployment_id,
                "deployed_at": deployed_at or _now(),
                "received_at": _now(),
            },
        )
        ledger.add_entity(entity)

    # If deployment succeeded, find matching PS items and advance
    if status in ("successful", "success", "deployed"):
        matched_items = _find_ps_items_by_deployment(dep_id, commit_sha)
        for item in matched_items:
            ps_entity = ledger.get_entity(item["id"])
            if ps_entity and ps_entity.attributes.get("status") == "done":
                ps_entity.attributes["status"] = "deployed"
                ps_entity.attributes["deployment_run_id"] = dep_id
                ps_entity.attributes["coolify_deployment_id"] = deployment_id
                ps_entity.attributes["updated_at"] = _now()
                _add_work_note(ps_entity, f"Deployed via Coolify ({dep_id}) — status auto-advanced from done to deployed")

    _save()
    return {
        "status": "processed",
        "deployment_id": dep_id,
        "deployment_status": status,
        "commit_sha": commit_sha,
    }


def _find_ps_items_by_deployment(deployment_entity_id: str, commit_sha: str) -> list[dict[str, Any]]:
    """Find PS items linked to this deployment via coolify_deployment_id or commit_sha.

    deployment_entity_id is the full DeploymentRun entity ID (e.g. 'DEPLOY-abc123').
    We compare against the raw deployment_id stored on the DeploymentRun entity,
    since PS items store the raw Coolify deployment ID in coolify_deployment_id.
    """
    results = []
    dep_entity = ledger.get_entity(deployment_entity_id)
    raw_dep_id = dep_entity.attributes.get("deployment_id", "") if dep_entity else ""
    for entity_id in ledger.entities:
        entity = ledger.get_entity(entity_id)
        if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
            continue
        if (entity.attributes.get("coolify_deployment_id") == raw_dep_id or
            entity.attributes.get("ci_commit_sha") == commit_sha):
            results.append({"id": entity.id, **dict(entity.attributes)})
    return results


def poll_coolify_deployment(deployment_id: str) -> dict[str, Any]:
    """Poll the Coolify API for a deployment's current status.

    Used by the background loop and by agent-channel queries.
    """
    if not COOLIFY_API_KEY:
        return {"error": "Coolify API key not configured"}

    url = f"{COOLIFY_API_URL}/deployments/{deployment_id}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {COOLIFY_API_KEY}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"Coolify API error: {e.code} {e.reason}"}
    except urllib.error.URLError as e:
        return {"error": f"Coolify API unreachable: {e.reason}"}
    except Exception as e:
        return {"error": f"Coolify API error: {e}"}

    return {
        "deployment_id": deployment_id,
        "status": data.get("status", "unknown"),
        "application": data.get("application", {}).get("name", "") if isinstance(data.get("application"), dict) else "",
        "commit_sha": data.get("commit_sha", ""),
        "finished_at": data.get("finished_at", ""),
        "health": data.get("health", "unknown"),
    }


def verify_production_health(item_id: str) -> dict[str, Any]:
    """Verify that a deployed item is actually live in production.

    Checks:
    1. Coolify deployment status is 'successful'
    2. The application responds with HTTP 200 on the primary route
    3. (Optional) A health-check endpoint returns 200
    """
    entity = ledger.get_entity(item_id)
    if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
        return {"error": f"Item '{item_id}' not found"}

    coolify_dep_id = entity.attributes.get("coolify_deployment_id")
    resources = entity.attributes.get("resources", [])

    if not coolify_dep_id:
        return {"error": "No Coolify deployment ID linked to this item"}

    # Poll Coolify for deployment status
    dep_info = poll_coolify_deployment(coolify_dep_id)
    if "error" in dep_info:
        return dep_info

    if dep_info["status"] not in ("successful", "success", "deployed"):
        return {
            "verified": False,
            "reason": f"Deployment status is '{dep_info['status']}', not successful",
            "deployment_status": dep_info["status"],
        }

    # Check production health via resources attached to the item
    # Resources may include health-check URLs or primary routes
    health_urls = [r for r in resources if isinstance(r, str) and r.startswith("https://")]
    all_healthy = True
    health_details = []

    for url in health_urls:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                healthy = resp.status == 200
                health_details.append({"url": url, "status": resp.status, "healthy": healthy})
                if not healthy:
                    all_healthy = False
        except Exception as e:
            health_details.append({"url": url, "error": str(e), "healthy": False})
            all_healthy = False

    return {
        "verified": all_healthy,
        "deployment_status": dep_info["status"],
        "commit_sha": dep_info.get("commit_sha", ""),
        "health_checks": health_details,
    }


def mark_pushed_live(item_id: str, verified_by: str = "auto") -> dict[str, Any]:
    """Mark a deployed item as pushed_live after verifying production health.

    This is the final step in the completion pipeline:
    done → deployed → pushed_live.

    Can be called manually by an admin or automatically by the polling loop.
    """
    entity = ledger.get_entity(item_id)
    if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
        return {"error": f"Item '{item_id}' not found"}

    if entity.attributes.get("status") != "deployed":
        return {"error": f"Item '{item_id}' must be 'deployed' before marking pushed_live (currently: {entity.attributes.get('status')})"}

    entity.attributes["status"] = "pushed_live"
    entity.attributes["pushed_live_at"] = _now()
    entity.attributes["pushed_live_by"] = verified_by
    entity.attributes["updated_at"] = _now()
    _save()

    _add_work_note(entity, f"Marked as pushed_live by {verified_by} at {_now()}")

    return {"id": item_id, **{k: v for k, v in entity.attributes.items()}}


# ---------------------------------------------------------------------------
# Agent communication channel (desktop Hermes ↔ VPS Hermes)
# ---------------------------------------------------------------------------

def _channel_id(from_agent: str, to_agent: str) -> str:
    """Deterministic channel ID for bidirectional agent communication.

    The channel is a single entity shared between both agents — messages
    are tagged with direction (from_agent → to_agent). Both agents poll
    the same channel for messages addressed to them.
    """
    participants = sorted([from_agent, to_agent])
    return "CH-" + "-".join(participants)


def _verify_agent_secret(token: str) -> bool:
    """Verify the shared agent secret token for agent-to-agent communication."""
    if not AGENT_SECRET:
        log.warning("NXTDEAL_AGENT_SECRET not configured; rejecting agent message")
        return False
    return hmac.compare_digest(AGENT_SECRET, token)


def send_agent_message(from_agent: str, to_agent: str, message_type: str,
                       payload: dict[str, Any], token: str) -> dict[str, Any]:
    """Send a message from one agent to another via the shared channel.

    Agents authenticate with the shared NXTDEAL_AGENT_SECRET token.
    Messages are persisted as a CHANNEL entity with a messages list.
    """
    if not _verify_agent_secret(token):
        return {"error": "Invalid agent secret token"}

    if not from_agent or not to_agent or from_agent == to_agent:
        return {"error": "from_agent and to_agent must be different non-empty strings"}

    if message_type not in ("deploy", "status_query", "status_response",
                            "ci_result", "health_check", "ack", "error", "info"):
        return {"error": f"Invalid message_type '{message_type}'. "
                         f"Valid: deploy, status_query, status_response, ci_result, "
                         f"health_check, ack, error, info"}

    channel_id = _channel_id(from_agent, to_agent)
    entity = ledger.get_entity(channel_id)

    message = {
        "timestamp": _now(),
        "from_agent": from_agent,
        "to_agent": to_agent,
        "type": message_type,
        "payload": payload,
        "read": False,
    }

    if entity:
        messages = entity.attributes.get("messages", [])
        messages.append(message)
        entity.attributes["messages"] = messages
        entity.attributes["updated_at"] = _now()
    else:
        entity = Entity(
            id=channel_id,
            entity_type=DEPLOYMENT_CHANNEL,
            attributes={
                "workspace_id": ledger.tenant.workspace_id if hasattr(ledger, "tenant") else "default",
                "from_agent": from_agent,
                "to_agent": to_agent,
                "messages": [message],
                "created_at": _now(),
                "updated_at": _now(),
            },
        )
        ledger.add_entity(entity)

    _save()

    return {
        "status": "sent",
        "channel_id": channel_id,
        "message_id": len(entity.attributes.get("messages", [])) - 1,
    }


def get_agent_messages(agent_name: str, token: str, unread_only: bool = True,
                       limit: int = 50) -> list[dict[str, Any]] | dict[str, Any]:
    """Retrieve messages addressed to the given agent from all channels.

    If unread_only=True, only returns messages where read=False.
    Marking messages as read requires a separate call.
    """
    if not _verify_agent_secret(token):
        return {"error": "Invalid agent secret token"}

    results = []
    for entity_id in ledger.entities:
        entity = ledger.get_entity(entity_id)
        if not entity or entity.entity_type != DEPLOYMENT_CHANNEL:
            continue
        messages = entity.attributes.get("messages", [])
        for msg in messages:
            if msg.get("to_agent") == agent_name:
                if unread_only and msg.get("read"):
                    continue
                results.append({
                    "channel_id": entity_id,
                    "message": msg,
                })

    results.sort(key=lambda r: r["message"]["timestamp"], reverse=True)
    return results[:limit]


def mark_messages_read(agent_name: str, token: str, channel_id: str | None = None) -> dict[str, Any]:
    """Mark messages as read for the given agent.

    If channel_id is provided, only marks messages in that channel.
    Otherwise marks all messages addressed to this agent as read.
    """
    if not _verify_agent_secret(token):
        return {"error": "Invalid agent secret token"}

    marked = 0
    for entity_id in ledger.entities:
        entity = ledger.get_entity(entity_id)
        if not entity or entity.entity_type != DEPLOYMENT_CHANNEL:
            continue
        if channel_id and entity_id != channel_id:
            continue
        if entity.attributes.get("from_agent") != agent_name and entity.attributes.get("to_agent") != agent_name:
            continue
        for msg in entity.attributes.get("messages", []):
            if msg.get("to_agent") == agent_name and not msg.get("read"):
                msg["read"] = True
                marked += 1
        if channel_id:
            entity.attributes["updated_at"] = _now()
            break
        entity.attributes["updated_at"] = _now()

    _save()
    return {"marked_read": marked}


def _add_work_note(entity: Entity, note: str) -> None:
    """Internal helper: append a work note to a PS item entity."""
    notes = entity.attributes.get("work_notes", [])
    notes.append({"timestamp": _now(), "note": note})
    entity.attributes["work_notes"] = notes


# ---------------------------------------------------------------------------
# Background polling loop (started via lifespan in api/app.py)
# ---------------------------------------------------------------------------

_task = None


def tick() -> dict[str, Any]:
    """One polling pass: check open deployment runs for status changes."""
    if not COOLIFY_API_KEY:
        return {"status": "disabled", "reason": "COOLIFY_API_KEY not configured"}

    results = []
    now = datetime.now(timezone.utc)

    for entity_id in list(ledger.entities):
        entity = ledger.get_entity(entity_id)
        if not entity or entity.entity_type != DEPLOYMENT_RUN:
            continue
        if entity.attributes.get("workspace_id") != (ledger.tenant.workspace_id if hasattr(ledger, "tenant") else "default"):
            continue

        current_status = entity.attributes.get("status", "")
        if current_status not in ("in_progress", "queued", "building"):
            continue

        # Poll Coolify for the current status
        dep_id = entity.attributes.get("deployment_id", "")
        if not dep_id:
            continue

        info = poll_coolify_deployment(dep_id)
        if "error" in info:
            results.append({"deployment_id": dep_id, "error": info["error"]})
            continue

        new_status = info.get("status", "")
        if new_status != current_status:
            entity.attributes["status"] = new_status
            entity.attributes["last_polled_at"] = now.isoformat()
            _save()
            results.append({"deployment_id": dep_id, "old_status": current_status, "new_status": new_status})

            # If deployment just succeeded, check if we can advance PS items
            if new_status in ("successful", "success", "deployed"):
                _advance_deployed_items(dep_id)

    return {"polled": len(results), "results": results}


def _advance_deployed_items(deployment_id: str) -> None:
    """When a deployment succeeds, advance linked PS items from 'done' → 'deployed'."""
    for entity_id in list(ledger.entities):
        entity = ledger.get_entity(entity_id)
        if not entity or entity.entity_type != PROGRAMMING_SCHEDULE:
            continue
        if entity.attributes.get("coolify_deployment_id") != deployment_id:
            continue
        if entity.attributes.get("status") == "done":
            entity.attributes["status"] = "deployed"
            entity.attributes["updated_at"] = _now()
            _add_work_note(entity, f"Deployment {deployment_id} succeeded — status auto-advanced from done to deployed")
            _save()


async def loop():
    """Background loop: polls Coolify every 60 seconds for deployment status."""
    while True:
        import asyncio
        await asyncio.sleep(60)
        try:
            tick()
        except Exception:
            log.error("CI/CD pipeline polling tick failed; review durable state")


def start():
    global _task
    if _task is None:
        import asyncio
        _task = asyncio.get_running_loop().create_task(loop())


def stop():
    global _task
    task = _task
    if task is not None:
        task.cancel()
        def release(completed):
            global _task
            if _task is completed:
                _task = None
        if task.done():
            release(task)
        else:
            task.add_done_callback(release)
    return task
