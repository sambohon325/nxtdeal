"""Kill real writers at acknowledged boundaries; never touch application storage."""
import multiprocessing
import os
import signal
from uuid import uuid4

import psycopg
import pytest

from db.shadow_compare import ShadowRejected
from db.shadow_file import locked_test_file
from db.shadow_journal import inspect_recovery
from db.shadow_save import save_test_snapshot
from db.tests.test_migrations import DSN, database
from db.tests.test_shadow_save import arguments, GRAPH

pytestmark = pytest.mark.skipif(not DSN or os.name != 'posix',
                                reason='POSIX process kill and disposable PostgreSQL required')


def interrupted_writer(dsn, args, stage, channel):
    # Spawn gives the child its own DB connection and file descriptors. Only
    # tests inject these hooks; no fault switches exist in application code.
    from db import shadow_save, shadow_file
    def pause_after(original):
        def wrapped(*a, **kw):
            result = original(*a, **kw)
            channel.send('boundary_reached')
            channel.recv()  # Parent kills us; no Python cleanup runs.
            return result
        return wrapped
    if stage == 'prepared':
        shadow_save.prepare = pause_after(shadow_save.prepare)
    elif stage == 'replaced_before_directory_sync':
        shadow_file.os.replace = pause_after(shadow_file.os.replace)
    elif stage == 'file_durable':
        shadow_file._LockedFile.replace = pause_after(shadow_file._LockedFile.replace)
    elif stage == 'receipt_committed':
        shadow_save.record_json_commit = pause_after(shadow_save.record_json_commit)
    with psycopg.connect(dsn, autocommit=True) as connection:
        save_test_snapshot(connection, **args)


@pytest.mark.parametrize('stage', ['prepared', 'replaced_before_directory_sync',
                                  'file_durable', 'receipt_committed'])
@pytest.mark.parametrize('identical', [False, True])
def test_killed_writer_reconnects_without_inferred_commit(database, tmp_path, stage, identical):
    conn, dsn = database
    args = arguments(conn, tmp_path)
    save_test_snapshot(conn, **args)
    snapshot = GRAPH if identical else GRAPH+b' '
    args.update(operation_id=str(uuid4()), graph_bytes=snapshot, expected_bytes=GRAPH)
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=interrupted_writer, args=(dsn, args, stage, child))
    process.start()
    child.close()
    try:
        assert parent.poll(30), 'writer did not reach crash boundary'
        assert parent.recv() == 'boundary_reached'
        # A separate process still owns the lock until killed.
        with pytest.raises(ShadowRejected, match='^writer_busy$'):
            with locked_test_file(args['directory'], args['workspace_id']):
                pytest.fail('writer lost lock before crash')
        process.kill()
        process.join(10)
        assert process.exitcode == -signal.SIGKILL
    finally:
        if process.is_alive():
            process.kill()
            process.join(10)
        parent.close()
        if not process.is_alive():
            process.close()

    # Fresh handles verify OS lock release and database reconnect after death.
    with psycopg.connect(dsn, autocommit=True) as reopened:
        with locked_test_file(args['directory'], args['workspace_id']) as store:
            observed = store.read()
            assert observed == (GRAPH if stage == 'prepared' else snapshot)
            report = inspect_recovery(reopened, workspace_id=args['workspace_id'],
                                      operation_id=args['operation_id'], observed_graph_bytes=observed)
        committed = stage == 'receipt_committed'
        assert report['generation'] == report['latest_generation'] == 2
        assert report['status'] == ('commit_recorded' if committed else 'prepared_unresolved')
        assert report['database_written'] is False
        if identical:
            assert report['matches_prepared_bytes'] is True
            assert report['matches_predecessor_bytes'] is True
        assert reopened.execute('SELECT count(*) FROM nxtdeal.shadow_commits').fetchone()[0] == (2 if committed else 1)
        with pytest.raises(ShadowRejected, match='^operation_already_prepared$'):
            save_test_snapshot(reopened, **{**args, 'expected_bytes': observed})
        next_args = {**args, 'operation_id': str(uuid4()), 'expected_bytes': observed}
        if committed:
            assert save_test_snapshot(reopened, **next_args)['generation'] == 3
        else:
            with pytest.raises(ShadowRejected, match='^pending_predecessor$'):
                save_test_snapshot(reopened, **next_args)
        assert (args['directory'] / 'graph.json').read_bytes() == observed
