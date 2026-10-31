from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import psycopg
from psycopg import sql
import pytest

from db.shadow_normalized import apply_test_normalized
from db.shadow_projection import apply_test_projection
from db.shadow_compare import ShadowRejected
from db.tests.test_migrations import DSN, database
from db.tests.test_shadow_journal import setup, GRAPH
from db.tests.test_shadow_projection import committed
from db.tests.test_import_writer import workspace as create_workspace

pytestmark = pytest.mark.skipif(not DSN,reason='Disposable PostgreSQL required')
DATA = b'{"entities":[{"id":"a","entity_type":"Customer","attributes":{"price":1.234567890123456789}},{"id":"b","entity_type":"Vehicle","attributes":{}}],"relationships":[{"source_id":"a","target_id":"b","relationship_type":"owns"},{"source_id":"a","target_id":"b","relationship_type":"owns","created_by":null}]}'


def project(conn,workspace,data,generation):
    op = str(uuid4())
    committed(conn,workspace,op,data)
    apply_test_projection(conn,workspace_id=workspace,operation_id=op,expected_predecessor=generation-1)


def test_normalized_evolution_identity_duplicates_and_delete(database):
    conn,_ = database
    workspace,_ = setup(conn)
    project(conn,workspace,DATA,1)
    assert apply_test_normalized(conn,workspace_id=workspace,generation=1)['status'] == 'applied'
    internal = conn.execute("SELECT internal_id,created_at FROM nxtdeal.entities WHERE id='a'").fetchone()
    assert conn.execute('SELECT count(*) FROM nxtdeal.relationships').fetchone()[0] == 2
    project(conn,workspace,DATA.replace(b'1.234567890123456789',b'2.234567890123456789'),2)
    apply_test_normalized(conn,workspace_id=workspace,generation=2)
    assert conn.execute("SELECT internal_id,created_at FROM nxtdeal.entities WHERE id='a'").fetchone() == internal
    assert apply_test_normalized(conn,workspace_id=workspace,generation=2)['status'] == 'already_applied'
    project(conn,workspace,GRAPH,3)
    apply_test_normalized(conn,workspace_id=workspace,generation=3)
    assert conn.execute('SELECT count(*) FROM nxtdeal.entities').fetchone()[0] == 0
    assert conn.execute('SELECT count(*) FROM nxtdeal.relationships').fetchone()[0] == 0


def test_skip_and_external_drift_rejected(database):
    conn,_ = database
    workspace,_ = setup(conn)
    project(conn,workspace,DATA,1)
    project(conn,workspace,GRAPH,2)
    with pytest.raises(ShadowRejected,match='normalized_predecessor_mismatch'):
        apply_test_normalized(conn,workspace_id=workspace,generation=2)
    apply_test_normalized(conn,workspace_id=workspace,generation=1)
    conn.execute("UPDATE nxtdeal.entities SET attributes='{}'")
    with pytest.raises(ShadowRejected,match='normalized_parity_failed'):
        apply_test_normalized(conn,workspace_id=workspace,generation=2)
    assert conn.execute('SELECT max(generation) FROM nxtdeal.normalized_receipts').fetchone()[0] == 1


def test_corrupted_write_rolls_back_all_tables(database):
    conn,_ = database
    workspace,_ = setup(conn)
    project(conn,workspace,GRAPH,1)
    apply_test_normalized(conn,workspace_id=workspace,generation=1)
    project(conn,workspace,DATA,2)
    conn.execute("CREATE FUNCTION nxtdeal.break_entity() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN NEW.attributes='{}'; RETURN NEW; END $$")
    conn.execute('CREATE TRIGGER break_entity BEFORE INSERT ON nxtdeal.entities FOR EACH ROW EXECUTE FUNCTION nxtdeal.break_entity()')
    with pytest.raises(ShadowRejected,match='normalized_parity_failed'):
        apply_test_normalized(conn,workspace_id=workspace,generation=2)
    assert conn.execute('SELECT count(*) FROM nxtdeal.entities').fetchone()[0] == 0
    assert conn.execute('SELECT count(*) FROM nxtdeal.relationships').fetchone()[0] == 0
    assert conn.execute('SELECT max(generation) FROM nxtdeal.normalized_receipts').fetchone()[0] == 1


def test_suppressed_receipt_rolls_back_then_retries(database):
    conn,_ = database
    workspace,_ = setup(conn)
    project(conn,workspace,DATA,1)
    conn.execute('CREATE FUNCTION nxtdeal.drop_receipt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$')
    conn.execute('CREATE TRIGGER drop_receipt BEFORE INSERT ON nxtdeal.normalized_receipts FOR EACH ROW EXECUTE FUNCTION nxtdeal.drop_receipt()')
    with pytest.raises(ShadowRejected,match='^normalized_receipt_missing$'):
        apply_test_normalized(conn,workspace_id=workspace,generation=1)
    for table in ('entities','relationships','normalized_receipts'):
        assert conn.execute(sql.SQL('SELECT count(*) FROM nxtdeal.{}').format(sql.Identifier(table))).fetchone()[0] == 0
    conn.execute('DROP TRIGGER drop_receipt ON nxtdeal.normalized_receipts')
    assert apply_test_normalized(conn,workspace_id=workspace,generation=1)['status'] == 'applied'


def test_concurrent_reconnect_replay(database):
    conn,dsn = database
    workspace,_ = setup(conn)
    project(conn,workspace,DATA,1)
    def run(_):
        with psycopg.connect(dsn,autocommit=True) as fresh:
            return apply_test_normalized(fresh,workspace_id=workspace,generation=1)['status']
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run,range(2))) == ['already_applied','applied']
    assert conn.execute('SELECT count(*) FROM nxtdeal.normalized_receipts').fetchone()[0] == 1


def test_two_tenants_shared_ids_and_delete_isolation(database):
    conn,_ = database
    a,_ = setup(conn)
    b = str(create_workspace(conn))
    for target in (a,b):
        project(conn,target,DATA,1)
        apply_test_normalized(conn,workspace_id=target,generation=1)
    before = conn.execute('SELECT id,internal_id,attributes::text FROM nxtdeal.entities WHERE workspace_id=%s ORDER BY id',(b,)).fetchall()
    project(conn,a,GRAPH,2)
    apply_test_normalized(conn,workspace_id=a,generation=2)
    assert conn.execute('SELECT count(*) FROM nxtdeal.entities WHERE workspace_id=%s',(a,)).fetchone()[0] == 0
    assert conn.execute('SELECT id,internal_id,attributes::text FROM nxtdeal.entities WHERE workspace_id=%s ORDER BY id',(b,)).fetchall() == before
    assert conn.execute('SELECT count(*) FROM nxtdeal.relationships WHERE workspace_id=%s',(b,)).fetchone()[0] == 2
    assert apply_test_normalized(conn,workspace_id=b,generation=1)['status'] == 'already_applied'


def test_imported_target_remains_unchanged(database):
    from db.import_package import ImportPackage
    from db.import_writer import import_into_test_database
    conn,_ = database
    workspace,_ = setup(conn)
    import_into_test_database(conn,ImportPackage(workspace,'graph_only',DATA),workspace_id=workspace)
    project(conn,workspace,GRAPH,1)
    with pytest.raises(ShadowRejected,match='^imported_workspace_requires_handoff$'):
        apply_test_normalized(conn,workspace_id=workspace,generation=1)
    assert conn.execute('SELECT count(*) FROM nxtdeal.entities').fetchone()[0] == 2


def test_receipt_scope_and_immutability(database):
    conn,_ = database
    a,_ = setup(conn)
    project(conn,a,DATA,1)
    apply_test_normalized(conn,workspace_id=a,generation=1)
    for statement in ('UPDATE nxtdeal.normalized_receipts SET generation=generation',
                      'DELETE FROM nxtdeal.normalized_receipts','TRUNCATE nxtdeal.normalized_receipts'):
        with pytest.raises(psycopg.Error):
            conn.execute(statement)
    role = 'nxtdeal_test_' + uuid4().hex
    conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS').format(sql.Identifier(role)))
    try:
        conn.execute(sql.SQL('GRANT USAGE ON SCHEMA nxtdeal TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('GRANT SELECT,INSERT ON nxtdeal.normalized_receipts TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
        assert conn.execute('SELECT count(*) FROM nxtdeal.normalized_receipts').fetchone()[0] == 0
        with conn.transaction():
            conn.execute("SELECT set_config('nxtdeal.workspace_id',%s,true)",(a,))
            assert conn.execute('SELECT count(*) FROM nxtdeal.normalized_receipts').fetchone()[0] == 1
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute('INSERT INTO nxtdeal.normalized_receipts VALUES (%s,1)',(uuid4(),))
        assert conn.execute('SELECT count(*) FROM nxtdeal.normalized_receipts').fetchone()[0] == 0
    finally:
        conn.execute('RESET ROLE')
        conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
