"""
NXTDeal Hub (session 50) -- dealer provisioning: "enter their basic information" ->
a scaffolded, ready-to-boot child portal.

Architecture decision (mine; flagged in CLAUDE.md for Sam to revisit): NXTDeal stays
one codebase, one process per dealer ("process-per-tenant"), not one process serving
many dealers' data. Provisioning a dealer means creating a fresh, empty
backend/storage/tenants/{dealer_id}/ directory (graph.json, audit.json,
credentials.json) that a normal `uvicorn api.app:app` run can point at via the
DEALEROS_STORAGE_DIR env var (see backend/core/storage_paths.py). This was chosen over
teaching the graph/ledger layer to be tenant-aware in-process, because that would mean
touching the singleton repository pattern every hub_core/*.py module relies on -- a much
bigger, riskier rewrite for the same result at this stage. Actually starting that
process (systemd unit, container, whatever "deploy new builds to dealerships" ends up
meaning operationally) is intentionally NOT handled here -- that's real infra work,
flagged as an open decision in BUILD_QUEUE.md, not something to guess at.

Reuses hub_core/auth.py's password hashing so a tenant's first ADMIN credential is created
with the exact same primitives their own running instance will later verify logins
against. Originally this reached across into backend/core/auth.py directly (hub/ and
backend/ are sibling directories, not sub-packages of one another) via a sys.path shim
at import time. Session 87 replaced that with hub/hub_core/auth.py, a vendored copy of the
same file -- see that file's own docstring for why: the cross-directory import broke
the moment hub/ was deployed as its own isolated Coolify app, since Coolify's
per-subdirectory build for Base Directory `hub/` doesn't include the sibling backend/
directory the old shim depended on. `from hub_core.auth import ...` below now resolves
against hub/hub_core/auth.py directly, no sys.path manipulation needed.
"""

import json
import os

from hub_core.auth import CredentialStore, generate_temp_password

from hub_core.dealer import Dealer, VALID_STATUSES
from hub_core.dealer_registry import registry

# Separate from the auth-import question above: create_dealer() below still needs to
# physically write backend/storage/tenants/{dealer_id}/ files to disk (this is
# provisioning's actual job, not an import concern), so _BACKEND_DIR is kept purely as
# a filesystem path constant -- no sys.path manipulation. **Open question, flagged, not
# silently assumed away:** if hub/ is deployed as an isolated Coolify app whose build
# doesn't include the sibling backend/ directory on disk (the same condition that broke
# the old cross-directory auth import -- see this module's docstring), this path won't
# exist at runtime either, and create_dealer()/adopt_dealer() will fail on the
# os.makedirs() call below. That's a real, separate problem from the import crash this
# session fixed: provisioning a dealer inherently needs write access to backend/storage/,
# which can't be vendored away like a stdlib-only file can. If hub ends up truly isolated
# from backend/ in production, this needs either a shared volume between the two
# containers or for provisioning to happen somewhere with real access to backend/ instead
# of inside the Hub's own container -- a deploy-topology decision, not a code guess.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_HERE, "..", "..", "backend"))


def create_dealer(
    name,
    contact_email,
    contact_name=None,
    contact_phone=None,
    address=None,
    city=None,
    state=None,
    plan_tier="Standard",
    network_opt_in=True,
    created_by="nxtdeal_staff"
):
    """Validates input, scaffolds backend/storage/tenants/{dealer_id}/, creates the
    tenant's first ADMIN credential, and registers the Dealer record in memory (caller
    is responsible for calling save_dealers() afterward, same division of
    responsibility as every other core module's create_* function in this codebase).

    Returns (dealer_dict, admin_temp_password, error). On validation failure, returns
    (None, None, error) and creates nothing -- either the whole provision succeeds or
    nothing on disk changes, same "all or nothing" precedent as
    imports/credential_import.py's bulk validation."""

    name = (name or "").strip()
    contact_email = (contact_email or "").strip()

    if not name:
        return None, None, "name is required"

    if not contact_email or "@" not in contact_email:
        return None, None, "a valid contact_email is required"

    if registry.get_by_email(contact_email):
        return None, None, f"a dealer with contact_email '{contact_email}' already exists"

    dealer_id = registry.id_generator.generate()
    slug = registry.id_generator.default_slug()
    storage_dir_relative = f"storage/tenants/{dealer_id}"
    storage_dir_absolute = os.path.join(_BACKEND_DIR, "storage", "tenants", dealer_id)

    os.makedirs(storage_dir_absolute, exist_ok=True)

    # Empty graph -- this dealer's first entities will come from either the same
    # imports/*.py seed scripts every dealer so far has used, or real live use once
    # their instance is deployed and someone logs in.
    with open(
        os.path.join(storage_dir_absolute, "graph.json"), "w", encoding="utf-8"
    ) as file:
        json.dump({"entities": [], "relationships": []}, file, indent=4)

    with open(
        os.path.join(storage_dir_absolute, "audit.json"), "w", encoding="utf-8"
    ) as file:
        json.dump([], file, indent=4)

    admin_temp_password = generate_temp_password()
    admin_employee_id = f"{dealer_id}-ADMIN"

    tenant_credentials = CredentialStore()
    tenant_credentials.set_credential(
        admin_employee_id,
        admin_temp_password,
        role="ADMIN",
        must_change_password=True,
        created_by="nxtdeal_hub",
        email=contact_email
    )

    with open(
        os.path.join(storage_dir_absolute, "credentials.json"), "w", encoding="utf-8"
    ) as file:
        json.dump(tenant_credentials.credentials, file, indent=4)

    dealer = Dealer(
        dealer_id=dealer_id,
        slug=slug,
        name=name,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        address=address,
        city=city,
        state=state,
        plan_tier=plan_tier,
        status="active",
        storage_dir=storage_dir_relative,
        network_opt_in=network_opt_in,
        api_base_url=None,
        created_by=created_by
    )

    registry.add(dealer)

    return dealer.to_dict(), admin_temp_password, None


def adopt_dealer(
    name,
    contact_email,
    storage_dir,
    contact_name=None,
    contact_phone=None,
    address=None,
    city=None,
    state=None,
    plan_tier="Standard",
    network_opt_in=True,
    api_base_url=None,
    created_by="nxtdeal_staff"
):
    """Registers an ALREADY-existing, already-populated NXTDeal instance in the Hub's
    registry -- for adopting "dealer1" (today's one real dealer, seeded with real
    vehicles/leads/employees/deals long before the Hub existed) rather than
    provisioning a brand new empty one. Unlike create_dealer(), this does NOT touch
    `storage_dir` at all: no graph.json/audit.json/credentials.json are written, no new
    admin credential is generated -- that directory already has real data and real
    credentials, and re-scaffolding it would be destructive. `storage_dir` is whatever
    that dealer's backend is (or will be) started with as DEALEROS_STORAGE_DIR --
    today's one real dealer's storage lives at plain "storage" (backend/core/
    storage_paths.py's default), not "storage/tenants/{id}" like a freshly-provisioned
    one, since it predates the tenants/ convention entirely.

    Returns (dealer_dict, error) -- no temp password to hand back, since no credential
    was created here."""

    name = (name or "").strip()
    contact_email = (contact_email or "").strip()
    storage_dir = (storage_dir or "").strip()

    if not name:
        return None, "name is required"

    if not contact_email or "@" not in contact_email:
        return None, "a valid contact_email is required"

    if not storage_dir:
        return None, "storage_dir is required (e.g. \"storage\" for today's one real dealer)"

    if registry.get_by_email(contact_email):
        return None, f"a dealer with contact_email '{contact_email}' already exists"

    dealer_id = registry.id_generator.generate()
    slug = registry.id_generator.default_slug()

    dealer = Dealer(
        dealer_id=dealer_id,
        slug=slug,
        name=name,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        address=address,
        city=city,
        state=state,
        plan_tier=plan_tier,
        status="active",
        storage_dir=storage_dir,
        network_opt_in=network_opt_in,
        api_base_url=api_base_url,
        created_by=created_by
    )

    registry.add(dealer)

    return dealer.to_dict(), None


def set_dealer_status(dealer_id, status):

    if status not in VALID_STATUSES:
        return None, f"status must be one of {VALID_STATUSES}"

    dealer = registry.get(dealer_id)

    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    dealer.status = status
    registry.add(dealer)

    return dealer.to_dict(), None


def set_dealer_api_base_url(dealer_id, api_base_url):
    """Records where a dealer's instance is actually reachable once it's deployed --
    filled in manually (or by whatever deploy tooling gets built later) after
    provisioning, since provisioning itself only scaffolds files, it doesn't launch a
    process. This is what lets the network aggregator (hub_core/network_aggregator.py) call
    a real tenant's own /network/benchmark endpoint instead of only ever seeing
    simulated peers."""

    dealer = registry.get(dealer_id)

    if not dealer:
        return None, f"no dealer with id '{dealer_id}'"

    dealer.api_base_url = api_base_url
    registry.add(dealer)

    return dealer.to_dict(), None
