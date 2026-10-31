"""Isolation controls around the separately executable fictional dealership."""
import importlib.util
import json
from pathlib import Path
import pytest

script = Path(__file__).resolve().parents[2] / 'scripts/synthetic_dealership.py'
spec = importlib.util.spec_from_file_location('synthetic_dealership', script)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def test_synthetic_environment_never_inherits_provider_or_dealer_credentials(tmp_path, monkeypatch):
    (tmp_path/'synthetic.json').write_text(json.dumps({'kind':fixture.MARKER,'auth_secret':'fixture-secret'}))
    for key in ['OPENAI_API_KEY','NXTDEAL_PRIVATEEMAIL_PASSWORD','DEALEROS_AUTH_SECRET',
                'NXTDEAL_CHRONO_TOKEN','NXTDEAL_CLOUD_CONNECTIONS','HTTP_PROXY']:
        monkeypatch.setenv(key,'must-not-leak')
    env=fixture.clean_environment(tmp_path)
    assert 'must-not-leak' not in env.values()
    assert env['DEALEROS_STORAGE_DIR']==str(tmp_path/'dealer')
    assert env['NXTDEAL_MARKETING_DELIVERY_ENABLED']=='false'
    assert env['NXTDEAL_CLOUD_BACKUPS_ENABLED']=='false'


def test_create_refuses_existing_data_before_any_write(tmp_path):
    (tmp_path/'graph.json').write_text('preserve me')
    with pytest.raises(FileExistsError):
        fixture.create(tmp_path)
    assert (tmp_path/'graph.json').read_text()=='preserve me'
    assert list(tmp_path.iterdir()) == [tmp_path/'graph.json']


def test_ordinary_directory_cannot_be_served_as_fixture(tmp_path):
    (tmp_path/'synthetic.json').write_text(json.dumps({'kind':'production'}))
    with pytest.raises(ValueError,match='Not a synthetic'):
        fixture.clean_environment(tmp_path)


def test_container_seed_preserves_marked_data_and_refuses_incomplete_volume(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(script.parent))
    from staging_container import seed
    (tmp_path/'synthetic.json').write_text(json.dumps({'kind':fixture.MARKER,'auth_secret':'fixture-secret'}))
    with pytest.raises(ValueError,match='Incomplete'):
        seed(tmp_path)
    (tmp_path/'dealer').mkdir()
    (tmp_path/'dealer/graph.json').write_text('preserved fixture data')
    (tmp_path/'dealer/credentials.json').write_text('preserved fixture credentials')
    assert seed(tmp_path) == 'preserved'
    assert (tmp_path/'dealer/graph.json').read_text() == 'preserved fixture data'
    assert (tmp_path/'dealer/credentials.json').read_text() == 'preserved fixture credentials'


def test_warranty_fixture_connects_all_claims_and_recall_vehicles(monkeypatch):
    from core.dealeros import ledger
    from core.entities import Entity
    from core.relationships import Relationship
    from core import warranty_desk
    ledger.reset()
    try:
        data = fixture.warranty_graph()
        for row in data['entities']:
            assert row['attributes']['synthetic'] is True
            ledger.add_entity(Entity(**row))
        for row in data['relationships']:
            ledger.add_relationship(Relationship(**row))
        claims = warranty_desk.get_claims_queue()
        assert claims['count'] == 17
        assert all(c['customer_name'].startswith('Fictional Warranty') and c['vin'].startswith('SYNTHETIC') for c in claims['claims'])
        recalls = warranty_desk.get_recall_management_queue()
        assert recalls['total_needs_repair'] == 17
        assert recalls['campaign_count'] == 1
    finally:
        ledger.reset()
