"""
Tests for core/pci_dss_guard.py -- the PCI-DSS card-data guard + posture self-check
(security-hardening pass, 2026-07-20, Task #11 "Add GLBA + PCI-DSS readiness
controls," half 1 of 2), and for its real wiring as a blocking pre-flight check
inside core/payments.py's record_payment() (see TestWiredIntoPayments below).

Covers: Luhn validation (a real valid test card number passes, a single-digit-altered
number fails), card_number detection through the string scanner (plain digits, dash-
separated, space-separated, and the length-window/word-boundary reason a bare 25-
digit run never matches at all), false-positive avoidance against VIN/SSN/phone-
shaped strings, the field-name-based cvv_field/expiration_field detection (including
the exact real-world field-name shape -- "expiration_date" -- the module's own
substring-refactor was built to correctly match, plus the "expected_delivery" false-
positive guard the module's own docstring names explicitly), scan_for_card_data()'s
real recursion through nested dict/list/tuple structures with correct path tracking,
assert_no_card_data()'s real all-categories-block behavior (unlike core/pii_scan.py,
there is no low-confidence carve-out here), CardDataDetectedError's real carried
findings/context, run_pci_posture_scan()'s real clean-vs-not-clean dealership-wide
scan, and -- the concern this whole blocking pre-flight was built around -- that a
real card number typed into a payment's notes field is genuinely rejected by
core/payments.py's record_payment(), not just that both functions independently
exist.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import pci_dss_guard
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import FINANCE_CONTRACT, PAYMENT


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


# A real, well-known Luhn-valid test card number (Visa test PAN). Luhn-verified by
# hand before being used here: the alternating-doubled-digit sum lands on a multiple
# of 10.
VALID_TEST_CARD = "4111111111111111"
# Same number with the final digit altered by 1 -- fails Luhn.
INVALID_TEST_CARD = "4111111111111112"


class TestLuhnValidation:

    def test_a_known_valid_test_card_number_passes_luhn(self):
        assert pci_dss_guard._luhn_valid(VALID_TEST_CARD) is True

    def test_altering_the_last_digit_by_one_fails_luhn(self):
        assert pci_dss_guard._luhn_valid(INVALID_TEST_CARD) is False


class TestCardNumberDetection:

    def test_detects_a_real_luhn_valid_card_number_in_plain_text(self):
        findings = pci_dss_guard.scan_for_card_data(f"card on file: {VALID_TEST_CARD}")
        assert any(f["type"] == "card_number" for f in findings)

    def test_finding_is_high_confidence(self):
        findings = pci_dss_guard.scan_for_card_data(VALID_TEST_CARD)
        card_findings = [f for f in findings if f["type"] == "card_number"]
        assert card_findings
        assert card_findings[0]["confidence"] == "high"

    def test_finding_redacts_the_value(self):
        findings = pci_dss_guard.scan_for_card_data(VALID_TEST_CARD)
        card_findings = [f for f in findings if f["type"] == "card_number"]
        assert "redacted" in card_findings[0]["value_excerpt"]
        assert VALID_TEST_CARD not in card_findings[0]["value_excerpt"]

    def test_a_luhn_invalid_digit_run_of_the_right_length_is_not_flagged(self):
        # Same length/shape as a real card number, but fails the checksum -- the real
        # false-positive reduction this module's own docstring names.
        findings = pci_dss_guard.scan_for_card_data(INVALID_TEST_CARD)
        assert not any(f["type"] == "card_number" for f in findings)

    def test_detects_a_dash_separated_card_number(self):
        findings = pci_dss_guard.scan_for_card_data("4111-1111-1111-1111")
        assert any(f["type"] == "card_number" for f in findings)

    def test_detects_a_space_separated_card_number(self):
        findings = pci_dss_guard.scan_for_card_data("4111 1111 1111 1111")
        assert any(f["type"] == "card_number" for f in findings)

    def test_does_not_false_positive_on_a_real_vin(self):
        # A real, valid-shaped VIN (letters present) -- the digit-only card pattern
        # can never match across the embedded letters at all.
        findings = pci_dss_guard.scan_for_card_data("VIN 1HGCM82633A123456 on file")
        assert not any(f["type"] == "card_number" for f in findings)

    def test_does_not_false_positive_on_an_ssn_shaped_string(self):
        # Only 9 real digits -- below the 13-digit floor this pattern requires.
        findings = pci_dss_guard.scan_for_card_data("SSN 123-45-6789")
        assert not any(f["type"] == "card_number" for f in findings)

    def test_does_not_false_positive_on_a_phone_number(self):
        # Only 10 real digits -- below the 13-digit floor.
        findings = pci_dss_guard.scan_for_card_data("call 555-123-4567")
        assert not any(f["type"] == "card_number" for f in findings)

    def test_a_bare_25_digit_run_never_matches_because_it_exceeds_the_length_window(self):
        # No internal separators means no internal word-boundary for the regex to
        # anchor a 13-19-digit submatch on -- the whole 25-digit run either matches
        # entirely (impossible, since the pattern caps out at 19 digits) or not at
        # all.
        findings = pci_dss_guard.scan_for_card_data("1" * 25)
        assert not any(f["type"] == "card_number" for f in findings)

    def test_clean_business_text_has_no_findings(self):
        findings = pci_dss_guard.scan_for_card_data("Stock Number 45821, Total Gross Profit $4,200")
        assert findings == []


class TestCvvFieldDetection:

    def test_detects_a_cvv_named_field(self):
        findings = pci_dss_guard.scan_for_card_data({"cvv": "123"})
        assert any(f["type"] == "cvv_field" for f in findings)

    def test_detects_a_card_verification_code_named_field(self):
        # Normalized substring match against "cardverification".
        findings = pci_dss_guard.scan_for_card_data({"card_verification_code": "999"})
        assert any(f["type"] == "cvv_field" for f in findings)

    def test_detects_a_cvc2_named_field(self):
        findings = pci_dss_guard.scan_for_card_data({"cvc2": "12"})
        assert any(f["type"] == "cvv_field" for f in findings)

    def test_an_empty_string_value_is_not_flagged(self):
        # An unused/blank field merely named "cvv" isn't a real leak.
        findings = pci_dss_guard.scan_for_card_data({"cvv": ""})
        assert not any(f["type"] == "cvv_field" for f in findings)

    def test_a_none_value_is_not_flagged_and_does_not_raise(self):
        findings = pci_dss_guard.scan_for_card_data({"cvv": None})
        assert not any(f["type"] == "cvv_field" for f in findings)

    def test_finding_redacts_the_value(self):
        findings = pci_dss_guard.scan_for_card_data({"cvv": "123"})
        cvv_findings = [f for f in findings if f["type"] == "cvv_field"]
        assert cvv_findings[0]["value_excerpt"] == "...redacted..."


class TestExpirationFieldDetection:

    def test_detects_expiration_date_field_name_with_a_real_mm_yy_value(self):
        # The exact real-world field-name shape ("expiration_date" -- doesn't end in
        # "expir...") the module's substring-refactor was built to correctly match.
        findings = pci_dss_guard.scan_for_card_data({"expiration_date": "11/27"})
        assert any(f["type"] == "expiration_field" for f in findings)

    def test_detects_card_exp_field_name_with_a_real_mm_yyyy_value(self):
        findings = pci_dss_guard.scan_for_card_data({"card_exp": "05/2028"})
        assert any(f["type"] == "expiration_field" for f in findings)

    def test_detects_expiry_field_name(self):
        findings = pci_dss_guard.scan_for_card_data({"expiry": "01/26"})
        assert any(f["type"] == "expiration_field" for f in findings)

    def test_expected_delivery_field_with_a_real_iso_date_is_not_flagged(self):
        # The module's own docstring names this exact case: "exp" is a substring of
        # "expected_delivery", but the value "2026-08-01" does not match the real
        # MM/YY(YY) shape at all (it starts with a 4-digit year, not a 1-2 digit
        # month), so no expiration_field finding fires.
        findings = pci_dss_guard.scan_for_card_data({"expected_delivery": "2026-08-01"})
        assert not any(f["type"] == "expiration_field" for f in findings)

    def test_a_field_containing_exp_with_a_non_date_shaped_value_is_not_flagged(self):
        findings = pci_dss_guard.scan_for_card_data({"experience_years": "5"})
        assert not any(f["type"] == "expiration_field" for f in findings)

    def test_an_invalid_month_is_not_flagged(self):
        # "13" is not a real month.
        findings = pci_dss_guard.scan_for_card_data({"card_exp": "13/27"})
        assert not any(f["type"] == "expiration_field" for f in findings)


class TestScanForCardDataRecursion:

    def test_recurses_through_nested_dicts_and_lists(self):
        obj = {"level_one": {"level_two": ["safe text", VALID_TEST_CARD]}}
        findings = pci_dss_guard.scan_for_card_data(obj)
        assert any(f["type"] == "card_number" for f in findings)

    def test_path_is_tracked_correctly_for_a_field_name_finding(self):
        obj = {"payment": {"cvv": "123"}}
        findings = pci_dss_guard.scan_for_card_data(obj)
        cvv_finding = next(f for f in findings if f["type"] == "cvv_field")
        assert cvv_finding["path"] == "root.payment.cvv"

    def test_path_is_tracked_correctly_for_a_list_item_card_number(self):
        obj = {"notes": ["fine", VALID_TEST_CARD]}
        findings = pci_dss_guard.scan_for_card_data(obj)
        card_finding = next(f for f in findings if f["type"] == "card_number")
        assert card_finding["path"] == "root.notes[1]"

    def test_tuples_are_recursed_into_like_lists(self):
        obj = ("fine", VALID_TEST_CARD)
        findings = pci_dss_guard.scan_for_card_data(obj)
        assert any(f["type"] == "card_number" for f in findings)

    def test_non_string_non_dict_non_list_leaf_values_never_raise(self):
        obj = {"count": 42, "active": True, "missing": None, "ratio": 3.14}
        findings = pci_dss_guard.scan_for_card_data(obj)
        assert findings == []

    def test_empty_structures_return_no_findings(self):
        assert pci_dss_guard.scan_for_card_data({}) == []
        assert pci_dss_guard.scan_for_card_data([]) == []
        assert pci_dss_guard.scan_for_card_data("") == []


class TestAssertNoCardData:

    def test_raises_on_a_card_number(self):
        with pytest.raises(pci_dss_guard.CardDataDetectedError):
            pci_dss_guard.assert_no_card_data({"note": VALID_TEST_CARD})

    def test_raises_on_a_cvv_field(self):
        # Unlike core/pii_scan.py, every category here blocks -- there is no
        # low-confidence carve-out for cardholder data.
        with pytest.raises(pci_dss_guard.CardDataDetectedError):
            pci_dss_guard.assert_no_card_data({"cvv": "123"})

    def test_raises_on_an_expiration_field(self):
        with pytest.raises(pci_dss_guard.CardDataDetectedError):
            pci_dss_guard.assert_no_card_data({"expiration_date": "11/27"})

    def test_clean_input_returns_empty_findings_list(self):
        result = pci_dss_guard.assert_no_card_data({"note": "Total Gross Profit"})
        assert result == []

    def test_error_carries_real_findings_and_context(self):
        try:
            pci_dss_guard.assert_no_card_data({"note": VALID_TEST_CARD}, context="my export")
            assert False, "expected CardDataDetectedError"
        except pci_dss_guard.CardDataDetectedError as exc:
            assert exc.context == "my export"
            assert any(f["type"] == "card_number" for f in exc.findings)
            assert "my export" in str(exc)
            assert "card_number" in str(exc)


class TestPciPostureScan:

    def test_a_clean_graph_reports_clean_and_saq_a_eligible(self):
        ledger.add_entity(Entity(id="CUST-T1", entity_type="Customer", attributes={"FirstName": "Jane"}))
        result = pci_dss_guard.run_pci_posture_scan()
        assert result["clean"] is True
        assert result["saq_a_eligible"] is True
        assert result["entities_with_findings"] == []
        assert result["total_findings"] == 0

    def test_a_graph_with_a_real_card_number_is_reported_not_clean(self):
        ledger.add_entity(Entity(
            id="LEAD-T1",
            entity_type="Lead",
            attributes={"Notes": f"customer quoted card {VALID_TEST_CARD} over the phone"},
        ))
        result = pci_dss_guard.run_pci_posture_scan()
        assert result["clean"] is False
        assert result["saq_a_eligible"] is False
        assert result["total_findings"] >= 1
        assert any(e["entity_id"] == "LEAD-T1" for e in result["entities_with_findings"])
        assert "card_number" in result["findings_by_type"]

    def test_entity_count_reflects_everything_in_the_ledger(self):
        ledger.add_entity(Entity(id="CUST-T1", entity_type="Customer", attributes={}))
        ledger.add_entity(Entity(id="CUST-T2", entity_type="Customer", attributes={}))
        result = pci_dss_guard.run_pci_posture_scan()
        assert result["entity_count"] == 2


class TestWiredIntoPayments:
    """Confirms assert_no_card_data() is genuinely called inside
    core/payments.py's record_payment(), not just that both functions
    independently exist."""

    def _seed_loan(self, loan_id="FIN-TEST01"):
        ledger.add_entity(Entity(
            id=loan_id,
            entity_type=FINANCE_CONTRACT,
            attributes={
                "AmountFinanced": 10000.0,
                "APR": 6.0,
                "MonthlyPayment": 300.0,
                "ContractDate": "2026-01-01",
            },
        ))
        return loan_id

    def test_a_real_card_number_typed_into_notes_blocks_the_real_payment(self):
        from core.payments import record_payment

        loan_id = self._seed_loan()
        result = record_payment(
            loan_id=loan_id,
            amount=250.0,
            method="ach",
            recorded_by="EMP-00001",
            notes=f"customer read card number {VALID_TEST_CARD} over the phone",
        )

        assert "error" in result
        assert "card" in result["error"].lower()
        assert any(f["type"] == "card_number" for f in result["findings"])

    def test_blocked_payment_never_reaches_the_ledger(self):
        from core.payments import record_payment

        loan_id = self._seed_loan()
        record_payment(
            loan_id=loan_id,
            amount=250.0,
            method="ach",
            recorded_by="EMP-00001",
            notes=f"card {VALID_TEST_CARD}",
        )

        payments = [e for e in ledger.get_all().values() if e.entity_type == PAYMENT]
        assert payments == []

    def test_a_real_payment_with_clean_notes_is_not_blocked(self):
        from core.payments import record_payment

        loan_id = self._seed_loan()
        result = record_payment(
            loan_id=loan_id,
            amount=250.0,
            method="cash",
            recorded_by="EMP-00001",
            notes="customer paid at the front desk",
        )

        # record_payment() returns the real Payment Entity on success (not an
        # {"error": ...} dict) the moment nothing blocks it. Cash always approves
        # (no simulated gateway involved), keeping this deterministic.
        assert hasattr(result, "entity_type")
        assert result.entity_type == PAYMENT

        payments = [e for e in ledger.get_all().values() if e.entity_type == PAYMENT]
        assert len(payments) == 1

    def test_a_cvv_shaped_field_in_notes_is_not_itself_scanned_since_notes_is_a_plain_string(self):
        # record_payment() only ever wraps `notes` in {"notes": notes} before
        # scanning -- notes is always a plain string field on this entity, so only
        # the card_number string pattern can ever fire against it, never the
        # field-name-based cvv_field/expiration_field checks (those require a real
        # dict KEY named like a CVV/expiration field, which `notes` never is).
        # Confirms a merely CVV-shaped sentence in free text doesn't spuriously
        # block a real payment.
        from core.payments import record_payment

        loan_id = self._seed_loan()
        result = record_payment(
            loan_id=loan_id,
            amount=100.0,
            method="cash",
            recorded_by="EMP-00001",
            notes="customer mentioned their cvv is on the back of the card",
        )

        assert hasattr(result, "entity_type")
        assert result.entity_type == PAYMENT
