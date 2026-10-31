"""Disposable manual backup-log persistence checks; never imports hub.app."""
import os
import sys
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from hub_core import dealer_backups as backups
from hub_core import dealer_backups_api as api
from hub_core import dealer_backups_storage as storage


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    registry = backups.DealerBackupLogRegistry()
    for module in (backups, api, storage):
        monkeypatch.setattr(module, 'registry', registry)
    monkeypatch.setattr(backups, 'dealer_registry', SimpleNamespace(get=lambda _: SimpleNamespace(name='Fixture')))
    monkeypatch.setattr(api, 'get_backups_for_dealer', lambda dealer: ({'logged_events':[e.to_dict() for e in registry.list_for_dealer(dealer)]}, None))
    monkeypatch.setattr(api, 'DEALER_BACKUPS_LOG_PATH', str(tmp_path / 'backup-log.json'))
    audit = []
    monkeypatch.setattr(api, 'record_and_save', lambda **event: audit.append(event))
    return registry, audit, tmp_path / 'backup-log.json'


def test_failed_backup_log_save_preserves_prior_entries_and_fresh_retry_id(isolated, monkeypatch):
    registry, audit, path = isolated
    first = api.log_dealer_backup_api('D1', 'fixture-staff')['logged_events'][0]
    before = path.read_bytes()
    attempted = []
    with monkeypatch.context() as patch:
        def fail(_):
            attempted.append(registry.counter)
            raise OSError('fixture write failure')
        patch.setattr(api, 'save_dealer_backups_log', fail)
        with pytest.raises(OSError): api.log_dealer_backup_api('D1', 'fixture-staff', label='Failed')
    assert [e.log_id for e in registry.list_all()] == [first['log_id']]
    assert path.read_bytes() == before and len(audit) == 1
    api.log_dealer_backup_api('D1', 'fixture-staff', label='Retry')
    assert registry.counter > attempted[0] and len(audit) == 2
    registry.reset()
    storage.load_dealer_backups_log(str(path))
    assert len(registry.entries) == 2
    assert {e.label for e in registry.list_all()} == {None, 'Retry'}


def test_first_failed_log_is_not_visible_or_audited(isolated, monkeypatch):
    registry, audit, path = isolated
    def fail(_): raise OSError('fixture write failure')
    monkeypatch.setattr(api, 'save_dealer_backups_log', fail)
    with pytest.raises(OSError): api.log_dealer_backup_api('D1', 'fixture-staff')
    assert registry.entries == {} and registry.counter == 1
    assert audit == [] and not path.exists()


@pytest.mark.parametrize('invalid', [None, {}, 'invalid', 42,
    [{'log_id':'BKLOG-00020','dealer_id':'D1'}, {}],
    [{'log_id':'BKLOG-00020','dealer_id':'D1'}, {'log_id':'BKLOG-00020','dealer_id':'D2'}],
    [{'log_id':[],'dealer_id':'D1'}], [{'log_id':'BKLOG-00020','dealer_id':''}]])
def test_invalid_load_cannot_partially_mutate_existing_log(isolated, invalid):
    import json
    registry, _, path = isolated
    api.log_dealer_backup_api('D1', 'fixture-staff')
    original = dict(registry.entries)
    counter = registry.counter
    path.write_text(json.dumps(invalid), encoding='utf-8')
    before = path.read_bytes()
    with pytest.raises(ValueError): storage.load_dealer_backups_log(str(path))
    assert registry.entries == original and registry.counter == counter
    assert path.read_bytes() == before


def test_truncated_log_recovers_complete_prefix_without_rewriting_source(isolated, capsys):
    import json
    registry, _, path = isolated
    entry = backups.DealerBackupLogEntry('BKLOG-00020', 'D1', 'fixture-staff')
    path.write_text('[' + json.dumps(entry.to_dict()) + ', {"log_id":', encoding='utf-8')
    before = path.read_bytes()
    storage.load_dealer_backups_log(str(path))
    assert list(registry.entries) == ['BKLOG-00020']
    assert registry.counter == 20 and path.read_bytes() == before
    assert 'recovered 1 complete record' in capsys.readouterr().out

@pytest.mark.parametrize('timestamp,status', [(None,'unknown'), ('broken','invalid'), ('2026-01-01T00:00:00','invalid'), ('2999-01-01T00:00:00Z','invalid')])
def test_loading_unknown_or_invalid_time_does_not_invent_recency(isolated, timestamp, status):
    import json
    registry, _, path = isolated
    row = {'log_id':'BKLOG-00020','dealer_id':'D1','logged_by':'fixture'}
    if timestamp is not None:
        row['logged_at'] = timestamp
    path.write_text(json.dumps([row]), encoding='utf-8')
    before = path.read_bytes()
    storage.load_dealer_backups_log(str(path))
    loaded = registry.list_all()[0].to_dict()
    assert loaded['logged_at'] == timestamp
    assert loaded['timestamp_status'] == status
    assert path.read_bytes() == before
    # Saving/reloading preserves the original time evidence rather than stamping now.
    storage.save_dealer_backups_log(str(path))
    registry.reset()
    storage.load_dealer_backups_log(str(path))
    assert registry.list_all()[0].to_dict() == loaded


def test_log_order_uses_instants_not_offset_text(isolated):
    registry, _, _ = isolated
    for key, when in [('later','2026-01-01T01:30:00+00:00'),
                      ('earlier','2026-01-01T02:00:00+01:00'),
                      ('unknown',None), ('invalid','bad')]:
        registry.add(backups.DealerBackupLogEntry(key,'D1','fixture',logged_at=when))
    assert [entry.log_id for entry in registry.list_all()] == ['later','earlier','unknown','invalid']
    assert registry.list_for_dealer('D1') == registry.list_all()


@pytest.mark.parametrize('timestamp', [42, {}, []])
def test_nontext_time_rejects_entire_load(isolated, timestamp):
    import json
    registry, _, path = isolated
    row = {'log_id':'BKLOG-00020','dealer_id':'D1','logged_at':timestamp}
    path.write_text(json.dumps([row]), encoding='utf-8')
    with pytest.raises(ValueError): storage.load_dealer_backups_log(str(path))
    assert registry.entries == {}


def test_undated_events_are_visible_but_not_reported_as_recent_or_latest(isolated, monkeypatch):
    from hub_core import tenant_storage_metrics, disaster_recovery
    registry, _, _ = isolated
    dealer = SimpleNamespace(dealer_id='D1', name='Fixture')
    dealers = SimpleNamespace(list_all=lambda: [dealer], get=lambda _: dealer)
    empty_storage = SimpleNamespace(get=lambda _: None)
    monkeypatch.setattr(backups, 'dealer_registry', dealers)
    monkeypatch.setattr(tenant_storage_metrics, 'registry', empty_storage)
    monkeypatch.setattr(disaster_recovery, 'dealer_registry', dealers)
    monkeypatch.setattr(disaster_recovery, 'storage_registry', empty_storage)
    monkeypatch.setattr(disaster_recovery, 'backups_log_registry', registry)
    monkeypatch.setattr(disaster_recovery, 'get_server_health_overview', lambda: {'dealers':[]})
    monkeypatch.setattr(disaster_recovery, '_co_located_git_snapshot_check', lambda _: {})
    registry.add(backups.DealerBackupLogEntry('legacy','D1','fixture',logged_at=None))
    overview = backups.get_backups_overview()
    assert overview['recent_logged_events'] == []
    assert overview['dealers'][0]['latest_logged_event_at'] is None
    assert overview['summary']['total_logged_events'] == 1
    detail, error = backups.get_backups_for_dealer('D1')
    assert error is None and len(detail['logged_events']) == 1
    assert detail['logged_events'][0]['timestamp_status'] == 'unknown'
    assert disaster_recovery.get_disaster_recovery_status()['dealers'][0]['latest_logged_backup_event'] is None
