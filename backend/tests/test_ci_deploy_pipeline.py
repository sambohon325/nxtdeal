"""Tests for the CI/CD pipeline integration module (core.ci_deploy_pipeline).

Covers: GitHub webhook signature verification + CI result recording + auto-advance,
Coolify webhook processing + deployment entity creation + auto-advance,
agent channel send/poll/mark-read with token auth, production health verification,
pushed_live marking, and the background tick() function.
"""
import hashlib
import hmac
import json
import os
import sys

# Set test secrets BEFORE importing the module
os.environ["NXTDEAL_GITHUB_WEBHOOK_SECRET"] = "test-gh-secret"
os.environ["NXTDEAL_COOLIFY_WEBHOOK_SECRET"] = "test-coolify-secret"
os.environ["NXTDEAL_AGENT_SECRET"] = "test-agent-secret"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import (
    CI_PIPELINE_RUN,
    DEPLOYMENT_RUN,
    DEPLOYMENT_CHANNEL,
    PROGRAMMING_SCHEDULE,
)
from core import ci_deploy_pipeline as cicd
from core import programming_schedule as ps


def reset():
    ledger.reset()


def _gh_signature(payload: bytes) -> str:
    secret = os.environ["NXTDEAL_GITHUB_WEBHOOK_SECRET"].encode("utf-8")
    sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def _coolify_signature(payload: bytes) -> str:
    secret = os.environ["NXTDEAL_COOLIFY_WEBHOOK_SECRET"].encode("utf-8")
    sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return sig  # Coolify sends without sha256= prefix


def test_github_webhook_invalid_signature():
    """GitHub webhook with wrong signature is rejected."""
    reset()
    payload = json.dumps({"action": "completed", "workflow_run": {"head_sha": "abc123"}}).encode()
    result = cicd.receive_github_webhook(payload, _gh_signature(payload) + "tampered")
    assert "error" in result
    assert "signature" in result["error"].lower()


def test_github_webhook_no_secret_configured():
    """GitHub webhook with no secret configured is rejected."""
    reset()
    old = os.environ.pop("NXTDEAL_GITHUB_WEBHOOK_SECRET", "")
    try:
        cicd.GITHUB_WEBHOOK_SECRET = ""
        payload = json.dumps({"action": "completed"}).encode()
        result = cicd.receive_github_webhook(payload, "sha256=abc")
        assert "error" in result
    finally:
        os.environ["NXTDEAL_GITHUB_WEBHOOK_SECRET"] = old
        cicd.GITHUB_WEBHOOK_SECRET = old


def test_github_webhook_ci_pass_advances_in_review_to_done():
    """CI pass on an in_review item auto-advances to 'done'."""
    reset()
    # Create a PS item in in_review status with a commit SHA
    item = ps.create_item(
        "Test Feature", "desc", item_type="feature", phase="Phase 0",
        est_hours=5, assignee="backend"
    )
    item_id = item["id"]
    ps.set_status(item_id, "in_review")
    ps.update_item(item_id, ci_commit_sha="abc123def456789012345678901234567890abcd")

    # Send GitHub webhook for a successful CI run
    payload = json.dumps({
        "action": "completed",
        "workflow_run": {
            "id": 999,
            "head_sha": "abc123def456789012345678901234567890abcd",
            "name": "CI Pipeline",
            "conclusion": "success",
        }
    }).encode()
    sig = _gh_signature(payload)
    result = cicd.receive_github_webhook(payload, sig)

    assert result["status"] == "processed"
    assert result["conclusion"] == "success"
    assert result["matched_items"] == 1

    # Verify the PS item was advanced to "done"
    updated = ps.get_item(item_id)
    assert updated["status"] == "done"
    assert updated["ci_passed"] == True
    assert updated["ci_ci_id"] == "CI-999"

    # Verify a CIPipelineRun entity was created
    ci_entities = [ledger.get_entity(eid) for eid in ledger.entities if
                   ledger.get_entity(eid) and ledger.get_entity(eid).entity_type == CI_PIPELINE_RUN]
    assert len(ci_entities) == 1
    assert ci_entities[0].attributes["conclusion"] == "success"


def test_github_webhook_ci_fail_does_not_advance():
    """CI failure does not advance status but records the failure note."""
    reset()
    item = ps.create_item(
        "Failing Feature", "desc", item_type="feature", phase="Phase 1",
        est_hours=3, assignee="frontend"
    )
    item_id = item["id"]
    ps.set_status(item_id, "in_review")
    ps.update_item(item_id, ci_commit_sha="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")

    payload = json.dumps({
        "action": "completed",
        "workflow_run": {
            "id": 100,
            "head_sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            "name": "CI Pipeline",
            "conclusion": "failure",
        }
    }).encode()
    result = cicd.receive_github_webhook(payload, _gh_signature(payload))

    assert result["status"] == "processed"
    assert result["conclusion"] == "failure"

    updated = ps.get_item(item_id)
    assert updated["status"] == "in_review"  # not advanced
    assert updated["ci_passed"] == False


def test_github_webhook_ignores_non_completed_action():
    """GitHub webhook with action != 'completed' is ignored."""
    reset()
    payload = json.dumps({
        "action": "requested",
        "workflow_run": {"head_sha": "abc123"}
    }).encode()
    result = cicd.receive_github_webhook(payload, _gh_signature(payload))
    assert result["status"] == "ignored"


def test_coolify_webhook_invalid_signature():
    """Coolify webhook with wrong signature is rejected."""
    reset()
    payload = json.dumps({"deployment_id": "dep123", "status": "successful"}).encode()
    result = cicd.receive_coolify_webhook(payload, "wrong-signature")
    assert "error" in result


def test_coolify_webhook_no_secret():
    """Coolify webhook with no secret is rejected."""
    reset()
    old = os.environ.pop("NXTDEAL_COOLIFY_WEBHOOK_SECRET", "")
    try:
        cicd.COOLIFY_WEBHOOK_SECRET = ""
        payload = json.dumps({"deployment_id": "dep123"}).encode()
        result = cicd.receive_coolify_webhook(payload, "abc")
        assert "error" in result
    finally:
        os.environ["NXTDEAL_COOLIFY_WEBHOOK_SECRET"] = old
        cicd.COOLIFY_WEBHOOK_SECRET = old


def test_coolify_webhook_advances_done_to_deployed():
    """Coolify deployment success auto-advances a 'done' PS item to 'deployed'."""
    reset()
    item = ps.create_item(
        "Deployable Item", "desc", item_type="feature", phase="Phase 2",
        est_hours=8, assignee="backend"
    )
    item_id = item["id"]
    ps.set_status(item_id, "done")
    # Set the coolify_deployment_id on the item
    ps.update_item(item_id, coolify_deployment_id="coolify-dep-abc123")

    payload = json.dumps({
        "deployment_id": "coolify-dep-abc123",
        "status": "successful",
        "application": {"name": "nxtdeal-app"},
        "commit_sha": "f00b4rf00b4rf00b4rf00b4rf00b4rf00b4rf00b",
        "finished_at": "2026-10-25T12:00:00Z",
    }).encode()
    result = cicd.receive_coolify_webhook(payload, _coolify_signature(payload))

    assert result["status"] == "processed"
    assert result["deployment_status"] == "successful"

    updated = ps.get_item(item_id)
    assert updated["status"] == "deployed"
    assert updated["deployment_run_id"] == result["deployment_id"]
    assert updated["coolify_deployment_id"] == "coolify-dep-abc123"

    # Verify DeploymentRun entity was created
    dep_entities = [ledger.get_entity(eid) for eid in ledger.entities if
                    ledger.get_entity(eid) and ledger.get_entity(eid).entity_type == DEPLOYMENT_RUN]
    assert len(dep_entities) == 1


def test_coolify_webhook_failed_does_not_advance():
    """Coolify deployment failure does not advance status."""
    reset()
    item = ps.create_item("Fail Deploy", "", item_type="feature", phase="Phase 3", est_hours=4)
    item_id = item["id"]
    ps.set_status(item_id, "done")
    ps.update_item(item_id, coolify_deployment_id="dep-fail")

    payload = json.dumps({"deployment_id": "dep-fail", "status": "failed"}).encode()
    result = cicd.receive_coolify_webhook(payload, _coolify_signature(payload))

    assert result["status"] == "processed"
    assert result["deployment_status"] == "failed"
    assert ps.get_item(item_id)["status"] == "done"  # not advanced


def test_agent_channel_invalid_token():
    """Agent messages with wrong token are rejected."""
    reset()
    result = cicd.send_agent_message("desktop", "vps", "status_query", {"q": 1}, "wrong-token")
    assert "error" in result
    assert "token" in result["error"].lower()

    result = cicd.get_agent_messages("vps", "wrong-token")
    assert "error" in result


def test_agent_channel_send_and_retrieve():
    """Agents can send and retrieve messages."""
    reset()
    token = os.environ["NXTDEAL_AGENT_SECRET"]

    result = cicd.send_agent_message("desktop", "vps", "deploy", {"item_id": "PS-test"}, token)
    assert result["status"] == "sent"
    assert result["channel_id"].startswith("CH-")

    # VPS agent retrieves messages addressed to it
    messages = cicd.get_agent_messages("vps", token, unread_only=True)
    assert len(messages) == 1
    msg = messages[0]["message"]
    assert msg["from_agent"] == "desktop"
    assert msg["to_agent"] == "vps"
    assert msg["type"] == "deploy"
    assert msg["payload"]["item_id"] == "PS-test"
    assert msg["read"] == False

    # Mark as read
    read_result = cicd.mark_messages_read("vps", token)
    assert read_result["marked_read"] == 1

    # Verify no unread messages now
    messages = cicd.get_agent_messages("vps", token, unread_only=True)
    assert len(messages) == 0


def test_agent_channel_self_message_rejected():
    """An agent cannot send a message to itself."""
    reset()
    token = os.environ["NXTDEAL_AGENT_SECRET"]
    result = cicd.send_agent_message("desktop", "desktop", "info", {}, token)
    assert "error" in result


def test_agent_channel_invalid_message_type():
    """Invalid message_type is rejected."""
    reset()
    token = os.environ["NXTDEAL_AGENT_SECRET"]
    result = cicd.send_agent_message("desktop", "vps", "malicious_command", {}, token)
    assert "error" in result


def test_verify_production_health_no_deployment_id():
    """Health check on item without deployment ID returns error."""
    reset()
    item = ps.create_item("No Deploy", "", item_type="feature", phase="Phase 0")
    item_id = item["id"]
    result = cicd.verify_production_health(item_id)
    assert "error" in result


def test_verify_production_health_item_not_found():
    """Health check on non-existent item returns error."""
    reset()
    result = cicd.verify_production_health("PS-nonexistent")
    assert "error" in result


def test_mark_pushed_live_requires_deployed_status():
    """Items not in 'deployed' status cannot be marked pushed_live."""
    reset()
    item = ps.create_item("Not Deployed", "", item_type="feature", phase="Phase 4")
    item_id = item["id"]
    ps.set_status(item_id, "done")
    result = cicd.mark_pushed_live(item_id)
    assert "error" in result
    assert "deployed" in result["error"].lower()


def test_mark_pushed_live_advances():
    """A 'deployed' item can be marked pushed_live."""
    reset()
    item = ps.create_item("Going Live", "", item_type="feature", phase="Phase 5")
    item_id = item["id"]
    ps.set_status(item_id, "done")
    ps.update_item(item_id, coolify_deployment_id="dep-live")
    ps.set_status(item_id, "deployed")

    result = cicd.mark_pushed_live(item_id, verified_by="vps-agent")
    assert "id" in result
    assert ps.get_item(item_id)["status"] == "pushed_live"
    assert ps.get_item(item_id)["pushed_live_at"] is not None
    assert ps.get_item(item_id)["pushed_live_by"] == "vps-agent"


def test_tick_disabled_without_api_key():
    """tick() returns disabled status when Coolify API key is not configured."""
    reset()
    old = os.environ.pop("NXTDEAL_COOLIFY_API_KEY", "")
    try:
        cicd.COOLIFY_API_KEY = ""
        result = cicd.tick()
        assert result["status"] == "disabled"
    finally:
        os.environ["NXTDEAL_COOLIFY_API_KEY"] = old


def test_dashboard_includes_deployed_and_pushed_live():
    """Dashboard counts 'deployed' and 'pushed_live' as completed."""
    reset()
    ps.create_item("Item A", "", item_type="feature", phase="Phase 0", est_hours=10)
    ps.create_item("Item B", "", item_type="bug", phase="Phase 1", est_hours=20)
    ps.create_item("Item C", "", item_type="security", phase="Phase 2", est_hours=5, security_severity="high")

    item_a = ps.get_item("PS-item-a")
    item_b = ps.get_item("PS-item-b")
    item_c = ps.get_item("PS-item-c")

    ps.set_status(item_a["id"], "deployed")
    ps.set_status(item_b["id"], "pushed_live")

    dash = ps.get_dashboard()
    assert dash["completed"] == 2  # deployed + pushed_live
    assert dash["deployed"] == 1
    assert dash["pushed_live"] == 1
    assert dash["remaining_hours"] == 5.0  # only item_c has est_hours=5, not completed
    assert dash["security_issues"] == 1


if __name__ == "__main__":
    reset()
    test_github_webhook_invalid_signature(); print("test_github_webhook_invalid_signature: PASS")
    reset()
    test_github_webhook_no_secret_configured(); print("test_github_webhook_no_secret_configured: PASS")
    reset()
    test_github_webhook_ci_pass_advances_in_review_to_done(); print("test_github_webhook_ci_pass_advances_in_review_to_done: PASS")
    reset()
    test_github_webhook_ci_fail_does_not_advance(); print("test_github_webhook_ci_fail_does_not_advance: PASS")
    reset()
    test_github_webhook_ignores_non_completed_action(); print("test_github_webhook_ignores_non_completed_action: PASS")
    reset()
    test_coolify_webhook_invalid_signature(); print("test_coolify_webhook_invalid_signature: PASS")
    reset()
    test_coolify_webhook_no_secret(); print("test_coolify_webhook_no_secret: PASS")
    reset()
    test_coolify_webhook_advances_done_to_deployed(); print("test_coolify_webhook_advances_done_to_deployed: PASS")
    reset()
    test_coolify_webhook_failed_does_not_advance(); print("test_coolify_webhook_failed_does_not_advance: PASS")
    reset()
    test_agent_channel_invalid_token(); print("test_agent_channel_invalid_token: PASS")
    reset()
    test_agent_channel_send_and_retrieve(); print("test_agent_channel_send_and_retrieve: PASS")
    reset()
    test_agent_channel_self_message_rejected(); print("test_agent_channel_self_message_rejected: PASS")
    reset()
    test_agent_channel_invalid_message_type(); print("test_agent_channel_invalid_message_type: PASS")
    reset()
    test_verify_production_health_no_deployment_id(); print("test_verify_production_health_no_deployment_id: PASS")
    reset()
    test_verify_production_health_item_not_found(); print("test_verify_production_health_item_not_found: PASS")
    reset()
    test_mark_pushed_live_requires_deployed_status(); print("test_mark_pushed_live_requires_deployed_status: PASS")
    reset()
    test_mark_pushed_live_advances(); print("test_mark_pushed_live_advances: PASS")
    reset()
    test_tick_disabled_without_api_key(); print("test_tick_disabled_without_api_key: PASS")
    reset()
    test_dashboard_includes_deployed_and_pushed_live(); print("test_dashboard_includes_deployed_and_pushed_live: PASS")
    print("\nAll CI/CD pipeline tests passed (18/18)")
