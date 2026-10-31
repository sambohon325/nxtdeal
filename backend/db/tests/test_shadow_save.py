import os
from uuid import UUID, uuid4

import pytest

from db import shadow_save
from db.shadow_compare import ShadowRejected
from db.shadow_journal import inspect_recovery
from db.shadow_save import save_test_snapshot
from db.tests.test_migrations import DSN, database
from db.tests.test_shadow_journal import setup, GRAPH

pytestmark = pytest.mark.skipif(not DSN or os.name != 'posix',
                                reason='POSIX and disposable PostgreSQL required')


def arguments(conn, tmp_path):
    workspace, operation = setup(conn)
    directory = tmp_path / ('nxtdeal_shadow_test_' + UUID(workspace).hex)
    directory.mkdir(mode=0o700)
    return dict(directory=directory, workspace_id=workspace, operation_id=operation,
                graph_bytes=GRAPH, expected_bytes=None)


def test_save_generations_and_no_operation_replay(database, tmp_path):
    conn, _ = database
    args = arguments(conn, tmp_path)
    result = save_test_snapshot(conn, **args)
    assert result['generation'] == 1
    assert result['postgres_graph_applied'] is False
    args['expected_bytes'] = GRAPH
    with pytest.raises(ShadowRejected, match='^operation_already_prepared$'):
        save_test_snapshot(conn, **args)
    args['operation_id'] = str(uuid4())
    assert save_test_snapshot(conn, **args)['generation'] == 2
    assert (args['directory'] / 'graph.json').read_bytes() == GRAPH


def test_stale_capture_does_not_prepare(database, tmp_path):
    conn, _ = database
    args = arguments(conn, tmp_path)
    with pytest.raises(ShadowRejected, match='^stale_file_snapshot$'):
        save_test_snapshot(conn, **{**args, 'expected_bytes': GRAPH})
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_preparations').fetchone()[0] == 0


def test_writer_lock_held_through_receipt(database, tmp_path, monkeypatch):
    from db.shadow_file import locked_test_file
    conn, _ = database
    args = arguments(conn, tmp_path)
    real_record = shadow_save.record_json_commit
    def record(*a, **kw):
        with pytest.raises(ShadowRejected, match='^writer_busy$'):
            with locked_test_file(args['directory'], args['workspace_id']):
                pytest.fail('lock released before receipt')
        return real_record(*a, **kw)
    monkeypatch.setattr(shadow_save, 'record_json_commit', record)
    save_test_snapshot(conn, **args)


def test_external_file_change_cannot_extend_journal(database, tmp_path):
    conn, _ = database
    args = arguments(conn, tmp_path)
    save_test_snapshot(conn, **args)
    (args['directory'] / 'graph.json').write_bytes(GRAPH+b' ')
    with pytest.raises(ShadowRejected, match='^authoritative_predecessor_mismatch$'):
        save_test_snapshot(conn, **{**args, 'operation_id': str(uuid4()), 'expected_bytes': GRAPH+b' '})
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_preparations').fetchone()[0] == 1


@pytest.mark.parametrize('stage', ['before_replace', 'after_replace', 'after_receipt'])
def test_interruption_never_promotes_matching_bytes(database, tmp_path, monkeypatch, stage):
    conn, _ = database
    args = arguments(conn, tmp_path)
    if stage == 'before_replace':
        from db.shadow_file import _LockedFile
        def fail(*a, **kw):
            raise ShadowRejected('file_commit_failed')
        monkeypatch.setattr(_LockedFile, 'replace', fail)
    else:
        real_record = shadow_save.record_json_commit
        def fail(*a, **kw):
            if stage == 'after_receipt':
                real_record(*a, **kw)
            raise ShadowRejected('journal_database_failed')
        monkeypatch.setattr(shadow_save, 'record_json_commit', fail)
    with pytest.raises(ShadowRejected):
        save_test_snapshot(conn, **args)
    observed = None if stage == 'before_replace' else GRAPH
    report = inspect_recovery(conn, workspace_id=args['workspace_id'],
                              operation_id=args['operation_id'], observed_graph_bytes=observed)
    assert report['status'] == ('commit_recorded' if stage == 'after_receipt' else 'prepared_unresolved')
    with pytest.raises(ShadowRejected, match='^operation_already_prepared$'):
        save_test_snapshot(conn, **{**args, 'expected_bytes': observed})
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_preparations').fetchone()[0] == 1


def test_directory_sync_failure_stays_unresolved_after_reopen(database, tmp_path, monkeypatch):
    import stat
    from db import shadow_file
    conn, _ = database
    args = arguments(conn, tmp_path)
    real_sync = os.fsync
    directory_syncs = 0
    def fail_commit_sync(fd):
        nonlocal directory_syncs
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            directory_syncs += 1
            # Permit lock acquisition's support check, fail commit acknowledgement.
            if directory_syncs == 2:
                raise OSError('fixture directory sync failure')
        real_sync(fd)
    monkeypatch.setattr(shadow_file.os, 'fsync', fail_commit_sync)
    with pytest.raises(ShadowRejected, match='^file_commit_uncertain$'):
        save_test_snapshot(conn, **args)
    monkeypatch.setattr(shadow_file.os, 'fsync', real_sync)
    observed = (args['directory'] / 'graph.json').read_bytes()
    assert observed == GRAPH
    report = inspect_recovery(conn, workspace_id=args['workspace_id'],
                              operation_id=args['operation_id'], observed_graph_bytes=observed)
    assert report['status'] == 'prepared_unresolved'
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_commits').fetchone()[0] == 0
    # A new lock and operation ID cannot bypass the durable unresolved journal.
    with pytest.raises(ShadowRejected, match='pending_predecessor'):
        save_test_snapshot(conn, **{**args, 'operation_id':str(uuid4()), 'expected_bytes':observed})
    assert conn.execute('SELECT count(*) FROM nxtdeal.shadow_preparations').fetchone()[0] == 1
    assert (args['directory'] / 'graph.json').read_bytes() == observed
