"""
Daily KPI snapshots for Department Intelligence's trend deltas (2026-07-13, session 35;
renamed from core/bumper_snapshots.py session 68 -- Sam: "i want to take out the term
'bumper bi'"). A DepartmentSnapshot is an ordinary graph entity (entity_type=
DEPARTMENT_SNAPSHOT), one per (department, calendar day) pair -- deliberately NOT a
separate JSON store, since the "One Graph Unification" effort (session 17) already
spent real effort undoing exactly that kind of fragmentation for lead pipeline state/
employee assignment. Snapshots ride on the same core/storage.py save_graph()/
load_graph() persistence as every other entity, no new storage module needed.

There's no real overnight batch job in this backend (no scheduler infrastructure) --
snapshots are recorded opportunistically and idempotently, whenever someone opens a
Department Intelligence dashboard (see with_trend() below, called from
core/department_intelligence_api.py): if today's snapshot for a department already
exists, nothing happens; if not, one is created from that department's CURRENT computed
KPIs before the response goes out. This means the first time a department is opened
each day, that day's snapshot reflects whatever the graph looked like at THAT moment,
not necessarily start-of-day -- an honest tradeoff of not having real cron
infrastructure, documented rather than hidden. A future phase could replace this with a
real scheduled job without changing the read side at all (find_snapshot()/
most_recent_prior_snapshot() don't care who called record_snapshot()).

This module was already fully generic by `department` (a plain string key) even before
the session-68 rename -- any caller can record/read a snapshot series for ANY
department key, not just the five core/department_intelligence.py originally computed
(sales/service/parts/fi/executive). That's what makes it reusable as the trend-delta
engine behind other departments' Reporting tabs too, per Sam's session-68 ask to
"include that level of reporting for each reporting section of every department."
"""

from datetime import datetime, timezone, date

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import DEPARTMENT_SNAPSHOT
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Real data-loss bug found and fixed (2026-07-18, codebase-wide save_graph() audit --
# see core/lead_conversion.py's docstring for the running list of confirmed instances).
# This module had ZERO save_graph() calls anywhere since it shipped (session 35) --
# every day's real snapshot was silently discarded on server restart, meaning trend
# deltas (has_history/delta_pct) would go permanently missing across a restart, always
# behaving as if that department had never been opened before. Fixed below.
# record_snapshot() is idempotent per (department, day) -- called on every dashboard
# open, but the actual mutation only happens once per department per real calendar
# day, so a direct save (no batching) is safe, unlike a truly per-request write.


def _now():

    return datetime.now(timezone.utc).isoformat()


def _today_iso():

    return date.today().isoformat()


def find_snapshot(department, snapshot_date=None):

    snapshot_date = snapshot_date or _today_iso()

    for entity in ledger.get_all().values():

        if entity.entity_type != DEPARTMENT_SNAPSHOT:
            continue

        if entity.attributes.get("department") != department:
            continue

        if entity.attributes.get("snapshot_date") != snapshot_date:
            continue

        return entity

    return None


def record_snapshot(department, kpis):
    """Idempotent per (department, today) -- returns the existing snapshot untouched
    if one's already been recorded today, rather than creating a duplicate. `kpis` is
    the {key: kpi_dict} mapping core/department_intelligence.py's compute_department()
    (or any other caller's own KPI dict of the same shape) produces -- only the raw
    numeric `value` from each is actually persisted."""

    existing = find_snapshot(department)

    if existing:
        return existing

    snapshot_id = id_generator.generate("SNAP")

    numeric_kpis = {
        key: kpi_dict["value"]
        for key, kpi_dict in kpis.items()
    }

    entity = Entity(
        id=snapshot_id,
        entity_type=DEPARTMENT_SNAPSHOT,
        attributes={
            "department": department,
            "snapshot_date": _today_iso(),
            "kpis": numeric_kpis,
            "recorded_at": _now()
        }
    )

    ledger.add_entity(entity)

    save_graph(GRAPH_PATH)

    return entity


def most_recent_prior_snapshot(department):
    """The most recent DepartmentSnapshot for this department that ISN'T today's --
    what trend deltas get computed against. None if no history exists yet (e.g. the
    very first time this department has ever been opened)."""

    today = _today_iso()
    candidates = []

    for entity in ledger.get_all().values():

        if entity.entity_type != DEPARTMENT_SNAPSHOT:
            continue

        if entity.attributes.get("department") != department:
            continue

        if entity.attributes.get("snapshot_date") == today:
            continue

        candidates.append(entity)

    if not candidates:
        return None

    candidates.sort(
        key=lambda entity: entity.attributes.get("snapshot_date", "")
    )

    return candidates[-1]


def with_trend(department, current_kpis):
    """Takes a {key: kpi_dict} mapping (core/department_intelligence.py's
    compute_department() shape, or any other real per-department KPI dict of the same
    shape) and returns a new mapping where each kpi dict gains `delta_pct` (float or
    None), `has_history` (bool), and `compared_to` (the prior snapshot's date or None).
    Records today's snapshot as a side effect first -- see this module's docstring for
    why that happens here rather than in a real scheduled job."""

    record_snapshot(department, current_kpis)

    prior = most_recent_prior_snapshot(department)
    prior_kpis = prior.attributes.get("kpis", {}) if prior else {}

    enriched = {}

    for key, kpi_dict in current_kpis.items():

        new_kpi = dict(kpi_dict)

        if prior and key in prior_kpis:

            prior_value = prior_kpis[key]
            current_value = kpi_dict["value"]

            if prior_value:

                delta_pct = round(
                    (current_value - prior_value) / abs(prior_value) * 100,
                    1
                )

            elif current_value:

                # Went from zero (or untracked) to something -- percent change is
                # undefined, not zero. Frontend renders this the same as "no history."
                delta_pct = None

            else:

                delta_pct = 0.0

            new_kpi["delta_pct"] = delta_pct
            new_kpi["has_history"] = True
            new_kpi["compared_to"] = prior.attributes.get("snapshot_date")

        else:

            new_kpi["delta_pct"] = None
            new_kpi["has_history"] = False
            new_kpi["compared_to"] = None

        enriched[key] = new_kpi

    return enriched
