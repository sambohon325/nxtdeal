"""Disposable whole-graph JSONB projection, not a PostgreSQL runtime repository."""
import psycopg
from psycopg.types.json import Jsonb

from db.import_package import ImportPackage
from db.import_preflight import canonical
from db.import_writer import _exact, _digest
from db.shadow_compare import GraphObservation, ShadowRejected
from db.shadow_journal import _guard, _lock


def apply_test_projection(connection, *, workspace_id, operation_id, expected_predecessor):
    workspace, operation = _guard(connection, workspace_id, operation_id)
    if type(expected_predecessor) is not int or not 0 <= expected_predecessor < 2**63:
        raise ShadowRejected('invalid_predecessor')
    try:
        with connection.transaction():
            _lock(connection, workspace)
            row = connection.execute('''SELECT p.generation,p.snapshot,p.semantic_digest
                FROM nxtdeal.shadow_preparations p JOIN nxtdeal.shadow_commits c
                  ON c.workspace_id=p.workspace_id AND c.generation=p.generation
                WHERE p.workspace_id=%s AND p.operation_id=%s''', (workspace,operation)).fetchone()
            if row is None:
                raise ShadowRejected('committed_snapshot_required')
            generation, snapshot, digest = row
            evidence = GraphObservation(str(workspace), generation, bytes(snapshot)).evidence()
            if evidence['semantic_sha256'] != digest:
                raise ShadowRejected('journal_snapshot_mismatch')
            if expected_predecessor != generation - 1:
                raise ShadowRejected('projection_predecessor_mismatch')
            existing = connection.execute('SELECT graph::text,semantic_digest FROM nxtdeal.shadow_projections WHERE workspace_id=%s AND generation=%s',
                (workspace,generation)).fetchone()
            if existing:
                if existing[1] != digest or _digest(_exact(existing[0])) != digest:
                    raise ShadowRejected('projection_parity_failed')
                return {'status':'already_applied', **evidence}
            latest = connection.execute('SELECT max(generation) FROM nxtdeal.shadow_projections WHERE workspace_id=%s', (workspace,)).fetchone()[0]
            if (latest or 0) != expected_predecessor:
                raise ShadowRejected('projection_predecessor_mismatch')
            if latest is not None:
                previous = connection.execute('''SELECT s.graph::text,s.semantic_digest,p.semantic_digest,p.snapshot
                    FROM nxtdeal.shadow_projections s JOIN nxtdeal.shadow_preparations p
                      ON p.workspace_id=s.workspace_id AND p.generation=s.generation
                    WHERE s.workspace_id=%s AND s.generation=%s''', (workspace,latest)).fetchone()
                if (previous is None or previous[1] != previous[2]
                        or _digest(_exact(previous[0])) != previous[2]
                        or GraphObservation(str(workspace),latest,bytes(previous[3])).evidence()['semantic_sha256'] != previous[2]):
                    raise ShadowRejected('projection_predecessor_corrupt')
            graph, _ = ImportPackage(str(workspace), 'graph_only', bytes(snapshot)).payloads()
            connection.execute('''INSERT INTO nxtdeal.shadow_projections
                (workspace_id,generation,predecessor,graph,semantic_digest) VALUES (%s,%s,%s,%s,%s)''',
                (workspace,generation,latest,Jsonb(graph,dumps=canonical),digest))
            stored = connection.execute('SELECT graph::text,semantic_digest FROM nxtdeal.shadow_projections WHERE workspace_id=%s AND generation=%s',
                (workspace,generation)).fetchone()
            if stored is None or stored[1] != digest or _digest(_exact(stored[0])) != digest:
                raise ShadowRejected('projection_parity_failed')
            return {'status':'applied', **evidence}
    except psycopg.Error:
        raise ShadowRejected('projection_database_failed') from None
