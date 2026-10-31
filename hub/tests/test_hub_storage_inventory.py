"""Recovery inventory must include persisted stores without opening their contents."""
import ast
import os
from pathlib import Path
import sqlite3

from hub_core import hub_storage_status as storage


def test_inventory_covers_json_paths_declared_by_hub_sources():
    root = Path(__file__).resolve().parents[1]
    declared = set()
    for source in [root / 'app.py', *(root / 'hub_core').glob('*.py')]:
        if source.name == 'hub_storage_status.py':
            continue
        for node in ast.walk(ast.parse(source.read_text(encoding='utf-8'))):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value.startswith('storage/') and node.value.endswith('.json')
                    and '\n' not in node.value and ' ' not in node.value):
                declared.add(node.value)
    # Credentials use a joined path instead of one string literal.
    declared.add('storage/hub_credentials.json')
    assert declared <= {path for _, path in storage._HUB_STORAGE_FILES}


def test_omitted_json_stores_contribute_to_usage_without_reading_contents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('NXTDEAL_MYSALES_DB', raising=False)
    (tmp_path / 'storage').mkdir()
    names = ['hub_credentials', 'provisioning', 'demo_accounts', 'network_connect_accounts',
             'code_audit_findings', 'code_audit_runs', 'dealer_ai_kill_switch_actions']
    for name in names:
        (tmp_path / 'storage' / (name + '.json')).write_bytes(b'fictional fixture')
    monkeypatch.setattr('builtins.open', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Content read')))
    result = storage.get_hub_own_storage()
    present = {row['store'] for row in result['files'] if row['exists']}
    assert present == set(names)
    assert result['total_size_bytes'] == len(names) * len(b'fictional fixture')
    assert result['mysales_path_status'] == 'not_configured'


def test_live_sqlite_sidecars_count_even_when_personal_access_disabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / 'private' / 'personal.sqlite3'
    path.parent.mkdir()
    monkeypatch.setenv('NXTDEAL_MYSALES_DB', str(path))
    monkeypatch.setenv('NXTDEAL_MYSALES_ENABLED', 'false')
    with sqlite3.connect(path) as con:
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('CREATE TABLE fixture(value TEXT)')
        con.execute("INSERT INTO fixture VALUES ('fictional')")
        con.commit()
        expected = {suffix: os.path.getsize(str(path) + suffix) for suffix in ['', '-wal', '-shm']}
        result = storage.get_hub_own_storage()
        measured = {row['store']: row for row in result['files'] if row['store'].startswith('mysales')}
        assert measured['mysales']['size_bytes'] == expected['']
        assert measured['mysales_wal']['size_bytes'] == expected['-wal']
        assert measured['mysales_shm']['size_bytes'] == expected['-shm']
        assert result['total_size_bytes'] == sum(expected.values())
        assert str(path) not in str(result)  # Do not expose host directory names.
        assert con.execute('SELECT value FROM fixture').fetchone() == ('fictional',)


def test_missing_or_invalid_personal_path_does_not_create_storage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / 'absent' / 'personal.sqlite3'
    monkeypatch.setenv('NXTDEAL_MYSALES_DB', str(path))
    result = storage.get_hub_own_storage()
    assert result['mysales_path_status'] == 'configured'
    assert not any(row['exists'] for row in result['files'])
    assert not path.parent.exists()
    monkeypatch.setenv('NXTDEAL_MYSALES_DB', 'relative.sqlite3')
    result = storage.get_hub_own_storage()
    assert result['mysales_path_status'] == 'invalid'
    assert not any(row['store'].startswith('mysales') for row in result['files'])
    assert not list(tmp_path.iterdir())
