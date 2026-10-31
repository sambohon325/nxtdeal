"""Tests for the VPS orchestrator's pure logic (Section 4).

These tests exercise the testable, side-effect-free logic:
  - assignment window (time-based, 30 min / 45 min intervals)
  - resource overlap detection
  - Mac model naming (local-mac provider is free)
  - _is_free_model accepts provider param

SSH and API calls are not exercised (they require the VPS + Mac to be live).
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("NXTDEAL_AGENT_SECRET", "test-agent-secret")

from core.dealeros import ledger  # noqa: E402
from core.storage_paths import GRAPH_PATH  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_ledger():
    if os.path.exists(GRAPH_PATH):
        os.remove(GRAPH_PATH)
    ledger.reset()
    yield
    if os.path.exists(GRAPH_PATH):
        os.remove(GRAPH_PATH)
    ledger.reset()


@pytest.fixture
def client():
    from api.app import app
    from core.auth import credential_store, issue_token
    credential_store.set_credential("PS-ADMIN", "pass-Word1!", "ADMIN",
                                    must_change_password=False)
    return app


# ---------------------------------------------------------------------------
# Import orchestrator functions (they reference API_BASE, VPS_TOKEN at import)
# ---------------------------------------------------------------------------

@pytest.fixture
def orch():
    """Import the orchestrator module fresh for each test."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "nxtdeal_orchestrator",
        os.path.join(os.path.dirname(__file__), "..", "scripts",
                     "nxtdeal_orchestrator.py")
    )
    mod = importlib.util.module_from_spec(spec)
    # Set test env vars before import — match the orchestrator's env var names.
    # No Windows defaults: the VPS needs these set explicitly.
    os.environ["HERMES_SCHEDULE_TOKEN_vps"] = "test-vps-token"
    os.environ["NXTDEAL_API_BASE"] = "http://test:8000"
    os.environ.setdefault("NXTDEAL_REPO_ROOT", os.path.dirname(os.path.dirname(__file__)))
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Resource overlap
# ---------------------------------------------------------------------------

class TestResourceOverlap:
    def test_no_resources_no_overlap(self, orch):
        assert orch.resources_overlap([], []) is False

    def test_empty_candidate_no_overlap(self, orch):
        running = [{"id": "PS-1", "resources": ["src/api.py"]}]
        assert orch.resources_overlap(running, []) is False

    def test_overlap_detected(self, orch):
        running = [{"id": "PS-1", "resources": ["src/api.py", "src/models.py"]}]
        candidate = ["src/api.py"]
        assert orch.resources_overlap(running, candidate) is True

    def test_no_overlap_different_files(self, orch):
        running = [{"id": "PS-1", "resources": ["src/api.py"]}]
        candidate = ["src/models.py"]
        assert orch.resources_overlap(running, candidate) is False


# ---------------------------------------------------------------------------
# Assignment window
# ---------------------------------------------------------------------------

class TestAssignmentWindow:
    def test_allowed_when_no_marker(self, orch, tmp_path, monkeypatch):
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        assert orch.assignment_allowed() is True

    def test_blocked_within_window(self, orch, tmp_path, monkeypatch):
        """15 min ago is within both 30-min (day) and 45-min (night) windows."""
        marker = tmp_path / "nxtdeal_last_assign"
        marker.write_text("test")
        past = datetime.now(timezone.utc) - timedelta(minutes=15)
        past_ts = past.timestamp()
        os.utime(marker, (past_ts, past_ts))
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        assert orch.assignment_allowed() is False

    def test_allowed_after_window(self, orch, tmp_path, monkeypatch):
        """50 min ago exceeds both 30-min and 45-min windows → always allowed."""
        marker = tmp_path / "nxtdeal_last_assign"
        marker.write_text("test")
        past = datetime.now(timezone.utc) - timedelta(minutes=50)
        past_ts = past.timestamp()
        os.utime(marker, (past_ts, past_ts))
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        assert orch.assignment_allowed() is True


# ---------------------------------------------------------------------------
# _is_free_model (Mac model naming — Review #2 #1)
# ---------------------------------------------------------------------------

class TestIsFreeModel:
    def test_local_mac_provider_is_free(self):
        from api.app import _is_free_model
        assert _is_free_model("local-mac/qwen3.6-35b", "local-mac") is True

    def test_local_mac_model_only_is_free(self):
        from api.app import _is_free_model
        assert _is_free_model("local-mac/qwen3.6-35b") is True

    def test_provider_only_local_mac_is_free(self):
        from api.app import _is_free_model
        assert _is_free_model("qwen3.6-35b", "local-mac") is True

    def test_paid_model_with_paid_provider_not_free(self):
        from api.app import _is_free_model
        assert _is_free_model("gpt-4", "openai") is False

    def test_no_model_is_free(self):
        from api.app import _is_free_model
        assert _is_free_model(None, "local-mac") is True
        assert _is_free_model(None) is True

    def test_free_suffix_is_free(self):
        from api.app import _is_free_model
        assert _is_free_model("poolside/laguna-s-2.1:free") is True
        assert _is_free_model("stepfun/step-5-preview:free") is True


class TestParseJobOutput:
    def test_parses_valid_json(self, orch):
        output = "Some log\nJOB_RESULT: {\"outcome\": \"completed\", \"input_tokens\": 50, \"model\": \"local-mac/qwen3.6-35b\"}\nMore log"
        metrics = orch._parse_job_output(output)
        assert metrics["outcome"] == "completed"
        assert metrics["input_tokens"] == 50
        assert metrics["model"] == "local-mac/qwen3.6-35b"

    def test_no_job_result_line(self, orch):
        output = "Just some log output\nno JSON here"
        metrics = orch._parse_job_output(output)
        assert metrics["input_tokens"] == 0
        assert "outcome" not in metrics

    def test_invalid_json(self, orch):
        output = "JOB_RESULT: {invalid json}"
        metrics = orch._parse_job_output(output)
        assert metrics["input_tokens"] == 0


# ---------------------------------------------------------------------------
# Worker token generation (VPS token exists alongside desktop + mac)
# ---------------------------------------------------------------------------

class TestWorkerTokens:
    @pytest.fixture(autouse=True)
    def _restore_tokens(self):
        """Save and restore module-level token state to prevent pollution."""
        from core.schedule_auth import _save_hashes, _load_hashes
        # Snapshot the token hash store before each test
        original = _load_hashes()
        yield
        # Restore after each test
        _save_hashes(original)

    def test_all_three_workers_have_tokens(self):
        """VPS token must exist alongside desktop and mac."""
        from core.schedule_auth import list_workers, generate_worker_token
        generate_worker_token("desktop")
        generate_worker_token("mac")
        generate_worker_token("vps")
        workers = list_workers()
        assert "desktop" in workers
        assert "mac" in workers
        assert "vps" in workers

    def test_vps_token_verifiable(self):
        """The VPS worker token must be verifiable."""
        from core.schedule_auth import generate_worker_token, verify_worker_token
        token = generate_worker_token("vps")
        assert verify_worker_token(f"Bearer {token}") == "vps"

    def test_vps_token_not_mac_token(self):
        """VPS token must differ from mac token."""
        from core.schedule_auth import generate_worker_token
        vps_token = generate_worker_token("vps")
        mac_token = generate_worker_token("mac")
        assert vps_token != mac_token
