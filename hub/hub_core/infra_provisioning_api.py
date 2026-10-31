"""
Thin API layer for dealer infrastructure auto-provisioning (2026-07-24). Validate + call +
shape, matching the Hub's *_api.py convention. Route handlers in hub/app.py gate these behind
require_hub_admin.
"""

from hub_core import infra_provisioning


def provision_dealer_api(dealer_id):
    return infra_provisioning.provision_dealer(dealer_id)


def provision_status_api(dealer_id, live=False):
    return infra_provisioning.get_status(dealer_id, live=live)


def provisioning_config_api():
    return infra_provisioning.provisioning_config()
