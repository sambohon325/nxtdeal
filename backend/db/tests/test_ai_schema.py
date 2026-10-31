"""Version-pinned metadata and honest measurements, with no provider calls."""
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from db.migrate import MIGRATIONS, migrate
from db.tests.test_migrations import DSN, database, seed
from db.tests.test_execution_usage import clone, execution_seed

pytestmark = pytest.mark.skipif(not DSN, reason='Dedicated PostgreSQL test server required')
TABLES = ['ai_model_revisions', 'ai_route_revisions', 'ai_usage_records']


def ai_seed(conn, workspace):
    conn.execute("""INSERT INTO nxtdeal.ai_model_revisions
        (workspace_id,model_key,revision,provider,provider_model,provider_version)
        VALUES (%s,'test-model',1,'test','test-model','test-version')""", (workspace,))
    conn.execute("""INSERT INTO nxtdeal.ai_route_revisions
        (workspace_id,route_key,revision,model_key,model_revision,policy_snapshot,recorded_by,reason,effective_at)
        VALUES (%s,'draft',1,'test-model',1,'{}','test','Fixture',now())""", (workspace,))
    conn.execute("""INSERT INTO nxtdeal.ai_usage_records
        (workspace_id,route_key,route_revision,actor,execution_mode,outcome,measurement_basis,measurement_source,started_at,idempotency_key)
        VALUES (%s,'draft',1,'test','mock','unknown','unavailable','Not measured',now(),'call-1')""", (workspace,))


def test_upgrade_keeps_execution_evidence_and_disabled_default(database, tmp_path):
    conn, _ = database
    for path in sorted(MIGRATIONS.glob('*.sql'))[:4]:
        (tmp_path / path.name).write_bytes(path.read_bytes())
    migrate(conn, tmp_path)
    a, _ = seed(conn)
    execution_seed(conn, a)
    before = conn.execute('SELECT * FROM nxtdeal.usage_settlements').fetchall()
    assert migrate(conn) == [p.name for p in sorted(MIGRATIONS.glob('*.sql'))][4:]
    ai_seed(conn, a)
    assert conn.execute('SELECT * FROM nxtdeal.usage_settlements').fetchall() == before
    assert conn.execute('SELECT enabled FROM nxtdeal.ai_route_revisions').fetchone() == (False,)
    assert migrate(conn) == []


def test_usage_keeps_original_route_model_after_reconfiguration(database):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    ai_seed(conn, a)
    clone(conn, 'ai_model_revisions', {'revision':'2', 'provider_version':"'new-version'"})
    clone(conn, 'ai_route_revisions', {'revision':'2', 'model_revision':'2'})
    assert conn.execute('''SELECT m.provider_version FROM nxtdeal.ai_usage_records u
        JOIN nxtdeal.ai_route_revisions r ON (u.workspace_id,u.route_key,u.route_revision)=(r.workspace_id,r.route_key,r.revision)
        JOIN nxtdeal.ai_model_revisions m ON (r.workspace_id,r.model_key,r.model_revision)=(m.workspace_id,m.model_key,m.revision)''').fetchall() == [('test-version',)]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'ai_route_revisions', {'revision':'3', 'model_revision':'99'})
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'ai_usage_records', {'id':'gen_random_uuid()', 'idempotency_key':"'other'", 'route_revision':'99'})


def test_model_and_credential_references_cannot_cross_workspaces(database):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    ai_seed(conn, a)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'ai_route_revisions', {'workspace_id':f"'{b}'::uuid"})
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'ai_usage_records', {'workspace_id':f"'{b}'::uuid"})
    credential = conn.execute("INSERT INTO nxtdeal.credential_references(workspace_id,secret_store,secret_reference,secret_version) VALUES (%s,'test','reference','v1') RETURNING id", (b,)).fetchone()[0]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'ai_route_revisions', {'revision':'2', 'credential_reference_id':f"'{credential}'::uuid"})
    ai_seed(conn, b)  # Same idempotency key is independent across workspaces.
    with pytest.raises(psycopg.errors.UniqueViolation):
        clone(conn, 'ai_usage_records', {'id':'gen_random_uuid()'})


@pytest.mark.parametrize('table', TABLES)
@pytest.mark.parametrize('operation', ['UPDATE','DELETE','TRUNCATE'])
def test_ai_history_is_immutable(database, table, operation):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    ai_seed(conn, a)
    statement = {'UPDATE':f'UPDATE nxtdeal.{table} SET workspace_id=workspace_id', 'DELETE':f'DELETE FROM nxtdeal.{table}', 'TRUNCATE':f'TRUNCATE nxtdeal.{table} CASCADE'}[operation]
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        conn.execute(statement)
    assert conn.execute(f'SELECT count(*) FROM nxtdeal.{table}').fetchone()[0] == 1


@pytest.mark.parametrize('table', TABLES)
def test_ai_rls_and_transaction_reset(database, table):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    ai_seed(conn, a)
    ai_seed(conn, b)
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


@pytest.mark.parametrize('changes', [
    {'input_tokens':'0'},  # Unavailable is different from observed zero.
    {'measurement_basis':"'reported'"},  # Must have at least one measurement.
    {'measurement_basis':"'reported'", 'input_tokens':'-1'},
    {'measurement_basis':"'estimated'", 'cost_micros':'1'},  # Currency required.
    {'currency':"'USD'"},
    {'measurement_basis':"'reported'", 'cost_micros':'1', 'currency':"'usd'"},
    {'completed_at':"started_at-interval '1 second'"},
    {'outcome':"'succeeded'"},  # Known terminal outcome requires completion time.
])
def test_invalid_or_fabricated_usage_is_rejected(database, changes):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    ai_seed(conn, a)
    with pytest.raises(psycopg.errors.CheckViolation):
        clone(conn, 'ai_usage_records', {'id':'gen_random_uuid()', 'idempotency_key':"'bad'", **changes})


def test_reported_zero_estimated_and_unavailable_remain_distinct(database):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    ai_seed(conn, a)
    clone(conn, 'ai_usage_records', {'id':'gen_random_uuid()', 'idempotency_key':"'reported'", 'measurement_basis':"'reported'", 'input_tokens':'0'})
    clone(conn, 'ai_usage_records', {'id':'gen_random_uuid()', 'idempotency_key':"'estimated'", 'measurement_basis':"'estimated'", 'cost_micros':'120', 'currency':"'USD'"})
    assert conn.execute('SELECT measurement_basis,input_tokens,cost_micros FROM nxtdeal.ai_usage_records ORDER BY measurement_basis').fetchall() == [('estimated',None,120), ('reported',0,None), ('unavailable',None,None)]
