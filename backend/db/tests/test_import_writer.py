from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest

from db.migrate import migrate
from db.import_package import prepare_import, ImportRejected
from db.import_writer import import_into_test_database, export_imported
from db.tests.test_migrations import DSN, database
from db.tests.test_import_package import fixtures
from db.import_preflight import canonical

pytestmark = pytest.mark.skipif(not DSN, reason='Dedicated PostgreSQL test server required')


def workspace(conn):
    organization = conn.execute("INSERT INTO nxtdeal.organizations(name) VALUES ('Synthetic') RETURNING id").fetchone()[0]
    return conn.execute("INSERT INTO nxtdeal.workspaces(organization_id,name) VALUES (%s,'Synthetic') RETURNING id", (organization,)).fetchone()[0]


def package(tmp_path, target):
    graph,audit,anchor = fixtures(tmp_path)
    # Duplicates and missing-vs-null optional fields must survive projection.
    text = graph.read_text(encoding='utf-8')
    links = '[{"source_id":"A","target_id":"A","relationship_type":"owns"},{"source_id":"A","target_id":"A","relationship_type":"owns","created_by":null,"created_at":"legacy timestamp"}]'
    graph.write_text(text.replace('"relationships":[]','"relationships":'+links),encoding='utf-8')
    return prepare_import(graph,str(target),audit_path=audit,checkpoint_path=anchor)


def test_exact_roundtrip_audit_provenance_and_repeat(database,tmp_path):
    conn,_ = database
    migrate(conn)
    target = workspace(conn)
    captured = package(tmp_path,target)
    original = captured.payloads()
    assert import_into_test_database(conn,captured,workspace_id=str(target))['status'] == 'imported'
    graph,audit,manifest = export_imported(conn,target)
    assert canonical(graph) == canonical(original[0])
    assert canonical(audit) == canonical(original[1])
    assert manifest == captured.manifest()
    assert import_into_test_database(conn,captured,workspace_id=str(target))['status'] == 'already_imported'
    assert conn.execute('SELECT count(*) FROM nxtdeal.audit_events').fetchone()[0] == 3
    assert conn.execute("SELECT current_setting('nxtdeal.workspace_id',true)").fetchone()[0] == ''


def test_conflicting_manifest_and_nonempty_target_are_rejected(database,tmp_path):
    conn,_ = database
    migrate(conn)
    target = workspace(conn)
    captured = package(tmp_path,target)
    conn.execute("INSERT INTO nxtdeal.entities(workspace_id,id,entity_type) VALUES (%s,'existing','Customer')", (target,))
    with pytest.raises(ImportRejected,match='target_not_empty'):
        import_into_test_database(conn,captured,workspace_id=str(target))
    assert conn.execute('SELECT count(*) FROM nxtdeal.import_manifests').fetchone()[0] == 0
    other = workspace(conn)
    captured = replace(captured,workspace_id=str(other))
    import_into_test_database(conn,captured,workspace_id=str(other))
    with pytest.raises(ImportRejected,match='manifest_conflict'):
        import_into_test_database(conn,replace(captured,graph_bytes=captured.graph_bytes+b' '),workspace_id=str(other))


def test_repeat_checks_target_data_instead_of_trusting_manifest(database,tmp_path):
    conn,_ = database
    migrate(conn)
    target = workspace(conn)
    captured = package(tmp_path,target)
    import_into_test_database(conn,captured,workspace_id=str(target))
    conn.execute("UPDATE nxtdeal.entities SET attributes='{}' WHERE workspace_id=%s", (target,))
    with pytest.raises(ImportRejected,match='graph_digest_failed'):
        import_into_test_database(conn,captured,workspace_id=str(target))
    assert conn.execute('SELECT attributes FROM nxtdeal.entities WHERE workspace_id=%s', (target,)).fetchone()[0] == {}


def test_parity_failure_rolls_back_all_rows_and_manifest(database,tmp_path):
    conn,_ = database
    migrate(conn)
    target = workspace(conn)
    captured = package(tmp_path,target)
    conn.execute("""CREATE FUNCTION nxtdeal.test_alter_import() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN NEW.attributes = '{}'::jsonb; RETURN NEW; END; $$;
        CREATE TRIGGER test_alter_import BEFORE INSERT ON nxtdeal.entities
        FOR EACH ROW EXECUTE FUNCTION nxtdeal.test_alter_import();""")
    with pytest.raises(ImportRejected,match='graph_digest_failed'):
        import_into_test_database(conn,captured,workspace_id=str(target))
    for table in ('entities','relationships','audit_events','import_manifests'):
        assert conn.execute(f'SELECT count(*) FROM nxtdeal.{table}').fetchone()[0] == 0


def test_workspace_binding_and_cross_workspace_independence(database,tmp_path):
    conn,_ = database
    migrate(conn)
    a,b = workspace(conn),workspace(conn)
    captured = package(tmp_path,a)
    with pytest.raises(ImportRejected,match='workspace_mismatch'):
        import_into_test_database(conn,captured,workspace_id=str(b))
    import_into_test_database(conn,captured,workspace_id=str(a))
    import_into_test_database(conn,replace(captured,workspace_id=str(b)),workspace_id=str(b))
    assert conn.execute('SELECT count(*) FROM nxtdeal.entities').fetchone()[0] == 2
    assert conn.execute('SELECT count(*) FROM nxtdeal.import_manifests').fetchone()[0] == 2


def test_concurrent_same_package_serializes_to_one_import(database,tmp_path):
    conn,dsn = database
    migrate(conn)
    target = workspace(conn)
    captured = package(tmp_path,target)
    def run(_):
        with psycopg.connect(dsn,autocommit=True) as separate:
            return import_into_test_database(separate,captured,workspace_id=str(target))['status']
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run,range(2))) == ['already_imported','imported']


@pytest.mark.parametrize('operation',['UPDATE','DELETE','TRUNCATE'])
def test_import_manifest_is_immutable(database,tmp_path,operation):
    conn,_ = database
    migrate(conn)
    target = workspace(conn)
    import_into_test_database(conn,package(tmp_path,target),workspace_id=str(target))
    query = {'UPDATE':'UPDATE nxtdeal.import_manifests SET manifest=manifest', 'DELETE':'DELETE FROM nxtdeal.import_manifests', 'TRUNCATE':'TRUNCATE nxtdeal.import_manifests'}[operation]
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        conn.execute(query)


def test_writer_rejects_non_test_database_and_ambient_transaction(database,tmp_path):
    conn,_ = database
    migrate(conn)
    target = workspace(conn)
    captured = package(tmp_path,target)
    fake = SimpleNamespace(autocommit=True,info=SimpleNamespace(transaction_status=psycopg.pq.TransactionStatus.IDLE,dbname='production'))
    with pytest.raises(ImportRejected,match='disposable_test_database_required'):
        import_into_test_database(fake,captured,workspace_id=str(target))
    with conn.transaction():
        with pytest.raises(ImportRejected,match='dedicated_idle_connection_required'):
            import_into_test_database(conn,captured,workspace_id=str(target))


def test_populated_upgrade(database,tmp_path):
    from db.migrate import MIGRATIONS
    conn,_ = database
    old = tmp_path / 'migrations'
    old.mkdir()
    for path in sorted(MIGRATIONS.glob('*.sql')):
        if path.name < '0010':
            (old / path.name).write_bytes(path.read_bytes())
    migrate(conn,old)
    target = workspace(conn)
    conn.execute("INSERT INTO nxtdeal.entities(workspace_id,id,entity_type) VALUES (%s,'existing','Customer')",(target,))
    assert migrate(conn) == ['0010_import_manifests.sql', '0011_shadow_journal.sql', '0012_shadow_projections.sql', '0013_normalized_receipts.sql']
    assert conn.execute('SELECT id FROM nxtdeal.entities').fetchall() == [('existing',)]


@pytest.mark.parametrize('with_audit',[False,True])
def test_empty_import(database,with_audit):
    from db.import_package import ImportPackage
    conn,_ = database
    migrate(conn)
    target = workspace(conn)
    captured = ImportPackage(str(target),'strict' if with_audit else 'graph_only',
        b'{"entities":[],"relationships":[]}',b'[]' if with_audit else None,None)
    assert import_into_test_database(conn,captured,workspace_id=str(target))['status'] == 'imported'
    graph,audit,_ = export_imported(conn,target)
    assert graph == {'entities':[],'relationships':[]}
    assert audit == ([] if with_audit else None)
    assert import_into_test_database(conn,captured,workspace_id=str(target))['status'] == 'already_imported'


def test_missing_workspace(database,tmp_path):
    conn,_ = database
    migrate(conn)
    target = uuid4()
    with pytest.raises(ImportRejected,match='^workspace_missing$'):
        import_into_test_database(conn,package(tmp_path,target),workspace_id=str(target))
    assert conn.execute('SELECT count(*) FROM nxtdeal.import_manifests').fetchone()[0] == 0


@pytest.mark.parametrize('assignment,expected',[
    ("NEW.action = 'synthetic-corrupted-action'",'audit_projection_failed'),
    ("NEW.actor = 'changed'",'audit_projection_failed'),
    ("NEW.occurred_at = NEW.occurred_at + interval '1 second'",'audit_projection_failed'),
    ("NEW.payload = jsonb_set(NEW.payload, '{summary}', '\"changed\"')",'audit_digest_failed'),
    ("RAISE EXCEPTION 'PRIVATE customer payload'",'database_import_failed'),
])
def test_audit_corruption_rolls_back_graph(database,tmp_path,assignment,expected):
    conn,_ = database
    migrate(conn)
    target = workspace(conn)
    conn.execute(f"""CREATE FUNCTION nxtdeal.test_corrupt_audit() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN {assignment}; RETURN NEW; END; $$;
        CREATE TRIGGER test_corrupt_audit BEFORE INSERT ON nxtdeal.audit_events
        FOR EACH ROW EXECUTE FUNCTION nxtdeal.test_corrupt_audit();""")
    with pytest.raises(ImportRejected,match=f'^{expected}$') as failure:
        import_into_test_database(conn,package(tmp_path,target),workspace_id=str(target))
    if expected == 'database_import_failed':
        assert failure.value.__suppress_context__
    for table in ('entities','relationships','audit_events','import_manifests'):
        assert conn.execute(f'SELECT count(*) FROM nxtdeal.{table}').fetchone()[0] == 0


@pytest.mark.parametrize('statement,expected',[
    ("UPDATE nxtdeal.relationships SET created_by='later' WHERE position=0",'relationship_provenance_failed'),
    ("UPDATE nxtdeal.relationships SET position=9 WHERE position=1",'relationship_order_failed'),
    ("DELETE FROM nxtdeal.relationships WHERE position=1",'relationship_parity_failed'),
    ("INSERT INTO nxtdeal.audit_events(workspace_id,action,occurred_at,payload) VALUES (%s,'later',now(),'{}')",'audit_parity_failed'),
])
def test_repeat_detects_later_changes(database,tmp_path,statement,expected):
    conn,_ = database
    migrate(conn)
    target = workspace(conn)
    captured = package(tmp_path,target)
    import_into_test_database(conn,captured,workspace_id=str(target))
    conn.execute(statement,(target,) if '%s' in statement else None)
    with pytest.raises(ImportRejected,match=f'^{expected}$'):
        import_into_test_database(conn,captured,workspace_id=str(target))


def test_manifest_rls(database,tmp_path):
    from psycopg import sql
    conn,_ = database
    migrate(conn)
    a,b,c = workspace(conn),workspace(conn),workspace(conn)
    captured = package(tmp_path,a)
    for target in (a,b):
        import_into_test_database(conn,replace(captured,workspace_id=str(target)),workspace_id=str(target))
    role = 'nxtdeal_test_' + uuid4().hex
    conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS').format(sql.Identifier(role)))
    try:
        conn.execute(sql.SQL('GRANT USAGE ON SCHEMA nxtdeal TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('GRANT SELECT, INSERT ON nxtdeal.import_manifests TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
        assert conn.execute('SELECT count(*) FROM nxtdeal.import_manifests').fetchone()[0] == 0
        with conn.transaction():
            conn.execute("SELECT set_config('nxtdeal.workspace_id',%s,true)",(str(a),))
            assert conn.execute('SELECT workspace_id FROM nxtdeal.import_manifests').fetchall() == [(a,)]
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute("INSERT INTO nxtdeal.import_manifests SELECT %s,manifest_digest,manifest,entity_order,relationship_fields,audit_order,recorded_at FROM nxtdeal.import_manifests",(c,))
        assert conn.execute('SELECT count(*) FROM nxtdeal.import_manifests').fetchone()[0] == 0
    finally:
        conn.execute('RESET ROLE')
        conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
