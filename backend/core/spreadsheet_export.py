"""Human-facing CSV text protection, separate from lossless machine interchange.

Use a visible text marker rather than invisible quoting that spreadsheet apps may
discard on save. Stored values are unchanged; exported text intentionally differs.
CSV serialization must still use the standard writer to escape cell delimiters.
"""
import unicodedata


def spreadsheet_cell(value):
    if not isinstance(value, str) or not value:
        return value
    candidate = value.lstrip()
    # Some readers ignore a leading BOM or other formatting/control characters.
    while candidate and unicodedata.category(candidate[0]) in ("Cc", "Cf"):
        candidate = candidate[1:].lstrip()
    if (candidate.startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠"))
            or value.startswith(("\t", "\r", "\n"))):
        return "[text] " + value
    return value
