"""Handoff-wide guarantees checked against the actual migrated PostgreSQL catalog."""
import pytest

from db.migrate import migrate
from db.tests.test_migrations import DSN, database

pytestmark = pytest.mark.skipif(not DSN, reason='Dedicated PostgreSQL test server required')

CATALOG = {
    'organizations', 'workspaces', 'accounts', 'memberships', 'rooftops',
    'entities', 'relationships', 'events', 'audit_events',
    'credential_references', 'integrations', 'integration_mappings', 'integration_runs', 'integration_records',
    'approval_requests', 'approval_decisions', 'entitlement_revisions',
    'execution_intents', 'execution_events', 'usage_reservations', 'usage_settlements',
    'ai_model_revisions', 'ai_route_revisions', 'ai_usage_records',
    'input_snapshots', 'model_runs', 'predictions',
    'experiments', 'experiment_alternatives', 'decisions',
    'interventions', 'intervention_events', 'outcome_observations',
    'chrono_releases', 'chrono_release_checks', 'chrono_release_authorizations', 'chrono_deployments',
    'import_manifests', 'shadow_preparations', 'shadow_commits', 'shadow_projections', 'normalized_receipts',
}
CONTROL_PLANE = {'organizations', 'workspaces', 'accounts'}
MUTABLE = CONTROL_PLANE | {
    'memberships', 'rooftops', 'entities', 'relationships',
    'credential_references', 'integrations', 'integration_runs',
}


def test_full_handoff_catalog_scope_public_access_and_history_contract(database):
    conn, _ = database
    migrate(conn)
    tables = conn.execute("""SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,c.oid
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='nxtdeal' AND c.relkind='r'""").fetchall()
    assert {name for name, *_ in tables} == CATALOG
    for name, rls, forced, oid in tables:
        columns = conn.execute('SELECT attname FROM pg_attribute WHERE attrelid=%s AND attnum>0 AND NOT attisdropped', (oid,)).fetchall()
        if name not in CONTROL_PLANE:
            assert ('workspace_id',) in columns, name
            assert rls and forced, name
            policies = conn.execute('SELECT polname,polqual IS NOT NULL,polwithcheck IS NOT NULL FROM pg_policy WHERE polrelid=%s', (oid,)).fetchall()
            assert policies == [('workspace_scope', True, True)], name
        # PUBLIC must not acquire any table permission, including through defaults.
        assert conn.execute("""SELECT count(*) FROM pg_class c,
            LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a
            WHERE c.oid=%s AND a.grantee=0""", (oid,)).fetchone()[0] == 0, name
        if name not in MUTABLE:
            triggers = conn.execute("""SELECT t.tgtype FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid
                WHERE t.tgrelid=%s AND NOT t.tgisinternal AND t.tgenabled='O'
                AND p.proname='reject_history_mutation'""", (oid,)).fetchall()
            # BEFORE + DELETE + UPDATE + TRUNCATE, statement-level, on every evidence table.
            assert triggers == [(58,)], name
    assert conn.execute("""SELECT count(*) FROM pg_namespace n,
        LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a
        WHERE n.nspname='nxtdeal' AND a.grantee=0""").fetchone()[0] == 0
