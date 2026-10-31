"""Read-only numeric normalization for customer inventory projections."""
from math import isfinite


def inventory_number(value, maximum=100000000):
    """Accept existing numeric imports without guessing currency/separators."""
    if isinstance(value, str):
        try:
            value = float(value) if len(value) <= 80 else None
        except ValueError:
            value = None
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not 0 <= value <= maximum or not isfinite(value)):
        return None
    return value
