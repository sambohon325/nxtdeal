"""
Tests for the NXTDeal Hub's AI Kill Switch emergency-response console
(hub_core/dealer_ai_kill_switch.py / dealer_ai_kill_switch_api.py /
dealer_ai_kill_switch_storage.py) -- security-hardening pass Task #6
("Expand AI kill switch to dealer/department/bot/workflow scope").

Run from hub/ with `pytest` (or `pytest tests/test_hub_ai_kill_switch.py`),
same as every other Hub test file.

Regression coverage for a real bug found and fixed while this feature was
being built and live-verified: DealerKillSwitchAction.to_dict() originally
had a field literally named "error" -- colliding with hub/app.py's
codebase-wide `if "error" in result: raise HTTPException(...)` convention,
which treats ANY dict containing an "error" key as a hard API-layer
failure. That meant a real, successfully-created action record describing
"push attempted but the dealer was unreachable" was misinterpreted by the
route layer as if the whole call had failed, returning HTTP 400 instead of
200 with success=False embedded in the body. Fixed by renaming the field
to "push_error" (see dealer_ai_kill_switch.py's own dataclass comment for
the full explanation and the identical prior bug this mirrors in
hub_core/dealer_ai_management.py, fixed there the same way). The tests
below deliberately assert on the CURRENT field name and on the absence of
a top-level "error" key in a failed-push API response, so a future
regression of this exact bug would fail loudly here rather than only being
caught by manual smoke testing again.

The two functions in dealer_ai_kill_switch.py that do real outbound HTTP
(_fetch_kill_switch_status / _push_kill_switch) are monkeypatched directly
in the tests that exercise a "reachable" dealer, rather than spinning up a
real socket -- the validation/persistence/response-shape logic under test
here doesn't depend on real network I/O, and this keeps the suite fast and
deterministic. The live, real end-to-end HTTP round trip (including a real
in-process mock tenant server) was already exercised manually during this
feature's own build -- see BUILD_QUEUE.md's Task #6 entry for that
verification.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_HUB_DIR = os.path.dirname(_HERE)

if _HUB_DIR not in sys.path:
    sys.path.insert(0, _HUB_DIR)

import pytest

from hub_core.dealer import Dealer
from hub_core.dealer_registry import registry as dealer_registry
from hub_core import dealer_ai_kill_switch as kill_switch
from hub_core.dealer_ai_kill_switch import DealerKillSwitchAction, VALID_PUSH_SCOPES
from hub_core import dealer_ai_kill_switch_api as kill_switch_api
from hub_core.dealer_ai_kill_switch_storage import (
    save_dealer_ai_kill_switch_actions,
    load_dealer_ai_kill_switch_actions,
    _recover_partial_array,
)
from hub_core.hub_audit import hub_audit_log
from hub_core import hub_audit_api


@pytest.fixture(autouse=True)
def fresh_state(tmp_path, monkeypatch):
    """Reset every singleton this module touches (the dealer registry, the
    kill-switch action registry, and the Hub's own centralized audit log --
    every real push also writes there) and redirect every disk write into a
    per-test tmp dir, matching test_hub_provisioning.py's own fresh_registry
    fixture discipline so no test ever touches the real
    hub/storage/dealer_ai_kill_switch_actions.json or hub/storage/
    hub_audit.json."""

    dealer_registry.reset()
    kill_switch.registry.reset()
    hub_audit_log.reset()

    monkeypatch.setattr(
        kill_switch_api,
        "DEALER_AI_KILL_SWITCH_ACTIONS_PATH",
        str(tmp_path / "dealer_ai_kill_switch_actions.json"),
    )
    monkeypatch.setattr(
        hub_audit_api, "HUB_AUDIT_LOG_PATH", str(tmp_path / "hub_audit.json")
    )

    yield

    dealer_registry.reset()
    kill_switch.registry.reset()
    hub_audit_log.reset()


def _add_dealer(dealer_id="DLR-00001", api_base_url=None):
    dealer = Dealer.from_dict({
        "dealer_id": dealer_id,
        "slug": dealer_id.lower().replace("dlr-", "dealer"),
        "name": f"Dealer {dealer_id}",
        "contact_email": "owner@example.com",
        "storage_dir": f"storage/tenants/{dealer_id}",
        "api_base_url": api_base_url,
        "created_by": "nxtdeal_staff",
    })
    dealer_registry.add(dealer)
    return dealer


# --------------------------------------------------------------------------------------
# DealerKillSwitchAction dataclass -- field-name regression coverage
# --------------------------------------------------------------------------------------

def test_action_to_dict_uses_push_error_not_error():
    """The specific regression this whole file exists to guard against: the
    serialized dict must carry "push_error", and must NEVER carry a bare
    "error" key -- that key name is reserved, codebase-wide on the Hub, for
    "the whole API call failed."""
    action = DealerKillSwitchAction(
        action_id="AIKS-00001",
        dealer_id="DLR-00001",
        pushed_by="staffer@nxtdeal.example",
        scope="dealer_wide",
        active=False,
        success=False,
        push_error="unreachable: timed out",
    )
    as_dict = action.to_dict()
    assert as_dict["push_error"] == "unreachable: timed out"
    assert "error" not in as_dict


def test_action_to_dict_from_dict_roundtrip():
    action = DealerKillSwitchAction(
        action_id="AIKS-00002",
        dealer_id="DLR-00002",
        pushed_by="staffer@nxtdeal.example",
        scope="department",
        active=True,
        reason="suspected prompt-injection incident",
        department="sales",
        success=True,
        push_error=None,
        resulting_state={"active": True, "scope": "department"},
    )
    restored = DealerKillSwitchAction.from_dict(action.to_dict())
    assert restored == action


def test_action_from_dict_defaults_missing_optional_fields():
    """An old/partial record missing every optional key still loads cleanly."""
    restored = DealerKillSwitchAction.from_dict({
        "action_id": "AIKS-00003",
        "dealer_id": "DLR-00003",
        "scope": "bot",
    })
    assert restored.pushed_by == "nxtdeal_staff"
    assert restored.active is False
    assert restored.success is False
    assert restored.push_error is None
    assert restored.resulting_state is None


# --------------------------------------------------------------------------------------
# DealerKillSwitchActionRegistry
# --------------------------------------------------------------------------------------

def test_registry_next_id_sequence():
    registry = kill_switch.DealerKillSwitchActionRegistry()
    assert registry.next_id() == "AIKS-00001"
    assert registry.next_id() == "AIKS-00002"


def test_registry_list_for_dealer_and_list_all_sorted_newest_first():
    registry = kill_switch.DealerKillSwitchActionRegistry()
    older = DealerKillSwitchAction(
        action_id="AIKS-00001", dealer_id="DLR-00001", pushed_by="a",
        scope="dealer_wide", active=False, pushed_at="2026-01-01T00:00:00+00:00",
    )
    newer_same_dealer = DealerKillSwitchAction(
        action_id="AIKS-00002", dealer_id="DLR-00001", pushed_by="a",
        scope="dealer_wide", active=True, pushed_at="2026-01-02T00:00:00+00:00",
    )
    other_dealer = DealerKillSwitchAction(
        action_id="AIKS-00003", dealer_id="DLR-00002", pushed_by="a",
        scope="dealer_wide", active=True, pushed_at="2026-01-03T00:00:00+00:00",
    )
    registry.add(older)
    registry.add(newer_same_dealer)
    registry.add(other_dealer)

    for_d1 = registry.list_for_dealer("DLR-00001")
    assert [a.action_id for a in for_d1] == ["AIKS-00002", "AIKS-00001"]

    all_actions = registry.list_all()
    assert [a.action_id for a in all_actions] == ["AIKS-00003", "AIKS-00002", "AIKS-00001"]


def test_registry_recover_counter_never_reissues_an_existing_id():
    registry = kill_switch.DealerKillSwitchActionRegistry()
    registry.add(DealerKillSwitchAction(
        action_id="AIKS-00007", dealer_id="DLR-00001", pushed_by="a",
        scope="dealer_wide", active=False,
    ))
    registry.recover_counter()
    assert registry.next_id() == "AIKS-00008"


# --------------------------------------------------------------------------------------
# get_dealer_kill_switch_status -- always a live fetch, never cached
# --------------------------------------------------------------------------------------

def test_get_status_unknown_dealer():
    result, error = kill_switch.get_dealer_kill_switch_status("DLR-99999")
    assert result is None
    assert "no dealer with id" in error


def test_get_status_dealer_with_no_api_base_url_is_honestly_unreachable():
    _add_dealer("DLR-00001", api_base_url=None)
    result, error = kill_switch.get_dealer_kill_switch_status("DLR-00001")
    assert error is None
    assert result["reachable"] is False
    assert "not yet deployed" in result["fetch_error"]
    assert result["state"] is None


def test_get_status_reachable_dealer_returns_real_state(monkeypatch):
    _add_dealer("DLR-00001", api_base_url="http://dealer1-api.example")

    monkeypatch.setattr(
        kill_switch, "_fetch_kill_switch_status",
        lambda dealer: ({"active": False, "scope": "dealer_wide"}, None),
    )

    result, error = kill_switch.get_dealer_kill_switch_status("DLR-00001")
    assert error is None
    assert result["reachable"] is True
    assert result["fetch_error"] is None
    assert result["state"] == {"active": False, "scope": "dealer_wide"}


# --------------------------------------------------------------------------------------
# push_kill_switch_to_dealer -- validation, and "always persist a real record"
# --------------------------------------------------------------------------------------

def test_push_unknown_dealer():
    action, error = kill_switch.push_kill_switch_to_dealer(
        "DLR-99999", "staffer", "dealer_wide", True
    )
    assert action is None
    assert "no dealer with id" in error


def test_push_requires_pushed_by():
    _add_dealer("DLR-00001")
    action, error = kill_switch.push_kill_switch_to_dealer(
        "DLR-00001", "   ", "dealer_wide", True
    )
    assert action is None
    assert "pushed_by is required" in error


def test_push_rejects_unknown_scope():
    _add_dealer("DLR-00001")
    action, error = kill_switch.push_kill_switch_to_dealer(
        "DLR-00001", "staffer", "not_a_real_scope", True
    )
    assert action is None
    assert "Unknown kill-switch scope" in error


def test_push_department_scope_requires_department():
    _add_dealer("DLR-00001")
    action, error = kill_switch.push_kill_switch_to_dealer(
        "DLR-00001", "staffer", "department", True, department=None
    )
    assert action is None
    assert "A department is required" in error


def test_all_valid_scopes_are_exactly_the_four_named_in_the_task():
    assert set(VALID_PUSH_SCOPES) == {"dealer_wide", "department", "bot", "workflow_automation"}


def test_push_unreachable_dealer_still_creates_a_real_persisted_failed_record():
    """The core design point of this whole module: a failed push is not a
    dropped request, it's a real, permanent DealerKillSwitchAction with
    success=False. dealer has no api_base_url on file, so the real
    _push_kill_switch codepath itself reports the honest reason -- no
    monkeypatch needed for this one."""
    _add_dealer("DLR-00001", api_base_url=None)

    action, error = kill_switch.push_kill_switch_to_dealer(
        "DLR-00001", "staffer@nxtdeal.example", "dealer_wide", True,
        reason="suspected incident",
    )
    assert error is None
    assert action.success is False
    assert "not yet deployed" in action.push_error
    assert action.resulting_state is None
    assert action.action_id == "AIKS-00001"

    # and it is really in the registry, not just returned transiently
    persisted = kill_switch.registry.list_for_dealer("DLR-00001")
    assert len(persisted) == 1
    assert persisted[0].action_id == action.action_id


def test_push_success_records_resulting_state(monkeypatch):
    _add_dealer("DLR-00001", api_base_url="http://dealer1-api.example")

    monkeypatch.setattr(
        kill_switch, "_push_kill_switch",
        lambda dealer, scope, active, reason, department: (
            {"state": {"active": True, "scope": "bot", "department": None}}, None
        ),
    )

    action, error = kill_switch.push_kill_switch_to_dealer(
        "DLR-00001", "staffer@nxtdeal.example", "bot", True, reason="lockdown",
    )
    assert error is None
    assert action.success is True
    assert action.push_error is None
    assert action.resulting_state == {"active": True, "scope": "bot", "department": None}


def test_push_reason_and_blank_reason_are_both_handled():
    _add_dealer("DLR-00001", api_base_url=None)
    action, _ = kill_switch.push_kill_switch_to_dealer(
        "DLR-00001", "staffer", "dealer_wide", False, reason="   "
    )
    # a blank/whitespace-only reason is normalized to None, not stored as "   "
    assert action.reason is None


# --------------------------------------------------------------------------------------
# list_kill_switch_actions_for_dealer / list_all_kill_switch_actions
# --------------------------------------------------------------------------------------

def test_list_actions_for_unknown_dealer():
    result, error = kill_switch.list_kill_switch_actions_for_dealer("DLR-99999")
    assert result is None
    assert "no dealer with id" in error


def test_list_actions_for_dealer_and_list_all_summary():
    _add_dealer("DLR-00001", api_base_url=None)
    kill_switch.push_kill_switch_to_dealer("DLR-00001", "a", "dealer_wide", True)
    kill_switch.push_kill_switch_to_dealer("DLR-00001", "a", "bot", False)

    for_dealer, error = kill_switch.list_kill_switch_actions_for_dealer("DLR-00001")
    assert error is None
    assert for_dealer["dealer_name"] == "Dealer DLR-00001"
    assert len(for_dealer["actions"]) == 2

    everything = kill_switch.list_all_kill_switch_actions()
    assert everything["summary"]["total_actions"] == 2
    assert everything["summary"]["successful_pushes"] == 0
    assert everything["summary"]["failed_pushes"] == 2
    # dealer_name is enriched onto each action for the cross-dealer view
    assert everything["actions"][0]["dealer_name"] == "Dealer DLR-00001"


# --------------------------------------------------------------------------------------
# dealer_ai_kill_switch_api -- response shaping, error passthrough, and the
# specific regression this file was written to catch
# --------------------------------------------------------------------------------------

def test_get_status_api_passes_through_unknown_dealer_error():
    result = kill_switch_api.get_dealer_kill_switch_status_api("DLR-99999")
    assert result == {"error": "no dealer with id 'DLR-99999'"}


def test_push_api_validation_error_response_shape():
    _add_dealer("DLR-00001")
    result = kill_switch_api.push_dealer_kill_switch_api(
        "DLR-00001", pushed_by="staffer", scope="bogus_scope", active=True,
    )
    assert "error" in result
    assert "Unknown kill-switch scope" in result["error"]
    # a real validation failure must not have persisted anything
    assert not os.path.exists(kill_switch_api.DEALER_AI_KILL_SWITCH_ACTIONS_PATH)


def test_push_api_failed_push_response_has_no_top_level_error_key():
    """THE regression test. A dealer with no api_base_url produces a real,
    successfully-created action record with success=False -- this must come
    back through the API layer WITHOUT a top-level "error" key, or
    hub/app.py's `if "error" in result: raise HTTPException(...)` check
    would wrongly turn a real 200 into a 400."""
    _add_dealer("DLR-00001", api_base_url=None)

    result = kill_switch_api.push_dealer_kill_switch_api(
        "DLR-00001", pushed_by="staffer@nxtdeal.example", scope="dealer_wide",
        active=True, reason="incident",
    )

    assert "error" not in result
    assert result["success"] is False
    assert "not yet deployed" in result["push_error"]
    assert result["action_id"] == "AIKS-00001"

    # and it really persisted to the (monkeypatched) actions file...
    assert os.path.exists(kill_switch_api.DEALER_AI_KILL_SWITCH_ACTIONS_PATH)
    # ...and really recorded a Hub audit event, whether the push succeeded or not
    events = hub_audit_log.get_all()
    assert len(events) == 1
    assert events[0].event_type == "ai_kill_switch_pushed"
    assert events[0].to_dict()["category"] == "other"
    assert "FAILED" in events[0].summary


def test_push_api_success_response_shape(monkeypatch):
    _add_dealer("DLR-00001", api_base_url="http://dealer1-api.example")
    monkeypatch.setattr(
        kill_switch, "_push_kill_switch",
        lambda dealer, scope, active, reason, department: (
            {"state": {"active": False}}, None
        ),
    )

    result = kill_switch_api.push_dealer_kill_switch_api(
        "DLR-00001", pushed_by="staffer", scope="workflow_automation",
        active=False,
    )
    assert "error" not in result
    assert result["success"] is True
    assert result["push_error"] is None
    assert result["resulting_state"] == {"active": False}

    events = hub_audit_log.get_all()
    assert len(events) == 1
    assert "succeeded" in events[0].summary


def test_get_dealer_history_api_and_all_history_api():
    _add_dealer("DLR-00001", api_base_url=None)
    kill_switch_api.push_dealer_kill_switch_api(
        "DLR-00001", pushed_by="a", scope="dealer_wide", active=True,
    )

    dealer_history = kill_switch_api.get_dealer_kill_switch_history_api("DLR-00001")
    assert len(dealer_history["actions"]) == 1

    assert kill_switch_api.get_dealer_kill_switch_history_api("DLR-99999") == {
        "error": "no dealer with id 'DLR-99999'"
    }

    everything = kill_switch_api.get_all_kill_switch_history_api()
    assert everything["summary"]["total_actions"] == 1


# --------------------------------------------------------------------------------------
# dealer_ai_kill_switch_storage -- atomic save + truncation-tolerant load
# --------------------------------------------------------------------------------------

def test_save_and_load_roundtrip_recovers_counter(tmp_path):
    _add_dealer("DLR-00001", api_base_url=None)
    kill_switch.push_kill_switch_to_dealer("DLR-00001", "a", "dealer_wide", True)
    kill_switch.push_kill_switch_to_dealer("DLR-00001", "a", "bot", False)

    path = str(tmp_path / "actions.json")
    save_dealer_ai_kill_switch_actions(path)

    kill_switch.registry.reset()
    assert kill_switch.registry.list_all() == []

    load_dealer_ai_kill_switch_actions(path)
    ids = [a.action_id for a in kill_switch.registry.list_all()]
    assert set(ids) == {"AIKS-00001", "AIKS-00002"}

    # the id generator must be recovered so a subsequent push doesn't collide
    action, _ = kill_switch.push_kill_switch_to_dealer("DLR-00001", "a", "bot", True)
    assert action.action_id == "AIKS-00003"


def test_load_missing_file_is_a_noop(tmp_path):
    load_dealer_ai_kill_switch_actions(str(tmp_path / "does-not-exist.json"))
    assert kill_switch.registry.list_all() == []


def test_recover_partial_array_salvages_truncated_file(tmp_path):
    _add_dealer("DLR-00001", api_base_url=None)
    kill_switch.push_kill_switch_to_dealer("DLR-00001", "a", "dealer_wide", True)
    kill_switch.push_kill_switch_to_dealer("DLR-00001", "a", "bot", False)
    kill_switch.push_kill_switch_to_dealer("DLR-00001", "a", "workflow_automation", True)

    path = str(tmp_path / "actions.json")
    save_dealer_ai_kill_switch_actions(path)

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    third = text.rindex("{")
    truncated = text[: third + 20]
    with open(path, "w", encoding="utf-8") as f:
        f.write(truncated)

    kill_switch.registry.reset()
    load_dealer_ai_kill_switch_actions(path)
    ids = [a.action_id for a in kill_switch.registry.list_all()]
    assert len(ids) == 2


def test_recover_partial_array_returns_empty_on_hopeless_input():
    assert _recover_partial_array("not json at all") == []
    assert _recover_partial_array("") == []
