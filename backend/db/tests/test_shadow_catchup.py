from uuid import uuid4

import pytest

from db import shadow_catchup
from db.shadow_catchup import catch_up_test_projections
from db.shadow_compare import ShadowRejected
from db.shadow_journal import prepare
from db.tests.test_migrations import DSN, database
from db.tests.test_shadow_journal import setup, GRAPH
from db.tests.test_shadow_projection import committed

pytestmark = pytest.mark.skipif(not DSN, reason='Disposable PostgreSQL required')


def test_bounded_catchup_and_unresolved_preparation(database):
    conn, _ = database
    workspace, op = setup(conn)
    for _ in range(3):
        committed(conn,workspace,str(uuid4()))
    prepare(conn,workspace_id=workspace,operation_id=op,graph_bytes=GRAPH)
    result = catch_up_test_projections(conn,workspace_id=workspace,batch_size=2)
    assert result == dict(observed_committed_generation=3,verified_through_generation=2,
                         processed_count=2,remaining_at_capture=1,
                         unresolved_preparation_at_capture=True,json_written=False)
    result = catch_up_test_projections(conn,workspace_id=workspace)
    assert result['processed_count'] == 1
    assert result['verified_through_generation'] == 3
    assert catch_up_test_projections(conn,workspace_id=workspace)['processed_count'] == 0
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_commits').fetchone()[0] == 3


def test_partial_failure_resumes_storage_only(database,monkeypatch):
    conn, _ = database
    workspace, _ = setup(conn)
    for _ in range(3):
        committed(conn,workspace,str(uuid4()))
    real = shadow_catchup.apply_test_projection
    def fail(connection,**args):
        if args['expected_predecessor'] == 1:
            raise ShadowRejected('injected_failure')
        return real(connection,**args)
    monkeypatch.setattr(shadow_catchup,'apply_test_projection',fail)
    with pytest.raises(ShadowRejected,match='injected_failure'):
        catch_up_test_projections(conn,workspace_id=workspace)
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_projections').fetchone()[0] == 1
    monkeypatch.setattr(shadow_catchup,'apply_test_projection',real)
    assert catch_up_test_projections(conn,workspace_id=workspace)['processed_count'] == 2


def test_new_commits_wait_for_next_capture(database,monkeypatch):
    conn, _ = database
    workspace, op = setup(conn)
    committed(conn,workspace,op)
    real = shadow_catchup.apply_test_projection
    def append(connection,**args):
        committed(connection,workspace,str(uuid4()))
        return real(connection,**args)
    monkeypatch.setattr(shadow_catchup,'apply_test_projection',append)
    result = catch_up_test_projections(conn,workspace_id=workspace)
    assert result['observed_committed_generation'] == result['verified_through_generation'] == 1
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_commits').fetchone()[0] == 2


def test_empty_and_invalid_bounds(database):
    conn, _ = database
    workspace, _ = setup(conn)
    assert catch_up_test_projections(conn,workspace_id=workspace)['verified_through_generation'] == 0
    for size in (0,101,True,1.5):
        with pytest.raises(ShadowRejected,match='invalid_catchup_batch_size'):
            catch_up_test_projections(conn,workspace_id=workspace,batch_size=size)
