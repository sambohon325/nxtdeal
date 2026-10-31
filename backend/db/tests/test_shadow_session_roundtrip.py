import os
from uuid import uuid4

import pytest

from core.entities import Entity
from core.tenant_context import TenantContext
from db.normalized_test_session import NormalizedTestSession
from db.shadow_save import save_test_snapshot
from db.shadow_projection import apply_test_projection
from db.shadow_normalized import apply_test_normalized, load_test_normalized
from db.shadow_compare import ShadowRejected
from db.tests.test_migrations import DSN, database
from db.tests.test_shadow_save import arguments, GRAPH

pytestmark = pytest.mark.skipif(not DSN or os.name != 'posix',reason='POSIX and disposable PostgreSQL required')


def normalize(conn,args,generation):
    apply_test_projection(conn,workspace_id=args['workspace_id'],operation_id=args['operation_id'],expected_predecessor=generation-1)
    apply_test_normalized(conn,workspace_id=args['workspace_id'],generation=generation)


def test_session_json_projection_normalized_roundtrip(database,tmp_path):
    conn,_ = database
    args = arguments(conn,tmp_path)
    save_test_snapshot(conn,**args,expected_generation=0)
    normalize(conn,args,1)
    session = NormalizedTestSession(TenantContext(args['workspace_id']))
    generation = session.load_from_test_database(conn)
    session.add_entity(Entity('customer-1','Customer',{'score':42}))
    captured = session.capture_snapshot()
    new = {**args,'operation_id':str(uuid4()),'graph_bytes':captured,'expected_bytes':GRAPH}
    save_test_snapshot(conn,**new,expected_generation=generation)
    normalize(conn,new,2)
    reopened = NormalizedTestSession(TenantContext(args['workspace_id']))
    assert reopened.load_from_test_database(conn) == 2
    assert reopened.get_entity('customer-1').attributes['score'] == 42
    assert (args['directory']/'graph.json').read_bytes() == captured
    # Further in-memory edits do not alter either persistence target.
    session.get_entity('customer-1').attributes['score'] = 99
    assert load_test_normalized(conn,workspace_id=args['workspace_id'])[1]['entities'][0]['attributes']['score'] == 42


def test_identical_bytes_cannot_hide_stale_generation(database,tmp_path):
    conn,_ = database
    args = arguments(conn,tmp_path)
    save_test_snapshot(conn,**args,expected_generation=0)
    args.update(operation_id=str(uuid4()),expected_bytes=GRAPH)
    save_test_snapshot(conn,**args,expected_generation=1)
    with pytest.raises(ShadowRejected,match='^stale_graph_generation$'):
        save_test_snapshot(conn,**{**args,'operation_id':str(uuid4())},expected_generation=1)
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_preparations').fetchone()[0] == 2
    assert (args['directory']/'graph.json').read_bytes() == GRAPH


def test_invalid_generation_never_prepares_or_saves(database,tmp_path):
    conn,_ = database
    args = arguments(conn,tmp_path)
    for generation in (-1,True,1.5,2**63):
        with pytest.raises(ShadowRejected,match='^invalid_predecessor$'):
            save_test_snapshot(conn,**args,expected_generation=generation)
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_preparations').fetchone()[0] == 0
    assert not (args['directory']/'graph.json').exists()
