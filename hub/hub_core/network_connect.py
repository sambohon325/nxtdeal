"""
NXTDeal Hub -- NXTDeal Network Connect: the free-tier, pre-customer flywheel
Sam described ("Give Value -> Collect Data -> Create Insight -> Create
Dependency -> Upgrade To NXTDeal"). A browser extension (Chrome/Edge) is the
eventual delivery vehicle -- NOT built this slice, deliberately (Sam scoped
this first pass to "Hub backend foundation": "everything else -- extension,
dashboard, migration scoring -- needs something to talk to"). This module is
that foundation: the identified pre-customer account record, a connector
catalog, Migration Readiness scoring, and the KPI catalog Network Connect
submissions use -- built on infrastructure this codebase already has, not
duplicated.

TWO DATA FLOWS, TWO PRIVACY POSTURES (read this before touching either):

  1. IDENTIFIED (this module, NetworkConnectAccount): company_name,
     contact_email, connected_systems, tier, migration readiness. NXTDeal
     legitimately knows this -- the account signed up with a name and email,
     same as any SaaS free-tier signup, and Migration Readiness is
     EXPLICITLY meant to be NXTDeal-internal-visible per Sam's own spec
     ("Visible to NXTDeal internally. Not necessarily the dealer."). This is
     a genuinely different privacy question from the tenant Network
     rebuild's pseudonym design, which is scoped to the AGGREGATE PEER
     BENCHMARK pool specifically (no dealer's own contributed KPI numbers
     should be attributable to a name when computing "network average"), not
     to whether NXTDeal can know a prospect's own company name at all.

  2. ANONYMOUS (hub/hub_core/network_snapshot.py, completely unchanged): KPI
     values (gross profit, appointment rate, RO count, inventory age, PVR,
     marketing spend, service retention, etc.) submitted under a random,
     unguessable pseudonym MINTED at signup and handed back to the caller
     exactly ONCE in the signup response -- deliberately NEVER stored
     anywhere on the NetworkConnectAccount record itself (there is no
     `pseudonym` field on the dataclass below at all -- that's not an
     oversight, it's the whole mechanism). Mirrors
     backend/core/network_pseudonym.py's own design: "a locally generated
     random token with no derivation from dealer_id/name." Possession of the
     pseudonym IS the access control for KPI ingestion/benchmark retrieval
     (same "unguessable capability token" pattern
     hub_core/approval_center.py's/hub_core/appointment_scheduling.py's public links
     already use in the tenant codebase) -- there is no way for the Hub, or
     even a NXTDeal engineer with full disk access, to look up which
     NetworkConnectAccount a given pseudonym belongs to, because that
     mapping was never written down anywhere. See network_connect_api.py's
     get_benchmark_api() docstring for the one deliberate, disclosed,
     IN-MEMORY-ONLY exception this makes for tier-gating a single request.

ACCOUNT AUTHENTICATION (a third, separate concern from both of the above):
identified account routes (view/update connected systems, view migration
readiness, request conversion to a real Dealer) need their OWN real
authentication, distinct from both the Hub-staff shared key
(X-NXTDeal-Hub-Key) and the anonymous pseudonym above -- a
NetworkConnectAccount is neither a NXTDeal employee nor an anonymous KPI
submission. `account_token` below reuses backend/core/api_keys.py's exact
convention: a real secrets.token_urlsafe(32) value returned in plaintext
exactly once (at signup), with only its SHA-256 hash ever persisted.

CONNECTOR CATALOG: a real, static list matching Sam's own named providers
(CRM/DMS/Website/Marketing/Service). This slice does NOT build real OAuth
integrations for any of them -- Sam's own kickoff message named that as its
own, separate, later "Connector framework" slice (explicitly deferred when
Sam picked "Hub backend foundation" via AskUserQuestion). What IS real here:
an account can record WHICH provider it uses per category (Connected Systems
tracking, Sam's own "Track: CRM/DMS/Website/Marketing/Service" ask), which is
real, honest, and immediately useful for both Migration Readiness and sales
conversations -- it just doesn't pull live data from any of them yet. Every
catalog entry's `integration_status` is honestly "planned," not "real" --
the field exists now so a future connector-framework slice can flip
individual entries as they're actually built, without a schema change.

MIGRATION READINESS: same honest-manual-entry + real-rule-based-computation
split hub/hub_core/dealer_migration.py already established for post-sale Dealer
migrations (see that module's own docstring) -- every readiness percentage
here is NXTDeal-staff-recorded, not auto-derived from connected_systems.
Considered and deliberately rejected: deriving a percentage from whether a
connector is selected. Sam's own readiness categories here (CRM/Inventory/
Service/Finance) don't map 1:1 onto the 5 connector categories above (there
is no "Finance connector" category at all -- Finance data would come via a
DMS or CRM connector, ambiguously), so a computed baseline would misrepresent
"a provider name is selected" as "records are mapped and verified ready,"
which it categorically is not without a real connector actually built.

The Go-Live status (blocked/at_risk/ready), by contrast, IS a real,
transparent rule over whatever readiness percentages have been recorded --
same threshold values as dealer_migration.py's own compute_go_live_status()
(a fresh, sibling function here rather than an import, since the two modules'
readiness categories genuinely differ -- same "two different real-world
things get their own function" precedent this whole codebase's department
rebuilds already established, e.g. Sales' Deal Desk vs. Operations' Vehicle
Lifecycle each getting their own status-lifecycle validator).
"""

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


VALID_TIERS = ["free", "premium"]

VALID_STATUSES = ["active", "trial_expired", "churned", "converted_to_dealer"]

# --- Connector catalog (Sam's own named lists, verbatim) ------------------

CONNECTOR_CATEGORIES = ["crm", "dms", "website", "marketing", "service"]

CONNECTOR_CATEGORY_LABELS = {
    "crm": "CRM",
    "dms": "DMS",
    "website": "Website Platform",
    "marketing": "Marketing / Advertising",
    "service": "Service Platform",
}

# (category, provider_key, display_name, integration_status)
CONNECTOR_CATALOG = [
    ("crm", "vinsolutions", "VinSolutions", "planned"),
    ("crm", "elead", "Elead", "planned"),
    ("crm", "dealersocket_crm", "DealerSocket", "planned"),
    ("crm", "dealerpeak", "DealerPeak", "planned"),
    ("crm", "hubspot", "HubSpot", "planned"),
    ("dms", "cdk", "CDK Global", "planned"),
    ("dms", "reynolds", "Reynolds & Reynolds", "planned"),
    ("dms", "tekion", "Tekion", "planned"),
    ("dms", "autosoft", "AutoSoft", "planned"),
    ("dms", "dealertrack", "DealerTrack", "planned"),
    ("website", "dealeron", "DealerOn", "planned"),
    ("website", "dealer_inspire", "Dealer Inspire", "planned"),
    ("website", "dealerfire", "DealerFire", "planned"),
    ("website", "dealer_com", "Dealer.com", "planned"),
    ("website", "wordpress", "WordPress", "planned"),
    ("marketing", "google", "Google (Analytics / Ads)", "planned"),
    ("marketing", "meta", "Meta (Facebook / Instagram Ads)", "planned"),
    ("marketing", "mailchimp", "Mailchimp", "planned"),
    ("marketing", "klaviyo", "Klaviyo", "planned"),
    ("marketing", "constant_contact", "Constant Contact", "planned"),
    ("service", "xtime", "Xtime", "planned"),
    ("service", "dealerfx", "DealerFX", "planned"),
    ("service", "mykaarma", "myKaarma", "planned"),
]

CONNECTOR_LOOKUP = {
    (category, provider_key): display_name
    for category, provider_key, display_name, _status in CONNECTOR_CATALOG
}


def get_connector_catalog_grouped():
    grouped = {category: [] for category in CONNECTOR_CATEGORIES}
    for category, provider_key, display_name, integration_status in CONNECTOR_CATALOG:
        grouped[category].append({
            "provider_key": provider_key,
            "display_name": display_name,
            "integration_status": integration_status,
        })
    return [
        {
            "category": category,
            "label": CONNECTOR_CATEGORY_LABELS[category],
            "providers": grouped[category],
        }
        for category in CONNECTOR_CATEGORIES
    ]


# --- Migration Readiness (Sam's own named categories, verbatim) -----------

READINESS_CATEGORIES = ["crm", "inventory", "service", "finance"]

READINESS_CATEGORY_LABELS = {
    "crm": "CRM Migration",
    "inventory": "Inventory",
    "service": "Service",
    "finance": "Finance",
}

READY_THRESHOLD_PCT = 95.0
BLOCKED_THRESHOLD_PCT = 80.0

GO_LIVE_STATUSES = ["not_started", "blocked", "at_risk", "ready"]


def compute_go_live_status(readiness):
    """Real, transparent rule over real (manually entered) readiness
    percentages -- see this module's own docstring for the exact thresholds.
    Never raises; always returns a (status, reason) pair."""

    recorded = {
        key: value for key, value in (readiness or {}).items()
        if key in READINESS_CATEGORIES
    }

    if not recorded:
        return "not_started", "No migration-readiness percentages have been recorded yet."

    below_blocked = {key: value for key, value in recorded.items() if value < BLOCKED_THRESHOLD_PCT}
    if below_blocked:
        worst_key, worst_value = min(below_blocked.items(), key=lambda kv: kv[1])
        return "blocked", (
            f"{READINESS_CATEGORY_LABELS.get(worst_key, worst_key)} is at {worst_value}%, "
            f"below the {BLOCKED_THRESHOLD_PCT:.0f}% blocked threshold."
        )

    missing = [category for category in READINESS_CATEGORIES if category not in recorded]
    if missing:
        missing_labels = [READINESS_CATEGORY_LABELS.get(c, c) for c in missing]
        return "at_risk", (
            "No blocking issues among what's recorded so far, but readiness "
            "hasn't been recorded yet for: " + ", ".join(missing_labels) + "."
        )

    below_ready = {key: value for key, value in recorded.items() if value < READY_THRESHOLD_PCT}
    if below_ready:
        worst_key, worst_value = min(below_ready.items(), key=lambda kv: kv[1])
        return "at_risk", (
            "All 4 required categories recorded and clear of the blocked threshold, "
            f"but {READINESS_CATEGORY_LABELS.get(worst_key, worst_key)} is at "
            f"{worst_value}%, below the {READY_THRESHOLD_PCT:.0f}% ready threshold."
        )

    return "ready", (
        f"All {len(READINESS_CATEGORIES)} required categories recorded at or above "
        f"{READY_THRESHOLD_PCT:.0f}%."
    )


# --- KPI catalog (Sam's own "Network Receives" list, verbatim) ------------
# Same {label, value, format} shape hub/hub_core/network_snapshot.py's
# NetworkSnapshot.departments already uses for real NXTDeal tenant
# submissions -- Network Connect submissions land in the EXACT SAME pool
# (hub/storage/network_snapshots.json), no schema change needed there.

NETWORK_CONNECT_KPI_CATALOG = {
    "sales": [
        ("close_rate", "Sales Close Rate", "percent"),
        ("gross_profit", "Gross Profit (per unit, monthly avg)", "currency"),
        ("appointment_rate", "Appointment Rate", "percent"),
    ],
    "service": [
        ("ro_count", "RO Count (monthly)", "number"),
        ("service_retention", "Service Retention", "percent"),
    ],
    "inventory": [
        ("inventory_age_days", "Average Inventory Age (days)", "number"),
        ("inventory_turns", "Inventory Turns (annualized)", "number"),
    ],
    "marketing": [
        ("marketing_spend", "Marketing Spend (monthly)", "currency"),
    ],
    "fi": [
        ("pvr", "PVR (Per Vehicle Retailed)", "currency"),
    ],
}

NETWORK_CONNECT_DEPARTMENTS = list(NETWORK_CONNECT_KPI_CATALOG.keys())

_KPI_KEYS_BY_DEPARTMENT = {
    department: {key for key, _label, _format in kpis}
    for department, kpis in NETWORK_CONNECT_KPI_CATALOG.items()
}


def get_kpi_catalog():
    return [
        {
            "department": department,
            "kpis": [
                {"key": key, "label": label, "format": format}
                for key, label, format in kpis
            ],
        }
        for department, kpis in NETWORK_CONNECT_KPI_CATALOG.items()
    ]


# --- Account model ----------------------------------------------------------

@dataclass
class NetworkConnectAccount:
    account_id: str
    company_name: str
    contact_email: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    tier: str = "free"
    status: str = "active"
    connected_systems: Dict[str, str] = field(default_factory=dict)
    migration_readiness: Dict[str, float] = field(default_factory=dict)
    migration_readiness_notes: Dict[str, str] = field(default_factory=dict)
    account_token_hash: Optional[str] = None
    converted_dealer_id: Optional[str] = None
    created_by: str = "self_signup"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self):
        return {
            "account_id": self.account_id,
            "company_name": self.company_name,
            "contact_email": self.contact_email,
            "contact_name": self.contact_name,
            "contact_phone": self.contact_phone,
            "tier": self.tier,
            "status": self.status,
            "connected_systems": self.connected_systems,
            "migration_readiness": self.migration_readiness,
            "migration_readiness_notes": self.migration_readiness_notes,
            "account_token_hash": self.account_token_hash,
            "converted_dealer_id": self.converted_dealer_id,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data):
        return NetworkConnectAccount(
            account_id=data["account_id"],
            company_name=data["company_name"],
            contact_email=data["contact_email"],
            contact_name=data.get("contact_name"),
            contact_phone=data.get("contact_phone"),
            tier=data.get("tier", "free"),
            status=data.get("status", "active"),
            connected_systems=dict(data.get("connected_systems", {})),
            migration_readiness=dict(data.get("migration_readiness", {})),
            migration_readiness_notes=dict(data.get("migration_readiness_notes", {})),
            account_token_hash=data.get("account_token_hash"),
            converted_dealer_id=data.get("converted_dealer_id"),
            created_by=data.get("created_by", "self_signup"),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
        )

    def public_dict(self):
        """Same as to_dict() minus the hash -- never return account_token_hash
        over the wire, same "never re-expose a stored secret hash" discipline
        backend/core/api_keys.py's own generate_api_key() response follows."""
        out = self.to_dict()
        out.pop("account_token_hash", None)
        return out


class NetworkConnectAccountRegistry:

    def __init__(self):
        self.accounts = {}
        self.id_generator = NetworkConnectIDGenerator()

    def get(self, account_id):
        return self.accounts.get(account_id)

    def get_by_email(self, contact_email):
        for account in self.accounts.values():
            if account.contact_email.lower() == (contact_email or "").lower():
                return account
        return None

    def add(self, account: "NetworkConnectAccount"):
        self.accounts[account.account_id] = account

    def list_all(self):
        return sorted(self.accounts.values(), key=lambda a: a.account_id)

    def reset(self):
        self.accounts = {}
        self.id_generator = NetworkConnectIDGenerator()


class NetworkConnectIDGenerator:
    """Mirrors hub/hub_core/dealer.py's DealerIDGenerator exactly, scoped to the
    "NCA" prefix."""

    def __init__(self):
        self.counter = 0

    def generate(self):
        self.counter += 1
        return f"NCA-{self.counter:05}"

    def recover_from(self, accounts):
        for account in accounts:
            try:
                number = int(account.account_id.split("-")[1])
            except (IndexError, ValueError):
                continue
            if number > self.counter:
                self.counter = number


registry = NetworkConnectAccountRegistry()


# --- Token / pseudonym minting ---------------------------------------------

_ACCOUNT_TOKEN_PREFIX = "ncon_"


def _hash_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _mint_account_token():
    return f"{_ACCOUNT_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def mint_pseudonym():
    """A random, unguessable 256-bit token -- same primitive
    backend/core/network_pseudonym.py uses, minted here and handed back
    ONCE in the signup response. Deliberately never stored anywhere on the
    NetworkConnectAccount record -- see this module's own docstring."""
    return secrets.token_hex(32)


def verify_account_token(account_id, raw_token):
    account = registry.get(account_id)
    if not account or not account.account_token_hash:
        return False
    if not raw_token:
        return False
    return _hash_token(raw_token) == account.account_token_hash


# --- Core mutations ----------------------------------------------------------

def create_account(company_name, contact_email, contact_name=None, contact_phone=None):
    """Returns (account_public_dict, raw_account_token, raw_pseudonym, error).
    On validation failure returns (None, None, None, error) and creates
    nothing, same all-or-nothing precedent as hub_core/provisioning.py's
    create_dealer()."""

    company_name = (company_name or "").strip()
    contact_email = (contact_email or "").strip()

    if not company_name:
        return None, None, None, "company_name is required"

    if not contact_email or "@" not in contact_email:
        return None, None, None, "a valid contact_email is required"

    if registry.get_by_email(contact_email):
        return None, None, None, f"an account with contact_email '{contact_email}' already exists"

    account_id = registry.id_generator.generate()
    raw_token = _mint_account_token()
    raw_pseudonym = mint_pseudonym()

    account = NetworkConnectAccount(
        account_id=account_id,
        company_name=company_name,
        contact_email=contact_email,
        contact_name=contact_name,
        contact_phone=contact_phone,
        account_token_hash=_hash_token(raw_token),
    )

    registry.add(account)

    return account.public_dict(), raw_token, raw_pseudonym, None


def set_connected_system(account_id, category, provider_key, updated_by="self_service"):

    account = registry.get(account_id)
    if not account:
        return None, f"no account with id '{account_id}'"

    if category not in CONNECTOR_CATEGORIES:
        return None, f"category must be one of {CONNECTOR_CATEGORIES}"

    if provider_key is None:
        account.connected_systems.pop(category, None)
    else:
        if (category, provider_key) not in CONNECTOR_LOOKUP:
            return None, f"unknown provider_key '{provider_key}' for category '{category}'"
        account.connected_systems[category] = provider_key

    account.updated_at = _now_iso()
    registry.add(account)

    return get_account_detail(account_id), None


def set_tier(account_id, tier, updated_by="nxtdeal_staff"):

    account = registry.get(account_id)
    if not account:
        return None, f"no account with id '{account_id}'"

    if tier not in VALID_TIERS:
        return None, f"tier must be one of {VALID_TIERS}"

    account.tier = tier
    account.updated_at = _now_iso()
    registry.add(account)

    return get_account_detail(account_id), None


def set_status(account_id, status, updated_by="nxtdeal_staff"):

    account = registry.get(account_id)
    if not account:
        return None, f"no account with id '{account_id}'"

    if status not in VALID_STATUSES:
        return None, f"status must be one of {VALID_STATUSES}"

    account.status = status
    account.updated_at = _now_iso()
    registry.add(account)

    return get_account_detail(account_id), None


def set_migration_readiness(account_id, category, pct, note=None, updated_by="nxtdeal_staff"):

    account = registry.get(account_id)
    if not account:
        return None, f"no account with id '{account_id}'"

    if category not in READINESS_CATEGORIES:
        return None, f"category must be one of {READINESS_CATEGORIES}"

    try:
        pct = float(pct)
    except (TypeError, ValueError):
        return None, "pct must be a number"

    if pct < 0 or pct > 100:
        return None, "pct must be between 0 and 100"

    account.migration_readiness[category] = round(pct, 1)
    if note is not None:
        account.migration_readiness_notes[category] = note
    account.updated_at = _now_iso()
    registry.add(account)

    return get_account_detail(account_id), None


def mark_converted(account_id, dealer_id):

    account = registry.get(account_id)
    if not account:
        return None, f"no account with id '{account_id}'"

    account.status = "converted_to_dealer"
    account.converted_dealer_id = dealer_id
    account.updated_at = _now_iso()
    registry.add(account)

    return get_account_detail(account_id), None


# --- Composed reads -----------------------------------------------------------

def get_account_detail(account_id):

    account = registry.get(account_id)
    if not account:
        return None

    go_live_status, go_live_reason = compute_go_live_status(account.migration_readiness)

    connected_out = []
    for category in CONNECTOR_CATEGORIES:
        provider_key = account.connected_systems.get(category)
        connected_out.append({
            "category": category,
            "label": CONNECTOR_CATEGORY_LABELS[category],
            "provider_key": provider_key,
            "provider_display_name": (
                CONNECTOR_LOOKUP.get((category, provider_key)) if provider_key else None
            ),
        })

    readiness_out = []
    for category in READINESS_CATEGORIES:
        readiness_out.append({
            "key": category,
            "label": READINESS_CATEGORY_LABELS[category],
            "pct": account.migration_readiness.get(category),
            "note": account.migration_readiness_notes.get(category),
        })

    result = account.public_dict()
    result["connected_systems_detail"] = connected_out
    result["migration_readiness_detail"] = readiness_out
    result["go_live_status"] = go_live_status
    result["go_live_reason"] = go_live_reason
    result["migration_readiness_note"] = (
        "Every readiness percentage here is honest manual data entry -- no "
        "real CRM/DMS connector exists anywhere in this codebase yet to "
        "auto-compute a real migration-completeness percentage (Sam's "
        "kickoff scoped that as its own, separate, later 'Connector "
        "framework' slice). go_live_status IS a real, rule-based "
        f"computation over those recorded numbers (ready >= "
        f"{READY_THRESHOLD_PCT:.0f}%, blocked < {BLOCKED_THRESHOLD_PCT:.0f}%)."
    )
    return result


def list_all_accounts_summary():

    summaries = []
    for account in registry.list_all():
        go_live_status, _ = compute_go_live_status(account.migration_readiness)
        summaries.append({
            "account_id": account.account_id,
            "company_name": account.company_name,
            "contact_email": account.contact_email,
            "tier": account.tier,
            "status": account.status,
            "connected_system_count": len(account.connected_systems),
            "go_live_status": go_live_status,
            "converted_dealer_id": account.converted_dealer_id,
            "created_at": account.created_at,
        })

    return summaries


def get_network_connect_overview():

    accounts = registry.list_all()

    by_tier = {"free": 0, "premium": 0}
    by_status = {status: 0 for status in VALID_STATUSES}
    by_go_live = {status: 0 for status in GO_LIVE_STATUSES}
    connector_adoption = {category: 0 for category in CONNECTOR_CATEGORIES}

    for account in accounts:
        by_tier[account.tier] = by_tier.get(account.tier, 0) + 1
        by_status[account.status] = by_status.get(account.status, 0) + 1
        go_live_status, _ = compute_go_live_status(account.migration_readiness)
        by_go_live[go_live_status] = by_go_live.get(go_live_status, 0) + 1
        for category in account.connected_systems:
            if category in connector_adoption:
                connector_adoption[category] += 1

    return {
        "total_accounts": len(accounts),
        "by_tier": by_tier,
        "by_status": by_status,
        "by_go_live_status": by_go_live,
        "connector_adoption": connector_adoption,
        "converted_to_dealer_count": by_status.get("converted_to_dealer", 0),
        "note": (
            "Real counts over every real signed-up NetworkConnectAccount. "
            "This is the identified half of Network Connect (company name, "
            "contact info, connected-system selections, migration "
            "readiness) -- it is deliberately NOT joinable to the anonymized "
            "KPI benchmark pool (hub/storage/network_snapshots.json), which "
            "is keyed only by a pseudonym never stored on any account "
            "record. See hub_core/network_connect.py's own module docstring."
        ),
    }
