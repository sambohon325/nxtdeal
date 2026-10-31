"""Intent is not execution; later corrected observations preserve predictions."""
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from db.migrate import MIGRATIONS, migrate
from db.tests.test_migrations import DSN, database, seed
from db.tests.test_execution_usage import clone
from db.tests.test_decision_schema import decision_seed

pytestmark = pytest.mark.skipif(not DSN, reason='Dedicated PostgreSQL test server required')
TABLES = ['interventions', 'intervention_events', 'outcome_observations']


def outcome_seed(conn, workspace, prepared=False):
    if not prepared:
        decision_seed(conn, workspace)
    intervention = conn.execute("""INSERT INTO nxtdeal.interventions
        (workspace_id,decision_id,experiment_id,alternative_id,intended_action,planned_start,planned_end,idempotency_key)
        SELECT workspace_id,id,experiment_id,selected_alternative_id,'{"staff":1}',now(),now()+interval '1 day','intervention-1'
        FROM nxtdeal.decisions WHERE workspace_id=%s RETURNING id""", (workspace,)).fetchone()[0]
    conn.execute("""INSERT INTO nxtdeal.intervention_events
        (workspace_id,intervention_id,sequence,event_type,actor,source,evidence,occurred_at,idempotency_key)
        VALUES (%s,%s,1,'scheduled','test','test','{}',now(),'intervention-event-1')""", (workspace,intervention))
    observation = conn.execute("""INSERT INTO nxtdeal.outcome_observations
        (workspace_id,prediction_id,evidence_snapshot_id,observed_value,basis,source,method_version,evidence,limitations,observed_at,idempotency_key)
        SELECT p.workspace_id,p.id,r.input_snapshot_id,14,'ACTUAL','test','1','{}','[]',now(),'observation-1'
        FROM nxtdeal.predictions p JOIN nxtdeal.model_runs r ON (p.workspace_id,p.model_run_id)=(r.workspace_id,r.id)
        WHERE p.workspace_id=%s RETURNING id""", (workspace,)).fetchone()[0]
    return intervention, observation


def test_outcome_upgrade_preserves_comparison_evidence(database, tmp_path):
    conn, _ = database
    for path in sorted(MIGRATIONS.glob('*.sql'))[:7]:
        (tmp_path / path.name).write_bytes(path.read_bytes())
    migrate(conn, tmp_path)
    a, _ = seed(conn)
    decision_seed(conn, a)
    before = conn.execute('SELECT * FROM nxtdeal.decisions').fetchall()
    assert migrate(conn) == [p.name for p in sorted(MIGRATIONS.glob('*.sql'))][7:]
    outcome_seed(conn, a, prepared=True)
    assert conn.execute('SELECT * FROM nxtdeal.decisions').fetchall() == before
    assert migrate(conn) == []


def test_intervention_requires_exact_selected_alternative(database):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    outcome_seed(conn, a)
    other = uuid4()
    clone(conn, 'experiment_alternatives', {'id':f"'{other}'::uuid", 'idempotency_key':"'other'"})
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'interventions', {'id':'gen_random_uuid()', 'idempotency_key':"'bad'", 'alternative_id':f"'{other}'::uuid"})
    baseline = uuid4()
    clone(conn, 'decisions', {'id':f"'{baseline}'::uuid", 'sequence':'2', 'idempotency_key':"'baseline'", 'selection_kind':"'baseline'", 'selected_alternative_id':'NULL'})
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'interventions', {'id':'gen_random_uuid()', 'idempotency_key':"'bad'", 'decision_id':f"'{baseline}'::uuid"})


def test_correction_preserves_original_and_cannot_branch_or_change_target(database):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    _, observation = outcome_seed(conn, a)
    before = conn.execute('SELECT * FROM nxtdeal.predictions').fetchall()
    changes = {'id':'gen_random_uuid()', 'idempotency_key':"'correction'", 'observed_value':'15', 'supersedes_id':f"'{observation}'::uuid", 'supersedes_revision':'1', 'revision':'2'}
    clone(conn, 'outcome_observations', changes)
    with pytest.raises(psycopg.errors.UniqueViolation):
        clone(conn, 'outcome_observations', {**changes, 'idempotency_key':"'branch'"})
    other_prediction = uuid4()
    clone(conn, 'predictions', {'id':f"'{other_prediction}'::uuid", 'idempotency_key':"'other'"})
    latest = conn.execute('SELECT id FROM nxtdeal.outcome_observations WHERE revision=2').fetchone()[0]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'outcome_observations', {**changes, 'idempotency_key':"'wrong-target'", 'prediction_id':f"'{other_prediction}'::uuid", 'supersedes_id':f"'{latest}'::uuid", 'supersedes_revision':'2', 'revision':'3'})
    assert conn.execute('SELECT observed_value FROM nxtdeal.outcome_observations ORDER BY revision').fetchall() == [(14,),(15,)]
    assert conn.execute('SELECT * FROM nxtdeal.predictions WHERE id=%s', (before[0][1],)).fetchall() == before


@pytest.mark.parametrize('table', TABLES)
def test_outcome_scope_and_idempotency(database, table):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    outcome_seed(conn, a)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, table, {'workspace_id':f"'{b}'::uuid"})
    outcome_seed(conn, b)
    with pytest.raises(psycopg.errors.UniqueViolation):
        clone(conn, table, {'id':'gen_random_uuid()', 'sequence':'2'})


@pytest.mark.parametrize('table', TABLES)
@pytest.mark.parametrize('operation', ['UPDATE','DELETE','TRUNCATE'])
def test_outcome_history_is_immutable(database, table, operation):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    outcome_seed(conn, a)
    statement = {'UPDATE':f'UPDATE nxtdeal.{table} SET workspace_id=workspace_id', 'DELETE':f'DELETE FROM nxtdeal.{table}', 'TRUNCATE':f'TRUNCATE nxtdeal.{table} CASCADE'}[operation]
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        conn.execute(statement)
    assert conn.execute(f'SELECT count(*) FROM nxtdeal.{table}').fetchone()[0] == 1


@pytest.mark.parametrize('table', TABLES)
def test_outcome_rls_and_transaction_reset(database, table):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    outcome_seed(conn, a)
    outcome_seed(conn, b)
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
    ('interventions', {'planned_end':'planned_start'}),
    ('interventions', {'intended_action':"'{}'::jsonb"}),
    ('intervention_events', {'sequence':'0'}),
    ('outcome_observations', {'basis':"'MODELED'"}),
    ('outcome_observations', {'observed_value':"'NaN'::numeric"}),
    ('outcome_observations', {'revision':'2'}),
    ('outcome_observations', {'supersedes_revision':'1'}),
    ('outcome_observations', {'supersedes_id':'id', 'supersedes_revision':'1', 'revision':'1'}),
])
def test_outcome_invalid_evidence(database, table, changes):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    outcome_seed(conn, a)
    with pytest.raises(psycopg.errors.CheckViolation):
        clone(conn, table, {'id':'gen_random_uuid()', 'idempotency_key':"'bad'", **changes})
