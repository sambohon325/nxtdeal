"""
core/menu_data.py -- the generic engine behind the Top Menu (core/menu_catalog.py),
session 60. Mirrors core/workflow_tab_data.py's REAL_SOURCES pattern one level up: a
department -> item_key -> fetch function map, so GET /menu/data is one route serving
every department's every item rather than growing a new endpoint per department.

All 9 departments -- "Operations", "Sales", "Service", "Marketing", "Inventory",
"Finance", "Administration", "Readiness", and "Network" -- are wired into
MENU_SOURCES as of session 67 (Sam: "Operations first, fully realized" then "lets
move to sales"; the scheduled builder added Service & Parts in session 61; Marketing
followed in session 62 after Sam uploaded an updated spec, marketing2.pdf; Inventory
followed in session 63; Finance followed in session 64; Administration followed in
session 65; Readiness followed in session 66; Network followed in session 67, closing
out the rollout). Extending further means deepening an existing department's real
data coverage (backed by core/operations_menu.py/core/sales_menu.py/
core/service_menu.py/core/marketing_menu.py/core/inventory_menu.py/
core/finance_menu.py/core/administration_menu.py/core/readiness_menu.py/
core/network_menu.py), not adding a new department key here.
"""

from core.menu_catalog import get_department_menu
from core.operations_menu import (
    overview as operations_overview,
    tasks as operations_tasks,
    communications as operations_communications,
    customer_journey as operations_customer_journey,
    workforce as operations_workforce,
    vehicles as operations_vehicles,
    inventory as operations_inventory,
    scheduling as operations_scheduling,
    documents as operations_documents,
    alerts as operations_alerts,
    reporting as operations_reporting,
)
from core.sales_menu import (
    overview as sales_overview,
    prospects as sales_prospects,
    customers as sales_customers,
    deals as sales_deals,
    appointments as sales_appointments,
    inventory as sales_inventory,
    communications as sales_communications,
    reporting as sales_reporting,
    accessories as sales_accessories,
    equity_center as sales_equity_center,
)
from core.service_menu import (
    overview as service_overview,
    appointments as service_appointments,
    repair_orders as service_repair_orders,
    customers as service_customers,
    shop_control as service_shop_control,
    parts as service_parts,
    warranty as service_warranty,
    reporting as service_reporting,
)
from core.marketing_menu import (
    overview as marketing_overview,
    crm as marketing_crm,
    campaigns as marketing_campaigns,
    purls as marketing_purls,
    email_sms as marketing_email_sms,
    events as marketing_events,
    website as marketing_website,
    social_reputation as marketing_social_reputation,
    advertising as marketing_advertising,
    analytics as marketing_analytics,
    reporting as marketing_reporting,
    inventory_advertising as marketing_inventory_advertising,
    loyalty as marketing_loyalty,
)
from core.inventory_menu import (
    overview as inventory_overview,
    inventory as inventory_inventory,
    acquisitions as inventory_acquisitions,
    lot_management as inventory_lot_management,
    pricing as inventory_pricing,
    merchandising as inventory_merchandising,
    wholesale as inventory_wholesale,
    syndication as inventory_syndication,
    reporting as inventory_reporting,
)
from core.finance_menu import (
    overview as finance_overview,
    deals as finance_deals,
    funding as finance_funding,
    compliance as finance_compliance,
    accounting as finance_accounting,
    floorplan as finance_floorplan,
    portfolio as finance_portfolio,
    payments as finance_payments,
    collections as finance_collections,
    repossessions as finance_repossessions,
    gps_devices as finance_gps_devices,
    starter_interrupt as finance_starter_interrupt,
    assets as finance_assets,
    commissions as finance_commissions,
    lender_intelligence as finance_lender_intelligence,
    reporting as finance_reporting,
)
from core.administration_menu import (
    overview as administration_overview,
    users as administration_users,
    roles_permissions as administration_roles_permissions,
    security as administration_security,
    systems as administration_systems,
    integrations as administration_integrations,
    vendors as administration_vendors,
    organizations as administration_organizations,
    data_management as administration_data_management,
    identity_access as administration_identity_access,
    governance as administration_governance,
    audit_center as administration_audit_center,
    workflow_automation as administration_workflow_automation,
    ai_management as administration_ai_management,
    modules as administration_modules,
    ai_spend as administration_ai_spend,
    fleet as administration_fleet,
    ai_workforce as administration_ai_workforce,
    connect as administration_connect,
    digital_retail as administration_digital_retail,
    reporting as administration_reporting,
    success_center as administration_success_center,
)
from core.readiness_menu import (
    overview as readiness_overview,
    business_health as readiness_business_health,
    data_health as readiness_data_health,
    readiness as readiness_readiness,
    forecasts as readiness_forecasts,
    simulations as readiness_simulations,
    exceptions as readiness_exceptions,
    recommendations as readiness_recommendations,
    strategic_planning as readiness_strategic_planning,
    reporting as readiness_reporting,
)
from core.network_menu import (
    overview as network_overview,
    peer_groups as network_peer_groups,
    benchmarks as network_benchmarks,
    gap_analysis as network_gap_analysis,
    trends as network_trends,
    forecasts as network_forecasts,
    playbooks as network_playbooks,
    ai_advisors as network_ai_advisors,
    consulting_engine as network_consulting_engine,
    opportunities as network_opportunities,
    reporting as network_reporting,
)


# Each fetch is called as fetch(role) or, for items that accept a search query,
# fetch(role, query=query). core/menu_api.py's get_menu_data_api introspects which shape
# a given item needs via QUERY_CAPABLE below rather than every fetch taking an unused
# `query` param.
MENU_SOURCES = {
    "Operations": {
        "overview": operations_overview,
        "tasks": operations_tasks,
        "vehicles": operations_vehicles,
        "inventory": operations_inventory,
        "scheduling": operations_scheduling,
        "documents": operations_documents,
        "alerts": operations_alerts,
        "communications": operations_communications,
        "customer_journey": operations_customer_journey,
        "workforce": operations_workforce,
        "reporting": operations_reporting,
    },
    "Sales": {
        "overview": sales_overview,
        "prospects": sales_prospects,
        "customers": sales_customers,
        "deals": sales_deals,
        "appointments": sales_appointments,
        "inventory": sales_inventory,
        "communications": sales_communications,
        "accessories": sales_accessories,
        "equity_center": sales_equity_center,
        "reporting": sales_reporting,
    },
    "Service": {
        "overview": service_overview,
        "appointments": service_appointments,
        "repair_orders": service_repair_orders,
        "customers": service_customers,
        "shop_control": service_shop_control,
        "parts": service_parts,
        "warranty": service_warranty,
        "reporting": service_reporting,
    },
    "Marketing": {
        "overview": marketing_overview,
        "crm": marketing_crm,
        "campaigns": marketing_campaigns,
        "purls": marketing_purls,
        "email_sms": marketing_email_sms,
        "events": marketing_events,
        "website": marketing_website,
        "social_reputation": marketing_social_reputation,
        "advertising": marketing_advertising,
        "analytics": marketing_analytics,
        "inventory_advertising": marketing_inventory_advertising,
        "loyalty": marketing_loyalty,
        "reporting": marketing_reporting,
    },
    "Inventory": {
        "overview": inventory_overview,
        "inventory": inventory_inventory,
        "acquisitions": inventory_acquisitions,
        "lot_management": inventory_lot_management,
        "pricing": inventory_pricing,
        "merchandising": inventory_merchandising,
        "wholesale": inventory_wholesale,
        "syndication": inventory_syndication,
        "reporting": inventory_reporting,
    },
    "Finance": {
        "overview": finance_overview,
        "deals": finance_deals,
        "funding": finance_funding,
        "compliance": finance_compliance,
        "accounting": finance_accounting,
        "floorplan": finance_floorplan,
        "portfolio": finance_portfolio,
        "payments": finance_payments,
        "collections": finance_collections,
        "repossessions": finance_repossessions,
        "gps_devices": finance_gps_devices,
        "starter_interrupt": finance_starter_interrupt,
        "assets": finance_assets,
        "commissions": finance_commissions,
        "lender_intelligence": finance_lender_intelligence,
        "reporting": finance_reporting,
    },
    "Administration": {
        "overview": administration_overview,
        "users": administration_users,
        "roles_permissions": administration_roles_permissions,
        "security": administration_security,
        "systems": administration_systems,
        "integrations": administration_integrations,
        "vendors": administration_vendors,
        "organizations": administration_organizations,
        "data_management": administration_data_management,
        "identity_access": administration_identity_access,
        "governance": administration_governance,
        "audit_center": administration_audit_center,
        "workflow_automation": administration_workflow_automation,
        "ai_management": administration_ai_management,
        "modules": administration_modules,
        "ai_spend": administration_ai_spend,
        "fleet": administration_fleet,
        "ai_workforce": administration_ai_workforce,
        "connect": administration_connect,
        "digital_retail": administration_digital_retail,
        "success_center": administration_success_center,
        "reporting": administration_reporting,
    },
    "Readiness": {
        "overview": readiness_overview,
        "business_health": readiness_business_health,
        "data_health": readiness_data_health,
        "readiness": readiness_readiness,
        "forecasts": readiness_forecasts,
        "simulations": readiness_simulations,
        "exceptions": readiness_exceptions,
        "recommendations": readiness_recommendations,
        "strategic_planning": readiness_strategic_planning,
        "reporting": readiness_reporting,
    },
    "Network": {
        "overview": network_overview,
        "peer_groups": network_peer_groups,
        "benchmarks": network_benchmarks,
        "gap_analysis": network_gap_analysis,
        "trends": network_trends,
        "forecasts": network_forecasts,
        "playbooks": network_playbooks,
        "ai_advisors": network_ai_advisors,
        "consulting_engine": network_consulting_engine,
        "opportunities": network_opportunities,
        "reporting": network_reporting,
    },
}

# Items whose fetch function accepts an optional `query` kwarg (a search box on the
# frontend) -- everything else is a straight fetch(role) dashboard-style view.
QUERY_CAPABLE = {
    ("Operations", "vehicles"),
    ("Operations", "documents"),
    ("Sales", "prospects"),
    ("Sales", "customers"),
    ("Sales", "inventory"),
    ("Service", "repair_orders"),
    ("Service", "customers"),
    ("Service", "parts"),
    ("Marketing", "crm"),
    ("Marketing", "campaigns"),
    ("Marketing", "purls"),
    ("Marketing", "email_sms"),
    ("Marketing", "events"),
    ("Marketing", "website"),
    ("Marketing", "social_reputation"),
    ("Marketing", "advertising"),
    ("Inventory", "inventory"),
    ("Inventory", "lot_management"),
    ("Inventory", "pricing"),
    ("Inventory", "wholesale"),
    ("Finance", "deals"),
    ("Finance", "portfolio"),
    ("Administration", "users"),
    ("Administration", "roles_permissions"),
}


def get_menu_data(role, department, item_key, query=None):
    """Real data for one Top Menu item. Returns {"error": ...} for an unknown
    department/item_key (including every department not catalogued this pass) -- the
    frontend hides the menu bar entirely for departments with an empty catalog, so this
    should only be reachable for real, catalogued items."""

    items = get_department_menu(department)

    if not any(item["key"] == item_key for item in items):
        return {"error": f"Unknown menu item '{item_key}' for department '{department}'"}

    fetch = MENU_SOURCES.get(department, {}).get(item_key)

    if not fetch:
        return {"error": f"'{item_key}' isn't wired to real data yet for {department}."}

    if (department, item_key) in QUERY_CAPABLE:
        return fetch(role, query=query)

    return fetch(role)
