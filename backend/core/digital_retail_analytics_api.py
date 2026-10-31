"""
core/digital_retail_analytics_api.py -- API layer for the Digital Retail KPI dashboard
(2026-07-24, DR-8). Read-only operational insight, open to any authenticated role (same
posture as the fleet/workforce/connect/verify views).
"""

from core.digital_retail_analytics import get_digital_retail_dashboard


def get_digital_retail_dashboard_api(role):
    return get_digital_retail_dashboard()
