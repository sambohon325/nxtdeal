"""
Tests for the AI Demo Platform backend (core/demo_mode.py + _api.py) and the non-persistence
guarantee (core/storage.demo_persistence_disabled) — 2026-07-24. Run from backend/ with `pytest`.

Covers: personas always listable but `enabled` gated on DEALEROS_DEMO; start_demo REFUSES unless
the tenant is a demo tenant; when enabled it mints a persona session token (valid as a normal
employee token) + a DemoSession; the optional access-code gate; analytics tracking; and the
core guarantee — in a demo tenant save_graph/save_audit_log/save_credentials all no-op so
nothing is written to disk.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core import storage
from core import demo_mode
from core import demo_mode_api as api
from core.auth import verify_token
from core.permissions import SALES


@pytest.fixture(autouse=True)
def fresh_ledger(monkeypatch):
    ledger.reset()
    monkeypatch.delenv("DEALEROS_DEMO", raising=False)
    monkeypatch.delenv("DEMO_ACCESS_CODE", raising=False)
    yield
    ledger.reset()


def _enable_demo(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")


def test_personas_always_listed_enabled_flag_gated():
    out = api.personas_api()
    assert len(out["personas"]) == 15
    assert out["enabled"] is False  # not a demo tenant
    assert any(p["key"] == "sales_manager" for p in out["personas"])


def test_start_demo_refused_off_tenant():
    assert "error" in demo_mode.start_demo("sales_manager")


def test_start_demo_mints_persona_session_and_analytics(monkeypatch):
    _enable_demo(monkeypatch)
    out = demo_mode.start_demo("sales_manager", mode="guided")
    assert "error" not in out
    assert out["role"] == SALES
    assert out["persona"]["key"] == "sales_manager"
    # token is a valid normal employee token so existing dashboards work.
    payload = verify_token(out["token"])
    assert payload and payload["role"] == SALES
    assert payload["employee_id"].startswith("DEMO:")
    # a DemoSession entity was created (in memory; nothing persisted).
    assert demo_mode.get_session(out["session_id"])["persona"] == "sales_manager"


def test_start_demo_unknown_persona_and_access_code(monkeypatch):
    _enable_demo(monkeypatch)
    assert "error" in demo_mode.start_demo("not_a_persona")
    monkeypatch.setenv("DEMO_ACCESS_CODE", "letмein")  # gate on
    assert "error" in demo_mode.start_demo("sales_manager", access_code="wrong")
    assert "error" not in demo_mode.start_demo("sales_manager", access_code="letмein")


def test_track_event_updates_analytics(monkeypatch):
    _enable_demo(monkeypatch)
    sid = demo_mode.start_demo("service_director")["session_id"]
    demo_mode.track_event(sid, "page_view", {"module": "Service"})
    demo_mode.track_event(sid, "page_view", {"module": "Service"})  # same module not double-counted
    demo_mode.track_event(sid, "page_view", {"module": "Inventory"})
    demo_mode.track_event(sid, "question", {"text": "How does DVI work?"})
    snap = demo_mode.get_session(sid)
    assert snap["pages_viewed"] == 3
    assert snap["questions_asked"] == 1
    assert set(snap["modules_visited"]) == {"Service", "Inventory"}
    assert "error" in demo_mode.track_event("DEMO-99999", "page_view")


def test_summarize_session_ranks_interests_and_intent(monkeypatch):
    _enable_demo(monkeypatch)
    sid = demo_mode.start_demo("sales_manager")["session_id"]
    # Simulate exploration: lots of Sales, some Marketing, three questions.
    for _ in range(3):
        demo_mode.track_event(sid, "navigate", {"department": "Sales"})
    demo_mode.track_event(sid, "navigate", {"department": "Marketing"})
    for _ in range(3):
        demo_mode.track_event(sid, "question", {"text": "?"})
    for _ in range(6):
        demo_mode.track_event(sid, "page_view", {"module": "Sales"})

    summary = demo_mode.summarize_session(sid)
    assert summary["interests"][0] == "Sales"          # most-navigated wins
    assert "Marketing" in summary["interests"]
    assert summary["intent"] == "high"                  # 3 questions → high intent
    assert "Sales" in summary["recommendation"]
    assert {c["kind"] for c in summary["ctas"]} == {"book", "network"}


def test_summarize_low_intent_and_unknown_session(monkeypatch):
    _enable_demo(monkeypatch)
    sid = demo_mode.start_demo("salesperson")["session_id"]
    summary = demo_mode.summarize_session(sid)  # no exploration
    assert summary["intent"] == "low"
    assert summary["interests"] == []
    assert "error" in demo_mode.summarize_session("DEMO-99999")


def test_demo_tenant_never_persists(monkeypatch, tmp_path):
    _enable_demo(monkeypatch)
    graph_file = str(tmp_path / "graph.json")
    audit_file = str(tmp_path / "audit.json")
    from core import audit_storage, auth_storage
    storage.save_graph(graph_file)
    audit_storage.save_audit_log(audit_file)
    auth_storage.save_credentials(str(tmp_path / "credentials.json"))
    # Nothing was written — the guarantee.
    assert not os.path.exists(graph_file)
    assert not os.path.exists(audit_file)
    assert not os.path.exists(str(tmp_path / "credentials.json"))


def test_persistence_normal_when_flag_off(tmp_path):
    # Sanity: with the flag off, save_graph writes as usual (no regression to real tenants).
    graph_file = str(tmp_path / "graph.json")
    storage.save_graph(graph_file)
    assert os.path.exists(graph_file)
