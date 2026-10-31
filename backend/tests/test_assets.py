"""
Tests for the marketing asset design/approval workflow (core/assets.py,
core/assets_api.py) -- session 30. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger
from core import assets
from core import assets_api
from core.permissions import ADMIN, MARKETING, SALES, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()

    yield

    ledger.reset()


@pytest.fixture(autouse=True)
def no_real_audit_writes(monkeypatch):
    """approve/reject write an audit event + save_audit_log("storage/audit.json") --
    stub the save so tests never touch the real file, same precaution
    tests/test_auth.py already documents for auth_api's save_credentials calls."""

    monkeypatch.setattr(assets_api, "save_audit_log", lambda filepath: None)


# --- Templates ---


def test_list_templates_returns_five_starter_templates():

    templates = assets.list_templates()

    assert {t["key"] for t in templates} == {
        "inventory_flyer",
        "social_post",
        "sold_announcement",
        "service_special",
        "finance_offer",
    }


def test_get_template_unknown_key_returns_none():

    assert assets.get_template("not-a-real-template") is None


# --- Create / submit lifecycle ---


def test_create_asset_starts_as_draft():

    result = assets_api.create_asset_api(
        "EMP-00001", "social_post", {"headline": "Big Sale", "body": "Come on down"}
    )

    assert "error" not in result
    assert result["status"] == "draft"
    assert result["requested_by"] == "EMP-00001"


def test_create_asset_rejects_unknown_template():

    result = assets_api.create_asset_api("EMP-00001", "not-a-template", {})

    assert "error" in result


def test_create_asset_rejects_missing_required_field():

    result = assets_api.create_asset_api("EMP-00001", "social_post", {"body": "no headline"})

    assert "error" in result
    assert "headline" in result["error"]


def test_submit_requires_being_the_requester():

    created = assets_api.create_asset_api(
        "EMP-00001", "social_post", {"headline": "Big Sale", "body": "Come on down"}
    )

    denied = assets_api.submit_asset_api(SALES, "EMP-00002", created["id"])
    assert "error" in denied

    allowed = assets_api.submit_asset_api(SALES, "EMP-00001", created["id"])
    assert allowed["status"] == "pending_approval"


def test_submit_allowed_for_admin_regardless_of_requester():

    created = assets_api.create_asset_api(
        "EMP-00001", "social_post", {"headline": "Big Sale", "body": "Come on down"}
    )

    result = assets_api.submit_asset_api(ADMIN, "EMP-99999", created["id"])

    assert result["status"] == "pending_approval"


def test_submit_unknown_asset():

    result = assets_api.submit_asset_api(SALES, "EMP-00001", "ASSET-99999")

    assert "error" in result


def test_cannot_resubmit_a_non_draft_asset():

    created = assets_api.create_asset_api(
        "EMP-00001", "social_post", {"headline": "Big Sale", "body": "Come on down"}
    )
    assets_api.submit_asset_api(SALES, "EMP-00001", created["id"])

    result = assets_api.submit_asset_api(SALES, "EMP-00001", created["id"])

    assert "error" in result


# --- Approval queue ACL ---


def test_pending_approvals_denied_for_non_marketing_non_admin():

    result = assets_api.list_pending_approvals_api(SALES)

    assert "error" in result


def test_pending_approvals_allowed_for_marketing_and_admin():

    created = assets_api.create_asset_api(
        "EMP-00001", "social_post", {"headline": "Big Sale", "body": "Come on down"}
    )
    assets_api.submit_asset_api(SALES, "EMP-00001", created["id"])

    for role in (MARKETING, ADMIN):
        result = assets_api.list_pending_approvals_api(role)
        assert isinstance(result, list)
        assert any(a["id"] == created["id"] for a in result)


def test_approve_denied_for_non_marketing_non_admin():

    created = assets_api.create_asset_api(
        "EMP-00001", "social_post", {"headline": "Big Sale", "body": "Come on down"}
    )
    assets_api.submit_asset_api(SALES, "EMP-00001", created["id"])

    result = assets_api.approve_asset_api(SERVICE, "EMP-00002", created["id"])

    assert "error" in result


def test_approve_requires_pending_status():

    created = assets_api.create_asset_api(
        "EMP-00001", "social_post", {"headline": "Big Sale", "body": "Come on down"}
    )
    # still a draft -- never submitted

    result = assets_api.approve_asset_api(MARKETING, "EMP-00002", created["id"])

    assert "error" in result


def test_approve_success_records_reviewer_and_notes():

    created = assets_api.create_asset_api(
        "EMP-00001", "social_post", {"headline": "Big Sale", "body": "Come on down"}
    )
    assets_api.submit_asset_api(SALES, "EMP-00001", created["id"])

    result = assets_api.approve_asset_api(MARKETING, "EMP-00002", created["id"], "Looks great")

    assert result["status"] == "approved"
    assert result["reviewed_by"] == "EMP-00002"
    assert result["review_notes"] == "Looks great"


def test_reject_success_records_reviewer_and_notes():

    created = assets_api.create_asset_api(
        "EMP-00001", "social_post", {"headline": "Big Sale", "body": "Come on down"}
    )
    assets_api.submit_asset_api(SALES, "EMP-00001", created["id"])

    result = assets_api.reject_asset_api(ADMIN, "EMP-00003", created["id"], "Wrong logo")

    assert result["status"] == "rejected"
    assert result["reviewed_by"] == "EMP-00003"
    assert result["review_notes"] == "Wrong logo"


# --- Visibility ---


def test_get_asset_visible_to_requester():

    created = assets_api.create_asset_api(
        "EMP-00001", "social_post", {"headline": "Big Sale", "body": "Come on down"}
    )

    result = assets_api.get_asset_api(SALES, "EMP-00001", created["id"])

    assert "error" not in result


def test_get_asset_denied_to_unrelated_non_reviewer():

    created = assets_api.create_asset_api(
        "EMP-00001", "social_post", {"headline": "Big Sale", "body": "Come on down"}
    )

    result = assets_api.get_asset_api(SALES, "EMP-00002", created["id"])

    assert "error" in result


def test_get_asset_visible_to_marketing_even_if_not_requester():

    created = assets_api.create_asset_api(
        "EMP-00001", "social_post", {"headline": "Big Sale", "body": "Come on down"}
    )

    result = assets_api.get_asset_api(MARKETING, "EMP-00002", created["id"])

    assert "error" not in result


def test_list_my_assets_only_returns_own_assets():

    assets_api.create_asset_api("EMP-00001", "social_post", {"headline": "A", "body": "b"})
    assets_api.create_asset_api("EMP-00002", "social_post", {"headline": "C", "body": "d"})

    mine = assets_api.list_my_assets_api("EMP-00001")

    assert len(mine) == 1
    assert mine[0]["requested_by"] == "EMP-00001"


def test_list_assets_most_recent_first():

    first = assets_api.create_asset_api("EMP-00001", "social_post", {"headline": "A", "body": "b"})
    second = assets_api.create_asset_api("EMP-00001", "social_post", {"headline": "C", "body": "d"})

    mine = assets_api.list_my_assets_api("EMP-00001")

    assert [a["id"] for a in mine] == [second["id"], first["id"]]
