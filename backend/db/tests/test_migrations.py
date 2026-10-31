"""Real PostgreSQL tests in disposable databases, never application storage."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from db.migrate import MIGRATIONS, migrate

DSN = os.environ.get("NXTDEAL_TEST_ADMIN_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="Dedicated PostgreSQL test server required")


@pytest.fixture
def database():
    # Only this freshly generated test database may be dropped by this fixture.
    name = "nxtdeal_test_" + uuid4().hex
    with psycopg.connect(DSN, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    dsn = psycopg.conninfo.make_conninfo(DSN, dbname=name)
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            yield conn, dsn
    finally:
        with psycopg.connect(DSN, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def seed(conn):
    organization = conn.execute("INSERT INTO nxtdeal.organizations(name) VALUES ('Test') RETURNING id").fetchone()[0]
    workspaces = [conn.execute("INSERT INTO nxtdeal.workspaces(organization_id,name) VALUES (%s,%s) RETURNING id", (organization, name)).fetchone()[0] for name in ['A', 'B']]
    for workspace in workspaces:
        conn.execute("INSERT INTO nxtdeal.entities(workspace_id,id,entity_type,attributes) VALUES (%s,'shared-id','customer',%s)", (workspace, psycopg.types.json.Jsonb({'nested': [1, None, 'unicode é']})))
    return workspaces


def test_empty_and_populated_rerun(database):
    conn, _ = database
    assert migrate(conn) == [p.name for p in sorted(MIGRATIONS.glob('*.sql'))]
    seed(conn)
    assert migrate(conn) == []
    assert conn.execute('SELECT count(*) FROM nxtdeal.entities').fetchone()[0] == 2


def test_concurrent_migration_is_serialized(database):
    _, dsn = database
    def run():
        with psycopg.connect(dsn, autocommit=True) as conn:
            return migrate(conn)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert sorted(map(len, results)) == [0, len(list(MIGRATIONS.glob('*.sql')))]


def test_checksum_and_unknown_history_fail_closed(database, tmp_path):
    conn, _ = database
    migrate(conn)
    for migration in MIGRATIONS.glob('*.sql'):
        (tmp_path / migration.name).write_bytes(migration.read_bytes())
    path = tmp_path / '0001_graph_foundation.sql'
    path.write_bytes((MIGRATIONS / path.name).read_bytes() + b'\n-- changed')
    with pytest.raises(ValueError, match='checksum'):
        migrate(conn, tmp_path)
    path.unlink()
    with pytest.raises(ValueError, match='prefix'):
        migrate(conn, tmp_path)


def test_failed_batch_rolls_back_schema_and_tracking(database, tmp_path):
    conn, _ = database
    (tmp_path / '0001_good.sql').write_text('CREATE TABLE public.should_rollback(id integer);')
    (tmp_path / '0002_bad.sql').write_text('SELECT missing_column FROM missing_table;')
    with pytest.raises(psycopg.Error):
        migrate(conn, tmp_path)
    assert conn.execute("SELECT to_regclass('public.should_rollback')").fetchone()[0] is None
    assert conn.execute("SELECT to_regclass('nxtdeal_migrations.versions')").fetchone()[0] is None


def test_relationship_scope_multiplicity_order_and_provenance(database):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    conn.execute("INSERT INTO nxtdeal.entities(workspace_id,id,entity_type) VALUES (%s,'only-b','vehicle')", (b,))
    insert = """INSERT INTO nxtdeal.relationships(workspace_id,source_id,target_id,relationship_type,position,created_at)
                VALUES (%s,'shared-id',%s,'owns',%s,'legacy timestamp')"""
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute(insert, (a, 'only-b', 0))
    conn.execute(insert, (a, 'shared-id', 0))
    conn.execute(insert, (a, 'shared-id', 1))
    assert conn.execute('SELECT position,created_at FROM nxtdeal.relationships ORDER BY position').fetchall() == [(0,'legacy timestamp'),(1,'legacy timestamp')]
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(insert, (a, 'shared-id', 1))


def test_rls_missing_wrong_and_transaction_local_context(database):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    role = 'nxtdeal_test_' + uuid4().hex
    conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS').format(sql.Identifier(role)))
    try:
        conn.execute(sql.SQL('GRANT USAGE ON SCHEMA nxtdeal TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON nxtdeal.entities TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('GRANT USAGE ON ALL SEQUENCES IN SCHEMA nxtdeal TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
        assert conn.execute('SELECT count(*) FROM nxtdeal.entities').fetchone()[0] == 0
        with conn.transaction():
            conn.execute("SELECT set_config('nxtdeal.workspace_id', %s, true)", (str(a),))
            assert conn.execute('SELECT workspace_id FROM nxtdeal.entities').fetchall() == [(a,)]
            assert conn.execute('DELETE FROM nxtdeal.entities WHERE workspace_id=%s', (b,)).rowcount == 0
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute("INSERT INTO nxtdeal.entities(workspace_id,id,entity_type) VALUES (%s,'leak','customer')", (b,))
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute('UPDATE nxtdeal.entities SET workspace_id=%s', (b,))
        assert conn.execute('SELECT count(*) FROM nxtdeal.entities').fetchone()[0] == 0
        conn.execute('RESET ROLE')
        assert conn.execute('SELECT count(*) FROM nxtdeal.entities').fetchone()[0] == 2
    finally:
        conn.execute('RESET ROLE')
        conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


@pytest.mark.parametrize('table', ['events', 'audit_events'])
@pytest.mark.parametrize('operation', ['UPDATE', 'DELETE', 'TRUNCATE'])
def test_history_rejects_mutation(database, table, operation):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    if table == 'events':
        conn.execute("INSERT INTO nxtdeal.events(workspace_id,event_type,schema_version,occurred_at,source,payload) VALUES (%s,'created',1,now(),'test','{}')", (a,))
    else:
        conn.execute("INSERT INTO nxtdeal.audit_events(workspace_id,action,occurred_at,payload) VALUES (%s,'created',now(),'{}')", (a,))
    query = {'UPDATE':f'UPDATE nxtdeal.{table} SET actor=\'changed\'', 'DELETE':f'DELETE FROM nxtdeal.{table}', 'TRUNCATE':f'TRUNCATE nxtdeal.{table} CASCADE'}[operation]
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        conn.execute(query)
    assert conn.execute(f'SELECT count(*) FROM nxtdeal.{table}').fetchone()[0] == 1


def test_event_idempotency_is_workspace_scoped(database):
    conn, _ = database
    migrate(conn)
    a,b = seed(conn)
    insert = "INSERT INTO nxtdeal.events(workspace_id,event_type,schema_version,occurred_at,source,payload,idempotency_key) VALUES (%s,'created',1,now(),'test','{}','same-key')"
    conn.execute(insert,(a,))
    conn.execute(insert,(b,))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(insert,(a,))


def connector_seed(conn, workspace, *, credential=None):
    if credential is None:
        credential = conn.execute("INSERT INTO nxtdeal.credential_references(workspace_id,secret_store,secret_reference,secret_version) VALUES (%s,'test-store',%s,'v1') RETURNING id", (workspace, uuid4().hex)).fetchone()[0]
    integration = conn.execute("INSERT INTO nxtdeal.integrations(workspace_id,name,provider,category,method,direction,cadence,credential_reference_id) VALUES (%s,'Test CSV','csv','crm','csv','inbound','manual',%s) RETURNING id", (workspace, credential)).fetchone()[0]
    conn.execute("INSERT INTO nxtdeal.integration_mappings(workspace_id,integration_id,version,entity_type,definition) VALUES (%s,%s,1,'Customer','{}')", (workspace, integration))
    run = conn.execute("INSERT INTO nxtdeal.integration_runs(workspace_id,integration_id,mapping_version,execution_mode,idempotency_key) VALUES (%s,%s,1,'mock','same-key') RETURNING id", (workspace, integration)).fetchone()[0]
    conn.execute("INSERT INTO nxtdeal.integration_records(workspace_id,integration_id,run_id,position,source_record_id,source_digest,outcome) VALUES (%s,%s,%s,0,'external-id',%s,'accepted')", (workspace, integration, run, 'a' * 64))
    return credential, integration, run


def test_upgrade_preserves_populated_graph(database, tmp_path):
    conn, _ = database
    first = MIGRATIONS / '0001_graph_foundation.sql'
    (tmp_path / first.name).write_bytes(first.read_bytes())
    migrate(conn, tmp_path)
    a, _ = seed(conn)
    before = conn.execute('SELECT workspace_id,id,attributes FROM nxtdeal.entities ORDER BY workspace_id').fetchall()
    assert migrate(conn) == [p.name for p in sorted(MIGRATIONS.glob('*.sql'))][1:]
    connector_seed(conn, a)
    assert conn.execute('SELECT workspace_id,id,attributes FROM nxtdeal.entities ORDER BY workspace_id').fetchall() == before
    assert migrate(conn) == []


def test_connector_foreign_keys_isolate_workspace_and_integration(database):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    _, ia, ra = connector_seed(conn, a)
    cb, ib, rb = connector_seed(conn, b)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        connector_seed(conn, a, credential=cb)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute("INSERT INTO nxtdeal.integration_runs(workspace_id,integration_id,mapping_version,execution_mode,idempotency_key) VALUES (%s,%s,1,'mock','cross-tenant')", (a, ib))
    _, other, _ = connector_seed(conn, a)
    for integration, run in [(ib, rb), (other, ra)]:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute("INSERT INTO nxtdeal.integration_records(workspace_id,integration_id,run_id,position,source_record_id,source_digest,outcome) VALUES (%s,%s,%s,1,'external',%s,'accepted')", (a, integration, run, 'b' * 64))
    event = conn.execute("INSERT INTO nxtdeal.events(workspace_id,event_type,schema_version,occurred_at,source,payload) VALUES (%s,'imported',1,now(),'test','{}') RETURNING id", (b,)).fetchone()[0]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute("INSERT INTO nxtdeal.integration_records(workspace_id,integration_id,run_id,position,source_record_id,source_digest,outcome,event_id) VALUES (%s,%s,%s,1,'external',%s,'accepted',%s)", (a, ia, ra, 'b' * 64, event))


def test_run_idempotency_mapping_and_status_constraints(database):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    _, integration, run = connector_seed(conn, a)
    connector_seed(conn, b)  # Same external key is valid in another workspace.
    connector_seed(conn, a)  # It is also valid for a different connector.
    insert = "INSERT INTO nxtdeal.integration_runs(workspace_id,integration_id,mapping_version,execution_mode,idempotency_key) VALUES (%s,%s,%s,'dry_run',%s)"
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(insert, (a, integration, 1, 'same-key'))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute(insert, (a, integration, 2, 'missing-mapping'))
    for assignment in ["status='succeeded'", "records_seen=1,records_accepted=1,records_rejected=1", "records_seen=-1"]:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(f'UPDATE nxtdeal.integration_runs SET {assignment} WHERE id=%s', (run,))
    conn.execute("UPDATE nxtdeal.integration_runs SET status='running',started_at=now() WHERE id=%s", (run,))
    conn.execute("UPDATE nxtdeal.integration_runs SET status='succeeded',finished_at=now(),records_seen=1,records_accepted=1 WHERE id=%s", (run,))
    assert conn.execute('SELECT execution_mode,status FROM nxtdeal.integration_runs WHERE id=%s', (run,)).fetchone() == ('mock', 'succeeded')


@pytest.mark.parametrize('table', ['integration_mappings', 'integration_records'])
@pytest.mark.parametrize('operation', ['UPDATE', 'DELETE', 'TRUNCATE'])
def test_connector_evidence_is_immutable(database, table, operation):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    connector_seed(conn, a)
    query = {'UPDATE': f'UPDATE nxtdeal.{table} SET workspace_id=workspace_id', 'DELETE': f'DELETE FROM nxtdeal.{table}', 'TRUNCATE': f'TRUNCATE nxtdeal.{table} CASCADE'}[operation]
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        conn.execute(query)
    assert conn.execute(f'SELECT count(*) FROM nxtdeal.{table}').fetchone()[0] == 1


@pytest.mark.parametrize('table', ['credential_references', 'integrations', 'integration_mappings', 'integration_runs', 'integration_records'])
def test_connector_rls_read_and_write_isolation(database, table):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    connector_seed(conn, a)
    connector_seed(conn, b)
    role = 'nxtdeal_test_' + uuid4().hex
    conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS').format(sql.Identifier(role)))
    try:
        conn.execute(sql.SQL('GRANT USAGE ON SCHEMA nxtdeal TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA nxtdeal TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
        query = sql.SQL('SELECT workspace_id FROM nxtdeal.{}').format(sql.Identifier(table))
        assert conn.execute(query).fetchall() == []
        with conn.transaction():
            conn.execute("SELECT set_config('nxtdeal.workspace_id', %s, true)", (str(a),))
            assert conn.execute(query).fetchall() == [(a,)]
            # Copy the visible row but substitute the other tenant. RLS must reject
            # before any duplicate-key/FK diagnostic can expose that tenant's data.
            columns = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='nxtdeal' AND table_name=%s ORDER BY ordinal_position", (table,)).fetchall()
            selection = sql.SQL(',').join(sql.SQL('%s::uuid') if name == 'workspace_id' else sql.Identifier(name) for (name,) in columns)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute(sql.SQL('INSERT INTO nxtdeal.{} SELECT {} FROM nxtdeal.{}').format(sql.Identifier(table), selection, sql.Identifier(table)), (b,))
        assert conn.execute(query).fetchall() == []
    finally:
        conn.execute('RESET ROLE')
        conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


def test_connector_configuration_and_record_validation(database):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    _, integration, run = connector_seed(conn, a)
    for assignment in ["cadence='scheduled'", "schedule_expression='daily'", "configuration='[]'", "method='unknown'", "direction='unknown'", "health='pretend-healthy'"]:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(f'UPDATE nxtdeal.integrations SET {assignment} WHERE id=%s', (integration,))
    conn.execute("UPDATE nxtdeal.integrations SET cadence='scheduled',schedule_expression='0 4 * * *' WHERE id=%s", (integration,))
    assert conn.execute('SELECT enabled,health FROM nxtdeal.integrations WHERE id=%s', (integration,)).fetchone() == (False, 'unknown')
    insert = "INSERT INTO nxtdeal.integration_records(workspace_id,integration_id,run_id,position,source_record_id,source_digest,outcome,error_code) VALUES (%s,%s,%s,1,'external',%s,%s,%s)"
    for digest, outcome, error in [('invalid', 'accepted', None), ('a'*64, 'rejected', None), ('a'*64, 'rejected', ' '), ('a'*64, 'unknown', None)]:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(insert, (a, integration, run, digest, outcome, error))
    conn.execute(insert, (a, integration, run, 'a'*64, 'rejected', 'INVALID_SOURCE'))
    # Repeating a source ID in an input is preserved by position, not overwritten.
    assert conn.execute('SELECT position,outcome FROM nxtdeal.integration_records WHERE run_id=%s ORDER BY position', (run,)).fetchall() == [(0, 'accepted'), (1, 'rejected')]


def test_run_identity_and_credential_rotation_preserve_history(database):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    credential, integration, run = connector_seed(conn, a)
    conn.execute("INSERT INTO nxtdeal.integration_mappings(workspace_id,integration_id,version,entity_type,definition) VALUES (%s,%s,2,'Customer','{}')", (a, integration))
    for assignment in ["mapping_version=2", "execution_mode='live'", "idempotency_key='rewritten'"]:
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            conn.execute(f'UPDATE nxtdeal.integration_runs SET {assignment} WHERE id=%s', (run,))
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        conn.execute("UPDATE nxtdeal.credential_references SET secret_version='v2' WHERE id=%s", (credential,))
    conn.execute('UPDATE nxtdeal.credential_references SET revoked_at=now() WHERE id=%s', (credential,))
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        conn.execute('UPDATE nxtdeal.credential_references SET revoked_at=NULL WHERE id=%s', (credential,))
    replacement = conn.execute("INSERT INTO nxtdeal.credential_references(workspace_id,secret_store,secret_reference,secret_version) SELECT workspace_id,secret_store,secret_reference,'v2' FROM nxtdeal.credential_references WHERE id=%s RETURNING id", (credential,)).fetchone()[0]
    conn.execute('UPDATE nxtdeal.integrations SET credential_reference_id=%s WHERE id=%s', (replacement, integration))
    assert conn.execute('SELECT count(*) FROM nxtdeal.credential_references').fetchone()[0] == 2


def governance_seed(conn, workspace):
    account = conn.execute("INSERT INTO nxtdeal.accounts(subject) VALUES (%s) RETURNING id", (uuid4().hex,)).fetchone()[0]
    conn.execute("INSERT INTO nxtdeal.memberships(workspace_id,account_id,role) VALUES (%s,%s,'ADMIN')", (workspace, account))
    request = conn.execute("""INSERT INTO nxtdeal.approval_requests(workspace_id,action_key,revision,action_type,requested_by,payload,payload_digest,policy_key,policy_revision,policy_snapshot,risk_level,expires_at,idempotency_key)
        VALUES (%s,'publish-site',1,'website.publish','test-requester','{}',%s,'publishing',1,'{}','high',now()+interval '1 hour','request-1') RETURNING id""", (workspace, 'a'*64)).fetchone()[0]
    conn.execute("""INSERT INTO nxtdeal.approval_decisions(workspace_id,request_id,sequence,decision,decided_by,authority_snapshot,reason,occurred_at,idempotency_key)
        VALUES (%s,%s,1,'approved',%s,'{}','Test approval',now(),'decision-1')""", (workspace, request, account))
    conn.execute("""INSERT INTO nxtdeal.entitlement_revisions(workspace_id,capability_key,revision,feature_level,quota_limit,quota_unit,quota_period,effective_at,granted_by,authority_snapshot,reason,idempotency_key)
        VALUES (%s,'staff.seats',1,'free',3,'seats','concurrent',now(),'test-control-plane','{}','Test entitlement','entitlement-1')""", (workspace,))
    return account, request


def test_governance_workspace_and_revision_binding(database):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    actor, request = governance_seed(conn, a)
    other_actor, other_request = governance_seed(conn, b)
    insert = """INSERT INTO nxtdeal.approval_decisions(workspace_id,request_id,sequence,decision,decided_by,authority_snapshot,reason,occurred_at,idempotency_key)
        VALUES (%s,%s,2,'revoked',%s,'{}','Changed policy',now(),'decision-2')"""
    for req, who in [(other_request, actor), (request, other_actor)]:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute(insert, (a, req, who))
    conn.execute(insert, (a, request, actor))
    # Revocation appends evidence and retains the original approval.
    assert conn.execute('SELECT decision FROM nxtdeal.approval_decisions WHERE workspace_id=%s ORDER BY sequence', (a,)).fetchall() == [('approved',), ('revoked',)]
    conn.execute("""INSERT INTO nxtdeal.approval_requests(workspace_id,action_key,revision,action_type,requested_by,payload,payload_digest,policy_key,policy_revision,policy_snapshot,risk_level,expires_at,idempotency_key)
        SELECT workspace_id,action_key,2,action_type,requested_by,'{"changed":true}',%s,policy_key,policy_revision,policy_snapshot,risk_level,expires_at,'request-2'
        FROM nxtdeal.approval_requests WHERE workspace_id=%s AND id=%s""", ('b'*64, a, request))
    assert conn.execute('SELECT count(*) FROM nxtdeal.approval_decisions WHERE workspace_id=%s AND request_id<>%s', (a, request)).fetchone()[0] == 0
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(insert, (a, request, actor))


@pytest.mark.parametrize('table', ['approval_requests','approval_decisions','entitlement_revisions'])
@pytest.mark.parametrize('operation', ['UPDATE','DELETE','TRUNCATE'])
def test_governance_history_rejects_mutation(database, table, operation):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    governance_seed(conn, a)
    query = {'UPDATE': f'UPDATE nxtdeal.{table} SET workspace_id=workspace_id', 'DELETE': f'DELETE FROM nxtdeal.{table}', 'TRUNCATE': f'TRUNCATE nxtdeal.{table} CASCADE'}[operation]
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        conn.execute(query)
    assert conn.execute(f'SELECT count(*) FROM nxtdeal.{table}').fetchone()[0] == 1


@pytest.mark.parametrize('table', ['approval_requests','approval_decisions','entitlement_revisions'])
def test_governance_rls_read_write_and_missing_context(database, table):
    conn, _ = database
    migrate(conn)
    a, b = seed(conn)
    governance_seed(conn, a)
    governance_seed(conn, b)
    role = 'nxtdeal_test_' + uuid4().hex
    conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS').format(sql.Identifier(role)))
    try:
        conn.execute(sql.SQL('GRANT USAGE ON SCHEMA nxtdeal TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA nxtdeal TO {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(role)))
        query = sql.SQL('SELECT workspace_id FROM nxtdeal.{}').format(sql.Identifier(table))
        assert conn.execute(query).fetchall() == []
        with conn.transaction():
            conn.execute("SELECT set_config('nxtdeal.workspace_id', %s, true)", (str(a),))
            assert conn.execute(query).fetchall() == [(a,)]
            columns = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='nxtdeal' AND table_name=%s ORDER BY ordinal_position", (table,)).fetchall()
            selection = sql.SQL(',').join(sql.SQL('%s::uuid') if name == 'workspace_id' else sql.Identifier(name) for (name,) in columns)
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute(sql.SQL('INSERT INTO nxtdeal.{} SELECT {} FROM nxtdeal.{}').format(sql.Identifier(table), selection, sql.Identifier(table)), (b,))
        assert conn.execute(query).fetchall() == []
    finally:
        conn.execute('RESET ROLE')
        conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
        conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


def test_entitlement_zero_unlimited_disabled_and_revision_uniqueness(database):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    governance_seed(conn, a)
    assert conn.execute('SELECT enabled,quota_limit FROM nxtdeal.entitlement_revisions').fetchone() == (False, 3)
    insert = """INSERT INTO nxtdeal.entitlement_revisions(workspace_id,capability_key,revision,enabled,feature_level,quota_limit,quota_unit,quota_period,effective_at,granted_by,authority_snapshot,reason,idempotency_key)
        VALUES (%s,'staff.seats',%s,true,'professional',%s,'seats','concurrent',now(),'test','{}','Test change',%s)"""
    conn.execute(insert, (a, 2, 0, 'entitlement-2'))
    conn.execute(insert, (a, 3, None, 'entitlement-3'))
    assert conn.execute('SELECT quota_limit FROM nxtdeal.entitlement_revisions ORDER BY revision').fetchall() == [(3,), (0,), (None,)]
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(insert, (a, 3, 1, 'duplicate-revision'))
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(insert, (a, 4, 1, 'entitlement-3'))
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(insert, (a, 4, -1, 'invalid-limit'))


@pytest.mark.parametrize('change', ["expires_at=created_at", "revision=0", "payload_digest='invalid'", "payload='[]'::jsonb", "policy_revision=0", "risk_level='unknown'"])
def test_approval_request_rejects_invalid_evidence(database, change):
    conn, _ = database
    migrate(conn)
    a, _ = seed(conn)
    governance_seed(conn, a)
    columns = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='nxtdeal' AND table_name='approval_requests' ORDER BY ordinal_position").fetchall()
    changed, expression = change.split('=', 1)
    selection = sql.SQL(',').join(sql.SQL(expression) if name == changed else sql.SQL('gen_random_uuid()') if name == 'id' else sql.SQL("'new-request'") if name in ('action_key','idempotency_key') else sql.Identifier(name) for (name,) in columns)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(sql.SQL('INSERT INTO nxtdeal.approval_requests SELECT {} FROM nxtdeal.approval_requests').format(selection))


def test_governance_upgrade_preserves_connector_evidence(database, tmp_path):
    conn, _ = database
    for name in ['0001_graph_foundation.sql', '0002_connector_foundation.sql']:
        (tmp_path / name).write_bytes((MIGRATIONS / name).read_bytes())
    migrate(conn, tmp_path)
    a, _ = seed(conn)
    connector_seed(conn, a)
    before = conn.execute('SELECT * FROM nxtdeal.integration_records').fetchall()
    assert migrate(conn) == [p.name for p in sorted(MIGRATIONS.glob('*.sql'))][2:]
    governance_seed(conn, a)
    assert conn.execute('SELECT * FROM nxtdeal.integration_records').fetchall() == before
    assert migrate(conn) == []
