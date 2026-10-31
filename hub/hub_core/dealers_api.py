"""
NXTDeal Hub (session 50) -- thin functions between hub/app.py's route handlers and
hub_core/provisioning.py, matching backend/core/*_api.py's "validate + call the real
function + shape the response" convention.
"""

from hub_core.provisioning import (
    create_dealer,
    adopt_dealer,
    set_dealer_status,
    set_dealer_api_base_url
)
from hub_core.dealer_profile import (
    update_dealer_profile,
    update_dealer_subscription,
    update_dealer_version
)
from hub_core.dealer_overview import get_dealer_management_overview
from hub_core.dealer_registry import registry
from hub_core.dealer_storage import save_dealers
from hub_core.hub_audit_api import record_and_save

DEALERS_PATH = "storage/dealers.json"


def create_dealer_api(
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

    dealer, admin_temp_password, error = create_dealer(
        name=name,
        contact_email=contact_email,
        contact_name=contact_name,
        contact_phone=contact_phone,
        address=address,
        city=city,
        state=state,
        plan_tier=plan_tier,
        network_opt_in=network_opt_in,
        created_by=created_by
    )

    if error:
        return {"error": error}

    save_dealers(DEALERS_PATH)

    return {
        "dealer": dealer,
        "admin_employee_id": f"{dealer['dealer_id']}-ADMIN",
        "admin_temp_password": admin_temp_password,
        "note": (
            "Store this temp password now -- it is never shown again. The dealer's "
            "instance must be started with DEALEROS_STORAGE_DIR={} for this credential "
            "to be usable.".format(dealer["storage_dir"])
        )
    }


def adopt_dealer_api(
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

    dealer, error = adopt_dealer(
        name=name,
        contact_email=contact_email,
        storage_dir=storage_dir,
        contact_name=contact_name,
        contact_phone=contact_phone,
        address=address,
        city=city,
        state=state,
        plan_tier=plan_tier,
        network_opt_in=network_opt_in,
        api_base_url=api_base_url,
        created_by=created_by
    )

    if error:
        return {"error": error}

    save_dealers(DEALERS_PATH)

    return {
        "dealer": dealer,
        "note": (
            "No credential was created -- {} already has its own real "
            "credentials.json. Existing logins are unaffected.".format(storage_dir)
        )
    }


def list_dealers_api():
    return [dealer.to_dict() for dealer in registry.list_all()]


def get_dealer_api(dealer_id):
    dealer = registry.get(dealer_id)
    if not dealer:
        return {"error": f"no dealer with id '{dealer_id}'"}
    return dealer.to_dict()


def update_dealer_status_api(dealer_id, status):
    dealer, error = set_dealer_status(dealer_id, status)
    if error:
        return {"error": error}
    save_dealers(DEALERS_PATH)
    record_and_save(
        event_type="dealer_status_changed",
        summary=f"Dealer {dealer_id} status set to '{status}'",
        dealer_id=dealer_id,
        details={"status": status},
    )
    return dealer


def update_dealer_api_base_url_api(dealer_id, api_base_url):
    dealer, error = set_dealer_api_base_url(dealer_id, api_base_url)
    if error:
        return {"error": error}
    save_dealers(DEALERS_PATH)
    record_and_save(
        event_type="dealer_api_base_url_updated",
        summary=f"Dealer {dealer_id} api_base_url updated",
        dealer_id=dealer_id,
        details={"api_base_url": api_base_url},
    )
    return dealer


def get_dealer_management_overview_api():
    """The real Overview screen -- KPIs + Dealer Lifecycle Funnel off this Hub's own
    registry. See hub_core/dealer_overview.py's own module docstring."""

    return get_dealer_management_overview()


def update_dealer_profile_api(
    dealer_id,
    group=None,
    oem=None,
    location_count=None,
    industry_type=None,
    region=None
):
    dealer, error = update_dealer_profile(
        dealer_id,
        group=group,
        oem=oem,
        location_count=location_count,
        industry_type=industry_type,
        region=region
    )
    if error:
        return {"error": error}
    save_dealers(DEALERS_PATH)
    record_and_save(
        event_type="dealer_profile_updated",
        summary=f"Dealer {dealer_id} profile updated",
        dealer_id=dealer_id,
        details={"group": group, "oem": oem, "location_count": location_count, "industry_type": industry_type, "region": region},
    )
    return dealer


def update_dealer_subscription_api(
    dealer_id,
    plan_tier=None,
    active_modules=None,
    renewal_date=None,
    seat_count=None
):
    dealer, error = update_dealer_subscription(
        dealer_id,
        plan_tier=plan_tier,
        active_modules=active_modules,
        renewal_date=renewal_date,
        seat_count=seat_count
    )
    if error:
        return {"error": error}
    save_dealers(DEALERS_PATH)
    record_and_save(
        event_type="dealer_subscription_updated",
        summary=f"Dealer {dealer_id} subscription updated",
        dealer_id=dealer_id,
        details={"plan_tier": plan_tier, "active_modules": active_modules, "renewal_date": renewal_date, "seat_count": seat_count},
    )
    return dealer


def update_dealer_version_api(dealer_id, current_release=None, beta_programs=None):
    dealer, error = update_dealer_version(
        dealer_id,
        current_release=current_release,
        beta_programs=beta_programs
    )
    if error:
        return {"error": error}
    save_dealers(DEALERS_PATH)
    record_and_save(
        event_type="dealer_version_updated",
        summary=f"Dealer {dealer_id} version/beta programs updated",
        dealer_id=dealer_id,
        details={"current_release": current_release, "beta_programs": beta_programs},
    )
    return dealer


def resolve_dealer_api(identifier):
    """PUBLIC tenant resolver for the shared apps host (apps.dealeros.xyz).

    Given a dealership identifier a user types at app sign-in (its slug like "dealer1",
    or its internal id like "DLR-00001"), return WHERE that dealer's backend API lives so
    the one shared apps deployment can route the login to the correct tenant. Deliberately
    unauthenticated and minimal: it reveals only a dealer's already-public API subdomain
    and display name -- never data, credentials, or the dealer list (exact match required,
    no enumeration). The dealership id + real employee credentials still gate all data.
    """

    ident = (identifier or "").strip()
    if not ident:
        return {"error": "Enter your dealership ID."}

    dealer = (
        registry.get_by_slug(ident)
        or registry.get(ident)
        or registry.get(ident.upper())
    )
    if dealer is None:
        return {"error": f"No dealership found for '{ident}'."}
    if not dealer.api_base_url:
        return {"error": "That dealership isn't available online yet."}

    from hub_core.canonical_domain import canonical_api_url
    try:
        api_base_url = canonical_api_url(dealer.api_base_url)
    except ValueError as exc:
        return {"error": str(exc)}

    # Deliberately minimal per this function's contract: only the already-public subdomain + display
    # name the shared apps host needs to route a login — NOT the internal dealer_id or lifecycle
    # status (the apps resolver reads only api_base_url anyway).
    return {
        "slug": dealer.slug,
        "name": dealer.name,
        "api_base_url": api_base_url,
    }
