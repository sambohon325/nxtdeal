"""Disposable-database prepare/commit journal; never writes authoritative JSON.

A commit observation is trusted-caller evidence, not filesystem verification.
No runtime coordinator, production entry point or automatic recovery is enabled.
"""
import re
from uuid import UUID

import psycopg
from psycopg.pq import TransactionStatus

from db.shadow_compare import GraphObservation, ShadowRejected


def _guard(connection,workspace_id,operation_id):
    try:
        workspace, operation = UUID(workspace_id), UUID(operation_id)
    except (ValueError,TypeError,AttributeError):
        raise ShadowRejected('invalid_journal_scope') from None
    if not connection.autocommit or connection.info.transaction_status != TransactionStatus.IDLE:
        raise ShadowRejected('dedicated_idle_connection_required')
    if not re.fullmatch(r'nxtdeal_test_[0-9a-f]{32}',connection.info.dbname):
        raise ShadowRejected('disposable_test_database_required')
    return workspace, operation


def _lock(connection,workspace):
    connection.execute("SELECT set_config('nxtdeal.workspace_id',%s,true)",(str(workspace),))
    if connection.execute('SELECT id FROM nxtdeal.workspaces WHERE id=%s FOR UPDATE',(workspace,)).fetchone() is None:
        raise ShadowRejected('workspace_missing')


def prepare(connection,*,workspace_id,operation_id,graph_bytes,require_new=False,previous_graph_bytes=None,expected_previous_generation=None):
    workspace,operation = _guard(connection,workspace_id,operation_id)
    if expected_previous_generation is not None and (type(expected_previous_generation) is not int or not 0 <= expected_previous_generation < 2**63):
        raise ShadowRejected('invalid_predecessor')
    evidence = GraphObservation(str(workspace),1,graph_bytes).evidence()
    digest = evidence['semantic_sha256']
    try:
        with connection.transaction():
            _lock(connection,workspace)
            existing = connection.execute('SELECT generation,snapshot FROM nxtdeal.shadow_preparations WHERE workspace_id=%s AND operation_id=%s',
                (workspace,operation)).fetchone()
            if existing:
                if require_new:
                    raise ShadowRejected('operation_already_prepared')
                if bytes(existing[1]) != graph_bytes:
                    raise ShadowRejected('operation_conflict')
                return existing[0]
            last = connection.execute('SELECT max(generation) FROM nxtdeal.shadow_preparations WHERE workspace_id=%s',(workspace,)).fetchone()[0]
            if expected_previous_generation is not None and (last or 0) != expected_previous_generation:
                raise ShadowRejected('stale_graph_generation')
            if last is not None and not connection.execute('SELECT 1 FROM nxtdeal.shadow_commits WHERE workspace_id=%s AND generation=%s',(workspace,last)).fetchone():
                raise ShadowRejected('pending_predecessor')
            if require_new and last is not None:
                previous = connection.execute('SELECT snapshot FROM nxtdeal.shadow_preparations WHERE workspace_id=%s AND generation=%s',
                    (workspace,last)).fetchone()[0]
                if previous_graph_bytes != bytes(previous):
                    raise ShadowRejected('authoritative_predecessor_mismatch')
            generation = (last or 0) + 1
            if generation > 2**63 - 1:
                raise ShadowRejected('generation_exhausted')
            connection.execute('''INSERT INTO nxtdeal.shadow_preparations
                (workspace_id,generation,operation_id,predecessor,snapshot,semantic_digest) VALUES (%s,%s,%s,%s,%s,%s)''',
                (workspace,generation,operation,last,graph_bytes,digest))
            return generation
    except psycopg.Error:
        raise ShadowRejected('journal_database_failed') from None


def record_json_commit(connection,*,workspace_id,operation_id,observation):
    workspace,operation = _guard(connection,workspace_id,operation_id)
    if type(observation) is not GraphObservation:
        raise ShadowRejected('observation_required')
    evidence = observation.evidence()
    if evidence['workspace_id'] != str(workspace):
        raise ShadowRejected('workspace_mismatch')
    try:
        with connection.transaction():
            _lock(connection,workspace)
            prepared = connection.execute('''SELECT generation,snapshot,semantic_digest FROM nxtdeal.shadow_preparations
                WHERE workspace_id=%s AND operation_id=%s''',(workspace,operation)).fetchone()
            if prepared is None:
                raise ShadowRejected('preparation_missing')
            if prepared[0] != observation.generation or bytes(prepared[1]) != observation.graph_bytes or prepared[2] != evidence['semantic_sha256']:
                raise ShadowRejected('commit_evidence_mismatch')
            inserted = connection.execute('''INSERT INTO nxtdeal.shadow_commits(workspace_id,generation,operation_id,semantic_digest)
                VALUES (%s,%s,%s,%s) ON CONFLICT (workspace_id,generation) DO NOTHING RETURNING generation''',
                (workspace,prepared[0],operation,prepared[2])).fetchone()
            return 'committed' if inserted else 'already_committed'
    except psycopg.Error:
        raise ShadowRejected('journal_database_failed') from None


def inspect_recovery(connection,*,workspace_id,operation_id,observed_graph_bytes=None):
    """Inspect journal evidence without promoting a preparation or changing data.

    File contents alone cannot establish which generation durably committed.
    Caller captures the file under its own authorized writer boundary. This
    observation is diagnostic, never authority to replay a business action.
    """
    workspace,operation = _guard(connection,workspace_id,operation_id)
    if observed_graph_bytes is not None:
        GraphObservation(str(workspace),1,observed_graph_bytes).evidence()
    try:
        with connection.transaction():
            _lock(connection,workspace)
            row = connection.execute('''SELECT p.generation,p.snapshot,p.semantic_digest,previous.snapshot,
                    c.generation IS NOT NULL
                FROM nxtdeal.shadow_preparations p
                LEFT JOIN nxtdeal.shadow_preparations previous
                    ON previous.workspace_id=p.workspace_id AND previous.generation=p.predecessor
                LEFT JOIN nxtdeal.shadow_commits c
                    ON c.workspace_id=p.workspace_id AND c.generation=p.generation
                WHERE p.workspace_id=%s AND p.operation_id=%s''',(workspace,operation)).fetchone()
            if row is None:
                return {'status':'preparation_missing','action':'investigate','database_written':False}
            generation,snapshot,digest,previous,committed = row
            # Revalidate stored bytes and digest; do not report trusted evidence
            # merely because a row exists in an immutable table.
            stored = GraphObservation(str(workspace),generation,bytes(snapshot)).evidence()
            if stored['semantic_sha256'] != digest:
                raise ShadowRejected('journal_snapshot_mismatch')
            latest = connection.execute('SELECT max(generation) FROM nxtdeal.shadow_preparations WHERE workspace_id=%s',(workspace,)).fetchone()[0]
            return {'status':'commit_recorded' if committed else 'prepared_unresolved',
                    'action':'verify_shadow_reconciliation' if committed else 'manual_reconciliation_required',
                    'generation':generation,'latest_generation':latest,
                    'matches_prepared_bytes':None if observed_graph_bytes is None else observed_graph_bytes == bytes(snapshot),
                    'matches_predecessor_bytes':None if observed_graph_bytes is None or previous is None else observed_graph_bytes == bytes(previous),
                    'database_written':False}
    except psycopg.Error:
        raise ShadowRejected('journal_database_failed') from None
