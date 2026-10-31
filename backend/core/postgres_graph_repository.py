"""Fail-closed boundary reserved for the PostgreSQL migration.

No driver, connection, schema, or JSON fallback is hidden behind this scaffold.
"""

from core.tenant_context import TenantContext


class PostgresGraphRepository:
    def __init__(self, tenant: TenantContext):
        raise NotImplementedError(
            "PostgreSQL repository is not available: schema and mutable "
            "unit-of-work compatibility must pass migration gates first."
        )
