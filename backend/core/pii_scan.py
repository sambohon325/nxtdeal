"""
Generalized, reusable PII / privacy-leak scanner (security-hardening Task #10).

Before this module: a real PII pattern check already existed, but only inside the
NXTDeal Hub's own Network Health privacy audit (hub/hub_core/infra_network_health.py's
run_privacy_audit()) -- scoped narrowly to inspecting already-STORED Hub-side
NetworkSnapshot records after the fact, and only for two pattern types (email/phone).
This module generalizes that into a real, tenant-side, dependency-free scanner any
future data-export path in this codebase can reuse -- not just this one -- and, per
this task's own scope, wires it as a real BLOCKING pre-flight check directly inside
core/network_snapshot.py's build_anonymous_snapshot(), before a snapshot is ever
returned to a caller, rather than only auditing it after it already left the process.

Real, regex+heuristic detection across 5 categories:

  - email            -- standard email-address shape.
  - phone            -- US phone-number shape (10 digits, common separators).
  - ssn              -- XXX-XX-XXXX, the standard DISPLAYED SSN format. Deliberately
                        NOT a bare 9-consecutive-digit pattern -- that would false-
                        positive constantly against ordinary large numbers (e.g. a
                        raw, unbucketed dollar figure) and would be worse than useless
                        as a blocking gate.
  - vin              -- a real 17-character VIN shape (alphanumeric, excluding I/O/Q,
                        the three letters the VIN standard itself never uses -- a real
                        reduction in false positives against arbitrary alphanumeric
                        tokens, not an arbitrary choice).
  - name_heuristic   -- two consecutive Title-Case words (e.g. "John Smith"). This is a
                        genuinely fuzzy heuristic, not a real named-entity-recognition
                        model, and it WILL match ordinary two-word Title-Case business
                        phrases ("Gross Profit", "Total Sales") -- exactly the shape of
                        label text core/department_intelligence.py's own real KPI cards
                        already publish. COMMON_NON_NAME_WORDS below is a real, if
                        non-exhaustive, stoplist of that vocabulary so the heuristic
                        doesn't fire on the very labels the network snapshot pipeline
                        legitimately produces -- but this can never be made fully
                        precise with regex alone. Stated here plainly rather than
                        silently suppressed or falsely presented as equally reliable
                        to the four pattern-based categories above.

Two real entry points:

  - scan_object(obj) -> a list of finding dicts. Recurses through any real dict/list/
    tuple, pattern-matching every string value it finds (never touches numeric/bool/
    None values -- only strings can carry text-shaped PII), and records a real,
    human-readable `path` per finding (dict keys joined by '.', list indices in
    brackets) so a caller can tell WHERE in a large nested structure a leak was found.
  - assert_no_pii(obj, context) -> re-runs scan_object() and raises PiiDetectedError
    the instant any HIGH-confidence finding (email/phone/ssn/vin) exists anywhere in
    `obj`. Low-confidence name_heuristic findings are still returned for visibility but
    deliberately do NOT block -- a blanket "never let any Title-Case pair through" gate
    would make this module unusable in practice, given the false-positive rate stated
    above. This is the real, honest scope of "blocking pre-flight check" this module
    offers, not a claim of catching every possible PII shape.
"""

import re


HIGH_CONFIDENCE_TYPES = {"email", "phone", "ssn", "vin"}
LOW_CONFIDENCE_TYPES = {"name_heuristic"}

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+")
_PHONE_PATTERN = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_VIN_PATTERN = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
_NAME_HEURISTIC_PATTERN = re.compile(r"\b[A-Z][a-z]{1,}\s[A-Z][a-z]{1,}\b")

# A real, non-exhaustive stoplist of common capitalized business/KPI vocabulary this
# codebase's own dashboards actually publish (core/department_intelligence.py's real
# label strings -- "Total Gross Profit", "Avg Sale Price", "Effective Labor Rate",
# etc. -- plus common department/report words used elsewhere), so name_heuristic
# doesn't constantly fire on ordinary business phrases. A match is only reported when
# at least one of its two words is NOT in this list -- both words being stoplisted
# ("Gross Profit") is treated as safe; a mix ("Total Priya" would still fire, since
# "Priya" isn't stoplisted) is not. Deliberately does not claim to make the heuristic
# precise -- see the module docstring's own stated limitation.
COMMON_NON_NAME_WORDS = {
    "total", "gross", "net", "avg", "average", "sale", "sales", "sold", "price", "profit",
    "unit", "units", "rate", "cost", "revenue", "margin", "volume", "count", "score",
    "ratio", "percent", "index", "report", "overview", "summary", "health", "status",
    "value", "amount", "balance", "payment", "contract", "deal", "deals", "vehicle",
    "vehicles", "service", "parts", "finance", "marketing", "inventory", "reporting",
    "executive", "contribution", "recoverable", "projected", "month", "end", "effective",
    "labor", "repair", "order", "obsolete", "turns", "reserve", "income", "per",
    "financed", "apr", "customer", "pay", "operations", "administration", "readiness",
    "network", "workforce", "coaching", "collections", "recovery", "risk", "credit",
    "closing", "close", "show", "appointment", "lead", "opportunity", "month-end",
    "wholesale", "actual", "budget", "forecast", "goal", "target", "expense", "expenses",
    "pending", "completed", "active", "open", "closed", "average", "median", "growth",
    "loss", "gain", "utilization", "capacity", "productivity", "efficiency",
}


def _is_stoplisted_pair(match_text):

    words = [w.lower() for w in match_text.split()]
    return all(w in COMMON_NON_NAME_WORDS for w in words)


def _scan_string(value):

    findings = []

    if _EMAIL_PATTERN.search(value):
        findings.append({"type": "email", "confidence": "high", "value_excerpt": value[:60]})

    if _PHONE_PATTERN.search(value):
        findings.append({"type": "phone", "confidence": "high", "value_excerpt": value[:60]})

    if _SSN_PATTERN.search(value):
        findings.append({"type": "ssn", "confidence": "high", "value_excerpt": value[:60]})

    if _VIN_PATTERN.search(value):
        findings.append({"type": "vin", "confidence": "high", "value_excerpt": value[:60]})

    for match in _NAME_HEURISTIC_PATTERN.finditer(value):
        if not _is_stoplisted_pair(match.group()):
            findings.append({
                "type": "name_heuristic",
                "confidence": "low",
                "value_excerpt": value[:60],
            })

    return findings


def scan_object(obj, path="root", findings=None):
    """Recursively scans any real Python dict/list/tuple/str structure for the 5 PII
    categories above. `path` tracks a real, human-readable location string per finding
    (dict keys joined by '.', list indices in brackets), so a caller can tell WHERE in
    a large nested structure a leak was found, not just that one exists somewhere."""

    if findings is None:
        findings = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            scan_object(value, f"{path}.{key}", findings)
    elif isinstance(obj, (list, tuple)):
        for index, item in enumerate(obj):
            scan_object(item, f"{path}[{index}]", findings)
    elif isinstance(obj, str):
        for finding in _scan_string(obj):
            finding["path"] = path
            findings.append(finding)

    return findings


class PiiDetectedError(Exception):
    """Raised by assert_no_pii() the instant a HIGH-confidence PII pattern is found.
    Carries the real findings list (each with type/confidence/path/value_excerpt) so a
    caller can log or surface exactly what was caught, not just that something was."""

    def __init__(self, findings, context):
        self.findings = findings
        self.context = context
        high_confidence = [f for f in findings if f["confidence"] == "high"]
        super().__init__(
            f"PII scan blocked {context!r}: {len(high_confidence)} high-confidence "
            f"finding(s) -- {[f['type'] for f in high_confidence]}"
        )


def assert_no_pii(obj, context="data export"):
    """The real blocking pre-flight check. Re-scans `obj` and raises PiiDetectedError
    the instant any HIGH-confidence finding (email/phone/ssn/vin) exists anywhere in
    it. Low-confidence name_heuristic findings are returned for visibility but
    deliberately do NOT block here -- see the module docstring's own stated limitation
    on why that heuristic isn't reliable enough to gate a real feature on.

    Returns the full findings list (including any low-confidence ones) on success, so
    a caller can still inspect/log them without treating them as fatal."""

    findings = scan_object(obj)
    high_confidence = [f for f in findings if f["confidence"] == "high"]

    if high_confidence:
        raise PiiDetectedError(findings, context)

    return findings
