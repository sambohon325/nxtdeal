import os
import stat
from uuid import UUID

import pytest

from db import shadow_file
from db.shadow_compare import GraphObservation, ShadowRejected
from db.shadow_file import locked_test_file

WORKSPACE = '11111111-1111-1111-1111-111111111111'
GRAPH = b'{"entities":[],"relationships":[]}'
posix = pytest.mark.skipif(os.name != 'posix', reason='POSIX durability contract')


@pytest.fixture
def directory(tmp_path):
    path = tmp_path / ('nxtdeal_shadow_test_' + UUID(WORKSPACE).hex)
    path.mkdir(mode=0o700)
    return path


def observation(data=GRAPH):
    return GraphObservation(WORKSPACE, 1, data)


def test_unsupported_platform_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow_file.os, 'name', 'nt')
    with pytest.raises(ShadowRejected, match='^unsupported_file_platform$'):
        with locked_test_file(tmp_path, WORKSPACE):
            pytest.fail('must not acquire')


@posix
def test_roundtrip_stale_check_and_reopen(directory):
    with locked_test_file(directory, WORKSPACE) as store:
        assert store.read() is None
        assert store.replace(observation(), expected_bytes=None)['generation'] == 1
        with pytest.raises(ShadowRejected, match='^stale_file_snapshot$'):
            store.replace(observation(GRAPH+b' '), expected_bytes=None)
        store.replace(observation(GRAPH+b' '), expected_bytes=GRAPH)
    with locked_test_file(directory, WORKSPACE) as reopened:
        assert reopened.read() == GRAPH+b' '
    assert stat.S_IMODE((directory / 'graph.json').stat().st_mode) == 0o600
    with pytest.raises(ShadowRejected, match='^writer_lock_required$'):
        store.read()


@posix
def test_busy_lock_and_exception_release(directory):
    with pytest.raises(RuntimeError):
        with locked_test_file(directory, WORKSPACE):
            with pytest.raises(ShadowRejected, match='^writer_busy$'):
                with locked_test_file(directory, WORKSPACE):
                    pytest.fail('second writer acquired')
            raise RuntimeError('caller failure')
    with locked_test_file(directory, WORKSPACE) as store:
        assert store.read() is None


@posix
def test_reject_scope_permissions_and_directory_symlink(directory, tmp_path):
    for path, code in ((tmp_path, 'disposable_test_directory_required'),):
        with pytest.raises(ShadowRejected, match='^'+code+'$'):
            with locked_test_file(path, WORKSPACE):
                pytest.fail('unsafe scope acquired')
    directory.chmod(0o755)
    with pytest.raises(ShadowRejected, match='^unsafe_test_file$'):
        with locked_test_file(directory, WORKSPACE):
            pytest.fail('public directory acquired')
    directory.chmod(0o700)
    elsewhere = tmp_path / 'elsewhere'
    directory.rename(elsewhere)
    directory.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ShadowRejected, match='^file_lock_failed$'):
        with locked_test_file(directory, WORKSPACE):
            pytest.fail('symlink acquired')


@posix
@pytest.mark.parametrize('name', ['graph.json', '.writer.lock'])
@pytest.mark.parametrize('link', ['symbolic', 'hard'])
def test_reject_linked_files(directory, tmp_path, name, link):
    source = tmp_path / 'private-source'
    source.write_bytes(GRAPH)
    source.chmod(0o600)
    target = directory / name
    if link == 'symbolic':
        target.symlink_to(source)
    else:
        os.link(source, target)
    with pytest.raises(ShadowRejected):
        with locked_test_file(directory, WORKSPACE) as store:
            store.replace(observation(), expected_bytes=None)
    assert source.read_bytes() == GRAPH


@posix
def test_fifo_does_not_block_reader(directory):
    os.mkfifo(directory / 'graph.json', 0o600)
    with locked_test_file(directory, WORKSPACE) as store:
        with pytest.raises(ShadowRejected, match='^unsafe_test_file$'):
            store.read()


@posix
def test_invalid_or_other_workspace_never_written(directory):
    with locked_test_file(directory, WORKSPACE) as store:
        for capture in (observation(b'PRIVATE-INVALID'),
                        GraphObservation('22222222-2222-2222-2222-222222222222', 1, GRAPH)):
            with pytest.raises(ShadowRejected) as error:
                store.replace(capture, expected_bytes=None)
            assert 'PRIVATE' not in str(error.value)
            assert store.read() is None


@posix
@pytest.mark.parametrize('failure', ['file_fsync', 'replace', 'directory_fsync'])
def test_failure_boundary_and_staging_cleanup(directory, monkeypatch, failure):
    with locked_test_file(directory, WORKSPACE) as store:
        store.replace(observation(), expected_bytes=None)
        real_sync = os.fsync
        def sync(fd):
            is_directory = stat.S_ISDIR(os.fstat(fd).st_mode)
            if (failure == 'directory_fsync' and is_directory
                    or failure == 'file_fsync' and not is_directory):
                raise OSError('PRIVATE-PATH')
            real_sync(fd)
        def replace(*args, **kwargs):
            raise OSError('PRIVATE-PATH')
        monkeypatch.setattr(shadow_file.os, 'fsync', sync)
        if failure == 'replace':
            monkeypatch.setattr(shadow_file.os, 'replace', replace)
        code = 'file_commit_uncertain' if failure == 'directory_fsync' else 'file_commit_failed'
        with pytest.raises(ShadowRejected, match='^'+code+'$'):
            store.replace(observation(GRAPH+b' '), expected_bytes=GRAPH)
        assert store.read() == (GRAPH+b' ' if failure == 'directory_fsync' else GRAPH)
        assert not list(directory.glob('.graph-*'))


@posix
def test_fsync_order_before_acknowledgement(directory, monkeypatch):
    with locked_test_file(directory, WORKSPACE) as store:
        events = []
        real_sync, real_replace = os.fsync, os.replace
        def sync(fd):
            events.append('directory_sync' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file_sync')
            real_sync(fd)
        def replace(*args, **kwargs):
            events.append('replace')
            return real_replace(*args, **kwargs)
        monkeypatch.setattr(shadow_file.os, 'fsync', sync)
        monkeypatch.setattr(shadow_file.os, 'replace', replace)
        store.replace(observation(), expected_bytes=None)
        assert events == ['file_sync', 'replace', 'directory_sync']


@posix
def test_uncertain_writer_cannot_overwrite_again_even_when_sync_recovers(directory, monkeypatch):
    with locked_test_file(directory, WORKSPACE) as store:
        store.replace(observation(), expected_bytes=None)
        real_sync = os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError('fixture directory sync failure')
            real_sync(fd)
        monkeypatch.setattr(shadow_file.os, 'fsync', fail_directory)
        changed = GRAPH + b' '
        with pytest.raises(ShadowRejected, match='^file_commit_uncertain$'):
            store.replace(observation(changed), expected_bytes=GRAPH)
        monkeypatch.setattr(shadow_file.os, 'fsync', real_sync)
        assert store.read() == changed  # Inspection is permitted, not durability proof.
        with pytest.raises(ShadowRejected, match='^file_reconciliation_required$'):
            store.replace(observation(), expected_bytes=changed)
        assert store.read() == changed
        assert not list(directory.glob('.graph-*'))
