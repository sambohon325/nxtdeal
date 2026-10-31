from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from db.shadow_compare import GraphObservation, ShadowRejected
from db.shadow_journal import prepare, record_json_commit
from db.shadow_projection import apply_test_projection
from db.tests.test_migrations import DSN, database
from db.tests.test_shadow_journal import setup, GRAPH
from db.tests.test_import_writer import workspace as create_workspace

pytestmark = pytest.mark.skipif(not DSN, reason='Disposable PostgreSQL required')


def committed(conn, workspace, operation, data=GRAPH):
    generation = prepare(conn, workspace_id=workspace, operation_id=operation, graph_bytes=data)
    record_json_commit(conn, workspace_id=workspace, operation_id=operation,
                       observation=GraphObservation(workspace,generation,data))


def test_projection_order_and_idempotent_reconnect(database):
    conn, dsn = database
    workspace, operation = setup(conn)
    committed(conn, workspace, operation)
    second = str(uuid4())
    committed(conn, workspace, second)
    with pytest.raises(ShadowRejected, match='projection_predecessor_mismatch'):
        apply_test_projection(conn, workspace_id=workspace, operation_id=second, expected_predecessor=1)
    args = dict(workspace_id=workspace, operation_id=operation, expected_predecessor=0)
    assert apply_test_projection(conn, **args)['status'] == 'applied'
    with psycopg.connect(dsn, autocommit=True) as fresh:
        assert apply_test_projection(fresh, **args)['status'] == 'already_applied'
        assert apply_test_projection(fresh, workspace_id=workspace, operation_id=second, expected_predecessor=1)['generation'] == 2
    assert conn.execute('SELECT count(*) FROM nxtdeal.entities').fetchone()[0] == 0


def test_uncommitted_and_other_scope_rejected(database):
    conn, _ = database
    workspace, operation = setup(conn)
    prepare(conn, workspace_id=workspace, operation_id=operation, graph_bytes=GRAPH)
    with pytest.raises(ShadowRejected, match='committed_snapshot_required'):
        apply_test_projection(conn, workspace_id=workspace, operation_id=operation, expected_predecessor=0)
    other = str(create_workspace(conn))
    with pytest.raises(ShadowRejected, match='committed_snapshot_required'):
        apply_test_projection(conn, workspace_id=other, operation_id=operation, expected_predecessor=0)
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_projections').fetchone()[0] == 0


def test_exact_decimal_order_duplicates_and_optional_shape(database):
    conn, _ = database
    workspace, operation = setup(conn)
    data = b'{"entities":[{"id":"b","entity_type":"Customer","attributes":{"v":0.12345678901234567890123456789}},{"id":"a","entity_type":"Customer","attributes":{}}],"relationships":[{"source_id":"b","target_id":"a","relationship_type":"owns"},{"source_id":"b","target_id":"a","relationship_type":"owns"}]}'
    committed(conn, workspace, operation, data)
    result = apply_test_projection(conn, workspace_id=workspace, operation_id=operation, expected_predecessor=0)
    assert result['semantic_sha256'] == GraphObservation(workspace,1,data).evidence()['semantic_sha256']


def test_concurrent_replay_applies_once(database):
    conn, dsn = database
    workspace, operation = setup(conn)
    committed(conn, workspace, operation)
    def run(_):
        with psycopg.connect(dsn, autocommit=True) as separate:
            return apply_test_projection(separate, workspace_id=workspace, operation_id=operation, expected_predecessor=0)['status']
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, range(2))) == ['already_applied','applied']


@pytest.mark.parametrize('statement', ['UPDATE nxtdeal.shadow_projections SET semantic_digest=semantic_digest',
                                      'DELETE FROM nxtdeal.shadow_projections', 'TRUNCATE nxtdeal.shadow_projections'])
def test_projection_history_immutable(database, statement):
    conn, _ = database
    workspace, operation = setup(conn)
    committed(conn, workspace, operation)
    apply_test_projection(conn, workspace_id=workspace, operation_id=operation, expected_predecessor=0)
    with pytest.raises(psycopg.Error):
        conn.execute(statement)
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_projections').fetchone()[0] == 1


def test_projection_rls_fail_closed(database):
    conn, _ = database
    a, operation = setup(conn)
    b = str(create_workspace(conn))
    for target in (a,b):
        committed(conn,target,operation)
        apply_test_projection(conn,workspace_id=target,operation_id=operation,expected_predecessor=0)
    role = 'nxtdeal_test_' + uuid4().hex
    conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS').format(sql.Identifier(role)))
    try:
        conn.execute(sql.SQL('GRANT USAGE ON SCHEMA nxtdeal TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('GRANT SELECT,INSERT ON nxtdeal.shadow_projections TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
        assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_projections').fetchone()[0] == 0
        with conn.transaction():
            conn.execute("SELECT set_config('nxtdeal.workspace_id',%s,true)",(a,))
            assert str(conn.execute('SELECT workspace_id FROM nxtdeal.shadow_projections').fetchone()[0]) == a
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute('INSERT INTO nxtdeal.shadow_projections SELECT %s,generation,predecessor,graph,semantic_digest,recorded_at FROM nxtdeal.shadow_projections',(uuid4(),))
        assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_projections').fetchone()[0] == 0
    finally:
        conn.execute('RESET ROLE')
        conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


@pytest.mark.parametrize('mutation', ["NEW.graph = '{\"entities\":[],\"relationships\":[],\"extra\":true}'::jsonb;",
                                     "NEW.semantic_digest = repeat('0',64);", 'RETURN NULL;'])
def test_projection_readback_failure_rolls_back_and_can_retry(database, mutation):
    conn, _ = database
    workspace, operation = setup(conn)
    committed(conn,workspace,operation)
    # Deliberate test-database insert corruption, including a swallowed insert.
    conn.execute('CREATE FUNCTION nxtdeal.break_projection() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN '
                 + mutation + ' RETURN NEW; END $$')
    conn.execute('CREATE TRIGGER break_projection BEFORE INSERT ON nxtdeal.shadow_projections FOR EACH ROW EXECUTE FUNCTION nxtdeal.break_projection()')
    args = dict(workspace_id=workspace,operation_id=operation,expected_predecessor=0)
    with pytest.raises(ShadowRejected,match='^projection_parity_failed$'):
        apply_test_projection(conn,**args)
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_projections').fetchone()[0] == 0
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_commits').fetchone()[0] == 1
    conn.execute('DROP TRIGGER break_projection ON nxtdeal.shadow_projections')
    assert apply_test_projection(conn,**args)['status'] == 'applied'


@pytest.mark.parametrize('column,value', [('graph', "'{\"unexpected\":true}'::jsonb"),
                                        ('semantic_digest', "repeat('0',64)")])
def test_replay_detects_privileged_corruption(database,column,value):
    conn, _ = database
    workspace, operation = setup(conn)
    committed(conn,workspace,operation)
    args = dict(workspace_id=workspace,operation_id=operation,expected_predecessor=0)
    apply_test_projection(conn,**args)
    # Simulate corruption by an administrator who can disable evidence guards.
    conn.execute('ALTER TABLE nxtdeal.shadow_projections DISABLE TRIGGER immutable_shadow_projections')
    try:
        conn.execute(sql.SQL('UPDATE nxtdeal.shadow_projections SET {} = ').format(sql.Identifier(column)) + sql.SQL(value))
    finally:
        conn.execute('ALTER TABLE nxtdeal.shadow_projections ENABLE TRIGGER immutable_shadow_projections')
    with pytest.raises(ShadowRejected,match='^projection_parity_failed$'):
        apply_test_projection(conn,**args)
    next_operation = str(uuid4())
    committed(conn,workspace,next_operation)
    with pytest.raises(ShadowRejected,match='^projection_predecessor_corrupt$'):
        apply_test_projection(conn,workspace_id=workspace,operation_id=next_operation,expected_predecessor=1)
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_projections').fetchone()[0] == 1
