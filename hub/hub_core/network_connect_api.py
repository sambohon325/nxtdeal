"""
NXTDeal Hub -- NXTDeal Network Connect API layer: the thin validate-call-shape
functions between hub/app.py's route handlers and hub_core/network_connect.py's
core logic, matching every other Hub *_api.py module's convention exactly
(hub_core/dealer_migration_api.py / hub_core/dealer_modules_api.py were both read in
full before writing this one).

Three real, separate concerns handled by three different gate shapes, per
hub_core/network_connect.py's own module docstring -- read that first if this
file's ACL choices look inconsistent, they're not:

  1. IDENTIFIED account routes (view own account, set connected systems) are
     gated by account_token -- the caller must possess the real secret handed
     back exactly once at signup. NOT the Hub-staff key.
  2. NXTDeal-staff-only routes (tier changes, status changes, migration
     readiness, the admin roster/overview, converting an account to a real
     Dealer) are gated by X-NXTDeal-Hub-Key at the ROUTE layer in hub/app.py,
     same as every other Hub route -- this file's functions for those don't
     re-check anything themselves, matching hub_core/dealer_migration_api.py's
     own convention (the route decorator is the enforcement point, not the
     api.py function).
  3. ANONYMOUS KPI ingestion + benchmark retrieval are gated by POSSESSION OF
     THE PSEUDONYM ALONE for ingestion (no account_token needed at all -- the
     whole point of the pseudonym is that submitting a KPI snapshot never has
     to prove who you are), and BOTH account_token (to look up tier) AND
     pseudonym (to fetch "your own" comparison row) for benchmark retrieval.
     See get_benchmark_api()'s own docstring below for the one deliberate,
     disclosed, in-memory-only exception this makes to the "never joinable"
     rule -- it never persists the join, only computes one response with it.
"""

import hashlib
import re
from datetime import datetime, timezone

from hub_core.network_connect import (
    CONNECTOR_CATEGORIES,
    READINESS_CATEGORIES,
    NETWORK_CONNECT_KPI_CATALOG,
    NETWORK_CONNECT_DEPARTMENTS,
    _KPI_KEYS_BY_DEPARTMENT,
    get_connector_catalog_grouped,
    get_kpi_catalog,
    create_account,
    set_connected_system,
    set_tier,
    set_status,
    set_migration_readiness,
    mark_converted,
    get_account_detail,
    list_all_accounts_summary,
    get_network_connect_overview,
    verify_account_token,
    registry as network_connect_registry,
)
from hub_core.network_connect_storage import save_network_connect_accounts

from hub_core.network_snapshot import NetworkSnapshot, registry as snapshot_registry, now_iso
from hub_core.network_snapshot_storage import save_network_snapshots
from hub_core.network_analytics import compute_network_analytics

from hub_core.hub_audit_api import record_and_save
from hub_core.provisioning import create_dealer
from hub_core.dealer_registry import registry as dealer_registry
from hub_core.dealer_storage import save_dealers


NETWORK_CONNECT_ACCOUNTS_PATH = "storage/network_connect_accounts.json"
NETWORK_SNAPSHOTS_PATH = "storage/network_snapshots.json"
DEALERS_PATH = "storage/dealers.json"


# --- Catalog reads (no auth needed -- static reference data) -----------------

def get_connector_catalog_api():
    return {"categories": get_connector_catalog_grouped()}


def get_migration_readiness_catalog_api():
    return {"categories": READINESS_CATEGORIES}


def get_kpi_catalog_api():
    return {"departments": get_kpi_catalog()}


# --- Signup + identified account routes (account_token-gated) ----------------

def signup_network_connect_account_api(company_name, contact_email, contact_name=None, contact_phone=None):
    """Returns the account (public dict, no token hash) plus the raw
    account_token and raw pseudonym -- BOTH shown to the caller exactly once,
    in this one response, and never recoverable again. Same "plaintext once"
    UX backend/core/api_keys.py's generate_api_key() and
    hub_core/provisioning.py's create_dealer() (admin_temp_password) already
    establish."""

    account, raw_token, raw_pseudonym, error = create_account(
        company_name=company_name,
        contact_email=contact_email,
        contact_name=contact_name,
        contact_phone=contact_phone,
    )

    if error:
        return {"error": error}

    save_network_connect_accounts(NETWORK_CONNECT_ACCOUNTS_PATH)

    record_and_save(
        event_type="network_connect_account_created",
        summary=f"Network Connect signup: {account['company_name']} ({account['contact_email']})",
        actor="self_signup",
        details={"account_id": account["account_id"]},
    )

    return {
        "account": account,
        "account_token": raw_token,
        "pseudonym": raw_pseudonym,
        "note": (
            "Save both of these now -- account_token and pseudonym are shown "
            "exactly once and can never be retrieved again. account_token "
            "authenticates you as this account (viewing your own data, "
            "updating connected systems). pseudonym authenticates your "
            "anonymous KPI submissions to the network benchmark pool -- "
            "NXTDeal has no way to look up which account a pseudonym belongs "
            "to, because that mapping is never stored anywhere. If you lose "
            "the pseudonym, past submissions become permanently "
            "unretrievable (a new one just starts a fresh anonymous history "
            "-- nothing to recover, nothing to reset)."
        ),
    }


def get_network_connect_account_api(account_id, account_token):

    if not verify_account_token(account_id, account_token):
        return {"error": "invalid account_id or account_token"}

    return get_account_detail(account_id)


def set_connected_system_api(account_id, account_token, category, provider_key):

    if not verify_account_token(account_id, account_token):
        return {"error": "invalid account_id or account_token"}

    if category not in CONNECTOR_CATEGORIES:
        return {"error": f"category must be one of {CONNECTOR_CATEGORIES}"}

    result, error = set_connected_system(account_id, category, provider_key, updated_by="self_service")

    if error:
        return {"error": error}

    save_network_connect_accounts(NETWORK_CONNECT_ACCOUNTS_PATH)

    record_and_save(
        event_type="network_connect_connected_system_set",
        summary=(
            f"{result['company_name']} connected {category}: "
            f"{provider_key or '(disconnected)'}"
        ),
        actor="self_service",
        details={"account_id": account_id, "category": category, "provider_key": provider_key},
    )

    return result


# --- NXTDeal-staff-only account administration (gated at the route layer) ---

def set_tier_api(account_id, tier, updated_by="nxtdeal_staff"):

    result, error = set_tier(account_id, tier, updated_by=updated_by)

    if error:
        return {"error": error}

    save_network_connect_accounts(NETWORK_CONNECT_ACCOUNTS_PATH)

    record_and_save(
        event_type="network_connect_tier_changed",
        summary=f"{result['company_name']}'s Network Connect tier set to {tier}",
        actor=updated_by,
        details={"account_id": account_id, "tier": tier},
    )

    return result


def set_status_api(account_id, status, updated_by="nxtdeal_staff"):

    result, error = set_status(account_id, status, updated_by=updated_by)

    if error:
        return {"error": error}

    save_network_connect_accounts(NETWORK_CONNECT_ACCOUNTS_PATH)

    record_and_save(
        event_type="network_connect_status_changed",
        summary=f"{result['company_name']}'s Network Connect status set to {status}",
        actor=updated_by,
        details={"account_id": account_id, "status": status},
    )

    return result


def set_migration_readiness_api(account_id, category, pct, note=None, updated_by="nxtdeal_staff"):

    result, error = set_migration_readiness(account_id, category, pct, note=note, updated_by=updated_by)

    if error:
        return {"error": error}

    save_network_connect_accounts(NETWORK_CONNECT_ACCOUNTS_PATH)

    record_and_save(
        event_type="network_connect_migration_readiness_set",
        summary=f"{result['company_name']}'s {category} migration readiness set to {pct}%",
        actor=updated_by,
        details={"account_id": account_id, "category": category, "pct": pct},
    )

    return result


def get_network_connect_account_admin_api(account_id):
    """NXTDeal-staff view of a single account -- no account_token needed
    (the X-NXTDeal-Hub-Key check already happened at the route layer), same
    "staff can see what a self-service caller sees, without needing that
    caller's own secret" pattern as get_dealer_api() alongside every
    dealer's own eventual self-service equivalent."""

    result = get_account_detail(account_id)
    if not result:
        return {"error": f"no Network Connect account with id '{account_id}'"}
    return result


def list_network_connect_accounts_api():
    return {"accounts": list_all_accounts_summary()}


def get_network_connect_overview_api():
    return get_network_connect_overview()


def convert_account_to_dealer_api(account_id, plan_tier="Standard", created_by="nxtdeal_staff"):
    """The one-click "Enable Account -> Activate Migration -> Import Data ->
    Go Live" conversion Sam's own spec described, minus the "Import Data"
    step -- there is no real connector built yet to import FROM (see
    hub_core/network_connect.py's own docstring on why Migration Readiness stays
    honest-manual-entry this slice), so this reuses hub_core/provisioning.py's
    create_dealer() verbatim to scaffold a real, EMPTY tenant instance and
    hands back the same real admin_temp_password create_dealer_api() already
    returns for a normal Hub-console-driven provision -- NXTDeal staff (or a
    future onboarding flow) still walks the new Dealer through real data
    import the same way every other provisioned dealer does today."""

    account = network_connect_registry.get(account_id)
    if not account:
        return {"error": f"no Network Connect account with id '{account_id}'"}

    if account.status == "converted_to_dealer":
        return {"error": f"account '{account_id}' has already been converted (dealer_id={account.converted_dealer_id})"}

    dealer, admin_temp_password, error = create_dealer(
        name=account.company_name,
        contact_email=account.contact_email,
        contact_name=account.contact_name,
        contact_phone=account.contact_phone,
        plan_tier=plan_tier,
        network_opt_in=True,
        created_by=created_by,
    )

    if error:
        return {"error": error}

    save_dealers(DEALERS_PATH)

    updated_account, error = mark_converted(account_id, dealer["dealer_id"])
    if error:
        # Extremely unlikely (the account was just confirmed to exist above), but
        # don't silently leave a real, just-created Dealer unlinked from its
        # originating account if it somehow does happen.
        return {"error": f"dealer '{dealer['dealer_id']}' was created, but linking it back to the account failed: {error}"}

    save_network_connect_accounts(NETWORK_CONNECT_ACCOUNTS_PATH)

    record_and_save(
        event_type="network_connect_converted_to_dealer",
        summary=f"{account.company_name} converted from Network Connect to a real Dealer ({dealer['dealer_id']})",
        dealer_id=dealer["dealer_id"],
        actor=created_by,
        details={"account_id": account_id, "dealer_id": dealer["dealer_id"]},
    )

    return {
        "dealer": dealer,
        "admin_employee_id": f"{dealer['dealer_id']}-ADMIN",
        "admin_temp_password": admin_temp_password,
        "network_connect_account": updated_account,
        "note": (
            "A real, empty NXTDeal tenant instance has been scaffolded, "
            "same as any other Hub-provisioned dealer -- no data was "
            "imported (Network Connect has no connected-data-import "
            "mechanism yet, only connected-system tracking). Deploy this "
            "instance and walk the dealer through real data import the same "
            "way any other new dealer onboarding does."
        ),
    }


# --- Anonymous KPI ingestion + benchmark retrieval ----------------------------
# Same bucket sizes hub_core/network_snapshot.py (tenant side) already established
# -- duplicated here, not imported, since hub/ and backend/ are sibling
# directories each with their own same-named "core" package (no cross-package
# import path exists between them, same reason hub_core/auth.py had to be
# vendored into hub/ rather than shimmed -- see hub_core/provisioning.py's own
# docstring).

_BUCKET_SIZE_BY_FORMAT = {"currency": 500, "number": 5, "percent": 1}


def _bucket(value, format):
    if not isinstance(value, (int, float)):
        return value
    size = _BUCKET_SIZE_BY_FORMAT.get(format, 1)
    if size <= 0:
        return value
    return round(value / size) * size


def submit_kpi_snapshot_api(pseudonym, departments):
    """Anonymous by design -- no account_token, no account lookup, nothing
    that could join this submission back to a specific NetworkConnectAccount.
    Possession of the pseudonym is the only credential this needs, same as
    every other pseudonym-gated write in this codebase. Values are bucketed
    server-side too (redundant with whatever the eventual browser
    extension/connector does client-side) so a submission can never bypass
    the coarseness guarantee by skipping client-side bucketing."""

    pseudonym = (pseudonym or "").strip()
    if not pseudonym:
        return {"error": "pseudonym is required"}

    # Minimal, non-breaking hardening: a real pseudonym is mint_pseudonym()'s 64-hex-char token, so
    # reject anything not even shaped like one. This does NOT fully close pool-poisoning — by design
    # the Hub never stores pseudonyms, so it can't confirm a given one was actually minted, nor
    # rate-limit per account without eroding that unlinkability. A real abuse control (per-IP rate
    # limit, or a network-key gate on this endpoint) is a deliberate design decision, flagged apart.
    if not re.fullmatch(r"[0-9a-fA-F]{64}", pseudonym):
        return {"error": "pseudonym is not a valid network pseudonym"}

    if not isinstance(departments, dict) or not departments:
        return {"error": "departments must be a non-empty object, e.g. {\"sales\": {\"close_rate\": 16.2}}"}

    bucketed = {}

    for department, kpi_values in departments.items():

        if department not in NETWORK_CONNECT_DEPARTMENTS:
            return {"error": f"unknown department '{department}' -- must be one of {NETWORK_CONNECT_DEPARTMENTS}"}

        if not isinstance(kpi_values, dict):
            return {"error": f"departments['{department}'] must be an object of {{kpi_key: value}}"}

        valid_keys = _KPI_KEYS_BY_DEPARTMENT[department]
        kpi_lookup = {key: (label, fmt) for key, label, fmt in NETWORK_CONNECT_KPI_CATALOG[department]}

        department_out = {}

        for kpi_key, value in kpi_values.items():

            if kpi_key not in valid_keys:
                return {"error": f"unknown KPI '{kpi_key}' for department '{department}'"}

            try:
                value = float(value)
            except (TypeError, ValueError):
                return {"error": f"'{department}.{kpi_key}' must be a number"}

            label, fmt = kpi_lookup[kpi_key]

            department_out[kpi_key] = {
                "label": label,
                "format": fmt,
                "value": _bucket(value, fmt),
            }

        if department_out:
            bucketed[department] = department_out

    if not bucketed:
        return {"error": "no valid KPI values were provided"}

    snapshot = NetworkSnapshot(
        pseudonym=pseudonym,
        submitted_at=now_iso(),
        collected_at=now_iso(),
        departments=bucketed,
    )

    snapshot_registry.upsert(snapshot)
    save_network_snapshots(NETWORK_SNAPSHOTS_PATH)

    return {
        "accepted": True,
        "departments_recorded": list(bucketed.keys()),
        "note": (
            "Recorded anonymously under your pseudonym. This replaces any "
            "prior submission under the same pseudonym (only the latest "
            "snapshot per pseudonym is kept), same convention "
            "hub/hub_core/network_snapshot.py already established for real "
            "NXTDeal tenant submissions -- Network Connect submissions land "
            "in the exact same benchmark pool."
        ),
    }


_LOWER_IS_BETTER_KPIS = {"inventory_age_days"}
_NOT_RANKED_KPIS = {"marketing_spend"}

_KPI_CAUSE_CATALOG = {
    "service_retention": {
        "common_causes": [
            "Low DVI (digital vehicle inspection) adoption",
            "Missed maintenance follow-up outreach",
            "No structured post-sale service reminder cadence",
        ],
        "common_actions": [
            "Deploy a service retention campaign",
            "Enable AI-assisted service follow-up",
            "Activate a 30-day maintenance recovery sequence",
        ],
    },
    "inventory_turns": {
        "common_causes": [
            "Aging units not flagged for price reduction early enough",
            "Limited merchandising / incomplete online listings",
            "Acquisition mix not matched to current demand",
        ],
        "common_actions": [
            "Set up an aging-inventory price-reduction workflow",
            "Audit online listing completeness (photos, descriptions)",
            "Review acquisition sourcing against real sell-through data",
        ],
    },
    "inventory_age_days": {
        "common_causes": [
            "No systematic aging-inventory review cadence",
            "Pricing not adjusted against real days-in-stock",
        ],
        "common_actions": [
            "Set up a weekly aging-inventory review",
            "Automate price adjustments past defined age thresholds",
        ],
    },
    "close_rate": {
        "common_causes": [
            "Inconsistent up-desk / lead-response process",
            "Limited follow-up cadence on unclosed opportunities",
        ],
        "common_actions": [
            "Standardize a lead-response SLA",
            "Deploy a structured follow-up cadence for open deals",
        ],
    },
    "appointment_rate": {
        "common_causes": [
            "Slow lead response time",
            "No automated appointment-confirmation/reminder flow",
        ],
        "common_actions": [
            "Speed up lead-response time with automated first-touch",
            "Add appointment confirmation + reminder messaging",
        ],
    },
    "gross_profit": {
        "common_causes": [
            "Limited desking discipline / pencil process",
            "Under-presented F&I product menu",
        ],
        "common_actions": [
            "Standardize a multi-scenario desking process",
            "Ensure F&I products are presented on every deal",
        ],
    },
    "pvr": {
        "common_causes": [
            "F&I product penetration below network norms",
            "Limited menu presentation consistency",
        ],
        "common_actions": [
            "Track F&I product penetration by deal",
            "Standardize menu presentation across the sales team",
        ],
    },
    "ro_count": {
        "common_causes": [
            "Limited service marketing / low customer pay volume",
            "No proactive service-drive outreach",
        ],
        "common_actions": [
            "Deploy a service-drive outreach campaign",
            "Review service capacity and scheduling availability",
        ],
    },
}

_PREMIUM_DISCLAIMER = (
    "These are common patterns observed across dealerships generally for "
    "this KPI, not a diagnosis of your specific operations -- Network "
    "Connect doesn't have access to your internal systems yet (no CRM/DMS "
    "connector is built yet, see the Connectors screen). Connecting a real "
    "system in a future release would let this become a specific, "
    "data-grounded diagnosis instead of a general pattern."
)

_NOT_YET_AVAILABLE_NOTE = (
    "Not yet available -- this requires a real history of submissions over "
    "time (for a trend) or a real connected data source (for a workflow "
    "automation plan), neither of which exists yet for any Network Connect "
    "account. Shown here, honestly empty, to prove the premium-tier gate is "
    "real and where this content will eventually appear."
)


def _gap_and_direction(kpi_key, your_value, network_average):

    if your_value is None or network_average is None:
        return None, None, None

    lower_is_better = kpi_key in _LOWER_IS_BETTER_KPIS

    if lower_is_better:
        gap = your_value - network_average
    else:
        gap = network_average - your_value

    if gap > 0.0001:
        direction = "behind"
        opportunity_gap = gap
    elif gap < -0.0001:
        direction = "ahead"
        opportunity_gap = 0
    else:
        direction = "even"
        opportunity_gap = 0

    return direction, round(gap, 2), round(opportunity_gap, 2)


# k-anonymity floor: below this many PEER contributors, an aggregate (or its inverse) can reveal an
# individual dealer's exact value, so benchmarks/percentiles are suppressed.
MIN_BENCHMARK_CONTRIBUTORS = 5


def _percentile_rank(department, kpi_key, your_value, lower_is_better, your_pseudonym=None):
    """A REAL percentile computed from the raw individual snapshot values (excluding the caller's
    own submission — a dealer never ranks against itself). Honestly None when there aren't enough
    PEERS to mean anything (k-anonymity floor)."""

    your_pseudonym = (your_pseudonym or "").strip()
    values = []
    for snapshot in snapshot_registry.list_all():
        if your_pseudonym and snapshot.pseudonym == your_pseudonym:
            continue  # exclude self — you can't beat/lose to your own number
        kpi = snapshot.departments.get(department, {}).get(kpi_key)
        if kpi and isinstance(kpi.get("value"), (int, float)):
            values.append(kpi["value"])

    sample_size = len(values)   # PEER count (self excluded)

    if your_value is None or sample_size < MIN_BENCHMARK_CONTRIBUTORS:
        return None, sample_size

    if lower_is_better:
        beaten = sum(1 for v in values if v >= your_value)
    else:
        beaten = sum(1 for v in values if v <= your_value)

    percentile = round((beaten / sample_size) * 100, 1)

    return percentile, sample_size


def get_benchmark_api(account_id, account_token, pseudonym):
    """Requires BOTH a valid account_token (to look up the account's tier,
    for paywall gating) AND the account's own pseudonym (to fetch that
    submission's own KPI values for a "you vs. network" comparison).

    THE ONE DELIBERATE, DISCLOSED EXCEPTION to "never joinable" in this whole
    module: for the few milliseconds this one request/response cycle takes,
    this function holds both an identified account_id AND a pseudonym in
    local variables at the same time, because the CALLER handed both to it
    in the same request (the caller obviously already knows both -- they're
    the account holder). This is NOT a stored join anywhere -- nothing here
    writes account_id and pseudonym into the same record, log line, or file.
    The account record itself still has no pseudonym field (see
    hub_core/network_connect.py's dataclass), and the snapshot record itself
    still has no account_id field (see hub_core/network_snapshot.py's
    dataclass). Mirrors hub/hub_core/network_collector.py's own documented
    exception ("the Hub still knows WHICH dealers it successfully reached...
    even though it can't tell which pseudonym belongs to which") -- same
    shape, applied to one interactive request instead of a collection pass.
    """

    if not verify_account_token(account_id, account_token):
        return {"error": "invalid account_id or account_token"}

    account = network_connect_registry.get(account_id)
    tier = account.tier

    your_snapshot = snapshot_registry.get((pseudonym or "").strip())

    if not your_snapshot:
        return {
            "error": (
                "no KPI snapshot found for this pseudonym yet -- submit one "
                "via POST /network-connect/kpi-snapshot first"
            )
        }

    network_aggregate = compute_network_analytics()

    comparisons = []
    percentile_sum = 0.0
    percentile_count = 0

    for department, kpi_catalog in NETWORK_CONNECT_KPI_CATALOG.items():
        for kpi_key, label, fmt in kpi_catalog:

            your_kpi = your_snapshot.departments.get(department, {}).get(kpi_key)
            if not your_kpi:
                continue

            your_value = your_kpi.get("value")

            network_kpi = network_aggregate.get("departments", {}).get(department, {}).get(kpi_key, {})
            network_average = network_kpi.get("average")
            network_median = network_kpi.get("median")
            sample_size = network_kpi.get("sample_size", 0)

            # k-anonymity: below the contributor floor an aggregate (or its inverse, 2*avg - own)
            # reveals another dealer's exact value — suppress the numbers rather than leak them.
            suppressed_below_k = sample_size < MIN_BENCHMARK_CONTRIBUTORS
            if suppressed_below_k:
                network_average = None
                network_median = None

            lower_is_better = kpi_key in _LOWER_IS_BETTER_KPIS
            not_ranked = kpi_key in _NOT_RANKED_KPIS

            direction, gap, opportunity_gap = (None, None, None)
            if not not_ranked and network_average is not None:
                direction, gap, opportunity_gap = _gap_and_direction(kpi_key, your_value, network_average)

            percentile, percentile_sample_size = (None, 0)
            if not not_ranked:
                percentile, percentile_sample_size = _percentile_rank(department, kpi_key, your_value, lower_is_better, your_pseudonym=pseudonym)
                if percentile is not None:
                    percentile_sum += percentile
                    percentile_count += 1

            # A dollar-denominated opportunity estimate is only meaningful when
            # the KPI itself is already currency-shaped -- there is no
            # per-account operational graph here (unlike the tenant-side
            # hub_core/network_opportunity_value.py, which can multiply a count gap
            # by that SAME dealer's own real per-unit dollar value) to derive
            # one for percent/number-format KPIs, so those are honestly
            # reported as not dollar-convertible rather than guessed at.
            dollar_opportunity = None
            dollar_basis = "not_convertible_to_dollars"
            if fmt == "currency" and opportunity_gap:
                dollar_opportunity = opportunity_gap
                dollar_basis = "direct_currency"
            elif fmt != "currency":
                dollar_basis = "not_convertible_to_dollars -- no per-account operational data exists to derive a real dollar multiplier for this KPI"

            comparisons.append({
                "department": department,
                "kpi_key": kpi_key,
                "label": label,
                "format": fmt,
                "your_value": your_value,
                "network_average": network_average,
                "network_median": network_median,
                "network_sample_size": sample_size,
                "suppressed_below_k": suppressed_below_k,
                "lower_is_better": lower_is_better,
                "not_ranked": not_ranked,
                "direction": direction,
                "gap": gap,
                "opportunity_gap": opportunity_gap,
                "your_percentile": percentile,
                "percentile_sample_size": percentile_sample_size,
                "dollar_opportunity_monthly": dollar_opportunity,
                "dollar_opportunity_basis": dollar_basis,
            })

    overall_score = round(percentile_sum / percentile_count, 1) if percentile_count else None

    opportunities = [c for c in comparisons if c["direction"] == "behind"]
    opportunities.sort(
        key=lambda c: (
            0 if c["dollar_opportunity_monthly"] else 1,
            -(c["dollar_opportunity_monthly"] or 0),
            -(c["opportunity_gap"] or 0),
        )
    )
    top_opportunities = opportunities[:5]

    daily_brief = _build_daily_brief(account.company_name, overall_score, top_opportunities, tier)

    result = {
        "account_id": account_id,
        "company_name": account.company_name,
        "tier": tier,
        "overall_score": overall_score,
        "overall_score_note": (
            "Average of your real percentile rank across every KPI you've "
            "submitted a value for (each KPI's own percentile is computed "
            "from the actual submitted values in the network pool, not from "
            "the average/median alone). Segmented rankings (by industry, "
            "OEM, or region) aren't available yet -- signup doesn't collect "
            "any of those attributes, an honest gap, not a fabricated second "
            "number."
        ) if overall_score is not None else "Not enough network data yet to compute a percentile.",
        "comparisons": comparisons,
        "top_opportunities": [
            {
                "department": o["department"],
                "kpi_key": o["kpi_key"],
                "label": o["label"],
                "format": o["format"],
                "your_value": o["your_value"],
                "network_average": o["network_average"],
                "gap": o["gap"],
                "dollar_opportunity_monthly": o["dollar_opportunity_monthly"],
            }
            for o in top_opportunities
        ],
        "daily_brief": daily_brief,
        "dealers_contributing": network_aggregate.get("dealers_contributing", 0),
    }

    if tier == "premium":
        result["premium_insights"] = _build_premium_insights(top_opportunities)
    else:
        result["premium_teaser"] = {
            "locked": True,
            "message": (
                "Upgrade to Network Premium to see the probable cause and "
                "recommended actions behind each opportunity above, plus a "
                "forecast and automation plan."
            ),
            "example": _KPI_CAUSE_CATALOG.get("service_retention"),
        }

    return result


def _build_premium_insights(top_opportunities):

    insights = []
    for o in top_opportunities:
        pattern = _KPI_CAUSE_CATALOG.get(o["kpi_key"])
        insights.append({
            "kpi_key": o["kpi_key"],
            "label": o["label"],
            "common_causes": pattern["common_causes"] if pattern else [],
            "common_actions": pattern["common_actions"] if pattern else [],
            "disclaimer": _PREMIUM_DISCLAIMER,
        })

    return {
        "root_cause_and_action_plans": insights,
        "forecast": {"available": False, "note": _NOT_YET_AVAILABLE_NOTE},
        "playbook": {"available": False, "note": _NOT_YET_AVAILABLE_NOTE},
        "automation_plan": {"available": False, "note": _NOT_YET_AVAILABLE_NOTE},
    }


def _build_daily_brief(company_name, overall_score, top_opportunities, tier):
    """A real, rule-based single-paragraph summary built from the real
    figures above -- NOT an OpenAI call (no isolated-wizard module was built
    for this slice) and NOT a fabricated statistic. Sam's own spec example
    ("Top performing network stores using this strategy increased retention
    by 14%") is a mockup flourish -- deliberately NOT reproduced here, since
    no real per-store outcome data exists anywhere in this codebase to back
    a claim like that."""

    if overall_score is None:
        return (
            f"Good morning. Not enough network data yet to rank {company_name} -- "
            "submit a KPI snapshot to get your first benchmark."
        )

    if not top_opportunities:
        return (
            f"Good morning. {company_name} ranks in the {overall_score:.0f}th percentile "
            "across the KPIs you've submitted, with no significant opportunities "
            "identified against the current network pool."
        )

    top = top_opportunities[0]

    if top["dollar_opportunity_monthly"]:
        opportunity_line = (
            f"Largest opportunity: {top['label']}, an estimated "
            f"${top['dollar_opportunity_monthly']:,.0f}/month gap vs. the network average."
        )
    else:
        opportunity_line = (
            f"Largest opportunity: {top['label']}, "
            f"{top['gap']:.1f} {'points' if top['format'] == 'percent' else 'units'} "
            "behind the network average."
        )

    action_line = (
        "See your Network Premium insights for the recommended action." if tier == "premium"
        else "Upgrade to Network Premium to see the probable cause and recommended action."
    )

    return (
        f"Good morning. {company_name} ranks in the {overall_score:.0f}th percentile "
        f"across the network. {opportunity_line} {action_line}"
    )
