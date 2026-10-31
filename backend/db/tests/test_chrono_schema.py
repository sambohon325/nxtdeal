from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from db.migrate import MIGRATIONS, migrate
from db.tests.test_migrations import DSN, database, seed, governance_seed
from db.tests.test_execution_usage import clone

pytestmark = pytest.mark.skipif(not DSN, reason='Dedicated PostgreSQL test server required')
TABLES = ['chrono_releases','chrono_release_checks','chrono_release_authorizations','chrono_deployments']


def release_seed(conn, workspace):
    _, request = governance_seed(conn, workspace)
    release = conn.execute("""INSERT INTO nxtdeal.chrono_releases
        (workspace_id,engine_version,adapter_version,contract_version,artifact_reference,artifact_digest,configuration,configuration_digest,changelog_reference,idempotency_key)
        VALUES (%s,'test','test','test','fixture',%s,'{}',%s,'fixture','release-1') RETURNING id""", (workspace,'a'*64,'b'*64)).fetchone()[0]
    check = conn.execute("""INSERT INTO nxtdeal.chrono_release_checks
        (workspace_id,release_id,outcome,compatibility_passed,staging_passed,automotive_regression_passed,suite_version,evidence_reference,evidence_digest,started_at,completed_at,idempotency_key)
        VALUES (%s,%s,'passed',true,true,true,'test','fixture',%s,now(),now(),'check-1') RETURNING id""", (workspace,release,'c'*64)).fetchone()[0]
    authorization = conn.execute("""INSERT INTO nxtdeal.chrono_release_authorizations
        (workspace_id,release_id,check_id,request_id,approval_sequence)
        VALUES (%s,%s,%s,%s,1) RETURNING id""", (workspace,release,check,request)).fetchone()[0]
    deployment = conn.execute("""INSERT INTO nxtdeal.chrono_deployments
        (workspace_id,release_id,authorization_id,action,outcome,actor,evidence_reference,started_at,completed_at,idempotency_key)
        VALUES (%s,%s,%s,'install','succeeded','test','fixture',now(),now(),'deploy-1') RETURNING id""", (workspace,release,authorization)).fetchone()[0]
    return release, check, authorization, deployment


def test_release_upgrade_preserves_graph(database, tmp_path):
    conn, _ = database
    for path in sorted(MIGRATIONS.glob('*.sql'))[:8]:
        (tmp_path / path.name).write_bytes(path.read_bytes())
    migrate(conn, tmp_path)
    a, _ = seed(conn)
    before = conn.execute('SELECT * FROM nxtdeal.entities ORDER BY workspace_id').fetchall()
    assert migrate(conn) == [p.name for p in sorted(MIGRATIONS.glob('*.sql'))][8:]
    release_seed(conn, a)
    assert conn.execute('SELECT * FROM nxtdeal.entities ORDER BY workspace_id').fetchall() == before
    assert migrate(conn) == []


def test_release_authorization_rejects_failed_checks_and_wrong_bundle(database):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    release_seed(conn, a)
    failed = uuid4()
    clone(conn, 'chrono_release_checks', {'id':f"'{failed}'::uuid", 'idempotency_key':"'failed'", 'outcome':"'failed'", 'staging_passed':'false'})
    request = uuid4()
    clone(conn, 'approval_requests', {'id':f"'{request}'::uuid", 'action_key':"'other-release'", 'idempotency_key':"'other-request'"})
    clone(conn, 'approval_decisions', {'request_id':f"'{request}'::uuid", 'idempotency_key':"'other-approval'"})
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'chrono_deployments', {'id':'gen_random_uuid()', 'idempotency_key':"'bad'", 'release_id':'gen_random_uuid()'})
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute("""INSERT INTO nxtdeal.chrono_release_authorizations
            (workspace_id,release_id,check_id,request_id,approval_sequence)
            SELECT workspace_id,release_id,%s,%s,1 FROM nxtdeal.chrono_release_checks LIMIT 1""", (failed, request))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'chrono_deployments', {'id':'gen_random_uuid()', 'idempotency_key':"'missing-approval'", 'authorization_id':'gen_random_uuid()'})


def test_rollback_pins_previously_successful_bundle(database):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    _, _, _, original = release_seed(conn, a)
    clone(conn, 'chrono_deployments', {'id':'gen_random_uuid()', 'idempotency_key':"'rollback'", 'action':"'rollback'", 'rollback_target_id':f"'{original}'::uuid"})
    failed = uuid4()
    clone(conn, 'chrono_deployments', {'id':f"'{failed}'::uuid", 'idempotency_key':"'failed'", 'outcome':"'failed'", 'action':"'install'", 'rollback_target_id':'NULL'})
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, 'chrono_deployments', {'id':'gen_random_uuid()', 'idempotency_key':"'bad-rollback'", 'action':"'rollback'", 'rollback_target_id':f"'{failed}'::uuid"})


@pytest.mark.parametrize('table', TABLES[1:])
def test_release_references_are_workspace_bound(database, table):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    release_seed(conn, a)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        clone(conn, table, {'workspace_id':f"'{b}'::uuid"})
    release_seed(conn, b)


@pytest.mark.parametrize('table,changes', [
    ('chrono_releases', {'artifact_digest':"'invalid'"}),
    ('chrono_release_checks', {'compatibility_passed':'false'}),
    ('chrono_release_authorizations', {'approval_state':"'rejected'"}),
    ('chrono_deployments', {'action':"'rollback'"}),
    ('chrono_deployments', {'completed_at':'NULL'}),
])
def test_release_invalid_evidence(database, table, changes):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    release_seed(conn, a)
    with pytest.raises(psycopg.errors.CheckViolation):
        clone(conn, table, {'id':'gen_random_uuid()', 'idempotency_key':"'bad'", **changes})
@pytest.mark.parametrize('table', TABLES)
@pytest.mark.parametrize('operation', ['UPDATE','DELETE','TRUNCATE'])
def test_release_history_is_immutable(database, table, operation):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    release_seed(conn, a)
    statement = {'UPDATE':f'UPDATE nxtdeal.{table} SET workspace_id=workspace_id', 'DELETE':f'DELETE FROM nxtdeal.{table}', 'TRUNCATE':f'TRUNCATE nxtdeal.{table} CASCADE'}[operation]
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        conn.execute(statement)
    assert conn.execute(f'SELECT count(*) FROM nxtdeal.{table}').fetchone()[0] == 1


@pytest.mark.parametrize('table', TABLES)
def test_release_rls_and_transaction_reset(database, table):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    release_seed(conn, a)
    release_seed(conn, b)
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



