"""Execution evidence is tenant-bound and immutable, not a dispatch service."""
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from db.migrate import MIGRATIONS, migrate
from db.tests.test_migrations import DSN, database, governance_seed, seed

pytestmark = pytest.mark.skipif(not DSN, reason='Dedicated PostgreSQL test server required')
TABLES = ['execution_intents', 'execution_events', 'usage_reservations', 'usage_settlements']


def execution_seed(conn, workspace, request=None):
    if request is None:
        _, request = governance_seed(conn, workspace)
    execution = conn.execute("""INSERT INTO nxtdeal.execution_intents
        (workspace_id,request_id,approval_sequence,executor_key,execution_mode,idempotency_key)
        VALUES (%s,%s,1,'test','mock','execute-1') RETURNING id""", (workspace, request)).fetchone()[0]
    conn.execute("""INSERT INTO nxtdeal.execution_events
        (workspace_id,execution_id,sequence,event_type,attempt,actor,occurred_at,idempotency_key)
        VALUES (%s,%s,1,'dispatched',1,'test',now(),'event-1')""", (workspace, execution))
    reservation = conn.execute("""INSERT INTO nxtdeal.usage_reservations
        (workspace_id,execution_id,capability_key,entitlement_revision,reserved_units,bucket_key,expires_at,idempotency_key)
        VALUES (%s,%s,'staff.seats',1,3,'concurrent',now()+interval '1 hour','reserve-1') RETURNING id""", (workspace, execution)).fetchone()[0]
    conn.execute("""INSERT INTO nxtdeal.usage_settlements
        (workspace_id,reservation_id,reserved_units,outcome,consumed_units,reason,actor,occurred_at,idempotency_key)
        VALUES (%s,%s,3,'consumed',2,'Test completion','test',now(),'settle-1')""", (workspace, reservation))
    return execution, reservation


def clone(conn, table, changes):
    """Insert a selected evidence row with SQL expressions replaced for constraint probes."""
    columns = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='nxtdeal' AND table_name=%s ORDER BY ordinal_position", (table,)).fetchall()
    selection = sql.SQL(',').join(sql.SQL(changes[name]) if name in changes else sql.Identifier(name) for (name,) in columns)
    return conn.execute(sql.SQL('INSERT INTO nxtdeal.{} SELECT {} FROM nxtdeal.{} LIMIT 1').format(sql.Identifier(table), selection, sql.Identifier(table)))


def test_populated_governance_upgrade_preserves_approval_binding(database, tmp_path):
    conn, _ = database
    for path in sorted(MIGRATIONS.glob('*.sql'))[:3]:
        (tmp_path / path.name).write_bytes(path.read_bytes())
    migrate(conn, tmp_path)
    a, _ = seed(conn)
    _, request = governance_seed(conn, a)
    before = conn.execute('SELECT * FROM nxtdeal.approval_decisions').fetchall()
    assert migrate(conn) == [p.name for p in sorted(MIGRATIONS.glob('*.sql'))][3:]
    execution_seed(conn, a, request)
    assert conn.execute('SELECT * FROM nxtdeal.approval_decisions').fetchall() == before
    assert migrate(conn) == []


def test_execution_requires_matching_positive_decision(database):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    actor, request = governance_seed(conn, a)
    execution_seed(conn, a, request)
    conn.execute("""INSERT INTO nxtdeal.approval_decisions
        (workspace_id,request_id,sequence,decision,decided_by,authority_snapshot,reason,occurred_at,idempotency_key)
        VALUES (%s,%s,2,'revoked',%s,'{}','Revoked',now(),'revoke-1')""", (a, request, actor))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'execution_intents', {'id':'gen_random_uuid()', 'idempotency_key':"'other'", 'approval_sequence':'2'})
    with pytest.raises(psycopg.errors.CheckViolation):
        clone(conn, 'execution_intents', {'id':'gen_random_uuid()', 'idempotency_key':"'other'", 'approval_sequence':'2', 'approval_state':"'revoked'"})
    # Revocation must not rewrite the historical execution's pinned decision.
    assert conn.execute('SELECT approval_sequence FROM nxtdeal.execution_intents').fetchone()[0] == 1


@pytest.mark.parametrize('table', TABLES)
def test_execution_usage_foreign_keys_and_idempotency_are_workspace_bound(database, table):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    execution_seed(conn, a)
    # All children point at A; a superuser cannot reassign them to B via insert.
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, table, {'workspace_id':f"'{b}'::uuid"})
    execution_seed(conn, b)  # Identical idempotency keys valid in a different workspace.
    with pytest.raises(psycopg.errors.UniqueViolation):
        clone(conn, table, {'id':'gen_random_uuid()', 'sequence':'99'})


@pytest.mark.parametrize('table', TABLES)
@pytest.mark.parametrize('operation', ['UPDATE','DELETE','TRUNCATE'])
def test_execution_usage_rejects_history_mutation(database, table, operation):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    execution_seed(conn, a)
    statement = {'UPDATE':f'UPDATE nxtdeal.{table} SET workspace_id=workspace_id', 'DELETE':f'DELETE FROM nxtdeal.{table}', 'TRUNCATE':f'TRUNCATE nxtdeal.{table} CASCADE'}[operation]
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        conn.execute(statement)
    assert conn.execute(f'SELECT count(*) FROM nxtdeal.{table}').fetchone()[0] == 1


@pytest.mark.parametrize('table', TABLES)
def test_execution_usage_rls_missing_and_transaction_context(database, table):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    execution_seed(conn, a)
    execution_seed(conn, b)
    role = 'nxtdeal_test_' + uuid4().hex
    conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS').format(sql.Identifier(role)))
    try:
        conn.execute(sql.SQL('GRANT USAGE ON SCHEMA nxtdeal TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA nxtdeal TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
        assert conn.execute(f'SELECT workspace_id FROM nxtdeal.{table}').fetchall() == []
        with conn.transaction():
            conn.execute("SELECT set_config('nxtdeal.workspace_id', %s, true)", (str(a),))
            assert conn.execute(f'SELECT workspace_id FROM nxtdeal.{table}').fetchall() == [(a,)]
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    clone(conn, table, {'workspace_id':f"'{b}'::uuid"})
        assert conn.execute(f'SELECT workspace_id FROM nxtdeal.{table}').fetchall() == []
    finally:
        conn.execute('RESET ROLE')
        conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


@pytest.mark.parametrize('table,changes', [
    ('execution_events', {'sequence':'2', 'idempotency_key':"'bad'", 'event_type':"'failed'"}),
    ('execution_events', {'sequence':'2', 'idempotency_key':"'bad'", 'attempt':'0'}),
    ('usage_reservations', {'id':'gen_random_uuid()', 'idempotency_key':"'bad'", 'reserved_units':'0'}),
    ('usage_reservations', {'id':'gen_random_uuid()', 'idempotency_key':"'bad'", 'expires_at':'reserved_at'}),
    ('usage_settlements', {'consumed_units':'4'}),
    ('usage_settlements', {'consumed_units':'-1'}),
    ('usage_settlements', {'outcome':"'released'"}),
])
def test_execution_usage_invalid_evidence(database, table, changes):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    execution_seed(conn, a)
    with pytest.raises(psycopg.errors.CheckViolation):
        clone(conn, table, changes)


def test_settlement_cannot_inflate_reservation_or_settle_twice(database):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    execution, _ = execution_seed(conn, a)
    reservation = conn.execute("""INSERT INTO nxtdeal.usage_reservations
        (workspace_id,execution_id,capability_key,entitlement_revision,reserved_units,bucket_key,expires_at,idempotency_key)
        VALUES (%s,%s,'staff.seats',1,1,'concurrent',now()+interval '1 hour','reserve-2') RETURNING id""", (a, execution)).fetchone()[0]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'usage_settlements', {'reservation_id':f"'{reservation}'::uuid", 'idempotency_key':"'settle-2'"})
    clone(conn, 'usage_settlements', {'reservation_id':f"'{reservation}'::uuid", 'idempotency_key':"'settle-2'", 'reserved_units':'1', 'consumed_units':'0', 'outcome':"'released'"})
    with pytest.raises(psycopg.errors.UniqueViolation):
        clone(conn, 'usage_settlements', {'idempotency_key':"'different-key'"})
