"""Repository scope, not authorization or a request-level tenant resolver."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TenantContext:
    workspace_id: str
    organization_id: str | None = None

    def __post_init__(self):
        for name in ("workspace_id", "organization_id"):
            value = getattr(self, name)
            if name == "organization_id" and value is None:
                continue
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"{name} must be a non-empty, trimmed string")


# Compatibility label for isolated legacy processes, never a database tenant
# or authorization fallback. Future shared hosting requires real membership scope.
LEGACY_PROCESS_CONTEXT = TenantContext(workspace_id="legacy-process")
