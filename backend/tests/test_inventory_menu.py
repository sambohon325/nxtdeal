"""Tests for core/inventory_menu.py -- Inventory's 8-item Top Menu dispatcher
(overview/inventory/acquisitions/lot_management/pricing/merchandising/
wholesale/syndication/reporting).

Like core/finance_menu.py, several functions here read `core.dealeros.ledger`
directly (`_entities()`/`_unsold_vehicles()`/`_vehicle_has_image()`) rather
than exclusively delegating to another module's dashboard function --
exercised here against a lightweight fake ledger object so the real
filtering/aggregation logic in those helpers gets genuine coverage.

`reporting()` calls this module's OWN `merchandising(role)` and `pricing(role)`
(same-module functions, resolved at call time via a bare name) -- tested the
same way `core/network_menu.py`'s composition functions were, by monkeypatching
those two names directly on the module alias for `reporting()`'s own tests,
with `merchandising()`/`pricing()` each covered separately by their own
dedicated test class exercising their real logic.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.inventory_menu as im


# ---------------------------------------------------------------------------
# Fake ledger / entity / relationship helpers
# ---------------------------------------------------------------------------


class _FakeEntity:
    def __init__(self, entity_type, id, attributes=None):
        self.entity_type = entity_type
        self.id = id
        self.attributes = attributes or {}


class _FakeRelationship:
    def __init__(self, source_id, relationship_type):
        self.source_id = source_id
        self.relationship_type = relationship_type


class _FakeLedger:
    def __init__(self, entities=None, relationships=None):
        self._entities = {e.id: e for e in (entities or [])}
        self._relationships = relationships or []

    def get_all(self):
        return self._entities

    def get_relationships(self):
        return self._relationships


def _use_ledger(monkeypatch, entities=None, relationships=None):
    monkeypatch.setattr(im, "ledger", _FakeLedger(entities, relationships))


def _vehicle(id, price=0.0, cost=0.0, date_sold=None, extra=None):
    attrs = {"Price": price, "Cost": cost, "DateSold": date_sold}
    if extra:
        attrs.update(extra)
    return _FakeEntity(im.VEHICLE, id, attrs)


def _deal(id, status=None, vehicle_id=None, trade_in=None):
    return _FakeEntity(im.DEAL, id, {"status": status, "vehicle_id": vehicle_id, "trade_in": trade_in})


def _document(id, entity_id, entity_type, doc_type):
    return _FakeEntity(im.DOCUMENT, id, {"EntityID": entity_id, "EntityType": entity_type, "DocumentType": doc_type})


def _stub_engines(monkeypatch, **overrides):
    """Neutral, empty-shaped defaults for every external engine call this
    module composes -- individual tests override only what they need."""
    defaults = {
        "inventory_auction_acquisition": lambda role: {"count": 0, "transactions": [], "by_transport_status": {}},
        "inventory_wholesale_disposition": lambda role: {"count": 0, "candidates": []},
        "inventory_aging_pricing_bands": lambda role: {"by_price_band": {}},
        "operations_recon_queue": lambda role: {"used_unsold_count": 0},
        "get_inventory_overview_enrichment": lambda: {
            "aging_summary": {"aged_units_by_band": {}, "basis": "simulated_market_data"},
            "turn_rate": {}, "market_days_supply": {}, "lifecycle_stage_counts": {},
            "readiness_score": {}, "frontline_ready_units": 0,
        },
        "readiness_predictions_api": lambda: {"departments": []},
        "get_acquisitions_summary_api": lambda role: {},
        "list_acquisition_requests_api": lambda role, stage=None: {"requests": []},
        "get_factory_allocations_api": lambda role: {},
        "get_pricing_queue_api": lambda role, limit=25: {"queue": []},
        "get_lot_map_api": lambda role: {},
        "get_key_board_api": lambda role: {},
        "get_showroom_board_api": lambda role: {},
        "list_damage_reports_api": lambda role, status=None: {},
        "get_merchandising_queue_api": lambda role, limit=25: {},
        "get_featured_vehicles_api": lambda role: {},
        "get_wholesale_desk_summary_api": lambda role: {},
        "get_sold_wholesale_units_api": lambda role, limit=1000: {"vehicles": []},
        "get_syndication_overview_api": lambda role: {},
        "get_cost_breakdown": lambda vehicle_id: {"error": "not found"},
        "get_market_pricing": lambda vehicle_id: {},
        "get_vdp_health": lambda vehicle_id: {"error": "no data"},
        "search_entities": lambda role, query: [],
        "get_entity_by_id": lambda role, q: {"error": "not found"},
        "get_related_entities": lambda role, q: [],
        "get_vehicle_workspace_api": lambda role, q: {"error": "not found"},
    }
    defaults.update(overrides)
    for name, fn in defaults.items():
        monkeypatch.setattr(im, name, fn)


# ---------------------------------------------------------------------------
# _entities / _safe_float / _unsold_vehicles / _vehicle_has_image
# ---------------------------------------------------------------------------


class TestEntities:

    def test_filters_by_entity_type(self, monkeypatch):
        _use_ledger(monkeypatch, [_deal("DEAL-1"), _vehicle("VEH-1")])

        assert [e.id for e in im._entities(im.VEHICLE)] == ["VEH-1"]


class TestSafeFloat:

    def test_valid(self):
        assert im._safe_float("12.5") == 12.5

    def test_invalid_returns_default(self):
        assert im._safe_float(None) == 0.0

    def test_custom_default(self):
        assert im._safe_float("bad", default=-1.0) == -1.0


class TestUnsoldVehicles:

    def test_excludes_sold(self, monkeypatch):
        _use_ledger(monkeypatch, [
            _vehicle("VEH-1", date_sold=None),
            _vehicle("VEH-2", date_sold="2026-01-01"),
        ])

        result = im._unsold_vehicles()

        assert [v.id for v in result] == ["VEH-1"]

    def test_ignores_non_vehicle_entities(self, monkeypatch):
        _use_ledger(monkeypatch, [_vehicle("VEH-1"), _deal("DEAL-1")])

        assert len(im._unsold_vehicles()) == 1


class TestVehicleHasImage:

    def test_true_when_has_image_relationship_present(self, monkeypatch):
        _use_ledger(monkeypatch, [], relationships=[_FakeRelationship("VEH-1", "HAS_IMAGE")])

        assert im._vehicle_has_image("VEH-1") is True

    def test_false_when_no_matching_relationship(self, monkeypatch):
        _use_ledger(monkeypatch, [], relationships=[_FakeRelationship("VEH-1", "OWNS")])

        assert im._vehicle_has_image("VEH-1") is False

    def test_false_when_relationship_type_matches_but_wrong_source(self, monkeypatch):
        _use_ledger(monkeypatch, [], relationships=[_FakeRelationship("VEH-2", "HAS_IMAGE")])

        assert im._vehicle_has_image("VEH-1") is False


# ---------------------------------------------------------------------------
# overview()
# ---------------------------------------------------------------------------


class TestOverview:

    def test_full_path(self, monkeypatch):
        _use_ledger(monkeypatch, [
            _vehicle("VEH-1", price=20000.0),
            _vehicle("VEH-2", price=15000.0),
            _deal("DEAL-1", status="funded"),
        ])
        _stub_engines(
            monkeypatch,
            inventory_aging_pricing_bands=lambda role: {"by_price_band": {"0-10k": 1}},
            inventory_wholesale_disposition=lambda role: {"count": 3},
            inventory_auction_acquisition=lambda role: {
                "count": 5,
                "transactions": [{"transport_status": "in_transit"}, {"transport_status": "delivered"}],
                "by_transport_status": {"in_transit": 1, "delivered": 1},
            },
            operations_recon_queue=lambda role: {"used_unsold_count": 4},
            get_inventory_overview_enrichment=lambda: {
                "aging_summary": {"aged_units_by_band": {"91+ days": 2}, "basis": "simulated_market_data"},
                "turn_rate": {"annualized_turn_rate": 5.5},
                "market_days_supply": {"days": 60},
                "lifecycle_stage_counts": {"Merchandising": 7},
                "readiness_score": {"overall_score": 80},
                "frontline_ready_units": 12,
            },
        )

        result = im.overview("ADMIN")

        assert result["total_inventory_value"] == 35000.0
        assert result["active_inventory_count"] == 2
        assert result["incoming_vehicles"]["count"] == 1
        assert result["wholesale_candidates"]["count"] == 3
        assert result["inventory_aging_by_price_band"] == {"0-10k": 1}
        assert result["average_days_in_stock"]["basis"] == "simulated_market_data"
        assert result["aged_units_30_60_90"] == {"91+ days": 2}
        assert result["inventory_turn_rate"] == {"annualized_turn_rate": 5.5}
        assert result["market_days_supply"] == {"days": 60}
        assert result["lifecycle_stage_counts"] == {"Merchandising": 7}
        assert result["readiness_score"] == {"overall_score": 80}
        assert result["vehicle_pipeline"] == {
            "purchased": 5, "in_transit": 1, "recon": 4,
            "merchandising": 7, "frontline_ready": 12, "sold_or_wholesale": 4,
        }

    def test_empty_inventory(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        _stub_engines(monkeypatch)

        result = im.overview("ADMIN")

        assert result["total_inventory_value"] == 0.0
        assert result["active_inventory_count"] == 0
        assert result["vehicle_pipeline"]["sold_or_wholesale"] == 0


# ---------------------------------------------------------------------------
# inventory()
# ---------------------------------------------------------------------------


class TestInventory:

    def test_no_query_returns_default_view(self, monkeypatch):
        _use_ledger(monkeypatch, [
            _vehicle("VEH-1", price=20000.0, extra={"VIN": "1FT123", "StockNumber": "S1", "Year": 2022, "Make": "Ford", "Model": "F-150", "Condition": "Used", "Lot": "A"}),
        ])
        _stub_engines(monkeypatch)

        result = im.inventory("ADMIN")

        assert result["default_view"] == "unsold_inventory"
        assert result["count"] == 1
        assert result["vehicles"][0]["id"] == "VEH-1"
        assert result["vehicles"][0]["vin"] == "1FT123"

    def test_veh_prefixed_query_error_short_circuits(self, monkeypatch):
        related_called = []
        _stub_engines(
            monkeypatch,
            get_entity_by_id=lambda role, q: {"error": "not found"},
            get_related_entities=lambda role, q: related_called.append(q) or [],
        )

        result = im.inventory("ADMIN", query="veh-00001")

        assert result == {"error": "not found"}
        assert related_called == []

    def test_veh_prefixed_query_with_workspace_error(self, monkeypatch):
        _use_ledger(monkeypatch, [], relationships=[])
        _stub_engines(
            monkeypatch,
            get_entity_by_id=lambda role, q: {"id": "VEH-00001", "attributes": {"Price": 20000, "Cost": 17000}},
            get_related_entities=lambda role, q: [{"id": "CUST-1"}],
            get_vehicle_workspace_api=lambda role, q: {"error": "denied"},
        )

        result = im.inventory("ADMIN", query="VEH-00001")

        assert result["vehicle"]["id"] == "VEH-00001"
        assert result["related_entities"] == [{"id": "CUST-1"}]
        assert result["vehicle_profile"]["margin"] == 3000.0
        assert result["vehicle_profile"]["has_photos"] is False
        assert result["lifecycle"] is None
        assert result["cost_breakdown"] is None
        assert result["ownership"] is None
        assert result["activity_feed"] is None

    def test_veh_prefixed_query_with_workspace_success(self, monkeypatch):
        _use_ledger(monkeypatch, [], relationships=[_FakeRelationship("VEH-00001", "HAS_IMAGE")])
        _stub_engines(
            monkeypatch,
            get_entity_by_id=lambda role, q: {"id": "VEH-00001", "attributes": {"Price": 20000, "Cost": 17000}},
            get_related_entities=lambda role, q: [],
            get_vehicle_workspace_api=lambda role, q: {
                "lifecycle_status": "Recon", "status_history": [{"stage": "Recon"}],
                "recon_checklist": {"inspection": True}, "vendor_assignments": [],
                "cost_breakdown": {"total_investment": 17500.0}, "ownership": {"buyer": "EMP-1"},
                "activity_feed": [{"type": "status_change"}],
            },
        )

        result = im.inventory("ADMIN", query="VEH-00001")

        assert result["vehicle_profile"]["has_photos"] is True
        assert result["lifecycle"]["lifecycle_status"] == "Recon"
        assert result["cost_breakdown"] == {"total_investment": 17500.0}
        assert result["ownership"] == {"buyer": "EMP-1"}
        assert result["activity_feed"] == [{"type": "status_change"}]
        assert "market_value" in result["not_yet_tracked"]

    def test_free_text_query_filters_by_vehicle_type(self, monkeypatch):
        _stub_engines(monkeypatch, search_entities=lambda role, query: [
            {"entity_type": im.VEHICLE, "id": "VEH-1"},
            {"entity_type": im.DEAL, "id": "DEAL-1"},
        ])

        result = im.inventory("ADMIN", query="Ford F-150")

        assert result["count"] == 1
        # Phase 2: each vehicle hit is enriched with a primary photo URL (None when the
        # vehicle has no Image on file, as here).
        assert result["results"] == [{"entity_type": im.VEHICLE, "id": "VEH-1", "photo_url": None}]


# ---------------------------------------------------------------------------
# acquisitions()
# ---------------------------------------------------------------------------


class TestAcquisitions:

    def test_full_path_with_cost_variance_and_pending_lookup(self, monkeypatch):
        _use_ledger(monkeypatch, [
            _vehicle("VEH-1", cost=18000.0),
            _deal("DEAL-1", trade_in={"appraised_value": 1000}),
            _deal("DEAL-2", trade_in=None),
        ])
        pending_calls = []
        _stub_engines(
            monkeypatch,
            inventory_auction_acquisition=lambda role: {
                "count": 2,
                "transactions": [
                    {"vehicle_id": "VEH-1", "bid_amount": 17000.0, "transport_status": "in_transit"},
                    {"vehicle_id": "VEH-MISSING", "bid_amount": 5000.0, "transport_status": "delivered"},
                ],
                "by_transport_status": {"in_transit": 1, "delivered": 1},
            },
            get_acquisitions_summary_api=lambda role: {"total_requests": 4},
            list_acquisition_requests_api=lambda role, stage=None: pending_calls.append(stage) or {"requests": [{"id": "ACQ-1"}]},
            get_factory_allocations_api=lambda role: {"basis": "simulated_market_data"},
        )

        result = im.acquisitions("ADMIN")

        assert result["auction_purchases"]["count"] == 2
        assert result["vehicles_in_transit"]["count"] == 1
        assert result["incoming_inventory"]["count"] == 1
        assert result["trade_acquisitions"]["count"] == 1
        assert result["cost_analysis"]["matched_transactions"] == 1
        assert result["cost_analysis"]["avg_cost_vs_bid_variance"] == 1000.0
        assert pending_calls == ["pending_approval"]
        assert result["acquisition_approvals"]["pending_approval"] == [{"id": "ACQ-1"}]
        assert result["purchase_requests"] == {"total_requests": 4}
        assert result["factory_allocations"] == {"basis": "simulated_market_data"}

    def test_acq_summary_with_error_skips_pending_lookup(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        pending_calls = []
        _stub_engines(
            monkeypatch,
            inventory_auction_acquisition=lambda role: {"count": 0, "transactions": [], "by_transport_status": {}},
            get_acquisitions_summary_api=lambda role: {"error": "denied"},
            list_acquisition_requests_api=lambda role, stage=None: pending_calls.append(stage) or {"requests": []},
        )

        result = im.acquisitions("SALES")

        assert pending_calls == []
        assert result["acquisition_approvals"]["pending_approval"] == []

    def test_no_matched_transactions_gives_none_variance(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        _stub_engines(monkeypatch)

        result = im.acquisitions("ADMIN")

        assert result["cost_analysis"]["matched_transactions"] == 0
        assert result["cost_analysis"]["avg_cost_vs_bid_variance"] is None


# ---------------------------------------------------------------------------
# lot_management()
# ---------------------------------------------------------------------------


class TestLotManagement:

    def test_query_returns_search_results(self, monkeypatch):
        _stub_engines(monkeypatch, search_entities=lambda role, query: [
            {"entity_type": im.VEHICLE, "id": "VEH-1"},
        ])

        result = im.lot_management("ADMIN", query="Lot A")

        assert result == {"query": "Lot A", "count": 1, "results": [{"entity_type": im.VEHICLE, "id": "VEH-1"}]}

    def test_no_query_returns_full_board(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            inventory_lot_audit=lambda role: {
                "unsold_by_lot": {"A": 5}, "total_vehicles": 10,
                "sold_without_purchase_relationship": 2, "discrepancies": ["VEH-1"],
            },
            get_lot_map_api=lambda role: {"positions": []},
            get_key_board_api=lambda role: {"checked_out": []},
            list_damage_reports_api=lambda role, status=None: {"reports": []},
            get_showroom_board_api=lambda role: {"assignments": []},
        )

        result = im.lot_management("ADMIN")

        assert result["vehicle_locations_by_lot"] == {"A": 5}
        assert result["total_vehicles"] == 10
        assert result["ownership_mismatches"]["count"] == 2
        assert result["ownership_mismatches"]["discrepancies"] == ["VEH-1"]
        assert result["lot_map"] == {"positions": []}
        assert result["key_management"] == {"checked_out": []}
        assert result["damage_reports"] == {"reports": []}
        assert result["showroom_assignments"] == {"assignments": []}
        assert "geofencing" in result["not_yet_tracked"]


# ---------------------------------------------------------------------------
# pricing()
# ---------------------------------------------------------------------------


class TestPricing:

    def test_query_returns_search_results(self, monkeypatch):
        _stub_engines(monkeypatch, search_entities=lambda role, query: [
            {"entity_type": im.VEHICLE, "id": "VEH-1"},
        ])

        result = im.pricing("ADMIN", query="Ford")

        assert result == {"query": "Ford", "count": 1, "results": [{"entity_type": im.VEHICLE, "id": "VEH-1"}]}

    def test_no_query_full_path(self, monkeypatch):
        _use_ledger(monkeypatch, [
            _vehicle("VEH-1", price=20000.0, cost=17000.0),
            _vehicle("VEH-2", price=0.0, cost=1000.0),  # zero-price -> flagged
            _vehicle("VEH-3", price=10000.0, cost=12000.0),  # negative margin
        ])
        _stub_engines(
            monkeypatch,
            inventory_aging_pricing_bands=lambda role: {"by_price_band": {"0-10k": 1}},
            get_pricing_queue_api=lambda role, limit=25: {"queue": ["VEH-3"]},
        )

        result = im.pricing("ADMIN")

        assert result["aging_by_price_band"] == {"0-10k": 1}
        assert result["pricing_queue"]["count"] == 1
        assert result["pricing_queue"]["vehicles"][0]["vehicle_id"] == "VEH-2"
        # margins computed only over vehicles with a real price: (20000-17000)/20000=0.15, (10000-12000)/10000=-0.2
        assert result["margin_analysis"]["unsold_with_margin_data"] == 2
        assert result["margin_analysis"]["avg_margin_pct"] == pytest.approx(-0.025, abs=1e-6)
        assert result["margin_analysis"]["min_margin_pct"] == -0.2
        assert result["margin_analysis"]["max_margin_pct"] == 0.15
        assert result["pricing_desk_queue"] == {"queue": ["VEH-3"]}
        assert "price_change_history" in result["not_yet_tracked"]

    def test_no_unsold_vehicles_gives_none_margins(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        _stub_engines(monkeypatch)

        result = im.pricing("ADMIN")

        assert result["margin_analysis"]["unsold_with_margin_data"] == 0
        assert result["margin_analysis"]["avg_margin_pct"] is None
        assert result["margin_analysis"]["min_margin_pct"] is None
        assert result["margin_analysis"]["max_margin_pct"] is None


# ---------------------------------------------------------------------------
# merchandising()
# ---------------------------------------------------------------------------


class TestMerchandising:

    def test_full_path(self, monkeypatch):
        _use_ledger(
            monkeypatch,
            [
                _vehicle("VEH-1", extra={"description": "Clean, one owner"}),
                _vehicle("VEH-2", extra={"description": ""}),
                _vehicle("VEH-3", extra={"description": "  "}),
            ],
            relationships=[_FakeRelationship("VEH-1", "HAS_IMAGE")],
        )
        _stub_engines(
            monkeypatch,
            get_inventory_overview_enrichment=lambda: {"frontline_ready_units": 9},
            get_featured_vehicles_api=lambda role: {"featured": ["VEH-1"]},
            get_merchandising_queue_api=lambda role, limit=25: {"queue": []},
        )

        result = im.merchandising("ADMIN")

        assert result["missing_photos"]["count"] == 2  # VEH-2, VEH-3
        assert result["missing_photos"]["pct_of_unsold"] == pytest.approx(round(2 / 3, 3), abs=1e-6)
        assert result["missing_comments"]["count"] == 2  # VEH-2 (empty), VEH-3 (whitespace)
        assert result["frontline_ready_units"] == 9
        assert result["featured_vehicles"] == {"featured": ["VEH-1"]}
        assert result["merchandising_queue"] == {"queue": []}

    def test_no_unsold_vehicles_gives_none_pct(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        _stub_engines(monkeypatch, get_inventory_overview_enrichment=lambda: {"frontline_ready_units": 0})

        result = im.merchandising("ADMIN")

        assert result["missing_photos"]["count"] == 0
        assert result["missing_photos"]["pct_of_unsold"] is None
        assert result["missing_comments"]["pct_of_unsold"] is None


# ---------------------------------------------------------------------------
# wholesale()
# ---------------------------------------------------------------------------


class TestWholesale:

    def test_query_returns_search_results(self, monkeypatch):
        _stub_engines(monkeypatch, search_entities=lambda role, query: [
            {"entity_type": im.VEHICLE, "id": "VEH-1"},
        ])

        result = im.wholesale("ADMIN", query="F-150")

        assert result == {"query": "F-150", "count": 1, "results": [{"entity_type": im.VEHICLE, "id": "VEH-1"}]}

    def test_no_query_title_cross_reference(self, monkeypatch):
        _use_ledger(monkeypatch, [
            _document("DOC-1", "VEH-1", im.VEHICLE, "Title"),
            _document("DOC-2", "VEH-2", im.VEHICLE, "Recon Form"),  # wrong doc type, ignored
        ])
        _stub_engines(
            monkeypatch,
            inventory_wholesale_disposition=lambda role: {
                "count": 2,
                "candidates": [{"vehicle_id": "VEH-1"}, {"vehicle_id": "VEH-2"}],
            },
            get_wholesale_desk_summary_api=lambda role: {
                "open_offers": {"count": 1}, "sold_wholesale_units": {"count": 3}, "fund_collection": {"awaiting": 500.0},
            },
        )

        result = im.wholesale("ADMIN")

        assert result["title_status"]["candidates_with_title_on_file"] == 1
        assert result["title_status"]["candidates_missing_title"] == 1
        assert result["title_status"]["missing_title_vehicle_ids"] == ["VEH-2"]
        assert result["open_offers"] == {"count": 1}
        assert result["sold_wholesale_units"] == {"count": 3}
        assert result["fund_collection"] == {"awaiting": 500.0}

    def test_non_dict_desk_summary_gives_none_fields(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        _stub_engines(
            monkeypatch,
            inventory_wholesale_disposition=lambda role: {"count": 0, "candidates": []},
            get_wholesale_desk_summary_api=lambda role: None,
        )

        result = im.wholesale("ADMIN")

        assert result["open_offers"] is None
        assert result["sold_wholesale_units"] is None
        assert result["fund_collection"] is None


# ---------------------------------------------------------------------------
# syndication()
# ---------------------------------------------------------------------------


class TestSyndication:

    def test_thin_passthrough(self, monkeypatch):
        monkeypatch.setattr(im, "get_syndication_overview_api", lambda role: {"feed_health": {}})

        assert im.syndication("ADMIN") == {"feed_health": {}}


# ---------------------------------------------------------------------------
# reporting()
# ---------------------------------------------------------------------------


class TestReporting:

    def test_full_path(self, monkeypatch):
        _use_ledger(monkeypatch, [
            _vehicle("VEH-1", price=20000.0, cost=17000.0),
            _vehicle("VEH-2", price=15000.0, cost=14000.0),
            _vehicle("VEH-3", price=22000.0, cost=19000.0, date_sold="2026-06-01"),
            _deal("DEAL-1", status="funded", vehicle_id="VEH-3"),
        ])
        _stub_engines(
            monkeypatch,
            inventory_aging_pricing_bands=lambda role: {"by_price_band": {"0-10k": 0}},
            inventory_wholesale_disposition=lambda role: {
                "count": 2, "candidates": [{"vehicle_id": "VEH-1", "margin": -500}, {"vehicle_id": "VEH-2", "margin": 300}],
            },
            inventory_auction_acquisition=lambda role: {
                "count": 2, "transactions": [
                    {"vehicle_id": "VEH-1", "auction_house": "Manheim"},
                    {"vehicle_id": "VEH-2", "auction_house": "Manheim"},
                ],
            },
            readiness_predictions_api=lambda: {"departments": [{"department": "sales", "units_sold": {"tomorrow": 3}}]},
            get_inventory_overview_enrichment=lambda: {
                "aging_summary": {"aged_units_by_band": {"91+ days": 2}, "basis": "simulated_market_data"},
                "turn_rate": {"annualized_turn_rate": 5.5},
            },
            get_cost_breakdown=lambda vehicle_id: (
                {"total_investment": 17500.0, "breakdown": {"floorplan_interest": 50.0}}
                if vehicle_id == "VEH-1" else {"error": "not found"}
            ),
            get_sold_wholesale_units_api=lambda role, limit=1000: {
                "vehicles": [{"cost": 12000.0, "wholesale_sale": {"sale_price": 11000.0}}],
            },
            get_market_pricing=lambda vehicle_id: (
                {"price_position": "below_market"} if vehicle_id == "VEH-1" else {"price_position": "at_market"}
            ),
            get_vdp_health=lambda vehicle_id: (
                {"simulated_page_views": 100, "simulated_lead_conversion_rate": 0.05}
                if vehicle_id == "VEH-1" else {"error": "no data"}
            ),
        )
        monkeypatch.setattr(im, "merchandising", lambda role: {"missing_photos": {"count": 1}})
        monkeypatch.setattr(im, "pricing", lambda role: {"margin_analysis": {"avg_margin_pct": 0.15}})

        result = im.reporting("ADMIN")

        assert result["aging_reports"]["by_price_band"] == {"0-10k": 0}
        assert result["aging_reports"]["forecasted_aging_risk"]["units_at_risk_91_plus_days"] == 2
        assert result["aging_reports"]["forecasted_aging_risk"]["pct_of_unsold"] == 1.0
        assert result["acquisition_reports"]["source_performance_by_auction_house"] == {"Manheim": 2}
        assert result["acquisition_reports"]["total_acquisitions"] == 2
        assert result["pricing_reports"]["margin_analysis"] == {"avg_margin_pct": 0.15}
        assert result["pricing_reports"]["market_position"]["distribution"] == {"below_market": 1, "at_market": 1, "above_market": 0}
        assert result["merchandising_reports"]["photo_completion"] == {"count": 1}
        assert result["merchandising_reports"]["vdp_lead_conversion"]["avg_simulated_page_views"] == 100.0
        assert result["merchandising_reports"]["vdp_lead_conversion"]["avg_simulated_lead_conversion_rate"] == 0.05
        assert result["merchandising_reports"]["vdp_lead_conversion"]["sample_size"] == 1
        assert result["wholesale_reports"]["candidate_count"] == 2
        assert result["wholesale_reports"]["loss_total_on_negative_margin_candidates"] == -500.0
        assert result["disposition_roi"]["wholesale"] == {"units": 1, "total_roi": -1000.0}
        assert result["disposition_roi"]["retail"] == {"units": 1, "total_roi": 3000.0}
        assert result["capital_reports"]["holding_cost"]["total_floorplan_interest"] == 50.0
        assert result["capital_reports"]["capital_utilization"]["total_investment"] == 17500.0
        assert result["capital_reports"]["capital_utilization"]["total_inventory_value"] == 35000.0
        assert result["capital_reports"]["capital_utilization"]["utilization_ratio"] == 0.5
        assert result["turn_rate"] == {"annualized_turn_rate": 5.5}
        assert result["executive_reports"] == {"total_inventory_value": 35000.0, "active_inventory_count": 2}
        assert result["forecasting"] == {"department": "sales", "units_sold": {"tomorrow": 3}}
        assert result["department_intelligence"] == im._DI_GAP_NOTE

    def test_empty_inventory_guards_against_division_by_zero(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        _stub_engines(monkeypatch)
        monkeypatch.setattr(im, "merchandising", lambda role: {"missing_photos": {}})
        monkeypatch.setattr(im, "pricing", lambda role: {"margin_analysis": {}})

        result = im.reporting("ADMIN")

        assert result["aging_reports"]["forecasted_aging_risk"]["pct_of_unsold"] is None
        assert result["capital_reports"]["capital_utilization"]["utilization_ratio"] is None
        assert result["merchandising_reports"]["vdp_lead_conversion"]["avg_simulated_page_views"] is None
        assert result["merchandising_reports"]["vdp_lead_conversion"]["sample_size"] == 0
        assert result["disposition_roi"]["wholesale"] == {"units": 0, "total_roi": 0.0}
        assert result["disposition_roi"]["retail"] == {"units": 0, "total_roi": 0.0}
        assert result["forecasting"] is None
