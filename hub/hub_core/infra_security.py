"""
NXTDeal Hub -- Infrastructure & Platform Operations rebuild, slice 4 of 4
(closing): Security.

Sam's original 12-item menu named "Security" with no further detail
attached before his message was cut off (see CLAUDE.md's slice-1 kickoff
entry for the full 12-item list). Scoped from what's actually real and
checkable at this layer -- two honest halves, neither fabricated:

  1. THE HUB'S OWN security posture -- whether this Hub process's two
     shared-secret auth gates (NXTDEAL_HUB_KEY, the header every Hub route
     requires; DEALEROS_NETWORK_KEY, the header this Hub sends on every
     outbound tenant fetch) are actually set from a real environment
     variable, or are silently running on this codebase's known, published
     dev-only fallback value. Configuration presence and known fallback checks --
     never the actual secret value itself, only whether a real one is
     configured -- matching the self-report pattern every _DEV_FALLBACK_KEY
     constant across this codebase already documents in its own module
     (backend/core/auth.py's DEALEROS_AUTH_SECRET, hub/app.py's own
     NXTDEAL_HUB_KEY, backend/core/network_snapshot_api.py's
     DEALEROS_NETWORK_KEY).

  2. Per-dealer TENANT account-security posture -- session 89's real
     account-lockout/IP-allowlist/password-policy work
     (backend/core/auth.py) had no Hub-visible rollup at all. REUSES, does
     not re-fetch: hub/hub_core/dealer_support.py's already-real operational-
     health snapshot (GET /network/operational-health-snapshot, Dealer
     Management rebuild slice 5), which this same closing slice extended
     with a new `security_posture` block
     (backend/core/audit_network_snapshot.py) rather than standing up a 4th
     narrowly-scoped tenant route for one more small addition. No new
     tenant route, no new Recheck action here -- the Support Center panel's
     own existing Recheck already refreshes a dealer's security posture
     too.

Every figure here is a plain count or boolean -- zero employee id, name, or
email is ever included anywhere in this module, matching this whole
rebuild's own privacy discipline.
"""

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.dealer_support import registry as operational_registry
from hub_core.secrets import is_configured, is_using_dev_fallback


_HUB_KEY_ENV_VAR = "NXTDEAL_HUB_KEY"
_NETWORK_KEY_ENV_VAR = "DEALEROS_NETWORK_KEY"


def get_hub_security_posture():
    """Report configuration presence and known fallback use without values."""
    hub_key_configured = is_configured(_HUB_KEY_ENV_VAR)
    network_key_configured = is_configured(_NETWORK_KEY_ENV_VAR)
    hub_fallback = is_using_dev_fallback(_HUB_KEY_ENV_VAR)
    network_fallback = is_using_dev_fallback(_NETWORK_KEY_ENV_VAR)

    fallback_names = [
        name for name, in_use in (
            (_HUB_KEY_ENV_VAR, hub_fallback),
            (_NETWORK_KEY_ENV_VAR, network_fallback),
        ) if in_use
    ]
    if not fallback_names:
        summary = "Both shared-secret auth gates have configured values distinct from the known development defaults."
    else:
        prefix = "NEITHER shared-secret auth gate has a non-default value. " if len(fallback_names) == 2 else ""
        summary = (
            prefix + ", ".join(fallback_names)
            + " uses a known, published dev-only fallback value, whether unset or explicitly configured."
        )

    return {
        "hub_shared_key_configured_from_env": hub_key_configured,
        "network_shared_key_configured_from_env": network_key_configured,
        "hub_shared_key_using_dev_fallback": hub_fallback,
        "network_shared_key_using_dev_fallback": network_fallback,
        "summary": summary,
        "note": (
            "Configuration presence is separate from known development fallback use. "
            "Both keys require private, non-default values before production use. "
            "This check does not verify key strength, rotation, network access or overall readiness. "
            "No secret value or part of it is included in this response."
        ),
    }



def _dealer_security_entry(dealer):

    snapshot = operational_registry.get(dealer.dealer_id)

    if not snapshot or not snapshot.reachable:
        return {
            "dealer_id": dealer.dealer_id,
            "dealer_name": dealer.name,
            "checked": snapshot is not None,
            "reachable": snapshot.reachable if snapshot else None,
            "fetched_at": snapshot.fetched_at if snapshot else None,
            "security_posture": None,
        }

    return {
        "dealer_id": dealer.dealer_id,
        "dealer_name": dealer.name,
        "checked": True,
        "reachable": True,
        "fetched_at": snapshot.fetched_at,
        "security_posture": snapshot.data.get("security_posture"),
    }


def get_tenant_security_overview():
    """REUSES hub/hub_core/dealer_support.py's already-fetched per-dealer
    operational-health snapshot -- no new tenant route, no separate
    Recheck action."""

    dealers = dealer_registry.list_all()
    entries = [_dealer_security_entry(d) for d in dealers]

    checked = [e for e in entries if e["security_posture"]]

    total_accounts = sum(e["security_posture"]["total_accounts"] for e in checked)
    total_locked = sum(e["security_posture"]["locked_accounts_count"] for e in checked)
    dealers_with_allowlist = len(
        [e for e in checked if e["security_posture"]["ip_allowlisting_in_use"]]
    )

    return {
        "dealers": entries,
        "aggregate": {
            "dealers_checked": len(checked),
            "dealers_total": len(dealers),
            "total_accounts_across_checked_dealers": total_accounts,
            "total_locked_accounts_across_checked_dealers": total_locked,
            "dealers_with_ip_allowlisting_in_use": dealers_with_allowlist,
        },
        "note": (
            "REUSES hub/hub_core/dealer_support.py's already-fetched per-dealer "
            "operational-health snapshot (GET /network/operational-health-"
            "snapshot, extended this slice with a real `security_posture` "
            "block) -- no new tenant route, no separate Recheck action. Use "
            "the Support Center panel's own Recheck to refresh a dealer's "
            "security posture too. Real, aggregate, non-PII counts only -- "
            "no employee id, name, or email is ever included."
        ),
    }


def get_security_overview():

    return {
        "hub_security_posture": get_hub_security_posture(),
        "tenant_account_security": get_tenant_security_overview(),
    }
