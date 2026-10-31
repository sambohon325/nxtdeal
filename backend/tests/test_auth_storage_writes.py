import json
import os
from types import SimpleNamespace
import pytest
from core import auth_storage

@pytest.fixture
def store(monkeypatch):
    monkeypatch.delenv('DEALEROS_DEMO', raising=False)
    value = SimpleNamespace(credentials={'synthetic': {'mfa_version': 2}})
    monkeypatch.setattr(auth_storage, 'credential_store', value)
    return value

def test_sync_precedes_replace_with_unique_private_temp(store, monkeypatch, tmp_path):
    target = tmp_path / 'credentials.json'
    paths, events = [], []
    original_replace, original_sync = os.replace, os.fsync
    def sync(fd):
        events.append('sync')
        return original_sync(fd)
    def replace(source, destination):
        events.append('replace')
        paths.append(source)
        assert os.path.dirname(source) == str(tmp_path)
        with open(source, encoding='utf-8') as f:
            assert json.load(f) == store.credentials
        if os.name == 'posix':
            assert os.stat(source).st_mode & 0o077 == 0
        return original_replace(source, destination)
    monkeypatch.setattr(auth_storage.os, 'fsync', sync)
    monkeypatch.setattr(auth_storage.os, 'replace', replace)
    monkeypatch.setattr(auth_storage, '_sync_parent_directory', lambda path: events.append('directory-sync'))
    auth_storage.save_credentials(target)
    auth_storage.save_credentials(target)
    assert events == ['sync', 'replace', 'directory-sync', 'sync', 'replace', 'directory-sync']
    assert paths[0] != paths[1]
    assert list(tmp_path.iterdir()) == [target]

@pytest.mark.parametrize('failure', ['serialize', 'sync', 'replace'])
def test_failed_save_preserves_prior_file_and_cleans_temp(store, monkeypatch, tmp_path, failure):
    target = tmp_path / 'credentials.json'
    target.write_text('{"previous": {}}', encoding='utf-8')
    prior = target.read_bytes()
    def fail(*args, **kwargs):
        raise OSError('synthetic failure')
    if failure == 'serialize':
        monkeypatch.setattr(auth_storage.json, 'dump', fail)
    else:
        monkeypatch.setattr(auth_storage.os, 'fsync' if failure == 'sync' else 'replace', fail)
    with pytest.raises(OSError, match='synthetic failure'):
        auth_storage.save_credentials(target)
    assert target.read_bytes() == prior
    assert list(tmp_path.iterdir()) == [target]


def test_directory_sync_failure_reports_uncertain_commit_without_deleting_new_file(store, monkeypatch, tmp_path):
    target = tmp_path / 'credentials.json'
    target.write_text('{"previous": {}}', encoding='utf-8')
    def fail(path):
        raise OSError('directory durability failure')
    monkeypatch.setattr(auth_storage, '_sync_parent_directory', fail)
    with pytest.raises(OSError, match='directory durability failure'):
        auth_storage.save_credentials(target)
    assert json.loads(target.read_text()) == store.credentials
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('fail_sync', [False, True])
def test_posix_directory_descriptor_always_closed(monkeypatch, fail_sync):
    events = []
    # Exercise the POSIX syscall sequence without changing the host platform.
    fake_os = SimpleNamespace(name='posix', path=os.path, O_RDONLY=0, O_DIRECTORY=65536,
                              open=lambda path, flags: events.append(('open', path, flags)) or 99,
                              close=lambda fd: events.append(('close', fd)))
    def sync(fd):
        events.append(('sync', fd))
        if fail_sync:
            raise OSError('synthetic directory sync failure')
    fake_os.fsync = sync
    monkeypatch.setattr(auth_storage, 'os', fake_os)
    if fail_sync:
        with pytest.raises(OSError, match='synthetic directory sync failure'):
            auth_storage._sync_parent_directory(os.path.abspath('credentials.json'))
    else:
        auth_storage._sync_parent_directory(os.path.abspath('credentials.json'))
    assert events[0][0] == 'open'
    assert events[1:] == [('sync', 99), ('close', 99)]
