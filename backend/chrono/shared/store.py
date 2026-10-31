"""Append-only persistence; valid time and knowledge time are independently queryable."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Protocol

from .analysis_index import INDEX_DDL
from .domain import Fact, FactKind, ModelVersion
from .workspace_revision import INDEX_DDL as REVISION_INDEX_DDL

DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS facts (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT,
 id TEXT NOT NULL UNIQUE,
 entity TEXT NOT NULL,
 metric TEXT NOT NULL,
 kind TEXT NOT NULL,
 valid_at REAL NOT NULL,
 recorded_at REAL NOT NULL,
 supersedes TEXT UNIQUE REFERENCES facts(id),
 payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS fact_temporal ON facts(entity,kind,valid_at,recorded_at);
CREATE TABLE IF NOT EXISTS models (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS runs_business_kind ON runs(json_extract(payload,'$.entity'),kind);
CREATE INDEX IF NOT EXISTS runs_numerical_entity ON runs(COALESCE(json_extract(payload,'$.request.entity'),json_extract(payload,'$.request.simulation.entity'))) WHERE kind IN ('simulation','plan','inflections','backtest');
"""
DDL += INDEX_DDL
DDL += REVISION_INDEX_DDL
for _table in ("facts", "models", "runs"):
    for _action in ("UPDATE", "DELETE"):
        DDL += f"""CREATE TRIGGER IF NOT EXISTS {_table}_no_{_action}
          BEFORE {_action} ON {_table} BEGIN
          SELECT RAISE(ABORT, 'append-only table'); END;\n"""


class TemporalRepository(Protocol):
    def append(self, facts: list[Fact]) -> int: ...
    def history(
        self, entity: str, as_of: datetime, known_at: datetime, kind: FactKind = FactKind.OBSERVED
    ) -> list[Fact]: ...
    def save_model(self, model: ModelVersion) -> None: ...
    def save_run(self, run_id: str, kind: str, payload: dict) -> None: ...


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(DDL)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def append(
        self, facts: list[Fact], *, received_at: datetime | None = None, new_dataset: bool = False
    ) -> int:
        inserted = 0
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if new_dataset:
                entities = {fact.entity for fact in facts}
                if len(entities) != 1:
                    raise ValueError("A dataset must have exactly one entity.")
                ids = {
                    row[0]
                    for row in connection.execute(
                        "SELECT id FROM facts WHERE entity=? AND kind='observed'", (next(iter(entities)),)
                    ).fetchall()
                }
                if ids and ids != {fact.id for fact in facts}:
                    raise ValueError(
                        "Entity changed since preview; use a new entity or explicit corrections."
                    )
            for fact in facts:
                if received_at is not None:
                    row = connection.execute("SELECT payload FROM facts WHERE id=?", (fact.id,)).fetchone()
                    stamp = Fact.model_validate_json(row[0]).recorded_at if row else received_at
                    fact = Fact.model_validate({**fact.model_dump(), "recorded_at": stamp})
                fact = Fact.model_validate(fact.model_dump())
                body = fact.model_dump_json()
                existing = connection.execute("SELECT payload FROM facts WHERE id=?", (fact.id,)).fetchone()
                if existing:
                    if Fact.model_validate_json(existing[0]) != fact:
                        raise ValueError("idempotency conflict: fact ID has different content")
                    continue
                if fact.supersedes:
                    previous = connection.execute(
                        "SELECT payload FROM facts WHERE id=?", (fact.supersedes,)
                    ).fetchone()
                    if not previous:
                        raise ValueError("superseded fact does not exist")
                    old = Fact.model_validate_json(previous[0])
                    if (old.entity, old.metric, old.valid_at, old.kind, old.unit) != (
                        fact.entity,
                        fact.metric,
                        fact.valid_at,
                        fact.kind,
                        fact.unit,
                    ) or old.recorded_at >= fact.recorded_at:
                        raise ValueError(
                            "corrections must retain identity, kind, time and unit; knowledge time must advance"
                        )
                    if connection.execute("SELECT 1 FROM facts WHERE supersedes=?", (old.id,)).fetchone():
                        raise ValueError("correction conflict: supersede the latest revision")
                elif connection.execute(
                    "SELECT 1 FROM facts WHERE entity=? AND metric=? AND valid_at=? AND kind=?",
                    (fact.entity, fact.metric, fact.valid_at.timestamp(), fact.kind.value),
                ).fetchone():
                    raise ValueError("duplicate observation slot; use an explicit correction")
                for parent_id in fact.evidence.parent_ids:
                    row = connection.execute("SELECT payload FROM facts WHERE id=?", (parent_id,)).fetchone()
                    if not row:
                        raise ValueError(f"unknown evidence parent: {parent_id}")
                    parent = Fact.model_validate_json(row[0])
                    if parent.entity != fact.entity or parent.recorded_at > fact.recorded_at:
                        raise ValueError("parent must belong to this entity and be known before the claim")
                connection.execute(
                    "INSERT INTO facts(id,entity,metric,kind,valid_at,recorded_at,supersedes,payload) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        fact.id,
                        fact.entity,
                        fact.metric,
                        fact.kind.value,
                        fact.valid_at.timestamp(),
                        fact.recorded_at.timestamp(),
                        fact.supersedes,
                        body,
                    ),
                )
                inserted += 1
        return inserted

    def history(
        self, entity: str, as_of: datetime, known_at: datetime, kind: FactKind = FactKind.OBSERVED
    ) -> list[Fact]:
        # Rank AFTER both cutoffs: a late correction must never erase an earlier knowledge state.
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM (
                  SELECT payload, valid_at, metric,
                    ROW_NUMBER() OVER (PARTITION BY metric,valid_at ORDER BY recorded_at DESC,sequence DESC) rank
                  FROM facts WHERE entity=? AND kind=? AND valid_at<=? AND recorded_at<=?
                ) WHERE rank=1 ORDER BY valid_at,metric
                """,
                (entity, kind.value, as_of.timestamp(), known_at.timestamp()),
            ).fetchall()
        return [Fact.model_validate_json(row[0]) for row in rows]

    def state(self, entity: str, as_of: datetime, known_at: datetime) -> dict:
        result: dict = {}
        for kind in FactKind:
            latest = {}
            for fact in self.history(entity, as_of, known_at, kind):
                latest[fact.metric] = fact.model_dump(mode="json")
            result[kind.value] = latest
        return result

    def save_model(self, model: ModelVersion) -> None:
        self._save("models", model.id, model.model_dump(mode="json"))

    def save_run(self, run_id: str, kind: str, payload: dict) -> None:
        self._save("runs", run_id, payload, kind)

    def _save(self, table: str, key: str, payload: dict, kind: str | None = None) -> None:
        body = json.dumps(payload, sort_keys=True, allow_nan=False)
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            old = connection.execute(f"SELECT payload FROM {table} WHERE id=?", (key,)).fetchone()
            if old:
                if old[0] != body:
                    raise ValueError("immutable artifact ID conflict")
                return
            if kind is None:
                connection.execute("INSERT INTO models VALUES (?,?)", (key, body))
            else:
                connection.execute("INSERT INTO runs VALUES (?,?,?)", (key, kind, body))

    def get(self, table: str, key: str) -> dict | None:
        if table not in {"models", "runs"}:
            raise ValueError("unknown artifact table")
        with self.connection() as connection:
            row = connection.execute(f"SELECT payload FROM {table} WHERE id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def entities(self) -> list[str]:
        with self.connection() as connection:
            return [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT entity FROM facts WHERE kind='observed' ORDER BY entity"
                ).fetchall()
            ]

    def list_runs(self, entity: str | None = None, kind: str | None = None, limit: int = 30) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT id,kind,json_extract(payload,'$.name'),json_extract(payload,'$.model_id'),
                    COALESCE(json_extract(payload,'$.entity'), json_extract(payload,'$.request.entity'),
                             json_extract(payload,'$.request.simulation.entity'),
                             json_extract(payload,'$.plan.simulation.entity')) entity
                FROM runs WHERE (? IS NULL OR kind=?)
                  AND (? IS NULL OR COALESCE(json_extract(payload,'$.entity'), json_extract(payload,'$.request.entity'),
                           json_extract(payload,'$.request.simulation.entity'),
                           json_extract(payload,'$.plan.simulation.entity'))=?)
                ORDER BY rowid DESC LIMIT ?
            """,
                (kind, kind, entity, entity, min(max(limit, 1), 100)),
            ).fetchall()
        return [{"id": r[0], "kind": r[1], "name": r[2], "model_id": r[3], "entity": r[4]} for r in rows]


class ReadOnlyStore(Store):
    """Existing ledger access that cannot create, migrate or write a database."""

    def __init__(self, path):
        self.path = str(Path(path).resolve())

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(Path(self.path).as_uri() + "?mode=ro", uri=True, timeout=5)
        connection.execute("PRAGMA query_only=ON")
        try:
            yield connection
        finally:
            connection.close()
