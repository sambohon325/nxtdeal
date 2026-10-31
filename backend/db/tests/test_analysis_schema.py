"""Durable analysis records preserve inputs and reject false evidence shapes."""
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from db.migrate import MIGRATIONS, migrate
from db.tests.test_migrations import DSN, database, seed
from db.tests.test_execution_usage import clone
from db.tests.test_ai_schema import ai_seed

pytestmark = pytest.mark.skipif(not DSN, reason='Dedicated PostgreSQL test server required')
TABLES = ['input_snapshots', 'model_runs', 'predictions']


def analysis_seed(conn, workspace):
    snapshot = conn.execute("""INSERT INTO nxtdeal.input_snapshots
        (workspace_id,schema_version,as_of,source,content_digest,inputs,provenance,limitations,idempotency_key)
        VALUES (%s,1,now(),'test',%s,'{"units":12}','{"units":"ACTUAL"}','[]','snapshot-1') RETURNING id""", (workspace, 'a'*64)).fetchone()[0]
    run = conn.execute("""INSERT INTO nxtdeal.model_runs
        (workspace_id,input_snapshot_id,engine_key,engine_version,model_key,model_version,adapter_version,runtime_manifest,configuration,assumptions,limitations,reproducibility,status,outputs,started_at,completed_at,idempotency_key)
        VALUES (%s,%s,'test','1','test','1','1','{}','{}','[]','[]','deterministic','succeeded','{"units":13}',now(),now(),'run-1') RETURNING id""", (workspace,snapshot)).fetchone()[0]
    conn.execute("""INSERT INTO nxtdeal.predictions
        (workspace_id,model_run_id,metric_key,subject_reference,unit,horizon_start,horizon_end,predicted_value,confidence_kind,evidence,limitations,idempotency_key)
        VALUES (%s,%s,'units','fixture','vehicles',now(),now()+interval '1 day',13,'unavailable','{}','[]','prediction-1')""", (workspace,run))
    return snapshot, run


def test_analysis_upgrade_preserves_existing_usage(database, tmp_path):
    conn, _ = database
    for path in sorted(MIGRATIONS.glob('*.sql'))[:5]:
        (tmp_path / path.name).write_bytes(path.read_bytes())
    migrate(conn, tmp_path)
    a, _ = seed(conn)
    ai_seed(conn, a)
    before = conn.execute('SELECT * FROM nxtdeal.ai_usage_records').fetchall()
    assert migrate(conn) == [p.name for p in sorted(MIGRATIONS.glob('*.sql'))][5:]
    analysis_seed(conn, a)
    assert conn.execute('SELECT * FROM nxtdeal.ai_usage_records').fetchall() == before
    assert migrate(conn) == []


def test_analysis_binding_tenant_idempotency_and_failed_run(database):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    snapshot, _ = analysis_seed(conn, a)
    for table in ['model_runs','predictions']:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            clone(conn, table, {'workspace_id':f"'{b}'::uuid"})
    analysis_seed(conn, b)
    for table in TABLES:
        with pytest.raises(psycopg.errors.UniqueViolation):
            clone(conn, table, {'id':'gen_random_uuid()'})
    failed = uuid4()
    clone(conn, 'model_runs', {'id':f"'{failed}'::uuid", 'idempotency_key':"'failed-run'", 'status':"'failed'", 'outputs':'NULL', 'error_code':"'test_error'"})
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'predictions', {'id':'gen_random_uuid()', 'idempotency_key':"'bad'", 'model_run_id':f"'{failed}'::uuid"})
    assert conn.execute('SELECT inputs FROM nxtdeal.input_snapshots WHERE workspace_id=%s AND id=%s', (a,snapshot)).fetchone()[0] == {'units':12}


@pytest.mark.parametrize('table', TABLES)
@pytest.mark.parametrize('operation', ['UPDATE','DELETE','TRUNCATE'])
def test_analysis_history_is_immutable(database, table, operation):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    analysis_seed(conn, a)
    statement = {'UPDATE':f'UPDATE nxtdeal.{table} SET workspace_id=workspace_id', 'DELETE':f'DELETE FROM nxtdeal.{table}', 'TRUNCATE':f'TRUNCATE nxtdeal.{table} CASCADE'}[operation]
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        conn.execute(statement)
    assert conn.execute(f'SELECT count(*) FROM nxtdeal.{table}').fetchone()[0] == 1


@pytest.mark.parametrize('table', TABLES)
def test_analysis_rls_and_transaction_reset(database, table):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    analysis_seed(conn, a)
    analysis_seed(conn, b)
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
    ('input_snapshots', {'content_digest':"'invalid'"}),
    ('input_snapshots', {'inputs':"'[]'::jsonb"}),
    ('model_runs', {'status':"'failed'"}),
    ('model_runs', {'outputs':'NULL'}),
    ('model_runs', {'completed_at':"started_at-interval '1 second'"}),
    ('model_runs', {'reproducibility':"'nondeterministic'"}),
    ('predictions', {'horizon_end':'horizon_start'}),
    ('predictions', {'basis':"'ACTUAL'"}),
    ('predictions', {'predicted_value':"'NaN'::numeric"}),
    ('predictions', {'predicted_value':"'Infinity'::numeric"}),
    ('predictions', {'confidence':'0.8'}),
    ('predictions', {'confidence_kind':"'heuristic'", 'confidence':'1.1'}),
    ('predictions', {'confidence_kind':"'calibrated_probability'", 'confidence':'0.8'}),
    ('predictions', {'confidence_kind':"'heuristic'", 'confidence':'0.8', 'calibration_reference':"'false-calibration'"}),
])
def test_analysis_invalid_evidence(database, table, changes):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    analysis_seed(conn, a)
    with pytest.raises(psycopg.errors.CheckViolation):
        clone(conn, table, {'id':'gen_random_uuid()', 'idempotency_key':"'bad'", **changes})


def test_nondeterminism_and_confidence_have_explicit_evidence(database):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    analysis_seed(conn, a)
    clone(conn, 'model_runs', {'id':'gen_random_uuid()', 'idempotency_key':"'nondeterministic'", 'reproducibility':"'nondeterministic'", 'limitations':"'[\"External nondeterministic test model\"]'::jsonb"})
    clone(conn, 'predictions', {'id':'gen_random_uuid()', 'idempotency_key':"'heuristic'", 'confidence_kind':"'heuristic'", 'confidence':'0.8'})
    clone(conn, 'predictions', {'id':'gen_random_uuid()', 'idempotency_key':"'calibrated'", 'confidence_kind':"'calibrated_probability'", 'confidence':'0.7', 'calibration_reference':"'test-evaluation-v1'"})
    assert conn.execute('SELECT confidence_kind FROM nxtdeal.predictions ORDER BY confidence_kind').fetchall() == [('calibrated_probability',),('heuristic',),('unavailable',)]
