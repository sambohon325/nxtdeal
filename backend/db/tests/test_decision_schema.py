"""Comparisons share original evidence and selections cannot cross experiments."""
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from db.migrate import MIGRATIONS, migrate
from db.tests.test_migrations import DSN, database, seed, governance_seed
from db.tests.test_execution_usage import clone
from db.tests.test_analysis_schema import analysis_seed

pytestmark = pytest.mark.skipif(not DSN, reason='Dedicated PostgreSQL test server required')
TABLES = ['experiments', 'experiment_alternatives', 'decisions']


def decision_seed(conn, workspace, snapshot=None, run=None):
    if snapshot is None:
        snapshot, run = analysis_seed(conn, workspace)
    actor, _ = governance_seed(conn, workspace)
    experiment = conn.execute("""INSERT INTO nxtdeal.experiments
        (workspace_id,input_snapshot_id,baseline_run_id,question,context,unchanged_variables,assumptions,limitations,created_by,idempotency_key)
        VALUES (%s,%s,%s,'Test comparison','{}','{}','[]','[]',%s,'experiment-1') RETURNING id""", (workspace,snapshot,run,actor)).fetchone()[0]
    alternative_run = uuid4()
    # Keep the same original inputs; the intervention lives in run configuration.
    conn.execute("""INSERT INTO nxtdeal.model_runs
        SELECT workspace_id,%s,input_snapshot_id,engine_key,engine_version,model_key,model_version,adapter_version,
        runtime_manifest,'{"staff":1}'::jsonb,assumptions,limitations,reproducibility,random_seed,status,outputs,error_code,
        started_at,completed_at,recorded_at,'alternative-run'
        FROM nxtdeal.model_runs WHERE workspace_id=%s AND id=%s""", (alternative_run,workspace,run))
    alternative = conn.execute("""INSERT INTO nxtdeal.experiment_alternatives
        (workspace_id,experiment_id,input_snapshot_id,model_run_id,name,changed_variables,assumptions,expected_results,idempotency_key)
        VALUES (%s,%s,%s,%s,'Staffing test','{"staff":1}','[]','{"basis":"MODELED"}','alternative-1') RETURNING id""", (workspace,experiment,snapshot,alternative_run)).fetchone()[0]
    conn.execute("""INSERT INTO nxtdeal.decisions
        (workspace_id,experiment_id,sequence,selection_kind,selected_alternative_id,decided_by,reason,authority_snapshot,occurred_at,idempotency_key)
        VALUES (%s,%s,1,'alternative',%s,%s,'Test choice','{}',now(),'decision-choice-1')""", (workspace,experiment,alternative,actor))
    return experiment, alternative


def test_comparison_upgrade_preserves_predictions(database, tmp_path):
    conn, _ = database
    for path in sorted(MIGRATIONS.glob('*.sql'))[:6]:
        (tmp_path / path.name).write_bytes(path.read_bytes())
    migrate(conn, tmp_path)
    a, _ = seed(conn)
    snapshot, run = analysis_seed(conn, a)
    before = conn.execute('SELECT * FROM nxtdeal.predictions').fetchall()
    assert migrate(conn) == [p.name for p in sorted(MIGRATIONS.glob('*.sql'))][6:]
    decision_seed(conn, a, snapshot, run)
    assert conn.execute('SELECT * FROM nxtdeal.predictions').fetchall() == before
    assert migrate(conn) == []


def test_decision_cannot_select_another_experiments_alternative(database):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    decision_seed(conn, a)
    other = uuid4()
    clone(conn, 'experiments', {'id':f"'{other}'::uuid", 'idempotency_key':"'other-experiment'"})
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'decisions', {'id':'gen_random_uuid()', 'idempotency_key':"'wrong-experiment'", 'experiment_id':f"'{other}'::uuid"})
    # Choosing the baseline is explicit and cannot retain an alternative reference.
    clone(conn, 'decisions', {'id':'gen_random_uuid()', 'idempotency_key':"'baseline'", 'sequence':'2', 'selection_kind':"'baseline'", 'selected_alternative_id':'NULL'})
    assert conn.execute('SELECT selection_kind FROM nxtdeal.decisions ORDER BY sequence').fetchall() == [('alternative',),('baseline',)]


def test_alternative_cannot_swap_original_snapshot(database):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    decision_seed(conn, a)
    other = uuid4()
    clone(conn, 'input_snapshots', {'id':f"'{other}'::uuid", 'idempotency_key':"'other-input'"})
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'experiment_alternatives', {'id':'gen_random_uuid()', 'idempotency_key':"'other'", 'input_snapshot_id':f"'{other}'::uuid"})
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'experiments', {'id':'gen_random_uuid()', 'idempotency_key':"'other'", 'input_snapshot_id':f"'{other}'::uuid"})


@pytest.mark.parametrize('table', TABLES)
def test_comparison_scope_and_idempotency(database, table):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    decision_seed(conn, a)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, table, {'workspace_id':f"'{b}'::uuid"})
    decision_seed(conn, b)
    with pytest.raises(psycopg.errors.UniqueViolation):
        clone(conn, table, {'id':'gen_random_uuid()', 'sequence':'2'})


@pytest.mark.parametrize('table', TABLES)
@pytest.mark.parametrize('operation', ['UPDATE','DELETE','TRUNCATE'])
def test_comparison_history_is_immutable(database, table, operation):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    decision_seed(conn, a)
    statement = {'UPDATE':f'UPDATE nxtdeal.{table} SET workspace_id=workspace_id', 'DELETE':f'DELETE FROM nxtdeal.{table}', 'TRUNCATE':f'TRUNCATE nxtdeal.{table} CASCADE'}[operation]
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        conn.execute(statement)
    assert conn.execute(f'SELECT count(*) FROM nxtdeal.{table}').fetchone()[0] == 1


@pytest.mark.parametrize('table', TABLES)
def test_comparison_rls_and_transaction_reset(database, table):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    decision_seed(conn, a)
    decision_seed(conn, b)
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
    ('experiments', {'question':"' '"}),
    ('experiment_alternatives', {'changed_variables':"'{}'::jsonb"}),
    ('experiment_alternatives', {'estimated_cost_micros':'1'}),
    ('experiment_alternatives', {'estimated_cost_micros':'-1', 'currency':"'USD'"}),
    ('decisions', {'selection_kind':"'baseline'"}),
    ('decisions', {'selected_alternative_id':'NULL'}),
    ('decisions', {'sequence':'0'}),
])
def test_comparison_invalid_evidence(database, table, changes):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    decision_seed(conn, a)
    with pytest.raises(psycopg.errors.CheckViolation):
        clone(conn, table, {'id':'gen_random_uuid()', 'idempotency_key':"'bad'", **changes})
