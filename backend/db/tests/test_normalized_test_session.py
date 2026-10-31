from decimal import Decimal

import pytest

from core.entities import Entity
from core.tenant_context import TenantContext
from db.normalized_test_session import NormalizedTestSession
from db.shadow_compare import ShadowRejected
from db.shadow_normalized import apply_test_normalized, load_test_normalized
from db.tests.test_migrations import DSN, database
from db.tests.test_shadow_journal import setup
from db.tests.test_shadow_normalized import project, DATA

pytestmark = pytest.mark.skipif(not DSN,reason='Disposable PostgreSQL required')


def ready(conn):
    workspace,_ = setup(conn)
    project(conn,workspace,DATA,1)
    apply_test_normalized(conn,workspace_id=workspace,generation=1)
    return workspace


def test_live_mutation_and_detached_immutable_capture(database):
    conn,_ = database
    workspace = ready(conn)
    session = NormalizedTestSession(TenantContext(workspace))
    assert session.load_from_test_database(conn) == 1
    entity = session.get_entity('a')
    assert session.get_all()['a'] is entity
    assert entity.attributes['price'] == Decimal('1.234567890123456789')
    captured = session.capture_snapshot()
    entity.attributes['price'] = 42
    assert session.capture_snapshot() != captured
    assert session.get_entity_relationships('a')[0] is session.get_relationships()[0]
    session.get_relationships().append(session.get_relationships()[0])
    assert len(session.get_entity_relationships('b')) == 3
    _, persisted = load_test_normalized(conn,workspace_id=workspace)
    assert persisted['entities'][0]['attributes']['price'] == Decimal('1.234567890123456789')
    assert len(persisted['relationships']) == 2


def test_merge_append_reset_and_session_isolation(database):
    conn,_ = database
    workspace = ready(conn)
    one = NormalizedTestSession(TenantContext(workspace))
    two = NormalizedTestSession(TenantContext(workspace))
    one.add_entity(Entity('local','Customer',{}))
    one.load_from_test_database(conn)
    one.load_from_test_database(conn)
    two.load_from_test_database(conn)
    assert list(one.get_all()) == ['local','a','b']
    assert len(one.get_relationships()) == 4
    one.reset()
    assert one.get_all() == {}
    assert list(two.get_all()) == ['a','b']


def test_runtime_paths_fail_closed_and_missing_snapshot(database,tmp_path):
    conn,_ = database
    workspace,_ = setup(conn)
    session = NormalizedTestSession(TenantContext(workspace))
    with pytest.raises(ShadowRejected,match='normalized_snapshot_missing'):
        session.load_from_test_database(conn)
    for method in (session.save,session.load):
        with pytest.raises(ShadowRejected,match='runtime_.*_disabled'):
            method(str(tmp_path/'graph.json'))
    assert not (tmp_path/'graph.json').exists()


@pytest.mark.parametrize('statement', [
    "UPDATE nxtdeal.entities SET attributes='{}' WHERE id='a'",
    "UPDATE nxtdeal.entities SET entity_type='Vehicle' WHERE id='a'",
    "DELETE FROM nxtdeal.relationships WHERE position=1",
    "UPDATE nxtdeal.relationships SET relationship_type='changed' WHERE position=0",
])
def test_corrupted_reload_preserves_existing_live_session(database, statement):
    conn, _ = database
    workspace = ready(conn)
    session = NormalizedTestSession(TenantContext(workspace))
    assert session.load_from_test_database(conn) == 1
    customer = session.get_entity('a')
    customer.attributes['local_edit'] = 'unsaved'
    links = list(session.get_relationships())
    before = session.capture_snapshot()
    conn.execute(statement)

    with pytest.raises(ShadowRejected, match='^normalized_parity_failed$'):
        session.load_from_test_database(conn)

    assert session.get_entity('a') is customer
    assert session.capture_snapshot() == before
    assert all(actual is prior for actual, prior in zip(session.get_relationships(), links))
    assert len(session.get_relationships()) == len(links)
    # Detection never repairs the database or invents a new receipt.
    assert conn.execute('SELECT max(generation) FROM nxtdeal.normalized_receipts').fetchone()[0] == 1
