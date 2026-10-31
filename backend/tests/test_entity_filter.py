"""
Tests for core/entity_filter.py -- get_visible_entities(role), a real, pure
"which entity types can this role see" filter: iterates core.permissions'
ENTITY_ACCESS dict and returns every entity_type key whose allowed-roles list
contains the given role.

Important, real distinction from core/security.py's can_access_entity(): this
function has NO admin bypass -- it's a straight membership check against
ENTITY_ACCESS, so an entity type with no ENTITY_ACCESS entry at all (e.g.
EMPLOYEE) never appears for ANY role, including ADMIN, whereas
can_access_entity(ADMIN, EMPLOYEE) returns True via its explicit bypass. Added
per BUILD_QUEUE.md's standing "convert to a real pytest suite as each module
gets touched" rule (CAF-00123 missing_test_coverage work) -- a loose,
print-based (not assertion-based) script already existed at
core/test_entity_filter.py, which is not real coverage and is left untouched.

No graph/ledger/save_graph involvement at all -- this module reads only the
static core.permissions.ENTITY_ACCESS dict, so no fixtures are needed beyond
the module-level constants themselves.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from core.entity_filter import get_visible_entities
from core.security import can_access_entity
from core.permissions import (
    ENTITY_ACCESS,
    ADMIN,
    OPERATIONS,
    SALES,
    MARKETING,
    SERVICE,
    FINANCE,
)
from core.entity_types import (
    VEHICLE,
    CUSTOMER,
    FINANCE_CONTRACT,
    LENDER,
    SERVICE_RECORD,
    DEAL,
    BOT_COVERAGE,
    LEAD,
    EMPLOYEE,
    DOCUMENT,
    COMPLIANCE_ALERT,
)


class TestGetVisibleEntities:
    def test_admin_sees_every_entity_type_that_has_an_entry(self):
        # Confirmed live: ADMIN is present on every one of ENTITY_ACCESS's 34
        # entries, so ADMIN's visible set equals the full key set exactly --
        # EXCEPT SYSTEM_ENTITY_TYPES entries, which are filtered out when
        # system_admin_context is not set (matching can_access_entity).
        from core.administration_access import SYSTEM_ENTITY_TYPES
        result = get_visible_entities(ADMIN)
        non_system = {et for et in ENTITY_ACCESS if et not in SYSTEM_ENTITY_TYPES}
        assert set(result) == non_system
        assert len(result) == len(non_system)

    def test_finance_role_sees_its_real_finance_specific_entity_types(self):
        # Verified live against the real ENTITY_ACCESS dict rather than assumed --
        # FINANCE's real list is much broader than just the finance-specific
        # types (it also carries the same broad marketing/content entries most
        # roles share), so this checks the real distinguishing facts rather than
        # a full-set snapshot that would drift as ENTITY_ACCESS grows.
        result = set(get_visible_entities(FINANCE))

        assert {VEHICLE, CUSTOMER, FINANCE_CONTRACT, LENDER, DEAL}.issubset(result)
        assert SERVICE_RECORD not in result
        assert LEAD not in result
        assert BOT_COVERAGE not in result
        assert COMPLIANCE_ALERT not in result

    def test_sales_role_sees_its_real_sales_specific_entity_types(self):
        result = set(get_visible_entities(SALES))

        assert {VEHICLE, CUSTOMER, DEAL, LEAD}.issubset(result)
        assert FINANCE_CONTRACT not in result
        assert LENDER not in result
        assert SERVICE_RECORD not in result
        assert COMPLIANCE_ALERT not in result

    def test_service_role_sees_its_real_service_specific_entity_types(self):
        result = set(get_visible_entities(SERVICE))

        assert {VEHICLE, CUSTOMER, SERVICE_RECORD, DOCUMENT}.issubset(result)
        assert DEAL not in result
        assert LEAD not in result
        assert FINANCE_CONTRACT not in result
        assert LENDER not in result

    def test_marketing_role_sees_its_real_marketing_specific_entity_types(self):
        result = set(get_visible_entities(MARKETING))

        assert {VEHICLE, CUSTOMER, LEAD}.issubset(result)
        assert FINANCE_CONTRACT not in result
        assert SERVICE_RECORD not in result
        assert DEAL not in result
        assert DOCUMENT not in result

    def test_narrow_allowlist_entity_type_only_visible_to_its_listed_role(self):
        # BOT_COVERAGE's real ENTITY_ACCESS entry is ["ADMIN"] only -- not even
        # OPERATIONS, unlike almost every other entry in the dict.
        assert BOT_COVERAGE in get_visible_entities(ADMIN)
        assert BOT_COVERAGE not in get_visible_entities(OPERATIONS)
        assert BOT_COVERAGE not in get_visible_entities(SALES)
        assert BOT_COVERAGE not in get_visible_entities(SERVICE)
        assert BOT_COVERAGE not in get_visible_entities(MARKETING)
        assert BOT_COVERAGE not in get_visible_entities(FINANCE)

    def test_entity_type_with_no_entry_never_appears_for_any_role(self):
        # EMPLOYEE has no ENTITY_ACCESS entry at all. get_visible_entities()
        # has no admin bypass (unlike core.security.can_access_entity), so
        # EMPLOYEE is absent from every role's result, including ADMIN's.
        assert EMPLOYEE not in ENTITY_ACCESS
        assert EMPLOYEE not in get_visible_entities(ADMIN)
        assert EMPLOYEE not in get_visible_entities(SALES)

    def test_unknown_role_string_returns_an_empty_list(self):
        assert get_visible_entities("NOT_A_REAL_ROLE") == []

    def test_result_type_is_always_a_list(self):
        assert isinstance(get_visible_entities(ADMIN), list)
        assert isinstance(get_visible_entities("NOT_A_REAL_ROLE"), list)

    def test_non_admin_result_matches_can_access_entity_for_every_known_type(self):
        # Without the admin bypass, get_visible_entities(role) and
        # can_access_entity(role, entity_type) are two different views of the
        # exact same ENTITY_ACCESS membership check -- for any non-ADMIN role,
        # every entity type get_visible_entities() returns must also pass
        # can_access_entity(), and every one it omits must fail it.
        for role in (OPERATIONS, SALES, MARKETING, SERVICE, FINANCE):
            visible = set(get_visible_entities(role))

            for entity_type in ENTITY_ACCESS:
                assert (entity_type in visible) == can_access_entity(role, entity_type)
