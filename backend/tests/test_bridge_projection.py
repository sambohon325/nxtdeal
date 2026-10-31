"""Review previews distinguish actual field updates from retained observations."""
import pytest

from core import dealer_bridge as b
from core.bridge_lineage import lookup
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, CSV, setup, imported, candidate_job, isolated  # noqa: F401


def test_new_record_and_update_preview_have_exact_field_changes():
    system, mapping = setup()
    first = b.simulate_mapping(A, mapping, CSV)["rows"][0]
    assert first["effect"] == "create"
    assert all(not change["before_present"] for change in first["changes"])
    imported(CSV, mapping)
    updated = CSV.replace("2026-01-01", "2026-01-02").replace("Ada,", "Updated,")
    row = b.simulate_mapping(A, mapping, updated)["rows"][0]
    assert row["effect"] == "update"
    assert row["changes"] == [{"field": "first_name", "before_present": True, "before": "Ada", "after": "Updated"}]
    assert row["current_values"]["first_name"] == "Ada"


def test_native_alias_difference_is_visible_even_when_canonical_value_matches_source():
    system, mapping = setup()
    imported(CSV, mapping)
    target = ledger.get_entity(lookup(A, system, "customers", "1")["canonical_id"])
    target.attributes.update(FirstName="Native edit", internal_secret="must-not-appear")
    content = CSV.replace("2026-01-01", "2026-01-02")
    row = b.simulate_mapping(A, mapping, content)["rows"][0]
    assert row["changes"] == [{"field": "first_name", "before_present": True, "before": "Ada", "after": "Ada", "legacy_before": "Native edit"}]
    assert row["legacy_conflicts"][0]["legacy_value"] == "Native edit"
    assert "must-not-appear" not in str(row)
    history = lookup(A, system, "customers", "1")
    assert history["legacy_conflicts"] == row["legacy_conflicts"]
    assert history["observations"][0]["values"]["first_name"] == "Ada"


def test_duplicate_and_historical_snapshots_never_claim_current_field_updates():
    system, mapping = setup()
    imported(CSV.replace("2026-01-01", "2026-03-01"), mapping)
    for content, effect in [(CSV, "history_only"), (CSV.replace("2026-01-01", "2026-03-01"), "none")]:
        row = b.simulate_mapping(A, mapping, content)["rows"][0]
        assert row["effect"] == effect and row["changes"] == []


def test_human_identity_link_explains_preservation_without_update_changes():
    mapping, job, candidate = candidate_job()
    b.resolve_identity(B, job, 1, candidate["id"], candidate["review_token"], "Verified existing customer identity")
    row = b.validate(A, job)[0]
    assert row["effect"] == "preserve_current" and row["changes"] == []
    assert row["current_values"]["first_name"] == "Original"


def test_intervening_native_alias_change_invalidates_reviewed_preview():
    system, mapping = setup()
    imported(CSV, mapping)
    job = b.stage(A, mapping, CSV.replace("2026-01-01", "2026-01-02"))["id"]
    b.validate(A, job)
    target = ledger.get_entity(lookup(A, system, "customers", "1")["canonical_id"])
    target.attributes["FirstName"] = "Changed after review"
    with pytest.raises(ValueError, match="Graph changed"):
        b.activate(B, job)
    assert target.attributes["FirstName"] == "Changed after review"


def test_invalid_foreign_target_never_leaks_current_values_in_preview():
    system, mapping = setup()
    imported(CSV, mapping)
    target = ledger.get_entity(lookup(A, system, "customers", "1")["canonical_id"])
    target.attributes.update(workspace_id="foreign", first_name="foreign-private-value", FirstName="foreign-private-value")
    row = b.simulate_mapping(A, mapping, CSV.replace("2026-01-01", "2026-01-02"))["rows"][0]
    assert row["effect"] == "blocked" and row["current_values"] == {}
    assert row["changes"] == [] and "foreign-private-value" not in str(row)
