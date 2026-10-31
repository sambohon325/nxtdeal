"""
Tests for core/pii_scan.py -- the generalized, reusable PII/privacy-leak scanner
(security-hardening pass, 2026-07-20, Task #10), and for its real wiring as a blocking
pre-flight check inside core/network_snapshot.py's build_anonymous_snapshot() (see
TestWiredIntoNetworkSnapshot below).

Covers: each of the 5 real detection categories individually (email/phone/ssn/vin/
name_heuristic), the stoplist's real effect on name_heuristic (both words stoplisted ->
not reported; a mix -> still reported), scan_object()'s real recursion through nested
dict/list/tuple structures with correct path tracking, that non-string values are never
scanned and never raise, assert_no_pii()'s real high-confidence-only blocking behavior
(raises on email/phone/ssn/vin, does NOT raise on name_heuristic alone, returns the full
findings list -- including low-confidence ones -- on success), PiiDetectedError's real
carried findings/context, and -- the concern this whole design was built around -- a
realistic snapshot-shaped payload using real core/department_intelligence.py-style KPI
labels ("Total Gross Profit", "Avg Sale Price", "Effective Labor Rate", etc.) that must
NOT trigger a false-positive block.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import pii_scan


class TestEmailPattern:

    def test_detects_a_real_email_address(self):
        findings = pii_scan.scan_object("contact john.smith@example.com for details")
        types = [f["type"] for f in findings]
        assert "email" in types

    def test_finding_is_high_confidence(self):
        findings = pii_scan.scan_object("jane@dealer.com")
        email_findings = [f for f in findings if f["type"] == "email"]
        assert email_findings
        assert email_findings[0]["confidence"] == "high"

    def test_no_email_no_finding(self):
        findings = pii_scan.scan_object("Total Gross Profit")
        assert not any(f["type"] == "email" for f in findings)


class TestPhonePattern:

    def test_detects_dashed_phone_number(self):
        findings = pii_scan.scan_object("call 555-123-4567 for a quote")
        assert any(f["type"] == "phone" for f in findings)

    def test_detects_dotted_phone_number(self):
        findings = pii_scan.scan_object("555.123.4567")
        assert any(f["type"] == "phone" for f in findings)

    def test_no_phone_shaped_text_no_finding(self):
        findings = pii_scan.scan_object("Units Sold")
        assert not any(f["type"] == "phone" for f in findings)


class TestSsnPattern:

    def test_detects_standard_ssn_format(self):
        findings = pii_scan.scan_object("SSN on file: 123-45-6789")
        assert any(f["type"] == "ssn" for f in findings)

    def test_does_not_false_positive_on_a_phone_number_shape(self):
        # A phone number (XXX-XXX-XXXX) has a different digit grouping than an SSN
        # (XXX-XX-XXXX) -- confirm the two patterns are genuinely distinct, not the
        # same regex reused under two names.
        findings = pii_scan.scan_object("555-123-4567")
        assert not any(f["type"] == "ssn" for f in findings)

    def test_does_not_false_positive_on_an_ordinary_large_number(self):
        # A bare 9-digit run (no dashes) must NOT match -- this is exactly why the
        # module deliberately requires the standard displayed dash format rather than
        # a bare-digit-run pattern (see the module's own docstring).
        findings = pii_scan.scan_object("total revenue was 123456789 dollars this year")
        assert not any(f["type"] == "ssn" for f in findings)


class TestVinPattern:

    def test_detects_a_real_17_character_vin(self):
        # A real, valid-shaped VIN: 17 alphanumeric characters, no I/O/Q.
        findings = pii_scan.scan_object("vehicle VIN 1HGCM82633A123456 on file")
        assert any(f["type"] == "vin" for f in findings)

    def test_does_not_false_positive_on_a_64_character_hex_pseudonym(self):
        # core/network_pseudonym.py's real pseudonym shape (secrets.token_hex(32), all
        # lowercase hex digits) -- the exact reason network_snapshot.py deliberately
        # excludes the pseudonym field from the scan rather than relying on this. VIN
        # pattern requires uppercase letters (case-sensitive), so a lowercase hex string
        # never matches regardless.
        fake_pseudonym = "a1b2c3d4e5f6" * 5 + "ab1234"
        findings = pii_scan.scan_object(fake_pseudonym)
        assert not any(f["type"] == "vin" for f in findings)

    def test_does_not_false_positive_on_a_16_character_alphanumeric_token(self):
        # One character short of a real VIN -- must not match.
        findings = pii_scan.scan_object("1HGCM82633A12345")
        assert not any(f["type"] == "vin" for f in findings)


class TestNameHeuristic:

    def test_detects_a_real_looking_two_word_name(self):
        findings = pii_scan.scan_object("Customer name: John Smith")
        assert any(f["type"] == "name_heuristic" for f in findings)

    def test_finding_is_low_confidence(self):
        findings = pii_scan.scan_object("Priya Nair")
        name_findings = [f for f in findings if f["type"] == "name_heuristic"]
        assert name_findings
        assert name_findings[0]["confidence"] == "low"

    def test_both_words_stoplisted_is_not_reported(self):
        # "Gross" and "Profit" are both in COMMON_NON_NAME_WORDS.
        findings = pii_scan.scan_object("Gross Profit")
        assert not any(f["type"] == "name_heuristic" for f in findings)

    def test_mixed_stoplisted_and_real_word_is_still_reported(self):
        # "Total" is stoplisted, "Priya" is not -- the pair should still fire, since
        # requiring only ONE non-stoplisted word keeps the heuristic from being trivially
        # defeated by prefixing a real name with a common business word.
        findings = pii_scan.scan_object("Total Priya")
        assert any(f["type"] == "name_heuristic" for f in findings)

    def test_single_word_is_never_matched(self):
        findings = pii_scan.scan_object("Marketing")
        assert not any(f["type"] == "name_heuristic" for f in findings)


class TestRealKpiLabelsDoNotFalsePositive:
    """The concern this whole module's design was built around: real, static, developer
    -controlled KPI label text from core/department_intelligence.py must never trip the
    name_heuristic (or any other) pattern, or the blocking pre-flight check in
    network_snapshot.py would break the Network snapshot feature in production."""

    REAL_KPI_LABELS = [
        "Total Gross Profit",
        "Gross Profit / Unit",
        "Units Sold",
        "Avg Sale Price",
        "Projected Month-End Units",
        "Total Gross",
        "RO Count",
        "Avg Repair Order",
        "Customer Pay %",
        "Effective Labor Rate",
        "Net Profit",
        "Parts Sales",
        "Inventory Turns",
        "Obsolete Inventory %",
        "Reserve Income",
        "Income / Contract",
        "Reserve / Vehicle",
        "Deals Financed",
        "Avg APR",
        "Sales Contribution %",
        "Service Contribution %",
        "Parts Contribution %",
        "F&I Contribution %",
    ]

    def test_no_real_kpi_label_triggers_any_high_confidence_finding(self):
        for label in self.REAL_KPI_LABELS:
            findings = pii_scan.scan_object(label)
            high_confidence = [f for f in findings if f["confidence"] == "high"]
            assert not high_confidence, f"{label!r} incorrectly flagged: {high_confidence}"

    def test_no_real_kpi_label_triggers_name_heuristic_either(self):
        # A stronger check than the above -- confirms the stoplist is actually doing its
        # job against this codebase's own real vocabulary, not just that these labels
        # happen not to match the high-confidence patterns.
        for label in self.REAL_KPI_LABELS:
            findings = pii_scan.scan_object(label)
            name_findings = [f for f in findings if f["type"] == "name_heuristic"]
            assert not name_findings, f"{label!r} incorrectly flagged as a possible name: {name_findings}"

    def test_a_realistic_full_snapshot_shaped_payload_does_not_raise(self):
        snapshot_shaped_payload = {
            "departments": {
                "sales": {
                    "total_gross_profit": {"label": "Total Gross Profit", "value": 12500, "format": "currency"},
                    "units_sold": {"label": "Units Sold", "value": 45, "format": "number"},
                },
                "finance": {
                    "avg_apr": {"label": "Avg APR", "value": 6.5, "format": "percent"},
                    "deals_financed": {"label": "Deals Financed", "value": 12, "format": "number"},
                },
            },
            "note": "Every value here is a real KPI with calibrated Laplace-mechanism noise applied.",
        }
        # Should not raise.
        pii_scan.assert_no_pii(snapshot_shaped_payload, context="test snapshot")


class TestScanObjectRecursion:

    def test_recurses_through_nested_dicts_and_lists(self):
        obj = {
            "level_one": {
                "level_two": ["safe text", "contact me at jane@dealer.com"],
            }
        }
        findings = pii_scan.scan_object(obj)
        assert any(f["type"] == "email" for f in findings)

    def test_path_is_tracked_correctly_for_a_dict_value(self):
        obj = {"customer": {"email": "jane@dealer.com"}}
        findings = pii_scan.scan_object(obj)
        email_finding = next(f for f in findings if f["type"] == "email")
        assert email_finding["path"] == "root.customer.email"

    def test_path_is_tracked_correctly_for_a_list_item(self):
        obj = {"notes": ["fine", "jane@dealer.com"]}
        findings = pii_scan.scan_object(obj)
        email_finding = next(f for f in findings if f["type"] == "email")
        assert email_finding["path"] == "root.notes[1]"

    def test_tuples_are_recursed_into_like_lists(self):
        obj = ("fine", "jane@dealer.com")
        findings = pii_scan.scan_object(obj)
        assert any(f["type"] == "email" for f in findings)

    def test_non_string_leaf_values_are_never_scanned_and_never_raise(self):
        obj = {"count": 42, "active": True, "missing": None, "ratio": 3.14}
        findings = pii_scan.scan_object(obj)
        assert findings == []

    def test_empty_structures_return_no_findings(self):
        assert pii_scan.scan_object({}) == []
        assert pii_scan.scan_object([]) == []
        assert pii_scan.scan_object("") == []


class TestAssertNoPii:

    def test_raises_on_email(self):
        with pytest.raises(pii_scan.PiiDetectedError):
            pii_scan.assert_no_pii({"note": "jane@dealer.com"})

    def test_raises_on_phone(self):
        with pytest.raises(pii_scan.PiiDetectedError):
            pii_scan.assert_no_pii({"note": "555-123-4567"})

    def test_raises_on_ssn(self):
        with pytest.raises(pii_scan.PiiDetectedError):
            pii_scan.assert_no_pii({"note": "123-45-6789"})

    def test_raises_on_vin(self):
        with pytest.raises(pii_scan.PiiDetectedError):
            pii_scan.assert_no_pii({"note": "1HGCM82633A123456"})

    def test_does_not_raise_on_name_heuristic_alone(self):
        # Low confidence only -- must not block, per the module's own stated design.
        result = pii_scan.assert_no_pii({"note": "Customer name: John Smith"})
        assert isinstance(result, list)

    def test_returns_full_findings_list_including_low_confidence_on_success(self):
        result = pii_scan.assert_no_pii({"note": "Priya Nair"})
        assert any(f["type"] == "name_heuristic" for f in result)

    def test_clean_input_returns_empty_findings_list(self):
        result = pii_scan.assert_no_pii({"note": "Total Gross Profit"})
        assert result == []

    def test_error_carries_real_findings_and_context(self):
        try:
            pii_scan.assert_no_pii({"note": "jane@dealer.com"}, context="my export")
            assert False, "expected PiiDetectedError"
        except pii_scan.PiiDetectedError as exc:
            assert exc.context == "my export"
            assert any(f["type"] == "email" for f in exc.findings)
            assert "my export" in str(exc)
            assert "email" in str(exc)


class TestWiredIntoNetworkSnapshot:
    """Confirms assert_no_pii() is genuinely called inside build_anonymous_snapshot(),
    not just that both functions independently exist."""

    def test_a_leaked_email_in_a_kpi_label_blocks_the_real_snapshot_builder(self, monkeypatch):
        from core import network_snapshot

        def fake_compute_department(department_key):
            return {
                "kpis": {
                    "total_gross_profit": {
                        "label": "contact jane@dealer.com",
                        "value": 1000,
                        "format": "currency",
                    }
                }
            }

        monkeypatch.setattr(network_snapshot, "compute_department", fake_compute_department)
        monkeypatch.setattr(network_snapshot, "DEPARTMENTS", ["sales"])

        with pytest.raises(pii_scan.PiiDetectedError):
            network_snapshot.build_anonymous_snapshot()

    def test_real_department_intelligence_kpis_do_not_trip_the_wired_check(self):
        # A real, non-monkeypatched call against this codebase's actual
        # compute_department() output -- the real end-to-end regression guard that the
        # blocking check doesn't break the real feature.
        from core import network_snapshot

        result = network_snapshot.build_anonymous_snapshot()
        assert "departments" in result
