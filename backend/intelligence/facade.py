"""NXTDeal-facing Chrono facade. Approved engine integration is not yet installed."""
from dataclasses import asdict
from chrono.contracts import Analysis


def analyze():
    return asdict(Analysis("unavailable", None, "1", (), "No approved Chrono engine is installed"))
