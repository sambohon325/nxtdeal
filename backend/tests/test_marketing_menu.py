"""Tests for core/marketing_menu.py -- Marketing's Top Menu dispatcher
(overview/campaigns/events/website/crm/purls/email_sms/social_reputation/
advertising/studio/analytics/reporting, plus private CRM-composition helpers).

Several functions here read `core.dealeros.ledger` directly (`_entities()`/
`_pipeline_board()`/`_audiences()`'s OWNS-relationship scan/`social_reputation()`'s
Review search) -- exercised against a lightweight fake ledger, same convention
established in test_finance_menu.py/test_inventory_menu.py.

`crm()` calls this module's own private helpers (`_pipeline_board`/
`_lists_summary`/`_campaigns`/`_audiences`/`_opportunities`) at call time via bare
names -- tested by monkeypatching those names directly on the module alias for
`crm()`'s own no-query test, with each private helper covered separately by its
own dedicated test class exercising its real logic (the "extract and isolate the
composing function" pattern already used for `reporting()` in both prior menu
test files).

`crm()`/`purls()`/`studio()` also perform DEFERRED (in-function) imports of
`core.customer_360`/`core.purls`/`core.marketing_studio_api` -- these are NOT
monkeypatchable via the module alias and must be patched at their real source via
the string-target form, e.g. `monkeypatch.setattr("core.purls.get_purl_dashboard", fake)`.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.marketing_menu as mm


# ---------------------------------------------------------------------------
# Fake ledger / entity helpers
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
    monkeypatch.setattr(mm, "ledger", _FakeLedger(entities, relationships))


def _lead(id, pipeline_state=None, source=None, lead_id=None, since=None):
    return _FakeEntity(mm.LEAD, id, {
        "PipelineState": pipeline_state, "Source": source, "LeadID": lead_id, "PipelineStateSince": since,
    })


def _deal(id, status=None, vehicle_id=None):
    return _FakeEntity(mm.DEAL, id, {"status": status, "vehicle_id": vehicle_id})


def _vehicle(id, price=0.0, cost=0.0):
    return _FakeEntity(mm.VEHICLE, id, {"Price": price, "Cost": cost})


def _campaign_entity(id, status=None, campaign_type=None, channel=None, audience_count=0, sent_count=0, name=None):
    return _FakeEntity(mm.CAMPAIGN, id, {
        "status": status, "campaign_type": campaign_type, "channel": channel,
        "audience_count": audience_count, "sent_count": sent_count, "name": name,
    })


def _review(id, author_name=None, text=None, rating=None, responded=None, platform=None):
    return _FakeEntity(mm.REVIEW, id, {
        "author_name": author_name, "text": text, "rating": rating, "responded": responded, "platform": platform,
    })


def _make_preview_audience(mapping):
    """mapping: {(campaign_type, frozenset(params.items())): result_dict}"""
    def fake(campaign_type, params=None):
        key = (campaign_type, frozenset((params or {}).items()))
        return mapping.get(key, {"count": 0, "sample": []})
    return fake


def _stub_engines(monkeypatch, **overrides):
    defaults = {
        "list_campaign_types": lambda: [],
        "list_channels": lambda: [],
        "list_campaigns": lambda: [],
        "preview_audience": lambda campaign_type, params=None: {"count": 0, "sample": []},
        "list_websites": lambda: [],
        "list_personal_sites": lambda: [],
        "list_chat_sessions": lambda: [],
        "marketing_database_mining": lambda role: {"count": 0, "candidates": []},
        "marketing_reputation_summary": lambda role: {},
        "get_lead_pipeline_dashboard": lambda: {},
        "list_alerts_api": lambda role, status=None: {"alerts": []},
        "readiness_predictions_api": lambda: {"departments": []},
        "search_entities": lambda role, query: [],
        "get_entity_by_id": lambda role, q: {"error": "not found"},
        "get_related_entities": lambda role, q: [],
        "list_email_templates": lambda: [],
        "list_block_types": lambda: [],
        "list_lists": lambda: [],
        "list_smart_audience_presets": lambda: [],
        "list_smart_audiences": lambda: [],
        "lead_scoring_leaderboard": lambda limit=10: {"count": 0, "by_tier": {}, "leads": []},
        "list_social_platforms": lambda: [],
        "list_social_posts": lambda: [],
        "get_social_calendar": lambda: {},
        "list_bad_review_alerts_api": lambda role: [],
        "get_competitor_tracking_api": lambda role: {},
        "list_ad_platforms": lambda: [],
        "list_ad_objectives": lambda: [],
        "list_ad_campaigns": lambda: [],
        "run_trigger_scan": lambda: None,
        "list_alerts": lambda status=None: [],
        "list_event_types": lambda: [],
        "list_dealership_events": lambda: [],
        "get_marketing_roi_dashboard_api": lambda role: {},
        "SECTION_TEMPLATES": {},
        "SITE_TEMPLATES": {},
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        monkeypatch.setattr(mm, name, value)


# ---------------------------------------------------------------------------
# list_alert_types / _entities / _safe_float / _funded_deal_gross / _avg_funded_deal_gross
# ---------------------------------------------------------------------------


class TestListAlertTypes:

    def test_returns_module_alert_types(self, monkeypatch):
        monkeypatch.setattr(mm, "_ALERT_TYPES", ["equity_mining", "lease_maturity"])

        assert mm.list_alert_types() == ["equity_mining", "lease_maturity"]


class TestEntities:

    def test_filters_by_entity_type(self, monkeypatch):
        _use_ledger(monkeypatch, [_lead("LEAD-1"), _vehicle("VEH-1")])

        assert [e.id for e in mm._entities(mm.LEAD)] == ["LEAD-1"]


class TestSafeFloat:

    def test_valid(self):
        assert mm._safe_float("42.5") == 42.5

    def test_invalid_returns_default(self):
        assert mm._safe_float(None) == 0.0

    def test_custom_default(self):
        assert mm._safe_float("bad", default=-1.0) == -1.0


class TestFundedDealGross:

    def test_sums_price_minus_cost_across_deals(self, monkeypatch):
        _use_ledger(monkeypatch, [_vehicle("VEH-1", price=20000.0, cost=17000.0), _vehicle("VEH-2", price=15000.0, cost=14000.0)])
        deals = [_deal("DEAL-1", vehicle_id="VEH-1"), _deal("DEAL-2", vehicle_id="VEH-2")]

        assert mm._funded_deal_gross(deals) == 4000.0

    def test_skips_deal_with_no_matching_vehicle(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        deals = [_deal("DEAL-1", vehicle_id="VEH-MISSING")]

        assert mm._funded_deal_gross(deals) == 0.0


class TestAvgFundedDealGross:

    def test_averages_over_funded_deals_only(self, monkeypatch):
        _use_ledger(monkeypatch, [
            _vehicle("VEH-1", price=20000.0, cost=17000.0),
            _vehicle("VEH-2", price=10000.0, cost=9000.0),
            _deal("DEAL-1", status="funded", vehicle_id="VEH-1"),
            _deal("DEAL-2", status="funded", vehicle_id="VEH-2"),
            _deal("DEAL-3", status="draft", vehicle_id="VEH-1"),
        ])

        assert mm._avg_funded_deal_gross() == 2000.0

    def test_no_funded_deals_returns_zero(self, monkeypatch):
        _use_ledger(monkeypatch, [])

        assert mm._avg_funded_deal_gross() == 0.0


# ---------------------------------------------------------------------------
# overview()
# ---------------------------------------------------------------------------


class TestOverview:

    def test_full_path(self, monkeypatch):
        _use_ledger(monkeypatch, [
            _lead("LEAD-1", pipeline_state="NEW"),
            _lead("LEAD-2", pipeline_state="VISITED"),
            _lead("LEAD-3", pipeline_state="VISITED"),
            _vehicle("VEH-1", price=20000.0, cost=17000.0),
            _deal("DEAL-1", status="funded", vehicle_id="VEH-1"),
            _deal("DEAL-2", status="draft", vehicle_id="VEH-1"),
            _campaign_entity("CAMP-1", audience_count=50),
            _campaign_entity("CAMP-2", audience_count=30),
        ])
        _stub_engines(
            monkeypatch,
            marketing_database_mining=lambda role: {"count": 4, "candidates": []},
            preview_audience=_make_preview_audience({
                ("finance_renewal", frozenset({"months_to_maturity": 6}.items())): {"count": 5, "sample": []},
                ("inventory_ads", frozenset()): {"count": 3, "sample": []},
                ("retention", frozenset({"months_since_service": 6}.items())): {"count": 2, "sample": []},
            }),
        )

        result = mm.overview("ADMIN")

        assert result["lead_volume"] == 3
        assert result["showroom_traffic"] == 2
        assert result["revenue_generated_funded_deals"] == 3000.0
        assert result["active_opportunities"] == 9  # equity 4 + lease 5
        assert result["revenue_funnel"] == {
            "audience": 80, "campaign": 2, "lead": 3, "appointment": None, "showroom": 2, "sold": 1,
        }
        assert result["opportunity_pipeline"] == {
            "equity_customers": 4, "lease_maturity": 5, "service_defectors": 2, "conquest_targets": 3,
        }


# ---------------------------------------------------------------------------
# _campaigns() / campaigns()
# ---------------------------------------------------------------------------


class TestPrivateCampaigns:

    def test_groups_by_status_category_channel(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            list_campaigns=lambda: [
                _campaign_entity("CAMP-1", status="active", campaign_type="finance_renewal", channel="email", name="C1", audience_count=10, sent_count=8),
                _campaign_entity("CAMP-2", status="draft", campaign_type="retention", channel="sms", name="C2"),
                _campaign_entity("CAMP-3", status="active", campaign_type="unmapped_type", channel="email", name="C3"),
            ],
            list_campaign_types=lambda: [
                {"key": "finance_renewal", "category": "lifecycle"},
                {"key": "retention", "category": "lifecycle"},
            ],
            list_channels=lambda: ["email", "sms"],
            list_alerts_api=lambda role, status=None: {"alerts": [
                {"category": "marketing", "id": "ALERT-1"}, {"category": "compliance", "id": "ALERT-2"},
            ]},
        )

        result = mm._campaigns("ADMIN")

        assert result["total_campaigns"] == 3
        assert result["by_status"] == {"active": 2, "draft": 1}
        assert result["by_category"] == {"lifecycle": 2, "unknown": 1}
        assert result["by_channel"] == {"email": 2, "sms": 1}
        assert result["pending_drafts"]["count"] == 1
        assert result["compliance_approval"]["count"] == 1
        assert result["compliance_approval"]["alerts"] == [{"category": "marketing", "id": "ALERT-1"}]
        assert result["recent_campaigns"][0]["id"] == "CAMP-1"

    def test_non_dict_alerts_result_gives_empty_marketing_alerts(self, monkeypatch):
        _stub_engines(monkeypatch, list_alerts_api=lambda role, status=None: None)

        result = mm._campaigns("ADMIN")

        assert result["compliance_approval"]["count"] == 0


class TestCampaigns:

    def test_no_query_delegates_to_private_campaigns(self, monkeypatch):
        monkeypatch.setattr(mm, "_campaigns", lambda role: {"total_campaigns": 9})

        assert mm.campaigns("ADMIN") == {"total_campaigns": 9}

    def test_query_not_matching_camp_prefix_falls_through(self, monkeypatch):
        monkeypatch.setattr(mm, "_campaigns", lambda role: {"total_campaigns": 3})

        assert mm.campaigns("ADMIN", query="spring sale") == {"total_campaigns": 3}

    def test_camp_prefix_error_short_circuits(self, monkeypatch):
        related_called = []
        _stub_engines(
            monkeypatch,
            get_entity_by_id=lambda role, q: {"error": "not found"},
            get_related_entities=lambda role, q: related_called.append(q) or [],
        )

        result = mm.campaigns("ADMIN", query="camp-00001")

        assert result == {"error": "not found"}
        assert related_called == []

    def test_camp_prefix_success_includes_related_entities(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            get_entity_by_id=lambda role, q: {"id": "CAMP-00001"},
            get_related_entities=lambda role, q: [{"id": "LEAD-1"}],
        )

        result = mm.campaigns("ADMIN", query="CAMP-00001")

        assert result == {"campaign": {"id": "CAMP-00001"}, "related_entities": [{"id": "LEAD-1"}]}


# ---------------------------------------------------------------------------
# _audiences()
# ---------------------------------------------------------------------------


class TestAudiences:

    def test_full_path(self, monkeypatch):
        _use_ledger(
            monkeypatch,
            [
                _lead("LEAD-1", pipeline_state="LOST"),
                _lead("LEAD-2", pipeline_state="NEW"),
            ],
            relationships=[
                _FakeRelationship("CUST-1", "OWNS"),
                _FakeRelationship("CUST-2", "OWNS"),
                _FakeRelationship("CUST-1", "OWNS"),  # duplicate -- deduped by set
                _FakeRelationship("CUST-3", "ASSIGNED_TO"),  # wrong type -- ignored
            ],
        )
        _stub_engines(
            monkeypatch,
            marketing_database_mining=lambda role: {"count": 4, "candidates": [{"id": f"C{i}"} for i in range(15)]},
            preview_audience=_make_preview_audience({
                ("finance_renewal", frozenset({"months_to_maturity": 6}.items())): {"count": 5, "sample": []},
                ("retention", frozenset({"months_since_service": 12}.items())): {"count": 6, "sample": []},
                ("retention", frozenset({"months_since_service": 0}.items())): {"count": 1, "sample": []},
                ("accessory_accelerator", frozenset({"days_since_sale": 30}.items())): {"count": 2, "sample": []},
            }),
        )

        result = mm._audiences("ADMIN")

        assert result["equity_mining"]["count"] == 4
        assert len(result["equity_mining"]["sample"]) == 10
        assert result["lease_maturity"]["count"] == 5
        assert result["service_defection"]["count"] == 6
        assert result["service_conquest"]["count"] == 1
        assert result["upgrade_opportunities"]["count"] == 2
        assert result["previous_buyers"]["count"] == 2
        assert result["unsold_leads"]["count"] == 1


# ---------------------------------------------------------------------------
# events()
# ---------------------------------------------------------------------------


class TestEvents:

    def test_query_matches_alerts_and_events_by_substring(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            list_alerts=lambda status=None: [
                _FakeEntity("TRIGGER_ALERT", "ALERT-1", {"target_name": "John Smith", "headline": "Equity"}),
                _FakeEntity("TRIGGER_ALERT", "ALERT-2", {"target_name": "Jane Doe", "headline": "Lease"}),
            ],
            list_dealership_events=lambda: [
                _FakeEntity("EVENT", "EVT-1", {"name": "Fall Sale", "location": "Showroom"}),
                _FakeEntity("EVENT", "EVT-2", {"name": "Spring Blast", "location": "Lot"}),
            ],
        )

        result = mm.events("ADMIN", query="john")

        assert result["count"] == 1
        assert result["results"]["alerts"] == [{
            "id": "ALERT-1", "alert_type": None, "headline": "Equity", "target_name": "John Smith", "status": None,
        }]
        assert result["results"]["events"] == []

    def test_no_query_full_timeline_and_events(self, monkeypatch):
        scan_called = []
        _stub_engines(
            monkeypatch,
            run_trigger_scan=lambda: scan_called.append(True),
            list_alerts=lambda status=None: [
                _FakeEntity("TRIGGER_ALERT", "ALERT-1", {"alert_type": "equity_mining", "urgency": "high"}),
                _FakeEntity("TRIGGER_ALERT", "ALERT-2", {"alert_type": "equity_mining", "urgency": "low"}),
                _FakeEntity("TRIGGER_ALERT", "ALERT-3", {"alert_type": "lease_maturity", "urgency": "high"}),
            ],
            list_event_types=lambda: [{"key": "sale_event"}],
            list_dealership_events=lambda: [
                _FakeEntity("EVENT", "EVT-1", {"status": "scheduled"}),
                _FakeEntity("EVENT", "EVT-2", {"status": "completed"}),
                _FakeEntity("EVENT", "EVT-3", {"status": "scheduled"}),
            ],
        )

        result = mm.events("ADMIN")

        assert scan_called == [True]
        assert result["timeline"]["open_count"] == 3
        assert result["timeline"]["by_type"] == {"equity_mining": 2, "lease_maturity": 1}
        assert result["timeline"]["by_urgency"] == {"high": 2, "low": 1}
        assert result["events"]["total"] == 3
        assert result["events"]["upcoming_count"] == 2
        assert result["events"]["event_types"] == [{"key": "sale_event"}]


# ---------------------------------------------------------------------------
# website()
# ---------------------------------------------------------------------------


class TestWebsite:

    def test_query_filters_by_website_type(self, monkeypatch):
        _stub_engines(monkeypatch, search_entities=lambda role, query: [
            {"entity_type": mm.WEBSITE, "id": "SITE-1"},
            {"entity_type": mm.CAMPAIGN, "id": "CAMP-1"},
        ])

        result = mm.website("ADMIN", query="ford")

        assert result == {"query": "ford", "count": 1, "results": [{"entity_type": mm.WEBSITE, "id": "SITE-1"}]}

    def test_no_query_full_path(self, monkeypatch):
        site1 = _FakeEntity(mm.WEBSITE, "SITE-1", {
            "status": "published", "mode": "traditional",
            "admin_settings": {"meta_title": "Best Dealer"},
            "pages": {"home": {"sections": [{"section_key": "inventory_grid"}, {"section_key": "contact_form"}]}},
        })
        site2 = _FakeEntity(mm.WEBSITE, "SITE-2", {
            "status": "draft", "mode": "dealer_gpt",
            "admin_settings": {"custom_domain": "example.com"},
            "pages": {"inventory": {"sections": [{"section_key": "inventory_grid"}]}},
        })
        _stub_engines(
            monkeypatch,
            list_websites=lambda: [site1, site2],
            list_personal_sites=lambda: [
                _FakeEntity("PERSONAL_SITE", "PS-1", {"status": "active"}),
                _FakeEntity("PERSONAL_SITE", "PS-2", {"status": "draft"}),
            ],
            list_chat_sessions=lambda: [
                _FakeEntity("WEBSITE_CHAT_SESSION", "CS-1", {"status": "open", "lead_id": None}),
                _FakeEntity("WEBSITE_CHAT_SESSION", "CS-2", {"status": "closed", "lead_id": "LEAD-1"}),
            ],
            SECTION_TEMPLATES={"inventory_grid": {}, "hero_banner": {}},
            SITE_TEMPLATES={"traditional": {"key": "traditional", "name": "Traditional", "dealer_type": "independent"}},
        )

        result = mm.website("ADMIN")

        assert result["total_websites"] == 2
        assert result["by_status"] == {"published": 1, "draft": 1}
        assert result["by_mode"] == {"traditional": 1, "dealer_gpt": 1}
        assert result["inventory_widgets"]["count"] == 2
        assert result["forms"]["count"] == 1
        assert result["seo_pages"]["sites_with_seo_configured"] == 1
        assert result["seo_pages"]["sites_with_custom_domain"] == 1
        assert result["site_builder"]["available_section_templates"] == ["inventory_grid", "hero_banner"]
        assert result["site_builder"]["available_layout_templates"] == [
            {"key": "traditional", "name": "Traditional", "dealer_type": "independent"},
        ]
        assert result["personal_sites"]["total"] == 2
        assert result["personal_sites"]["by_status"] == {"active": 1, "draft": 1}
        assert result["live_chat"]["total_sessions"] == 2
        assert result["live_chat"]["by_status"] == {"open": 1, "closed": 1}
        assert result["live_chat"]["promoted_to_lead"] == 1


# ---------------------------------------------------------------------------
# _opportunities()
# ---------------------------------------------------------------------------


class TestOpportunities:

    def test_full_path(self, monkeypatch):
        monkeypatch.setattr(mm, "_avg_funded_deal_gross", lambda: 2000.0)
        _stub_engines(
            monkeypatch,
            marketing_database_mining=lambda role: {"count": 7, "candidates": [{"id": "E1"}]},
            preview_audience=_make_preview_audience({
                ("finance_renewal", frozenset({"months_to_maturity": 6}.items())): {
                    "count": 5, "sample": [{"id": "L1"}, {"id": "L2"}, {"id": "L3"}, {"id": "L4"}],
                },
                ("inventory_ads", frozenset()): {"count": 3, "sample": []},
                ("retention", frozenset({"months_since_service": 6}.items())): {
                    "count": 4, "sample": [{"id": "S1"}, {"id": "S2"}, {"id": "S3"}],
                },
                ("retention", frozenset({"months_since_service": 12}.items())): {"count": 6, "sample": []},
            }),
        )

        result = mm._opportunities("ADMIN")

        assert result["equity_opportunities"]["count"] == 7
        assert result["equity_opportunities"]["sample"] == [{"id": "E1"}]
        assert result["trade_opportunities"] == result["equity_opportunities"]
        assert result["conquest_opportunities"]["projected_revenue_estimate"] == 6000.0
        assert result["lease_opportunities"]["projected_revenue_estimate"] == 10000.0
        assert result["service_opportunities"]["projected_revenue_estimate"] == 8000.0
        assert result["retention_opportunities"]["projected_revenue_estimate"] == 12000.0
        assert result["who_to_contact_today"] == [{"id": "L1"}, {"id": "L2"}, {"id": "L3"}, {"id": "S1"}, {"id": "S2"}]


# ---------------------------------------------------------------------------
# _pipeline_board()
# ---------------------------------------------------------------------------


class TestPipelineBoard:

    def test_groups_leads_by_pipeline_state(self, monkeypatch):
        states = mm.PIPELINE_STATES
        other_state = next((s for s in states if s != "NEW"), states[0])
        _use_ledger(monkeypatch, [
            _lead("LEAD-1", pipeline_state=None, source="Web"),
            _lead("LEAD-2", pipeline_state=other_state, source="Phone"),
        ])

        result = mm._pipeline_board()

        assert result["states"] == states
        assert result["total"] == 2
        assert len(result["columns"]["NEW"]) == 1
        assert result["columns"]["NEW"][0]["id"] == "LEAD-1"
        assert len(result["columns"][other_state]) == 1
        assert result["columns"][other_state][0]["source"] == "Phone"

    def test_setdefault_handles_state_not_in_pipeline_states(self, monkeypatch):
        _use_ledger(monkeypatch, [_lead("LEAD-1", pipeline_state="BOGUS_STATE")])

        result = mm._pipeline_board()

        assert result["columns"]["BOGUS_STATE"][0]["id"] == "LEAD-1"


# ---------------------------------------------------------------------------
# _lists_summary()
# ---------------------------------------------------------------------------


class TestListsSummary:

    def test_summarizes_lists(self, monkeypatch):
        _stub_engines(monkeypatch, list_lists=lambda: [
            _FakeEntity("MARKETING_LIST", "LIST-1", {"name": "VIPs", "member_ids": ["CUST-1", "CUST-2"], "source": "manual"}),
            _FakeEntity("MARKETING_LIST", "LIST-2", {"name": "Empty List", "member_ids": None, "source": "campaign"}),
        ])

        result = mm._lists_summary()

        assert result["total_lists"] == 2
        assert result["lists"][0]["member_count"] == 2
        assert result["lists"][1]["member_count"] == 0


# ---------------------------------------------------------------------------
# crm()
# ---------------------------------------------------------------------------


class TestCrm:

    def test_no_query_composes_private_helpers(self, monkeypatch):
        monkeypatch.setattr(mm, "_pipeline_board", lambda: {"total": 5})
        monkeypatch.setattr(mm, "_lists_summary", lambda: {"total_lists": 2})
        monkeypatch.setattr(mm, "_campaigns", lambda role: {"total_campaigns": 3})
        monkeypatch.setattr(mm, "_audiences", lambda role: {"equity_mining": {}})
        monkeypatch.setattr(mm, "_opportunities", lambda role: {"equity_opportunities": {}})
        _stub_engines(
            monkeypatch,
            list_smart_audience_presets=lambda: [{"key": "truck_owners"}],
            list_smart_audiences=lambda: [_FakeEntity("SMART_AUDIENCE", f"SA-{i}", {"name": f"Segment {i}"}) for i in range(12)],
            lead_scoring_leaderboard=lambda limit=10: {"count": 20, "by_tier": {"hot": 5}, "leads": [{"id": "LEAD-1"}]},
        )

        result = mm.crm("ADMIN")

        assert result["pipeline"] == {"total": 5}
        assert result["lists"] == {"total_lists": 2}
        assert result["campaigns"] == {"total_campaigns": 3}
        assert result["audiences"] == {"equity_mining": {}}
        assert result["opportunities"] == {"equity_opportunities": {}}
        assert result["smart_audiences"]["presets"] == [{"key": "truck_owners"}]
        assert result["smart_audiences"]["saved_count"] == 12
        assert len(result["smart_audiences"]["saved"]) == 10
        assert result["lead_scoring"]["total_scored"] == 20
        assert result["lead_scoring"]["by_tier"] == {"hot": 5}
        assert result["lead_scoring"]["top_leads"] == [{"id": "LEAD-1"}]

    def test_camp_prefix_query(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            get_entity_by_id=lambda role, q: {"id": "CAMP-1"},
            get_related_entities=lambda role, q: [{"id": "LEAD-1"}],
        )

        result = mm.crm("ADMIN", query="CAMP-00001")

        assert result == {"campaign": {"id": "CAMP-1"}, "related_entities": [{"id": "LEAD-1"}]}

    def test_lead_prefix_query_error_short_circuits(self, monkeypatch):
        related_called = []
        _stub_engines(
            monkeypatch,
            get_entity_by_id=lambda role, q: {"error": "not found"},
            get_related_entities=lambda role, q: related_called.append(q) or [],
        )

        result = mm.crm("ADMIN", query="LEAD-00001")

        assert result == {"error": "not found"}
        assert related_called == []

    def test_cust_prefix_query_uses_customer_360(self, monkeypatch):
        monkeypatch.setattr("core.customer_360.get_customer_360", lambda role, q: {"customer_id": q, "timeline": []})

        result = mm.crm("ADMIN", query="CUST-00001")

        assert result == {"customer_id": "CUST-00001", "timeline": []}

    def test_free_text_query_filters_by_type(self, monkeypatch):
        _stub_engines(monkeypatch, search_entities=lambda role, query: [
            {"entity_type": mm.LEAD, "id": "LEAD-1"},
            {"entity_type": mm.VEHICLE, "id": "VEH-1"},
        ])

        result = mm.crm("ADMIN", query="John Doe")

        assert result == {"query": "John Doe", "count": 1, "results": [{"entity_type": mm.LEAD, "id": "LEAD-1"}]}


# ---------------------------------------------------------------------------
# purls()
# ---------------------------------------------------------------------------


class TestPurls:

    def test_purl_prefix_not_found(self, monkeypatch):
        monkeypatch.setattr("core.purls.get_purl_dashboard", lambda role: {"should": "not be called"})
        monkeypatch.setattr("core.purls._get_purl", lambda q: None)

        result = mm.purls("ADMIN", query="PURL-00001")

        assert result == {"error": "PURL 'PURL-00001' not found"}

    def test_purl_prefix_found_returns_analytics(self, monkeypatch):
        monkeypatch.setattr("core.purls._get_purl", lambda q: {"id": q})
        monkeypatch.setattr("core.purls.get_purl_analytics", lambda q: {"visits": 10})

        result = mm.purls("ADMIN", query="PURL-00001")

        assert result == {"purl_id": "PURL-00001", "analytics": {"visits": 10}}

    def test_no_query_returns_dashboard(self, monkeypatch):
        monkeypatch.setattr("core.purls.get_purl_dashboard", lambda role: {"total": 5})

        assert mm.purls("ADMIN") == {"total": 5}

    def test_non_purl_query_falls_through_to_dashboard(self, monkeypatch):
        monkeypatch.setattr("core.purls.get_purl_dashboard", lambda role: {"total": 5})

        assert mm.purls("ADMIN", query="john smith") == {"total": 5}


# ---------------------------------------------------------------------------
# email_sms()
# ---------------------------------------------------------------------------


class TestEmailSms:

    def test_query_filters_by_customer_lead_type(self, monkeypatch):
        _stub_engines(monkeypatch, search_entities=lambda role, query: [
            {"entity_type": mm.CUSTOMER, "id": "CUST-1"},
            {"entity_type": mm.CAMPAIGN, "id": "CAMP-1"},
        ])

        result = mm.email_sms("ADMIN", query="john")

        assert result == {"query": "john", "count": 1, "results": [{"entity_type": mm.CUSTOMER, "id": "CUST-1"}]}

    def test_no_query_full_path(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            list_email_templates=lambda: [
                _FakeEntity(mm.EMAIL_TEMPLATE, "TMPL-1", {"channel": "email", "ai_generated": True, "linked_campaign_id": "CAMP-1"}),
                _FakeEntity(mm.EMAIL_TEMPLATE, "TMPL-2", {"channel": "sms", "ai_generated": False, "linked_campaign_id": None}),
                _FakeEntity(mm.EMAIL_TEMPLATE, "TMPL-3", {"channel": "email", "ai_generated": False, "linked_campaign_id": "CAMP-2"}),
            ],
            list_block_types=lambda: [{"key": "hero"}],
            list_campaign_types=lambda: [{"key": "retention"}],
        )

        result = mm.email_sms("ADMIN")

        assert result["total_templates"] == 3
        assert result["by_channel"] == {"email": 2, "sms": 1}
        assert result["ai_generated_count"] == 1
        assert result["attached_to_campaign_count"] == 2
        assert result["block_catalog"] == [{"key": "hero"}]
        assert result["available_campaign_types"] == [{"key": "retention"}]


# ---------------------------------------------------------------------------
# social_reputation()
# ---------------------------------------------------------------------------


class TestSocialReputation:

    def test_query_matches_reviews_and_posts(self, monkeypatch):
        _use_ledger(monkeypatch, [
            _review("REV-1", author_name="John Doe", text="great service"),
            _review("REV-2", author_name="Jane", text="bad service"),
        ])
        _stub_engines(monkeypatch, list_social_posts=lambda: [
            _FakeEntity("SOCIAL_POST", "POST-1", {"content": "promo sale"}),
            _FakeEntity("SOCIAL_POST", "POST-2", {"content": "john visited today"}),
        ])

        result = mm.social_reputation("ADMIN", query="john")

        assert result["count"] == 2
        assert result["results"]["reviews"][0]["id"] == "REV-1"
        assert result["results"]["posts"][0]["id"] == "POST-2"

    def test_no_query_full_path(self, monkeypatch):
        long_content = "x" * 200
        _stub_engines(
            monkeypatch,
            marketing_reputation_summary=lambda role: {
                "unresponded_negative": [{"id": "REV-1"}], "unresponded_negative_count": 1, "avg_rating": 4.2,
            },
            list_social_platforms=lambda: ["facebook", "instagram"],
            list_social_posts=lambda: [
                _FakeEntity("SOCIAL_POST", f"POST-{i}", {"content": long_content if i == 0 else "short", "status": "draft"})
                for i in range(12)
            ],
            get_social_calendar=lambda: {"days": []},
            list_bad_review_alerts_api=lambda role: [{"id": "ALERT-1"}],
            get_competitor_tracking_api=lambda role: {"basis": "simulated_peer_data"},
        )

        result = mm.social_reputation("ADMIN")

        assert result["social"]["platforms"] == ["facebook", "instagram"]
        assert len(result["social"]["recent_posts"]) == 10
        assert len(result["social"]["recent_posts"][0]["content"]) == 120
        assert result["social"]["calendar"] == {"days": []}
        assert result["reputation"]["avg_rating"] == 4.2
        assert result["reputation"]["response_management"]["count"] == 1
        assert result["reputation"]["response_management"]["queue"] == [{"id": "REV-1"}]
        assert result["reputation"]["bad_review_alerts"] == [{"id": "ALERT-1"}]
        assert result["reputation"]["competitor_tracking"] == {"basis": "simulated_peer_data"}


# ---------------------------------------------------------------------------
# advertising()
# ---------------------------------------------------------------------------


class TestAdvertising:

    def test_query_filters_by_name_or_headline(self, monkeypatch):
        _stub_engines(monkeypatch, list_ad_campaigns=lambda: [
            _FakeEntity("AD_CAMPAIGN", "AD-1", {"name": "Spring Sale", "headline": "Big Savings", "platform": "meta", "status": "active"}),
            _FakeEntity("AD_CAMPAIGN", "AD-2", {"name": "Summer Blast", "headline": "Hot Deals", "platform": "google", "status": "draft"}),
        ])

        result = mm.advertising("ADMIN", query="spring")

        assert result["count"] == 1
        assert result["results"][0]["id"] == "AD-1"

    def test_no_query_full_path(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            list_ad_platforms=lambda: ["meta", "google"],
            list_ad_objectives=lambda: ["awareness"],
            list_ad_campaigns=lambda: [
                _FakeEntity("AD_CAMPAIGN", "AD-1", {"platform": "meta", "status": "active"}),
                _FakeEntity("AD_CAMPAIGN", "AD-2", {"platform": "google", "status": "draft"}),
                _FakeEntity("AD_CAMPAIGN", "AD-3", {"platform": "meta", "status": "active"}),
            ],
        )

        result = mm.advertising("ADMIN")

        assert result["platforms"] == ["meta", "google"]
        assert result["objectives"] == ["awareness"]
        assert result["total_campaigns"] == 3
        assert result["by_status"] == {"active": 2, "draft": 1}
        assert result["by_platform"] == {"meta": 2, "google": 1}


# ---------------------------------------------------------------------------
# studio() / analytics()
# ---------------------------------------------------------------------------


class TestStudio:

    def test_thin_passthrough(self, monkeypatch):
        monkeypatch.setattr("core.marketing_studio_api.get_studio_overview_api", lambda role: {"drafts": []})

        assert mm.studio("ADMIN") == {"drafts": []}


class TestAnalytics:

    def test_thin_passthrough(self, monkeypatch):
        monkeypatch.setattr(mm, "get_marketing_roi_dashboard_api", lambda role: {"channel_mix": []})

        assert mm.analytics("ADMIN") == {"channel_mix": []}


# ---------------------------------------------------------------------------
# reporting()
# ---------------------------------------------------------------------------


class TestReporting:

    def test_full_path(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            list_campaigns=lambda: [
                _campaign_entity("CAMP-1", status="active", sent_count=10),
                _campaign_entity("CAMP-2", status="completed", sent_count=5),
                _campaign_entity("CAMP-3", status="draft", sent_count=100),
            ],
            list_websites=lambda: [
                _FakeEntity(mm.WEBSITE, "SITE-1", {"status": "published"}),
                _FakeEntity(mm.WEBSITE, "SITE-2", {"status": "draft"}),
            ],
            marketing_database_mining=lambda role: {"count": 4},
            preview_audience=_make_preview_audience({
                ("finance_renewal", frozenset({"months_to_maturity": 6}.items())): {"count": 6},
                ("retention", frozenset({"months_since_service": 12}.items())): {"count": 8},
            }),
            readiness_predictions_api=lambda: {"departments": [
                {"department": "marketing", "leads_generated": {"tomorrow": 10}},
                {"department": "sales", "units_sold": {}},
            ]},
        )

        result = mm.reporting("ADMIN")

        assert result["campaign_reports"] == {"total_campaigns": 3, "active_or_completed": 2, "total_audience_reached": 15}
        assert result["website_reports"] == {"total_websites": 2, "published": 1}
        assert result["opportunity_reports"] == {"equity_pool_size": 4, "lease_pool_size": 6, "retention_pool_size": 8}
        assert result["forecasting"] == {"department": "marketing", "leads_generated": {"tomorrow": 10}}
        assert result["department_intelligence"] == mm._DI_GAP_NOTE

    def test_no_marketing_forecast_entry_gives_none(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            readiness_predictions_api=lambda: {"departments": [{"department": "sales", "units_sold": {}}]},
        )

        result = mm.reporting("ADMIN")

        assert result["forecasting"] is None
