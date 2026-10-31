"""Opaque append revision hints; not a forecast, temporal snapshot or write precondition."""

from typing import Literal

from pydantic import Field

from .domain import Schema, digest

RUN_BUSINESS = "COALESCE(json_extract(payload,'$.entity'),json_extract(payload,'$.request.entity'),json_extract(payload,'$.request.simulation.entity'),json_extract(payload,'$.plan.simulation.entity'))"
INDEX_DDL = f"""
CREATE INDEX IF NOT EXISTS facts_business_append ON facts(entity,sequence);
CREATE INDEX IF NOT EXISTS runs_business_append ON runs({RUN_BUSINESS});
"""
QUERIES = (
    "SELECT sequence FROM platform_events WHERE business=? ORDER BY sequence DESC LIMIT 1",
    "SELECT sequence FROM facts WHERE entity=? ORDER BY sequence DESC LIMIT 1",
    f"SELECT rowid FROM runs WHERE {RUN_BUSINESS}=? ORDER BY rowid DESC LIMIT 1",
)


class WorkspaceRevision(Schema):
    business: str
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    scope: Literal["events_facts_saved_runs"] = "events_facts_saved_runs"
    interpretation: Literal["Append hint only; refresh explicitly. Not a forecast or permission."] = (
        "Append hint only; refresh explicitly. Not a forecast or permission."
    )


def workspace_revision(ledger, business: str) -> WorkspaceRevision:
    # One read transaction pins all three maxima; indexes bound each lookup.
    with ledger.store.connection() as db:
        db.execute("BEGIN")
        latest = [db.execute(query, (business,)).fetchone() for query in QUERIES]
    return WorkspaceRevision(business=business, revision=digest([business, latest]))
