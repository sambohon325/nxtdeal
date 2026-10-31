from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from db.migrate import migrate, MIGRATIONS
from db.shadow_compare import GraphObservation, ShadowRejected
from db.shadow_journal import prepare, record_json_commit
from db.tests.test_migrations import DSN, database
from db.tests.test_import_writer import workspace

pytestmark = pytest.mark.skipif(not DSN,reason='Dedicated PostgreSQL test server required')
GRAPH = b'{"entities":[],"relationships":[]}'


def setup(conn):
    migrate(conn)
    return str(workspace(conn)),str(uuid4())


def capture(target,generation=1):
    return GraphObservation(target,generation,GRAPH)


def test_prepare_reconnect_replay_commit_and_next_generation(database):
    conn,dsn = database
    target,operation = setup(conn)
    args = dict(workspace_id=target,operation_id=operation,graph_bytes=GRAPH)
    assert prepare(conn,**args) == 1
    with psycopg.connect(dsn,autocommit=True) as reopened:
        assert prepare(reopened,**args) == 1
        with pytest.raises(ShadowRejected,match='pending_predecessor'):
            prepare(reopened,**{**args,'operation_id':str(uuid4())})
        commit = dict(workspace_id=target,operation_id=operation,observation=capture(target))
        assert record_json_commit(reopened,**commit) == 'committed'
    assert record_json_commit(conn,**commit) == 'already_committed'
    assert prepare(conn,**{**args,'operation_id':str(uuid4())}) == 2
    assert conn.execute("SELECT current_setting('nxtdeal.workspace_id',true)").fetchone()[0] == ''


def test_conflicting_operation_and_commit_observation(database):
    conn,_ = database
    target,operation = setup(conn)
    args = dict(workspace_id=target,operation_id=operation)
    prepare(conn,**args,graph_bytes=GRAPH)
    with pytest.raises(ShadowRejected,match='operation_conflict'):
        prepare(conn,**args,graph_bytes=GRAPH+b' ')
    for invalid in (capture(target,2),replace(capture(target),graph_bytes=GRAPH+b' ')):
        with pytest.raises(ShadowRejected,match='commit_evidence_mismatch'):
            record_json_commit(conn,**args,observation=invalid)
    with pytest.raises(ShadowRejected,match='workspace_mismatch'):
        record_json_commit(conn,**args,observation=capture(str(uuid4())))
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_commits').fetchone()[0] == 0


def test_concurrent_same_operation_is_one_generation(database):
    conn,dsn = database
    target,operation = setup(conn)
    def run(_):
        with psycopg.connect(dsn,autocommit=True) as separate:
            return prepare(separate,workspace_id=target,operation_id=operation,graph_bytes=GRAPH)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(run,range(2))) == [1,1]
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_preparations').fetchone()[0] == 1


@pytest.mark.parametrize('table',['shadow_preparations','shadow_commits'])
@pytest.mark.parametrize('operation',['UPDATE','DELETE','TRUNCATE'])
def test_journal_immutable(database,table,operation):
    conn,_ = database
    target,op = setup(conn)
    prepare(conn,workspace_id=target,operation_id=op,graph_bytes=GRAPH)
    record_json_commit(conn,workspace_id=target,operation_id=op,observation=capture(target))
    statement = {'UPDATE':f'UPDATE nxtdeal.{table} SET semantic_digest=semantic_digest',
                 'DELETE':f'DELETE FROM nxtdeal.{table}',
                 'TRUNCATE':'TRUNCATE nxtdeal.shadow_preparations,nxtdeal.shadow_commits,nxtdeal.shadow_projections,nxtdeal.normalized_receipts'}[operation]
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        conn.execute(statement)


def test_constraints_reject_uncommitted_predecessor_and_wrong_digest(database):
    conn,_ = database
    target,operation = setup(conn)
    prepare(conn,workspace_id=target,operation_id=operation,graph_bytes=GRAPH)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute('''INSERT INTO nxtdeal.shadow_preparations SELECT workspace_id,2,%s,1,snapshot,semantic_digest,now()
            FROM nxtdeal.shadow_preparations''',(uuid4(),))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute("INSERT INTO nxtdeal.shadow_commits VALUES (%s,1,%s,%s,now())",(target,operation,'0'*64))


def test_journal_scope_guards_and_missing_preparation(database):
    conn,_ = database
    target,operation = setup(conn)
    with pytest.raises(ShadowRejected,match='preparation_missing'):
        record_json_commit(conn,workspace_id=target,operation_id=operation,observation=capture(target))
    fake = SimpleNamespace(autocommit=True,info=SimpleNamespace(transaction_status=psycopg.pq.TransactionStatus.IDLE,dbname='production'))
    with pytest.raises(ShadowRejected,match='disposable_test_database_required'):
        prepare(fake,workspace_id=target,operation_id=operation,graph_bytes=GRAPH)
    with conn.transaction():
        with pytest.raises(ShadowRejected,match='dedicated_idle_connection_required'):
            prepare(conn,workspace_id=target,operation_id=operation,graph_bytes=GRAPH)


def test_populated_0010_upgrade(database,tmp_path):
    conn,_ = database
    for path in MIGRATIONS.glob('*.sql'):
        if path.name < '0011':
            (tmp_path/path.name).write_bytes(path.read_bytes())
    migrate(conn,tmp_path)
    target = workspace(conn)
    assert migrate(conn) == ['0011_shadow_journal.sql', '0012_shadow_projections.sql', '0013_normalized_receipts.sql']
    assert conn.execute('SELECT id FROM nxtdeal.workspaces').fetchall() == [(target,)]


@pytest.mark.parametrize('table',['shadow_preparations','shadow_commits'])
def test_journal_rls(database,table):
    conn,_ = database
    a,op = setup(conn)
    b = str(workspace(conn))
    for target in (a,b):
        prepare(conn,workspace_id=target,operation_id=op,graph_bytes=GRAPH)
        record_json_commit(conn,workspace_id=target,operation_id=op,observation=capture(target))
    role = 'nxtdeal_test_' + uuid4().hex
    conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS').format(sql.Identifier(role)))
    try:
        conn.execute(sql.SQL('GRANT USAGE ON SCHEMA nxtdeal TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('GRANT SELECT,INSERT ON nxtdeal.{} TO {}').format(sql.Identifier(table),sql.Identifier(role)))
        conn.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
        assert conn.execute(f'SELECT count(*) FROM nxtdeal.{table}').fetchone()[0] == 0
        with conn.transaction():
            conn.execute("SELECT set_config('nxtdeal.workspace_id',%s,true)",(a,))
            assert str(conn.execute(f'SELECT workspace_id FROM nxtdeal.{table}').fetchone()[0]) == a
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    columns = 'generation,operation_id,predecessor,snapshot,semantic_digest,recorded_at' if table == 'shadow_preparations' else 'generation,operation_id,semantic_digest,recorded_at'
                    conn.execute(f'INSERT INTO nxtdeal.{table} SELECT %s,{columns} FROM nxtdeal.{table}',(uuid4(),))
        assert conn.execute(f'SELECT count(*) FROM nxtdeal.{table}').fetchone()[0] == 0
    finally:
        conn.execute('RESET ROLE')
        conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


def test_recovery_never_promotes_matching_preparation(database):
    from db.shadow_journal import inspect_recovery
    conn,dsn = database
    target,operation = setup(conn)
    args = dict(workspace_id=target,operation_id=operation)
    prepare(conn,**args,graph_bytes=GRAPH)
    with psycopg.connect(dsn,autocommit=True) as reopened:
        report = inspect_recovery(reopened,**args,observed_graph_bytes=GRAPH)
    assert report['status'] == 'prepared_unresolved'
    assert report['matches_prepared_bytes'] is True
    assert report['action'] == 'manual_reconciliation_required'
    assert report['database_written'] is False
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_commits').fetchone()[0] == 0


def test_identical_successive_snapshots_remain_ambiguous(database):
    from db.shadow_journal import inspect_recovery
    conn,_ = database
    target,operation = setup(conn)
    prepare(conn,workspace_id=target,operation_id=operation,graph_bytes=GRAPH)
    record_json_commit(conn,workspace_id=target,operation_id=operation,observation=capture(target))
    next_operation = str(uuid4())
    prepare(conn,workspace_id=target,operation_id=next_operation,graph_bytes=GRAPH)
    report = inspect_recovery(conn,workspace_id=target,operation_id=next_operation,observed_graph_bytes=GRAPH)
    assert report['matches_prepared_bytes'] and report['matches_predecessor_bytes']
    assert report['status'] == 'prepared_unresolved'
    assert report['action'] == 'manual_reconciliation_required'
    old = inspect_recovery(conn,workspace_id=target,operation_id=operation)
    assert old['status'] == 'commit_recorded'
    assert old['latest_generation'] == 2
    assert old['matches_prepared_bytes'] is None


def test_recovery_scope_missing_and_redaction(database):
    import json
    from db.shadow_journal import inspect_recovery
    conn,_ = database
    target,operation = setup(conn)
    private = b'{"entities":[{"id":"PRIVATE-ID","entity_type":"Customer","attributes":{"secret":"PRIVATE-VALUE"}}],"relationships":[]}'
    prepare(conn,workspace_id=target,operation_id=operation,graph_bytes=private)
    report = inspect_recovery(conn,workspace_id=target,operation_id=operation,observed_graph_bytes=GRAPH)
    assert report['matches_prepared_bytes'] is False
    assert 'PRIVATE' not in json.dumps(report)
    other = str(workspace(conn))
    assert inspect_recovery(conn,workspace_id=other,operation_id=operation)['status'] == 'preparation_missing'
    with pytest.raises(ShadowRejected,match='invalid_graph_observation'):
        inspect_recovery(conn,workspace_id=target,operation_id=operation,observed_graph_bytes=b'PRIVATE invalid')
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_commits').fetchone()[0] == 0


def test_recovery_detects_corrupt_prepared_digest(database):
    from db.shadow_journal import inspect_recovery
    conn,_ = database
    target,operation = setup(conn)
    # Direct synthetic malformed insert represents a faulty privileged writer;
    # no immutable-history protection is disabled to construct the fixture.
    conn.execute('''INSERT INTO nxtdeal.shadow_preparations
        (workspace_id,generation,operation_id,snapshot,semantic_digest) VALUES (%s,1,%s,%s,%s)''',
        (target,operation,GRAPH,'0'*64))
    with pytest.raises(ShadowRejected,match='journal_snapshot_mismatch'):
        inspect_recovery(conn,workspace_id=target,operation_id=operation)
