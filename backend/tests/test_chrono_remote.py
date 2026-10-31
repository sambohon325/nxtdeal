import pytest
from intelligence import chrono_remote as chrono


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv("NXTDEAL_CHRONO_BUSINESS", "test-business")
    monkeypatch.setattr(chrono, "get_secret", lambda _: "synthetic-test-token")


def test_missing_configuration_never_calls_remote(monkeypatch):
    monkeypatch.setattr(chrono, "get_secret", lambda _: None)
    monkeypatch.setattr(chrono, "fetch", lambda _: pytest.fail("No request allowed"))
    assert chrono.configuration()["missing"] == ["NXTDEAL_CHRONO_TOKEN"]
    assert chrono.read({"role": "ADMIN"}, "workspace-summary")["status"] == "unavailable"


def test_summary_is_bounded_and_excludes_source_record_bodies(monkeypatch):
    paths = []
    def fetch(path):
        paths.append(path)
        return {"business": "test-business", "checked_at": "2026-10-03T12:00:00Z", "claim_kinds": {"observed": 1}, "recent_changes": [{"private": "body"}], "attention_total": 2}
    monkeypatch.setattr(chrono, "fetch", fetch)
    result = chrono.read({"role": "ADMIN"}, "workspace-summary")
    assert result["status"] == "available"
    assert "recent_changes" not in result["data"]
    assert paths[0].startswith("/v1/businesses/test-business/workspace-summary?")


def test_history_keeps_original_cutoffs_and_reports(monkeypatch):
    payload = {"business": "test-business", "as_of": "original-as-of", "known_at": "original-known-at", "reports": [{"kind": "saved"}], "has_more": True, "next_before": "12"}
    monkeypatch.setattr(chrono, "fetch", lambda _: payload)
    result = chrono.read({"role": "OPERATIONS"}, "analysis-history")
    assert result["data"] == payload
    assert result["evidence_kind"] == "saved_external_analysis"


@pytest.mark.parametrize("payload", [{"business": "other"}, {"business": "test-business", "reports": []}, None])
def test_untrusted_scope_or_shape_fails_closed(monkeypatch, payload):
    monkeypatch.setattr(chrono, "fetch", lambda _: payload)
    assert chrono.read({"role": "ADMIN"}, "analysis-history")["status"] == "unavailable"


def test_errors_are_sanitized_and_sales_cannot_read_company(monkeypatch):
    def fail(_): raise RuntimeError("Bearer synthetic-test-token")
    monkeypatch.setattr(chrono, "fetch", fail)
    assert "synthetic-test-token" not in str(chrono.read({"role": "ADMIN"}, "analysis-history"))
    with pytest.raises(PermissionError): chrono.read({"role": "SALES"}, "workspace-summary")


def test_redirects_never_forward_credentials():
    assert chrono.NoRedirect().redirect_request(None, None, None, None, None, None) is None
