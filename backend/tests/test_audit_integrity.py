"""
Tests for core/audit_integrity.py (tamper-evidence verification for the audit
log's hash chain -- security-hardening pass, 2026-07-20). Closes Code Auditor
finding CAF-00123 (missing_test_coverage) for one of the highest-risk
untested security modules.

Covers both real checks this module provides:
  - verify_chain() -- internal hash-chain consistency (content_tampered /
    broken_link / broken_genesis / unverifiable_legacy_events).
  - verify_against_checkpoint() -- the currently-loaded chain's tail vs. a
    separately persisted checkpoint file (checkpoint_missing /
    checkpoint_mismatch / ok), which is what catches a wholesale replacement
    of audit.json that verify_chain() alone can't (a self-consistent but
    entirely different fake chain still "passes" verify_chain()).
  - full_integrity_report() -- the composed payload backing GET /audit/integrity.

Two real pieces of test-isolation are needed here, layered on top of what
tests/conftest.py already provides platform-wide:
  1. core.audit.audit_log is an in-memory singleton, not covered by
     conftest.py's file-based storage-path isolation -- reset explicitly via
     audit_log.reset(), matching tests/test_audit.py's own established
     fresh_audit_log fixture convention exactly.
  2. core.audit_integrity.write_checkpoint() persists a REAL file
     (storage_path("audit_chain_checkpoint.json")) into the isolated temp
     storage dir conftest.py already set up -- but unlike audit_log, that
     file is not automatically reset between tests within this file (it's a
     real file on disk, not an in-memory object), so this file's own
     fixture also deletes it before and after every test.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core import audit as audit_module
from core import audit_integrity
from core.audit import GENESIS_HASH, compute_event_hash, AuditEvent
from core.storage_paths import storage_path


@pytest.fixture(autouse=True)
def fresh_audit_state():
    """Resets the in-memory audit_log singleton AND removes any real
    checkpoint file left over from a prior test in this same process, before
    and after every test -- so no test can observe another test's chain or
    checkpoint."""

    audit_module.audit_log.reset()
    _remove_checkpoint_file()

    yield

    audit_module.audit_log.reset()
    _remove_checkpoint_file()


def _remove_checkpoint_file():
    path = storage_path("audit_chain_checkpoint.json")
    if os.path.exists(path):
        os.remove(path)


def _record(event_type="test_event", entity_id="ENT-1", actor="tester",
            summary="A test event", details=None):
    """Thin wrapper around the real audit_log.record() -- every event this
    produces goes through the real hash-chaining logic in core/audit.py, not
    a hand-built fixture, so these tests exercise the real chain-building
    path, not a mock of it."""

    return audit_module.audit_log.record(
        event_type=event_type,
        entity_id=entity_id,
        actor=actor,
        summary=summary,
        details=details or {}
    )


# ---------------------------------------------------------------------------
# verify_chain()
# ---------------------------------------------------------------------------


class TestVerifyChainEmptyAndTrivial:

    def test_empty_chain_is_valid(self):
        result = audit_integrity.verify_chain()

        assert result["valid"] is True
        assert result["total_events"] == 0
        assert result["verified_events"] == 0
        assert result["unverifiable_legacy_events"] == 0
        assert result["issues"] == []

    def test_single_real_event_is_valid(self):
        _record()

        result = audit_integrity.verify_chain()

        assert result["valid"] is True
        assert result["total_events"] == 1
        assert result["verified_events"] == 1
        assert result["issues"] == []

    def test_single_real_event_anchors_on_genesis_hash(self):
        event = _record()

        assert event.prev_hash == GENESIS_HASH


class TestVerifyChainRealMultiEventSequence:

    def test_a_real_correctly_chained_sequence_is_fully_valid(self):
        for i in range(5):
            _record(entity_id=f"ENT-{i}", summary=f"Event number {i}")

        result = audit_integrity.verify_chain()

        assert result["valid"] is True
        assert result["total_events"] == 5
        assert result["verified_events"] == 5
        assert result["unverifiable_legacy_events"] == 0
        assert result["issues"] == []

    def test_each_events_prev_hash_matches_the_actual_prior_hash(self):
        first = _record()
        second = _record()
        third = _record()

        assert second.prev_hash == first.hash
        assert third.prev_hash == second.hash

    def test_explicit_events_param_overrides_the_default_in_memory_list(self):
        # Two real events recorded, but we ask verify_chain() to check only
        # the second one, alone, treating it as its own chain start.
        _record()
        second = _record()

        result_full = audit_integrity.verify_chain()
        result_scoped = audit_integrity.verify_chain(events=[second])

        assert result_full["total_events"] == 2
        assert result_scoped["total_events"] == 1
        # The scoped check treats `second` as the first hash-chained event it
        # sees -- since its own real prev_hash isn't GENESIS_HASH (it really
        # does follow a first event), this is expected to flag broken_genesis
        # rather than silently passing, which is the correct, honest behavior
        # for a caller that hands it a truncated sub-list.
        assert result_scoped["valid"] is False
        assert result_scoped["issues"][0]["issue_type"] == "broken_genesis"

    def test_empty_explicit_events_list_is_valid(self):
        _record()

        result = audit_integrity.verify_chain(events=[])

        assert result["valid"] is True
        assert result["total_events"] == 0


class TestVerifyChainContentTampering:

    def test_mutating_an_events_summary_after_recording_is_caught(self):
        event = _record(summary="original summary")
        event.summary = "tampered summary"

        result = audit_integrity.verify_chain()

        assert result["valid"] is False
        issue = result["issues"][0]
        assert issue["issue_type"] == "content_tampered"
        assert issue["event_id"] == event.id

    def test_mutating_details_after_recording_is_caught(self):
        event = _record(details={"amount": 100})
        event.details = {"amount": 999999}

        result = audit_integrity.verify_chain()

        assert result["valid"] is False
        assert result["issues"][0]["issue_type"] == "content_tampered"

    def test_mutating_actor_after_recording_is_caught(self):
        event = _record(actor="real_employee")
        event.actor = "impersonator"

        result = audit_integrity.verify_chain()

        assert result["valid"] is False
        assert result["issues"][0]["issue_type"] == "content_tampered"

    def test_tampering_a_middle_event_does_not_falsely_flag_its_neighbors(self):
        first = _record(summary="first")
        second = _record(summary="second")
        third = _record(summary="third")

        second.summary = "TAMPERED"

        result = audit_integrity.verify_chain()

        issue_ids = [i["event_id"] for i in result["issues"]]
        # The tampered event's own content hash breaks -- but note that its
        # OWN stored hash (never recomputed after tampering) still matches
        # what the third event's prev_hash expects, so the link to `third`
        # is not separately broken. Only the one real content mismatch
        # should be reported, not three cascading false positives.
        assert issue_ids == [second.id]
        assert result["verified_events"] == 2

    def test_verified_count_excludes_tampered_events(self):
        _record()
        tampered = _record()
        _record()
        tampered.summary = "changed"

        result = audit_integrity.verify_chain()

        assert result["total_events"] == 3
        assert result["verified_events"] == 2


class TestVerifyChainBrokenLink:

    def test_a_manually_spliced_event_with_wrong_prev_hash_is_caught(self):
        _record()
        _record()

        # Hand-build a real AuditEvent whose content hash is internally
        # correct (so it would pass a content check on its own) but whose
        # prev_hash doesn't match the real preceding event's actual hash --
        # simulating an event deleted/reordered/inserted without correctly
        # rebuilding the chain.
        fake_prev_hash = "0" * 64  # deliberately wrong -- not the real 2nd event's hash
        forged_hash = compute_event_hash(
            "AUDIT-FORGED", "forged_event", "ENT-X", "attacker",
            "a spliced-in event", {}, "2026-01-01T00:00:00+00:00", fake_prev_hash
        )
        forged_event = AuditEvent(
            id="AUDIT-FORGED",
            event_type="forged_event",
            entity_id="ENT-X",
            actor="attacker",
            summary="a spliced-in event",
            details={},
            timestamp="2026-01-01T00:00:00+00:00",
            prev_hash=fake_prev_hash,
            hash=forged_hash
        )

        events = audit_module.audit_log.get_all() + [forged_event]

        result = audit_integrity.verify_chain(events=events)

        assert result["valid"] is False
        broken_link_issues = [
            i for i in result["issues"] if i["issue_type"] == "broken_link"
        ]
        assert len(broken_link_issues) == 1
        assert broken_link_issues[0]["event_id"] == "AUDIT-FORGED"

    def test_a_correctly_content_hashed_but_wrongly_linked_event_still_flags_broken_link_only(self):
        _record()

        wrong_prev = "f" * 64
        forged_hash = compute_event_hash(
            "AUDIT-X", "e", "ENT-1", "a", "s", {}, "2026-01-01T00:00:00+00:00", wrong_prev
        )
        forged = AuditEvent(
            id="AUDIT-X", event_type="e", entity_id="ENT-1", actor="a",
            summary="s", details={}, timestamp="2026-01-01T00:00:00+00:00",
            prev_hash=wrong_prev, hash=forged_hash
        )

        events = audit_module.audit_log.get_all() + [forged]
        result = audit_integrity.verify_chain(events=events)

        issue_types = {i["issue_type"] for i in result["issues"]}
        # The forged event's own hash IS internally consistent with its own
        # (wrong) claimed prev_hash+content, so content_tampered should NOT
        # fire for it -- only the real broken_link.
        assert issue_types == {"broken_link"}


class TestVerifyChainBrokenGenesis:

    def test_first_event_not_anchored_on_genesis_is_caught(self):
        wrong_genesis = "1" * 64
        forged_hash = compute_event_hash(
            "AUDIT-1", "e", "ENT-1", "a", "s", {}, "2026-01-01T00:00:00+00:00", wrong_genesis
        )
        forged_first = AuditEvent(
            id="AUDIT-1", event_type="e", entity_id="ENT-1", actor="a",
            summary="s", details={}, timestamp="2026-01-01T00:00:00+00:00",
            prev_hash=wrong_genesis, hash=forged_hash
        )

        result = audit_integrity.verify_chain(events=[forged_first])

        assert result["valid"] is False
        assert result["issues"][0]["issue_type"] == "broken_genesis"
        assert result["issues"][0]["event_id"] == "AUDIT-1"

    def test_a_real_first_event_correctly_anchors_and_does_not_flag_broken_genesis(self):
        _record()

        result = audit_integrity.verify_chain()

        issue_types = {i["issue_type"] for i in result["issues"]}
        assert "broken_genesis" not in issue_types


class TestVerifyChainLegacyUnverifiableEvents:

    def test_events_with_empty_hash_are_reported_as_unverifiable_not_tampered(self):
        legacy = AuditEvent(
            id="AUDIT-OLD", event_type="legacy_event", entity_id="ENT-OLD",
            actor="old_system", summary="predates hash chaining",
            details={}, timestamp="2020-01-01T00:00:00+00:00",
            prev_hash="", hash=""
        )

        result = audit_integrity.verify_chain(events=[legacy])

        assert result["valid"] is True
        assert result["unverifiable_legacy_events"] == 1
        assert result["verified_events"] == 0
        assert result["issues"] == []

    def test_legacy_events_followed_by_real_hash_chained_events_do_not_require_genesis(self):
        legacy = AuditEvent(
            id="AUDIT-OLD", event_type="legacy_event", entity_id="ENT-OLD",
            actor="old_system", summary="predates hash chaining",
            details={}, timestamp="2020-01-01T00:00:00+00:00",
            prev_hash="", hash=""
        )

        # A real event recorded normally, but its prev_hash is deliberately
        # NOT genesis (as if this were the first hash-chained event added to
        # an already-existing legacy log) -- should NOT be flagged, since we
        # can't hold a chain with real legacy history before it to the
        # "must start at genesis" standard.
        some_anchor = "a" * 64
        real_hash = compute_event_hash(
            "AUDIT-NEW", "e", "ENT-1", "a", "s", {}, "2026-01-01T00:00:00+00:00", some_anchor
        )
        first_real = AuditEvent(
            id="AUDIT-NEW", event_type="e", entity_id="ENT-1", actor="a",
            summary="s", details={}, timestamp="2026-01-01T00:00:00+00:00",
            prev_hash=some_anchor, hash=real_hash
        )

        result = audit_integrity.verify_chain(events=[legacy, first_real])

        assert result["valid"] is True
        assert result["unverifiable_legacy_events"] == 1
        assert result["verified_events"] == 1

    def test_mixed_legacy_and_real_events_count_correctly(self):
        legacy1 = AuditEvent(
            id="AUDIT-OLD1", event_type="e", entity_id="ENT-1", actor="a",
            summary="s", details={}, timestamp="2020-01-01T00:00:00+00:00",
            prev_hash="", hash=""
        )
        legacy2 = AuditEvent(
            id="AUDIT-OLD2", event_type="e", entity_id="ENT-1", actor="a",
            summary="s", details={}, timestamp="2020-01-02T00:00:00+00:00",
            prev_hash="", hash=""
        )
        _record()
        _record()

        events = [legacy1, legacy2] + audit_module.audit_log.get_all()
        result = audit_integrity.verify_chain(events=events)

        assert result["total_events"] == 4
        assert result["unverifiable_legacy_events"] == 2
        assert result["verified_events"] == 2
        assert result["valid"] is True


# ---------------------------------------------------------------------------
# write_checkpoint() / read_checkpoint()
# ---------------------------------------------------------------------------


class TestWriteAndReadCheckpoint:

    def test_read_checkpoint_returns_none_when_never_written(self):
        assert audit_integrity.read_checkpoint() is None

    def test_write_checkpoint_with_no_events_uses_genesis_hash(self):
        checkpoint = audit_integrity.write_checkpoint()

        assert checkpoint["event_count"] == 0
        assert checkpoint["last_event_id"] is None
        assert checkpoint["last_hash"] == GENESIS_HASH
        assert "checkpointed_at" in checkpoint

    def test_write_checkpoint_reflects_the_real_current_tail_event(self):
        _record()
        second = _record()

        checkpoint = audit_integrity.write_checkpoint()

        assert checkpoint["event_count"] == 2
        assert checkpoint["last_event_id"] == second.id
        assert checkpoint["last_hash"] == second.hash

    def test_write_then_read_round_trips_the_same_content(self):
        _record()

        written = audit_integrity.write_checkpoint()
        read_back = audit_integrity.read_checkpoint()

        assert read_back == written

    def test_writing_a_second_checkpoint_overwrites_the_first(self):
        _record()
        audit_integrity.write_checkpoint()

        _record()
        second_checkpoint = audit_integrity.write_checkpoint()

        read_back = audit_integrity.read_checkpoint()
        assert read_back == second_checkpoint
        assert read_back["event_count"] == 2

    def test_checkpoint_file_actually_exists_on_disk_after_write(self):
        audit_integrity.write_checkpoint()

        path = storage_path("audit_chain_checkpoint.json")
        assert os.path.exists(path)

    def test_read_checkpoint_returns_none_on_corrupt_json(self):
        path = storage_path("audit_chain_checkpoint.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json::")

        assert audit_integrity.read_checkpoint() is None


# ---------------------------------------------------------------------------
# verify_against_checkpoint()
# ---------------------------------------------------------------------------


class TestVerifyAgainstCheckpoint:

    def test_no_history_and_no_checkpoint_is_ok_initial_state(self):
        result = audit_integrity.verify_against_checkpoint()

        assert result["status"] == "ok"
        assert "initial state" in result["detail"].lower()

    def test_events_exist_but_no_checkpoint_ever_written_is_checkpoint_missing(self):
        _record()

        result = audit_integrity.verify_against_checkpoint()

        assert result["status"] == "checkpoint_missing"

    def test_matching_checkpoint_is_ok(self):
        _record()
        _record()
        audit_integrity.write_checkpoint()

        result = audit_integrity.verify_against_checkpoint()

        assert result["status"] == "ok"
        assert "checkpoint" in result
        assert result["checkpoint"]["event_count"] == 2

    def test_new_events_recorded_after_checkpointing_produce_a_mismatch(self):
        _record()
        audit_integrity.write_checkpoint()

        # A real event added after the checkpoint was taken -- the in-memory
        # chain has moved on, but the checkpoint hasn't, which is exactly the
        # real-world "audit.json was restored from an older backup" scenario
        # this check exists to catch.
        _record()

        result = audit_integrity.verify_against_checkpoint()

        assert result["status"] == "checkpoint_mismatch"
        assert result["current_event_count"] == 2
        assert "checkpoint" in result

    def test_a_wholesale_swap_for_a_different_but_internally_valid_chain_is_caught(self):
        # Build and checkpoint one real chain.
        _record()
        _record()
        audit_integrity.write_checkpoint()

        # Now simulate audit.json being wholesale replaced with an entirely
        # different, but INTERNALLY self-consistent, fake chain -- the exact
        # scenario verify_chain() alone can't catch (it would report this
        # replacement chain as perfectly "valid" on its own).
        audit_module.audit_log.reset()
        fake = _record(summary="a totally different forged chain")

        chain_result = audit_integrity.verify_chain()
        checkpoint_result = audit_integrity.verify_against_checkpoint()

        assert chain_result["valid"] is True  # internally consistent on its own
        assert checkpoint_result["status"] == "checkpoint_mismatch"  # but caught here

    def test_reverting_to_a_shorter_chain_after_checkpointing_is_caught(self):
        _record()
        second = _record()
        third = _record()
        audit_integrity.write_checkpoint()

        # Simulate a truncated restore -- back to just the first two events.
        audit_module.audit_log.reset()
        _record()
        _record()

        result = audit_integrity.verify_against_checkpoint()

        assert result["status"] == "checkpoint_mismatch"
        assert result["current_event_count"] == 2


# ---------------------------------------------------------------------------
# full_integrity_report()
# ---------------------------------------------------------------------------


class TestFullIntegrityReport:

    def test_clean_state_with_no_history_reports_ok(self):
        report = audit_integrity.full_integrity_report()

        assert report["overall_status"] == "ok"
        assert report["chain"]["valid"] is True
        assert report["checkpoint"]["status"] == "ok"

    def test_valid_chain_with_matching_checkpoint_reports_ok(self):
        _record()
        _record()
        audit_integrity.write_checkpoint()

        report = audit_integrity.full_integrity_report()

        assert report["overall_status"] == "ok"
        assert report["chain"]["valid"] is True
        assert report["checkpoint"]["status"] == "ok"

    def test_tampered_content_alone_flips_overall_status_even_with_no_checkpoint_issue(self):
        event = _record()
        event.summary = "tampered"

        report = audit_integrity.full_integrity_report()

        assert report["overall_status"] == "issues_detected"
        assert report["chain"]["valid"] is False

    def test_checkpoint_mismatch_alone_flips_overall_status_even_with_a_valid_chain(self):
        _record()
        audit_integrity.write_checkpoint()
        _record()  # chain itself is still internally valid, checkpoint is now stale

        report = audit_integrity.full_integrity_report()

        assert report["overall_status"] == "issues_detected"
        assert report["chain"]["valid"] is True
        assert report["checkpoint"]["status"] == "checkpoint_mismatch"

    def test_both_real_problems_at_once_are_both_reported(self):
        event = _record()
        audit_integrity.write_checkpoint()
        event.summary = "tampered after checkpointing too"
        _record()

        report = audit_integrity.full_integrity_report()

        assert report["overall_status"] == "issues_detected"
        assert report["chain"]["valid"] is False
        assert report["checkpoint"]["status"] == "checkpoint_mismatch"

    def test_report_shape_has_both_top_level_sections(self):
        report = audit_integrity.full_integrity_report()

        assert set(report.keys()) == {"overall_status", "chain", "checkpoint"}
