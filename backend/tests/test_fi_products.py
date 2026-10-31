"""
Tests for core/fi_products.py + core/fi_products_api.py -- the F&I Workflow
(session 105 follow-up): presenting VSC/GAP/Tire & Wheel/Paint & Fabric/Key
Replacement/Prepaid Maintenance products on a deal, tracking accept/decline
per product, and reporting real cross-deal product penetration.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import DEAL
from core import fi_products
from core import fi_products_api
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(fi_products, "save_graph", lambda filepath: None)


_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, FINANCE)
_VIEW_DENIED_ROLES = (MARKETING, SERVICE)
_FI_ROLES = (ADMIN, OPERATIONS, FINANCE)
_FI_DENIED_ROLES = (SALES, MARKETING, SERVICE)


def _add_deal(deal_id="DEAL-1", status="financing", updated_at=None):
    attrs = {"status": status}
    if updated_at is not None:
        attrs["updated_at"] = updated_at
    ledger.add_entity(Entity(id=deal_id, entity_type=DEAL, attributes=attrs))
    return deal_id


# ---------------------------------------------------------------------------
# get_fi_product_catalog
# ---------------------------------------------------------------------------

class TestGetFiProductCatalog:
    def test_returns_the_full_catalog(self):
        catalog = fi_products.get_fi_product_catalog()
        assert len(catalog) == 6
        keys = {p["key"] for p in catalog}
        assert keys == {"vsc", "gap", "tire_wheel", "paint_fabric", "key_replacement", "prepaid_maintenance"}


# ---------------------------------------------------------------------------
# get_fi_menu
# ---------------------------------------------------------------------------

class TestGetFiMenu:
    def test_rejects_unknown_deal(self):
        result = fi_products.get_fi_menu("DEAL-BAD")
        assert "error" in result

    def test_empty_menu_totals(self):
        _add_deal()
        result = fi_products.get_fi_menu("DEAL-1")
        assert result["totals"]["presented"] == 0
        assert result["totals"]["accepted"] == 0
        assert result["totals"]["total_price_accepted"] == 0

    def test_totals_reflect_mixed_decisions(self):
        _add_deal()
        fi_products.present_fi_products("DEAL-1", ["vsc", "gap", "tire_wheel"], "EMP-1")
        fi_products.decide_fi_product("DEAL-1", "vsc", "accepted")
        fi_products.decide_fi_product("DEAL-1", "gap", "declined", declined_reason="Too pricey")

        result = fi_products.get_fi_menu("DEAL-1")
        totals = result["totals"]
        assert totals["presented"] == 3
        assert totals["accepted"] == 1
        assert totals["declined"] == 1
        assert totals["pending"] == 1
        assert totals["total_price_accepted"] == 1895.0
        assert totals["total_cost_accepted"] == 900.0
        assert totals["total_gross_accepted"] == 995.0


# ---------------------------------------------------------------------------
# present_fi_products
# ---------------------------------------------------------------------------

class TestPresentFiProducts:
    def test_rejects_unknown_deal(self):
        result = fi_products.present_fi_products("DEAL-BAD", ["vsc"], "EMP-1")
        assert "error" in result

    def test_rejects_deal_not_in_presentable_status(self):
        _add_deal(status="desking")
        result = fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        assert "error" in result

    def test_allows_financing_status(self):
        _add_deal(status="financing")
        result = fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        assert "error" not in result

    def test_allows_contract_status(self):
        _add_deal(status="contract")
        result = fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        assert "error" not in result

    def test_rejects_empty_product_keys(self):
        _add_deal()
        result = fi_products.present_fi_products("DEAL-1", [], "EMP-1")
        assert "error" in result

    def test_rejects_unknown_product_key(self):
        _add_deal()
        result = fi_products.present_fi_products("DEAL-1", ["not_a_real_product"], "EMP-1")
        assert "error" in result

    def test_adds_entries_with_default_pricing(self):
        _add_deal()
        result = fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        entry = result["products"][0]
        assert entry["product_key"] == "vsc"
        assert entry["cost"] == 900.0
        assert entry["price"] == 1895.0
        assert entry["status"] == "presented"
        assert entry["presented_by"] == "EMP-1"
        assert entry["presented_at"] is not None

    def test_skips_a_product_key_already_on_the_menu(self):
        _add_deal()
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        result = fi_products.present_fi_products("DEAL-1", ["vsc", "gap"], "EMP-1")
        keys = [p["product_key"] for p in result["products"]]
        assert keys.count("vsc") == 1
        assert "gap" in keys

    def test_persists_onto_the_deal_entity(self):
        _add_deal()
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        deal = ledger.get_entity("DEAL-1")
        assert len(deal.attributes["fi_products"]) == 1


# ---------------------------------------------------------------------------
# update_fi_product_pricing
# ---------------------------------------------------------------------------

class TestUpdateFiProductPricing:
    def test_rejects_unknown_deal(self):
        result = fi_products.update_fi_product_pricing("DEAL-BAD", "vsc", price=1500)
        assert "error" in result

    def test_rejects_product_not_presented(self):
        _add_deal()
        result = fi_products.update_fi_product_pricing("DEAL-1", "vsc", price=1500)
        assert "error" in result

    def test_rejects_once_decided(self):
        _add_deal()
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        fi_products.decide_fi_product("DEAL-1", "vsc", "accepted")
        result = fi_products.update_fi_product_pricing("DEAL-1", "vsc", price=1500)
        assert "error" in result

    def test_rejects_bad_cost(self):
        _add_deal()
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        result = fi_products.update_fi_product_pricing("DEAL-1", "vsc", cost="not-a-number")
        assert "error" in result

    def test_rejects_bad_price(self):
        _add_deal()
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        result = fi_products.update_fi_product_pricing("DEAL-1", "vsc", price="not-a-number")
        assert "error" in result

    def test_updates_price_and_cost(self):
        _add_deal()
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        result = fi_products.update_fi_product_pricing("DEAL-1", "vsc", cost=850.0, price=1750.0)
        entry = next(p for p in result["products"] if p["product_key"] == "vsc")
        assert entry["cost"] == 850.0
        assert entry["price"] == 1750.0


# ---------------------------------------------------------------------------
# decide_fi_product
# ---------------------------------------------------------------------------

class TestDecideFiProduct:
    def test_rejects_bad_decision_value(self):
        _add_deal()
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        result = fi_products.decide_fi_product("DEAL-1", "vsc", "maybe")
        assert "error" in result

    def test_rejects_unknown_deal(self):
        result = fi_products.decide_fi_product("DEAL-BAD", "vsc", "accepted")
        assert "error" in result

    def test_rejects_product_not_presented(self):
        _add_deal()
        result = fi_products.decide_fi_product("DEAL-1", "vsc", "accepted")
        assert "error" in result

    def test_rejects_already_decided(self):
        _add_deal()
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        fi_products.decide_fi_product("DEAL-1", "vsc", "accepted")
        result = fi_products.decide_fi_product("DEAL-1", "vsc", "declined")
        assert "error" in result

    def test_accepted_clears_declined_reason(self):
        _add_deal()
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        result = fi_products.decide_fi_product("DEAL-1", "vsc", "accepted")
        entry = next(p for p in result["products"] if p["product_key"] == "vsc")
        assert entry["status"] == "accepted"
        assert entry["decided_at"] is not None
        assert entry["declined_reason"] is None

    def test_declined_records_a_reason(self):
        _add_deal()
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        result = fi_products.decide_fi_product("DEAL-1", "vsc", "declined", declined_reason="Not interested")
        entry = next(p for p in result["products"] if p["product_key"] == "vsc")
        assert entry["status"] == "declined"
        assert entry["declined_reason"] == "Not interested"


# ---------------------------------------------------------------------------
# get_product_penetration_stats
# ---------------------------------------------------------------------------

class TestProductPenetrationStats:
    def test_empty_stats_are_honest(self):
        stats = fi_products.get_product_penetration_stats()
        assert stats["deals_with_fi_menu"] == 0
        assert stats["products_per_deal_avg"] is None
        assert stats["total_accepted_gross"] == 0.0
        assert stats["by_product"] == []

    def test_only_counts_deals_with_an_fi_menu_on_file(self):
        _add_deal("DEAL-1")  # no F&I menu presented
        stats = fi_products.get_product_penetration_stats()
        assert stats["deals_with_fi_menu"] == 0

    def test_computes_real_penetration_across_deals(self):
        _add_deal("DEAL-1")
        fi_products.present_fi_products("DEAL-1", ["vsc", "gap"], "EMP-1")
        fi_products.decide_fi_product("DEAL-1", "vsc", "accepted")
        fi_products.decide_fi_product("DEAL-1", "gap", "declined")

        _add_deal("DEAL-2")
        fi_products.present_fi_products("DEAL-2", ["vsc"], "EMP-1")
        fi_products.decide_fi_product("DEAL-2", "vsc", "accepted")

        stats = fi_products.get_product_penetration_stats()
        assert stats["deals_with_fi_menu"] == 2

        vsc_stats = next(p for p in stats["by_product"] if p["product_key"] == "vsc")
        assert vsc_stats["presented"] == 2
        assert vsc_stats["accepted"] == 2
        assert vsc_stats["penetration_pct"] == 100.0
        assert vsc_stats["total_gross"] == round((1895.0 - 900.0) * 2, 2)

        gap_stats = next(p for p in stats["by_product"] if p["product_key"] == "gap")
        assert gap_stats["declined"] == 1
        assert gap_stats["accepted"] == 0
        assert gap_stats["penetration_pct"] == 0.0

    def test_by_product_sorted_by_penetration_descending(self):
        _add_deal("DEAL-1")
        fi_products.present_fi_products("DEAL-1", ["vsc", "gap"], "EMP-1")
        fi_products.decide_fi_product("DEAL-1", "vsc", "accepted")
        fi_products.decide_fi_product("DEAL-1", "gap", "declined")

        stats = fi_products.get_product_penetration_stats()
        pcts = [p["penetration_pct"] or 0 for p in stats["by_product"]]
        assert pcts == sorted(pcts, reverse=True)

    def test_total_accepted_gross_is_real(self):
        _add_deal("DEAL-1")
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        fi_products.decide_fi_product("DEAL-1", "vsc", "accepted")

        stats = fi_products.get_product_penetration_stats()
        assert stats["total_accepted_gross"] == 995.0


# ---------------------------------------------------------------------------
# list_deals_needing_fi_menu
# ---------------------------------------------------------------------------

class TestListDealsNeedingFiMenu:
    def test_excludes_deals_not_in_a_presentable_status(self):
        _add_deal("DEAL-1", status="desking")
        result = fi_products.list_deals_needing_fi_menu()
        assert result == []

    def test_excludes_deals_that_already_have_an_fi_menu(self):
        _add_deal("DEAL-1", status="financing")
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        result = fi_products.list_deals_needing_fi_menu()
        assert result == []

    def test_includes_a_presentable_deal_with_no_menu_yet(self):
        _add_deal("DEAL-1", status="financing")
        result = fi_products.list_deals_needing_fi_menu()
        assert len(result) == 1
        assert result[0].id == "DEAL-1"

    def test_sorted_by_updated_at_descending(self):
        _add_deal("DEAL-1", status="financing", updated_at="2026-01-01T00:00:00+00:00")
        _add_deal("DEAL-2", status="financing", updated_at="2026-06-01T00:00:00+00:00")
        result = fi_products.list_deals_needing_fi_menu()
        assert [d.id for d in result] == ["DEAL-2", "DEAL-1"]

    def test_respects_limit(self):
        for i in range(5):
            _add_deal(f"DEAL-{i}", status="financing")
        result = fi_products.list_deals_needing_fi_menu(limit=2)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# ACL sweep -- core/fi_products_api.py
# ---------------------------------------------------------------------------

class TestAcl:
    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_catalog_denied(self, role):
        result = fi_products_api.get_fi_product_catalog_api(role)
        assert isinstance(result, dict) and "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_catalog_allowed(self, role):
        result = fi_products_api.get_fi_product_catalog_api(role)
        assert isinstance(result, list)

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_get_menu_denied(self, role):
        _add_deal()
        result = fi_products_api.get_fi_menu_api(role, "DEAL-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_get_menu_allowed(self, role):
        ledger.reset()
        _add_deal()
        result = fi_products_api.get_fi_menu_api(role, "DEAL-1")
        assert "error" not in result

    @pytest.mark.parametrize("role", _FI_DENIED_ROLES)
    def test_present_denied(self, role):
        _add_deal()
        result = fi_products_api.present_fi_products_api(role, "DEAL-1", ["vsc"], "EMP-1")
        assert "error" in result

    @pytest.mark.parametrize("role", _FI_ROLES)
    def test_present_allowed(self, role):
        ledger.reset()
        _add_deal()
        result = fi_products_api.present_fi_products_api(role, "DEAL-1", ["vsc"], "EMP-1")
        assert "error" not in result

    @pytest.mark.parametrize("role", _FI_DENIED_ROLES)
    def test_update_pricing_denied(self, role):
        _add_deal()
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        result = fi_products_api.update_fi_product_pricing_api(role, "DEAL-1", "vsc", price=1500)
        assert "error" in result

    @pytest.mark.parametrize("role", _FI_ROLES)
    def test_update_pricing_allowed(self, role):
        ledger.reset()
        _add_deal()
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        result = fi_products_api.update_fi_product_pricing_api(role, "DEAL-1", "vsc", price=1500)
        assert "error" not in result

    @pytest.mark.parametrize("role", _FI_DENIED_ROLES)
    def test_decide_denied(self, role):
        _add_deal()
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        result = fi_products_api.decide_fi_product_api(role, "DEAL-1", "vsc", "accepted")
        assert "error" in result

    @pytest.mark.parametrize("role", _FI_ROLES)
    def test_decide_allowed(self, role):
        ledger.reset()
        _add_deal()
        fi_products.present_fi_products("DEAL-1", ["vsc"], "EMP-1")
        result = fi_products_api.decide_fi_product_api(role, "DEAL-1", "vsc", "accepted")
        assert "error" not in result

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_penetration_stats_denied(self, role):
        result = fi_products_api.get_product_penetration_stats_api(role)
        assert isinstance(result, dict) and "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_penetration_stats_allowed(self, role):
        result = fi_products_api.get_product_penetration_stats_api(role)
        assert "deals_with_fi_menu" in result

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_deals_needing_fi_menu_denied(self, role):
        result = fi_products_api.list_deals_needing_fi_menu_api(role)
        assert isinstance(result, dict) and "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_deals_needing_fi_menu_allowed(self, role):
        result = fi_products_api.list_deals_needing_fi_menu_api(role)
        assert isinstance(result, list)

    @pytest.mark.parametrize("role", _VIEW_DENIED_ROLES)
    def test_dashboard_denied(self, role):
        result = fi_products_api.get_fi_products_dashboard_api(role)
        assert "error" in result

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_dashboard_allowed(self, role):
        result = fi_products_api.get_fi_products_dashboard_api(role)
        assert "error" not in result
        assert "catalog" in result
        assert "queue" in result
        assert "penetration" in result
