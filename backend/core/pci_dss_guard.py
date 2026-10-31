"""
PCI-DSS card-data guard + posture self-check (security-hardening Task #11, half 1 of 2).

docs/SECURITY_ARCHITECTURE.md has documented this codebase's PCI-DSS posture as
PARTIAL: no code path anywhere stores, transmits, or processes a raw payment card
number -- core/payments.py's PAYMENT_METHODS is a fixed enum of method-name strings
(never a card number/CVV/expiration field), and record_payment()'s only freeform
field is `notes`. The stated readiness path has been "SAQ-A-eligible if a real
payment ever needs processing -- hand off to a real tokenizing gateway, never build
card capture in-house." This module turns that narrative into two real, checkable
controls instead of leaving it as prose alone:

  1. A real, blocking pre-flight scanner (assert_no_card_data()) wired directly into
     core/payments.py's record_payment(), so a staff member typing a card number into
     the one genuinely freeform field this system has (payment notes) gets rejected
     before it's ever written to the graph -- mirroring core/pii_scan.py's
     assert_no_pii() blocking-pre-flight pattern (Task #10), reused here for a
     different, cardholder-data-specific detection shape.

  2. A real, on-demand posture self-check (run_pci_posture_scan()) that walks every
     entity currently in the graph and confirms the same thing is true dealership-wide,
     not just at the one known freeform field -- the same "full-graph scan" shape
     core/compliance.py's run_full_scan()/the NXTDeal Hub's run_privacy_audit() already
     established in this codebase, applied here to cardholder data specifically. A
     clean scan is real, structural evidence for the SAQ-A eligibility claim, not an
     assertion made from code review alone.

Detection, unlike core/pii_scan.py's PII categories, is deliberately ALL high-
confidence/blocking -- there is no legitimate reason a real card number, CVV, or
expiration date should ever appear in this system's data at all (unlike PII, where a
customer's real name/email/phone is expected and legitimate everywhere), so there is
no "low-confidence, don't block" carve-out here the way PII's name_heuristic has one.

  - card_number   -- a real 13-19 digit sequence (optionally separated by spaces or
                     dashes, matching how a human would actually type one) that ALSO
                     passes the Luhn checksum algorithm every real payment card number
                     satisfies by design. Luhn validation is the real reduction in
                     false positives here -- without it, this would false-positive
                     constantly against ordinary long numeric strings (VINs' numeric
                     runs, stock numbers, phone numbers with separators stripped,
                     zip+4 sequences, etc). A random 13-19 digit run has roughly a 1-in-10
                     chance of passing Luhn by coincidence, which is an accepted,
                     standard tradeoff for this class of scanner -- stated plainly, not
                     claimed to be perfect.
  - cvv_field     -- a dict key whose name matches a real CVV/CVC/security-code naming
                     convention (cvv, cvv2, cvc, cvc2, card_verification*, security_code,
                     card_security_code) with a non-empty value. Field-name-based, not
                     content-based -- there is no real "CVV shape" to pattern-match on
                     since it's just 3-4 digits, indistinguishable from countless other
                     legitimate short numeric values without knowing the field's name.
  - expiration_field -- the same field-name-based approach for a card-expiration-shaped
                     key (card_exp*, cc_exp*, expiration_date, expiry) whose value looks
                     like a real MM/YY or MM/YYYY expiration shape.

Two real entry points, matching core/pii_scan.py's shape exactly:

  - scan_for_card_data(obj) -> a list of finding dicts, recursing through any real
    dict/list/tuple, with the same dot/bracket `path` tracking core/pii_scan.py already
    established.
  - assert_no_card_data(obj, context) -> re-runs scan_for_card_data() and raises
    CardDataDetectedError the instant ANY finding exists (every category here blocks,
    unlike PII's high/low split).

run_pci_posture_scan() is the third, dealership-wide entry point -- walks every entity
currently in core.dealeros.ledger.entities and scans each one's attributes dict,
returning a real posture report (clean/not-clean, entity/finding counts, and an
SAQ-A-eligibility narrative that is TRUE only when the scan is actually clean, never
asserted regardless of the scan result).
"""

import re


CARD_DATA_TYPES = {"card_number", "cvv_field", "expiration_field"}

_CARD_NUMBER_PATTERN = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")

_EXPIRATION_VALUE_PATTERN = re.compile(r"^\s*(0[1-9]|1[0-2])\s*[/\-]\s*(\d{2}|\d{4})\s*$")

# Field-name detection uses a normalized (lowercased, separators stripped) substring
# check rather than a strict anchored regex -- a real dealership/vendor schema names
# this kind of field inconsistently ("cvv", "card_verification_code", "cc_exp_date",
# "expiration_date", "expiry", ...), and a strict anchor missed real, common shapes
# (e.g. "expiration_date" doesn't END in "expir..."). Substring matching is
# deliberately broader here -- for CVV_SUBSTRINGS, that's safe on its own (the value
# still has to be non-empty). For EXPIRATION_SUBSTRINGS, "exp" alone would also match
# unrelated words like "experience"/"expected"/"expense" -- but the expiration finding
# additionally requires the VALUE to match a real MM/YY(YY) shape
# (_EXPIRATION_VALUE_PATTERN), which is what actually keeps this precise in practice;
# a field named "expected_delivery" holding a real date string like "2026-08-01"
# won't match that shape at all.
CVV_SUBSTRINGS = ("cvv", "cvc", "securitycode", "cardverification")
EXPIRATION_SUBSTRINGS = ("exp",)


def _normalize_key(key):
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _luhn_valid(digits):
    """Real Luhn checksum -- every genuine payment card number satisfies this by
    design. `digits` is a plain string of digit characters only (separators already
    stripped by the caller)."""

    total = 0
    reverse_digits = digits[::-1]

    for index, char in enumerate(reverse_digits):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit

    return total % 10 == 0


def _scan_string_for_card_number(value):

    findings = []

    for match in _CARD_NUMBER_PATTERN.finditer(value):
        raw = match.group()
        digits = re.sub(r"[ \-]", "", raw)

        if len(digits) < 13 or len(digits) > 19:
            continue

        if _luhn_valid(digits):
            findings.append({
                "type": "card_number",
                "confidence": "high",
                "value_excerpt": (raw[:4] + "...redacted...") if len(raw) > 4 else "...redacted...",
            })

    return findings


def _scan_dict_entry_for_card_fields(key, value):
    """Field-name-based detection for CVV/expiration -- only fires when the key name
    itself matches a real card-adjacent naming convention AND the value is a real,
    non-empty string (an empty/None value on a field that merely happens to be named
    "cvv" isn't a real leak, just an unused optional field some other system's schema
    might define)."""

    findings = []

    if not isinstance(value, str) or not value.strip():
        return findings

    normalized_key = _normalize_key(key)

    if any(sub in normalized_key for sub in CVV_SUBSTRINGS):
        findings.append({
            "type": "cvv_field",
            "confidence": "high",
            "value_excerpt": "...redacted...",
        })

    if any(sub in normalized_key for sub in EXPIRATION_SUBSTRINGS) and _EXPIRATION_VALUE_PATTERN.match(value):
        findings.append({
            "type": "expiration_field",
            "confidence": "high",
            "value_excerpt": "...redacted...",
        })

    return findings


def scan_for_card_data(obj, path="root", findings=None):
    """Recursively scans any real Python dict/list/tuple/str structure for the 3
    cardholder-data categories above. `path` tracks a real, human-readable location
    string per finding, matching core/pii_scan.py's scan_object() convention."""

    if findings is None:
        findings = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            for finding in _scan_dict_entry_for_card_fields(key, value):
                finding["path"] = f"{path}.{key}"
                findings.append(finding)
            scan_for_card_data(value, f"{path}.{key}", findings)
    elif isinstance(obj, (list, tuple)):
        for index, item in enumerate(obj):
            scan_for_card_data(item, f"{path}[{index}]", findings)
    elif isinstance(obj, str):
        for finding in _scan_string_for_card_number(obj):
            finding["path"] = path
            findings.append(finding)

    return findings


class CardDataDetectedError(Exception):
    """Raised by assert_no_card_data() the instant any cardholder-data finding exists
    anywhere in the scanned object. Every category here is treated as high-confidence
    and blocking -- unlike core/pii_scan.py, there is no legitimate low-confidence
    carve-out for cardholder data."""

    def __init__(self, findings, context):
        self.findings = findings
        self.context = context
        super().__init__(
            f"PCI-DSS card-data scan blocked {context!r}: {len(findings)} "
            f"finding(s) -- {[f['type'] for f in findings]}"
        )


def assert_no_card_data(obj, context="payment record"):
    """The real blocking pre-flight check. Re-scans `obj` and raises
    CardDataDetectedError the instant any finding exists anywhere in it. Returns the
    (empty) findings list on success, matching core/pii_scan.py's assert_no_pii()
    return-value convention."""

    findings = scan_for_card_data(obj)

    if findings:
        raise CardDataDetectedError(findings, context)

    return findings


def run_pci_posture_scan():
    """The real, on-demand, dealership-wide posture self-check -- walks every entity
    currently in the graph and scans its attributes dict for cardholder data, the same
    "full-graph scan" shape core/compliance.py's run_full_scan() already established
    in this codebase, applied here to cardholder data specifically.

    A deferred (in-function) import of core.dealeros, matching this codebase's own
    established convention for avoiding a top-level circular import between a scanning
    module and the ledger singleton it inspects (see e.g. core/compliance.py's own
    run_full_scan()).

    Returns a real posture report -- entity_count/entities_with_findings/finding
    counts by type, plus an honest saq_a_eligible flag that is True only when the scan
    is genuinely clean, never asserted regardless of the real result."""

    from core.dealeros import ledger

    entity_count = 0
    entities_with_findings = []
    findings_by_type = {}

    for entity in ledger.entities.values():
        entity_count += 1
        entity_findings = scan_for_card_data(entity.attributes, path=f"{entity.entity_type}.attributes")

        if entity_findings:
            entities_with_findings.append({
                "entity_id": entity.id,
                "entity_type": entity.entity_type,
                "finding_count": len(entity_findings),
                "finding_types": sorted({f["type"] for f in entity_findings}),
            })
            for finding in entity_findings:
                findings_by_type[finding["type"]] = findings_by_type.get(finding["type"], 0) + 1

    clean = len(entities_with_findings) == 0

    return {
        "scanned_at": _now(),
        "entity_count": entity_count,
        "entities_with_findings": entities_with_findings,
        "total_findings": sum(findings_by_type.values()),
        "findings_by_type": findings_by_type,
        "clean": clean,
        "saq_a_eligible": clean,
        "posture_note": (
            "No cardholder data (card number, CVV, or expiration) was found anywhere "
            "in the graph. This system stores no raw payment card data by design -- "
            "core/payments.py's PAYMENT_METHODS is a fixed enum of method-name "
            "strings, never a card-number/CVV/expiration field, and this scan's own "
            "blocking pre-flight check (assert_no_card_data()) is wired into the one "
            "genuinely freeform field the payments module has (payment notes). This "
            "is consistent with SAQ-A eligibility if a real payment ever needs "
            "processing -- hand off to a real tokenizing gateway (e.g. Stripe, "
            "Braintree), never build card capture in-house."
            if clean else
            "Cardholder-data-shaped content was found in the graph -- see "
            "entities_with_findings for exactly where. This is a real finding, not a "
            "drill: investigate and remediate the listed entities before relying on "
            "this system's SAQ-A-eligible posture claim."
        ),
        "not_legal_or_compliance_advice": (
            "This is an automated, code-level self-check, not a PCI-DSS assessment "
            "and not a substitute for a Qualified Security Assessor or your acquiring "
            "bank's own compliance validation requirements."
        ),
    }


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
