"""
Tests for the NXTDeal Hub (hub/) -- dealer provisioning, the flat dealer registry, its
atomic-write/truncation-recovery persistence, and the thin *_api.py layer.

Run from hub/ with `pytest` (or `pytest tests/test_hub_provisioning.py`), same as the
backend suite is run from backend/. This is the Hub's first committed regression
coverage (session 50 built it; it had zero tests through session 74).

Path setup: hub/ goes on sys.path so `hub_core.*` resolves. Historically (before
session 87) provisioning.py reached into backend/core/auth.py directly for password
primitives; that broke once hub/ was deployed as its own isolated Coolify app (the
sibling backend/ directory the old cross-directory import needed simply isn't present
in that container), so hub/hub_core/auth.py is now a vendored copy instead -- see its
docstring.

Renamed 2026-07-19 (Code Auditor finding CAF-00121, "duplicate_core_package_name"):
this package used to be named `core`, identical to backend/core -- an implicit
*namespace* package spanning both sibling directories on sys.path (neither had an
__init__.py), meaning which module actually resolved for a given `core.X` import
depended on sys.path insertion ORDER, not on which package a developer actually meant.
That ambiguity is now gone: this package is `hub_core`, backend's is still plainly
`core`, and the two can never collide again regardless of what's on sys.path.
_BACKEND_DIR is still inserted below purely because provisioning._BACKEND_DIR-based
storage-path tests write real files under it (a filesystem-path concern, not an
import concern -- see provisioning.py's own docstring) -- it is NOT needed for any
import in this file anymore.
"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_HUB_DIR = os.path.dirname(_HERE)
_BACKEND_DIR = os.path.join(os.path.dirname(_HUB_DIR), "backend")

if _HUB_DIR not in sys.path:
    sys.path.insert(0, _HUB_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import pytest

from hub_core.dealer import Dealer, DealerIDGenerator, VALID_STATUSES
from hub_core.dealer_registry import registry
from hub_core import provisioning
from hub_core import dealers_api
from hub_core.dealer_storage import save_dealers, load_dealers, _recover_partial_array


@pytest.fixture(autouse=True)
def fresh_registry(tmp_path, monkeypatch):
    """The Hub's singleton `registry` is shared by every module under test, exactly like
    backend's credential_store/audit_log singletons -- reset it around every test.

    Also redirect the two things provisioning/save write to disk into a per-test tmp dir
    so no test ever scaffolds into the real backend/storage/tenants/ tree or overwrites
    hub/storage/dealers.json:
      * provisioning._BACKEND_DIR -> tmp (create_dealer scaffolds graph/audit/creds here)
      * dealers_api.DEALERS_PATH  -> tmp (save_dealers writes here)
    """
    registry.reset()

    fake_backend = tmp_path / "backend"
    fake_backend.mkdir()
    monkeypatch.setattr(provisioning, "_BACKEND_DIR", str(fake_backend))
    monkeypatch.setattr(dealers_api, "DEALERS_PATH", str(tmp_path / "dealers.json"))

    yield

    registry.reset()


# --------------------------------------------------------------------------------------
# Dealer dataclass + id generator
# --------------------------------------------------------------------------------------

def test_dealer_to_dict_from_dict_roundtrip():
    dealer = Dealer(
        dealer_id="DLR-00007",
        slug="dealer7",
        name="Acme Motors",
        contact_name="Pat",
        contact_email="pat@acme.example",
        contact_phone=None,
        address=None,
        city=None,
        state=None,
        plan_tier="Standard",
        status="active",
        storage_dir="storage/tenants/DLR-00007",
        network_opt_in=True,
        api_base_url=None,
        created_by="nxtdeal_staff",
    )
    restored = Dealer.from_dict(dealer.to_dict())
    assert restored == dealer
    # created_at is auto-populated and survives the round trip unchanged.
    assert restored.created_at == dealer.created_at


def test_id_generator_sequence_and_slug():
    gen = DealerIDGenerator()
    assert gen.generate() == "DLR-00001"
    assert gen.default_slug() == "dealer1"
    assert gen.generate() == "DLR-00002"
    assert gen.default_slug() == "dealer2"
    # slug is not zero-padded even though dealer_id is.
    for _ in range(8):
        gen.generate()
    assert gen.generate() == "DLR-00011"
    assert gen.default_slug() == "dealer11"


def test_id_generator_recover_from_bumps_counter():
    gen = DealerIDGenerator()
    existing = [
        Dealer.from_dict(_dealer_dict("DLR-00003", "dealer3", "a@x.example")),
        Dealer.from_dict(_dealer_dict("DLR-00009", "dealer9", "b@x.example")),
        Dealer.from_dict(_dealer_dict("DLR-00005", "dealer5", "c@x.example")),
    ]
    gen.recover_from(existing)
    # next id must clear the highest already on file, never reissue DLR-00009.
    assert gen.generate() == "DLR-00010"


def test_id_generator_recover_ignores_malformed_ids():
    gen = DealerIDGenerator()
    bad = Dealer.from_dict(_dealer_dict("NOT-AN-ID", "dealerX", "z@x.example"))
    gen.recover_from([bad])
    # malformed id skipped, counter untouched -> first real id is DLR-00001.
    assert gen.generate() == "DLR-00001"


# --------------------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------------------

def test_registry_add_get_and_email_lookup_is_case_insensitive():
    dealer = Dealer.from_dict(_dealer_dict("DLR-00001", "dealer1", "Owner@Acme.Example"))
    registry.add(dealer)
    assert registry.get("DLR-00001") is dealer
    assert registry.get("DLR-99999") is None
    assert registry.get_by_email("owner@acme.example") is dealer
    assert registry.get_by_email("OWNER@ACME.EXAMPLE") is dealer
    assert registry.get_by_email("nobody@x.example") is None


def test_registry_slug_lookup_and_sorted_list():
    d2 = Dealer.from_dict(_dealer_dict("DLR-00002", "dealer2", "b@x.example"))
    d1 = Dealer.from_dict(_dealer_dict("DLR-00001", "dealer1", "a@x.example"))
    registry.add(d2)
    registry.add(d1)
    assert registry.get_by_slug("Dealer1") is d1
    assert registry.get_by_slug("dealer2") is d2
    assert registry.get_by_slug("dealer3") is None
    assert registry.get_by_slug(None) is None
    # list_all is sorted by dealer_id regardless of insertion order.
    assert [d.dealer_id for d in registry.list_all()] == ["DLR-00001", "DLR-00002"]


# --------------------------------------------------------------------------------------
# create_dealer -- scaffolds a fresh empty tenant
# --------------------------------------------------------------------------------------

def test_create_dealer_success_scaffolds_and_registers():
    dealer, temp_password, error = provisioning.create_dealer(
        name="  Bright Auto  ",
        contact_email="hi@bright.example",
        contact_name="Dana",
    )
    assert error is None
    assert temp_password  # a real generated password, shown once
    assert dealer["dealer_id"] == "DLR-00001"
    assert dealer["slug"] == "dealer1"
    assert dealer["name"] == "Bright Auto"  # trimmed
    assert dealer["status"] == "active"
    assert dealer["storage_dir"] == "storage/tenants/DLR-00001"
    assert dealer["api_base_url"] is None

    # registered in the singleton
    assert registry.get("DLR-00001") is not None

    # files scaffolded under the (monkeypatched) backend dir
    tenant_dir = os.path.join(provisioning._BACKEND_DIR, "storage", "tenants", "DLR-00001")
    with open(os.path.join(tenant_dir, "graph.json")) as f:
        graph = json.load(f)
    assert graph == {"entities": [], "relationships": []}
    with open(os.path.join(tenant_dir, "audit.json")) as f:
        assert json.load(f) == []
    with open(os.path.join(tenant_dir, "credentials.json")) as f:
        creds = json.load(f)
    assert "DLR-00001-ADMIN" in creds
    admin = creds["DLR-00001-ADMIN"]
    assert admin["role"] == "ADMIN"
    assert admin["must_change_password"] is True
    assert admin["email"] == "hi@bright.example"
    # the temp password is hashed, never stored in the clear
    assert "salt" in admin and "hash" in admin
    assert temp_password not in json.dumps(creds)


def test_create_dealer_rejects_blank_name_and_writes_nothing():
    dealer, temp_password, error = provisioning.create_dealer(
        name="   ",
        contact_email="hi@x.example",
    )
    assert dealer is None and temp_password is None
    assert "name is required" in error
    assert registry.list_all() == []
    # no tenant dir created
    assert not os.path.exists(
        os.path.join(provisioning._BACKEND_DIR, "storage", "tenants")
    )


def test_create_dealer_rejects_bad_email():
    _, _, error = provisioning.create_dealer(name="X", contact_email="not-an-email")
    assert "valid contact_email is required" in error


def test_create_dealer_rejects_duplicate_email_case_insensitive():
    provisioning.create_dealer(name="First", contact_email="dup@x.example")
    dealer, temp_password, error = provisioning.create_dealer(
        name="Second", contact_email="DUP@X.EXAMPLE"
    )
    assert dealer is None and temp_password is None
    assert "already exists" in error
    # the failed second attempt must not have registered a second dealer
    assert len(registry.list_all()) == 1


# --------------------------------------------------------------------------------------
# adopt_dealer -- registers an existing instance without touching its storage
# --------------------------------------------------------------------------------------

def test_adopt_dealer_does_not_touch_storage():
    dealer, error = provisioning.adopt_dealer(
        name="Legacy Dealer",
        contact_email="legacy@x.example",
        storage_dir="storage",
        api_base_url="http://dealer1-api.example",
    )
    assert error is None
    assert dealer["storage_dir"] == "storage"
    assert dealer["api_base_url"] == "http://dealer1-api.example"
    assert registry.get(dealer["dealer_id"]) is not None
    # adopt must NOT scaffold anything on disk
    assert not os.path.exists(
        os.path.join(provisioning._BACKEND_DIR, "storage", "tenants")
    )


def test_adopt_dealer_requires_storage_dir():
    dealer, error = provisioning.adopt_dealer(
        name="X", contact_email="x@x.example", storage_dir="   "
    )
    assert dealer is None
    assert "storage_dir is required" in error


def test_adopt_dealer_rejects_duplicate_email():
    provisioning.adopt_dealer(name="A", contact_email="same@x.example", storage_dir="storage")
    dealer, error = provisioning.adopt_dealer(
        name="B", contact_email="same@x.example", storage_dir="storage/tenants/DLR-00002"
    )
    assert dealer is None
    assert "already exists" in error


# --------------------------------------------------------------------------------------
# status + api_base_url mutation
# --------------------------------------------------------------------------------------

def test_set_dealer_status_valid_invalid_and_unknown():
    provisioning.create_dealer(name="S", contact_email="s@x.example")
    dealer, error = provisioning.set_dealer_status("DLR-00001", "suspended")
    assert error is None
    assert dealer["status"] == "suspended"
    assert registry.get("DLR-00001").status == "suspended"

    _, error = provisioning.set_dealer_status("DLR-00001", "bogus")
    assert error is not None and "status must be one of" in error
    # VALID_STATUSES was extended to the real 8-stage lifecycle funnel (Dealer
    # Management rebuild) -- this assertion is a plain, current-value equality
    # check against dealer.py's own list, not a hardcoded guess at its length.
    assert set(VALID_STATUSES) == {
        "lead", "demo", "trial", "provisioning", "active",
        "expansion", "churn_risk", "suspended",
    }

    _, error = provisioning.set_dealer_status("DLR-99999", "active")
    assert "no dealer with id" in error


def test_set_dealer_api_base_url():
    provisioning.create_dealer(name="U", contact_email="u@x.example")
    dealer, error = provisioning.set_dealer_api_base_url(
        "DLR-00001", "http://dealer1-api.example"
    )
    assert error is None
    assert dealer["api_base_url"] == "http://dealer1-api.example"

    _, error = provisioning.set_dealer_api_base_url("DLR-99999", "http://x")
    assert "no dealer with id" in error


# --------------------------------------------------------------------------------------
# dealer_storage -- atomic save + truncation-tolerant load
# --------------------------------------------------------------------------------------

def test_save_and_load_roundtrip_recovers_counter(tmp_path):
    provisioning.create_dealer(name="One", contact_email="one@x.example")
    provisioning.create_dealer(name="Two", contact_email="two@x.example")
    path = str(tmp_path / "dealers.json")
    save_dealers(path)

    # simulate a fresh Hub boot: clear the registry, then load from disk
    registry.reset()
    assert registry.list_all() == []
    load_dealers(path)

    ids = [d.dealer_id for d in registry.list_all()]
    assert ids == ["DLR-00001", "DLR-00002"]
    # the id generator must be recovered so the next create doesn't reissue DLR-00002
    nxt, _, err = provisioning.create_dealer(name="Three", contact_email="three@x.example")
    assert err is None
    assert nxt["dealer_id"] == "DLR-00003"


def test_load_missing_file_is_a_noop(tmp_path):
    load_dealers(str(tmp_path / "does-not-exist.json"))
    assert registry.list_all() == []


def test_recover_partial_array_salvages_truncated_file(tmp_path):
    provisioning.create_dealer(name="A", contact_email="a@x.example")
    provisioning.create_dealer(name="B", contact_email="b@x.example")
    provisioning.create_dealer(name="C", contact_email="c@x.example")
    path = str(tmp_path / "dealers.json")
    save_dealers(path)

    # Truncate the file mid-third-record (drop the trailing chars incl the closing `]`).
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    third = text.rindex("{")  # start of the last (third) record
    truncated = text[: third + 20]  # cut partway into the third record
    with open(path, "w", encoding="utf-8") as f:
        f.write(truncated)

    registry.reset()
    load_dealers(path)
    # salvage keeps the two complete records and drops the mangled third
    ids = [d.dealer_id for d in registry.list_all()]
    assert ids == ["DLR-00001", "DLR-00002"]


def test_recover_partial_array_returns_empty_on_hopeless_input():
    assert _recover_partial_array("not json at all") == []
    assert _recover_partial_array("") == []


# --------------------------------------------------------------------------------------
# dealers_api -- response shaping + error passthrough
# --------------------------------------------------------------------------------------

def test_create_dealer_api_response_shape():
    result = dealers_api.create_dealer_api(name="ApiCo", contact_email="api@x.example")
    assert "error" not in result
    assert result["dealer"]["dealer_id"] == "DLR-00001"
    assert result["admin_employee_id"] == "DLR-00001-ADMIN"
    assert result["admin_temp_password"]
    assert "never shown again" in result["note"]
    # save_dealers wrote to the monkeypatched path
    assert os.path.exists(dealers_api.DEALERS_PATH)


def test_create_dealer_api_passes_errors_through():
    result = dealers_api.create_dealer_api(name="", contact_email="x@x.example")
    assert result == {"error": "name is required"}
    # a validation error must not have persisted a dealers.json
    assert not os.path.exists(dealers_api.DEALERS_PATH)


def test_list_and_get_dealer_api():
    dealers_api.create_dealer_api(name="L", contact_email="l@x.example")
    listed = dealers_api.list_dealers_api()
    assert isinstance(listed, list) and listed[0]["dealer_id"] == "DLR-00001"
    got = dealers_api.get_dealer_api("DLR-00001")
    assert got["name"] == "L"
    assert dealers_api.get_dealer_api("DLR-99999") == {
        "error": "no dealer with id 'DLR-99999'"
    }


def test_update_status_and_url_api():
    dealers_api.create_dealer_api(name="M", contact_email="m@x.example")
    updated = dealers_api.update_dealer_status_api("DLR-00001", "suspended")
    assert updated["status"] == "suspended"
    assert dealers_api.update_dealer_status_api("DLR-00001", "bogus") == {
        "error": (
            "status must be one of ['lead', 'demo', 'trial', 'provisioning', "
            "'active', 'expansion', 'churn_risk', 'suspended']"
        )
    }
    urled = dealers_api.update_dealer_api_base_url_api("DLR-00001", "http://x.example")
    assert urled["api_base_url"] == "http://x.example"


def test_adopt_dealer_api_response_shape():
    result = dealers_api.adopt_dealer_api(
        name="Adopted", contact_email="adopt@x.example", storage_dir="storage"
    )
    assert "error" not in result
    assert result["dealer"]["storage_dir"] == "storage"
    assert "No credential was created" in result["note"]


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------

def _dealer_dict(dealer_id, slug, email):
    return {
        "dealer_id": dealer_id,
        "slug": slug,
        "name": f"Dealer {dealer_id}",
        "contact_name": None,
        "contact_email": email,
        "contact_phone": None,
        "address": None,
        "city": None,
        "state": None,
        "plan_tier": "Standard",
        "status": "active",
        "storage_dir": f"storage/tenants/{dealer_id}",
        "network_opt_in": True,
        "api_base_url": None,
        "created_by": "nxtdeal_staff",
        "created_at": "2026-01-01T00:00:00+00:00",
    }


# --------------------------------------------------------------------------------------
# Public tenant resolver (apps.dealeros.xyz routing) -- resolve_dealer_api
# --------------------------------------------------------------------------------------

def _register(dealer_id, slug, email, api_base_url=None):
    d = _dealer_dict(dealer_id, slug, email)
    d["api_base_url"] = api_base_url
    dealer = Dealer.from_dict(d)
    registry.add(dealer)
    return dealer


def test_resolve_dealer_by_slug_and_id_returns_api_base_url():
    _register("DLR-00042", "cityauto", "a@cityauto.com", "https://cityauto-api.nxtdeal.app")

    by_slug = dealers_api.resolve_dealer_api("cityauto")
    assert by_slug["api_base_url"] == "https://cityauto-api.nxtdeal.app"
    assert by_slug["slug"] == "cityauto"
    # Public resolver must NOT expose the internal dealer_id or lifecycle status.
    assert "dealer_id" not in by_slug
    assert "status" not in by_slug

    # id lookup + case-insensitive slug both resolve to the same dealer.
    assert dealers_api.resolve_dealer_api("DLR-00042")["api_base_url"] == "https://cityauto-api.nxtdeal.app"
    assert dealers_api.resolve_dealer_api("CITYAUTO")["slug"] == "cityauto"


def test_resolve_dealer_without_api_base_url_is_not_available():
    _register("DLR-00043", "notdeployed", "b@nd.com", None)
    result = dealers_api.resolve_dealer_api("notdeployed")
    assert "error" in result
    assert "api_base_url" not in result


def test_resolve_dealer_unknown_and_blank():
    assert "error" in dealers_api.resolve_dealer_api("ghost")
    assert "error" in dealers_api.resolve_dealer_api("")
    assert "error" in dealers_api.resolve_dealer_api("   ")


def test_resolve_dealer_does_not_enumerate():
    # An exact identifier is required -- a partial/substring must NOT resolve.
    _register("DLR-00044", "riverside-motors", "c@rm.com", "https://rm-api.dealeros.xyz")
    assert "error" in dealers_api.resolve_dealer_api("riverside")
    assert "error" in dealers_api.resolve_dealer_api("motors")
