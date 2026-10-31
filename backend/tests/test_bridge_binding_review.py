"""Changing scheduling settings cannot silently approve a replacement connector."""
from copy import deepcopy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.routers.dealer_bridge import router, admin
from core import bridge_sync as sync, bridge_runtime as runtime
from core.dealeros import ledger
from tests.test_bridge_sync import configured, state_of, FakeConnector, A, B, API, isolated  # noqa: F401


def changed():
    system,mapping,state,original=configured()
    replacement=FakeConnector()
    runtime.bind(system,replacement,revision="replacement-v2",objects=["customers"],environment="sandbox")
    return system,mapping,state,replacement


def test_disabling_keeps_original_binding_approval_and_blocks_manual_reads():
    system,mapping,state,replacement=changed()
    original=deepcopy(state_of(state))
    result=sync.configure(B,mapping,False,120)
    assert not result["enabled"] and result["interval_seconds"]==120
    assert result["authorized_binding_revision"]==original["authorized_binding_revision"]
    assert result["authorized_environment"]==original["authorized_environment"]
    assert result["availability"]["binding_review_required"]
    with pytest.raises(ValueError,match="not reviewed"):sync.run_once(B,state)
    assert replacement.calls==[]


def test_enabling_changed_binding_requires_explicit_review_and_rolls_back():
    system,mapping,state,replacement=changed()
    before=deepcopy(ledger.entities)
    with pytest.raises(ValueError,match="Explicit review"):sync.configure(B,mapping,True,120)
    assert ledger.entities==before and replacement.calls==[]


def test_exact_review_allows_manual_collection_without_enabling_schedule():
    system,mapping,state,replacement=changed()
    result=sync.configure(B,mapping,False,120,reviewed_binding_revision="replacement-v2",reviewed_binding_environment="sandbox")
    assert not result["enabled"] and not result["availability"]["binding_review_required"]
    assert replacement.calls==[]
    assert sync.run_once(B,state)["status"]=="awaiting_review"


@pytest.mark.parametrize("review",[
    {"reviewed_binding_revision":"replacement-v2"},
    {"reviewed_binding_environment":"sandbox"},
    {"reviewed_binding_revision":"old-v1","reviewed_binding_environment":"sandbox"},
    {"reviewed_binding_revision":"replacement-v2","reviewed_binding_environment":"production"},
])
def test_stale_or_partial_review_does_not_mutate_state(review):
    system,mapping,state,replacement=changed()
    before=deepcopy(ledger.entities)
    with pytest.raises(ValueError,match="configuration changed"):sync.configure(B,mapping,False,120,**review)
    assert ledger.entities==before and replacement.calls==[]


def test_unchanged_connector_can_still_disable_and_enable_normally():
    system,mapping,state,connector=configured()
    assert not sync.configure(B,mapping,False,120)["enabled"]
    assert sync.configure(B,mapping,True,120)["enabled"]
    assert connector.calls==[]


def test_http_review_requires_matching_fields_and_human_authority():
    system,mapping,state,replacement=changed()
    app=FastAPI();app.include_router(router);app.dependency_overrides[admin]=lambda:B
    api=TestClient(app)
    base={"mapping_id":mapping,"enabled":False,"interval_seconds":120}
    assert api.post("/dealer-bridge/sync",json=base).status_code==200
    assert state_of(state)["authorized_binding_revision"]=="test-1"
    reviewed={**base,"reviewed_binding_revision":"replacement-v2","reviewed_binding_environment":"sandbox"}
    assert api.post("/dealer-bridge/sync",json={**reviewed,"reviewed_binding_revision":"stale"}).status_code==400
    app.dependency_overrides[admin]=lambda:API
    assert api.post("/dealer-bridge/sync",json=reviewed).status_code==403
    app.dependency_overrides[admin]=lambda:B
    assert api.post("/dealer-bridge/sync",json=reviewed).status_code==200
    assert not state_of(state)["enabled"] and state_of(state)["authorized_binding_revision"]=="replacement-v2"
