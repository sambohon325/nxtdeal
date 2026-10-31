"""Isolated, offline multi-store Hub recovery rehearsal; never a live backup tool."""
import argparse
from contextlib import closing, ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
from unittest.mock import patch

from synthetic_dealership import ROOT, PASSWORD, clean_environment


def dealer_configuration_stores(stage):
    """Native serializers, with differing records for two fictional dealerships."""
    from hub_core.dealer_modules import DealerModuleConfig, MODULE_CATALOG, registry as modules, get_dealer_module_config
    from hub_core.dealer_modules_storage import save_dealer_modules
    from hub_core.dealer_onboarding import DealerOnboardingStatus, registry as onboarding
    from hub_core.dealer_onboarding_storage import save_dealer_onboarding
    from hub_core.dealer_network_membership import NetworkMembershipConfig, registry as memberships
    from hub_core.dealer_network_membership_storage import save_dealer_network_membership
    from hub_core.dealer_integrations import DealerIntegration, registry as integrations
    from hub_core.dealer_integrations_storage import save_dealer_integrations
    key = MODULE_CATALOG[0]['key']
    for i in (1, 2):
        dealer_id = f'DLR-{i:05}'
        enabled = i == 1
        tier = 'none' if i == 1 else 'premium'
        if stage == 'seed':
            modules.add(DealerModuleConfig(dealer_id, modules={key:enabled}, updated_by='synthetic-recovery'))
            onboarding.add(DealerOnboardingStatus(dealer_id, steps={'users_invited':{
                'complete':enabled, 'note':f'Fictional onboarding {i}'}}))
            memberships.add(NetworkMembershipConfig(dealer_id, tier=tier))
            integrations.add(DealerIntegration(
                integration_id=f'INTG-{i:05}', dealer_id=dealer_id, provider_key='other',
                custom_label=f'Fictional disconnected integration {i}', active=False,
                notes='No provider or credentials configured'))
        else:
            effective = get_dealer_module_config(dealer_id)
            assert next(row for row in effective['modules'] if row['key'] == key)['enabled'] is enabled
            step = onboarding.get(dealer_id).steps['users_invited']
            assert step == {'complete':enabled, 'note':f'Fictional onboarding {i}'}
            assert memberships.get(dealer_id).tier == tier
            records = integrations.list_for_dealer(dealer_id)
            assert len(records) == 1 and records[0].active is False
            assert records[0].custom_label == f'Fictional disconnected integration {i}'
    if stage == 'seed':
        save_dealer_modules('storage/dealer_modules.json')
        save_dealer_onboarding('storage/dealer_onboarding.json')
        save_dealer_network_membership('storage/dealer_network_membership.json')
        save_dealer_integrations('storage/dealer_integrations.json')
    else:
        assert integrations.next_id() == 'INTG-00003'



def operational_stores(stage):
    """Restore operational history without pretending to contact any provider."""
    from hub_core.dealer_migration import DealerMigrationStatus, registry as migrations, get_migration_status
    from hub_core.dealer_migration_storage import save_dealer_migrations
    from hub_core.dealer_support import DealerOperationalSnapshot, registry as support
    from hub_core.dealer_support_storage import save_dealer_support
    from hub_core.dealer_ai_management import DealerAiSnapshot, registry as ai
    from hub_core.dealer_ai_management_storage import save_dealer_ai_snapshots
    from hub_core.dealer_backups import DealerBackupLogEntry, registry as backups
    from hub_core.dealer_backups_storage import save_dealer_backups_log
    for i in (1, 2):
        dealer_id = f'DLR-{i:05}'
        readiness = {'customer_records':50} if i == 1 else {'customer_records':100}
        timestamp = None if i == 1 else '2026-01-01T00:00:00+00:00'
        if stage == 'seed':
            migrations.add(DealerMigrationStatus(dealer_id, readiness=readiness,
                readiness_notes={'customer_records':f'Fictional migration {i}'}))
            support.add(DealerOperationalSnapshot(dealer_id, reachable=False,
                error=f'Fictional unavailable tenant {i}', data={}))
            ai.add(DealerAiSnapshot(dealer_id, reachable=False,
                error=f'Fictional disabled AI {i}', tenant_note='No provider configured'))
            backups.add(DealerBackupLogEntry(log_id=f'BKLOG-{i:05}', dealer_id=dealer_id,
                logged_by='synthetic-recovery', label='Fictional manual history',
                note='Not evidence of an actual backup', logged_at=timestamp))
        else:
            status, error = get_migration_status(dealer_id)
            assert error is None
            assert status['go_live_status'] == ('blocked' if i == 1 else 'at_risk')
            assert migrations.get(dealer_id).readiness == readiness
            assert support.get(dealer_id).reachable is False
            assert support.get(dealer_id).error == f'Fictional unavailable tenant {i}'
            assert ai.get(dealer_id).reachable is False
            assert ai.get(dealer_id).error == f'Fictional disabled AI {i}'
            entries = backups.list_for_dealer(dealer_id)
            assert len(entries) == 1 and entries[0].logged_at == timestamp
            assert entries[0].to_dict()['timestamp_status'] == ('unknown' if i == 1 else 'known')
    if stage == 'seed':
        save_dealer_migrations('storage/dealer_migrations.json')
        save_dealer_support('storage/dealer_support.json')
        save_dealer_ai_snapshots('storage/dealer_ai_snapshots.json')
        save_dealer_backups_log('storage/dealer_backups_log.json')
    else:
        assert backups.next_id() == 'BKLOG-00003'



def remaining_stores(stage):
    from hub_core import infra_provisioning_storage as provisioning
    from hub_core import demo_leads
    from hub_core.network_snapshot import NetworkSnapshot, registry as snapshots
    from hub_core.network_snapshot_storage import save_network_snapshots
    from hub_core.network_connect import NetworkConnectAccount, registry as accounts
    from hub_core.network_connect_storage import save_network_connect_accounts
    from hub_core.code_auditor import CodeAuditFinding, CodeAuditRun, registry as audits
    from hub_core.code_auditor_storage import save_code_audit_findings, save_code_audit_runs
    from hub_core.dealer_ai_kill_switch import DealerKillSwitchAction, registry as actions
    from hub_core.dealer_ai_kill_switch_storage import save_dealer_ai_kill_switch_actions
    for i in (1, 2):
        dealer_id = f'DLR-{i:05}'
        email = f'demo{i}@example.test'
        state = {'status':'failed', 'warnings':['Fictional rehearsal only'],
                 'last_error':f'No provider configured {i}'}
        if stage == 'seed':
            provisioning.put(dealer_id, state)
            result = demo_leads.sign_up(name=f'Fictional Demo {i}', email=email,
                                       password=PASSWORD, persona='sales', username=f'fictional-demo-{i}')
            assert result.get('ok') is True
            accounts.add(NetworkConnectAccount(account_id=f'NCA-{i:05}',
                company_name=f'Fictional Network Company {i}', contact_email=f'network{i}@example.test',
                status='active' if i == 1 else 'suspended', connected_systems={}))
            audits.add_run(CodeAuditRun(run_id=f'CAR-{i:05}', triggered_by='synthetic-recovery',
                status='failed', error=f'Fictional scan failure {i}', total_findings=1))
            audits.add_finding(CodeAuditFinding(finding_id=f'CAF-{i:05}', run_id=f'CAR-{i:05}',
                rule_key='synthetic', rule_title='Fictional finding', severity='high',
                area='synthetic', file_path='fictional.py', line_number=i, description='Fictional only',
                evidence='No real scan performed', recommendation='Fixture only', status='new'))
            actions.add(DealerKillSwitchAction(action_id=f'AIKS-{i:05}', dealer_id=dealer_id,
                pushed_by='synthetic-recovery', scope='global', active=True, success=False,
                push_error=f'Fictional failed push {i}', resulting_state=None))
        else:
            assert provisioning.get(dealer_id) == state
            result = demo_leads.log_in(f'fictional-demo-{i}', PASSWORD)
            assert result.get('ok') is True and result['account']['email'] == email
            assert 'error' in demo_leads.log_in(email, 'wrong-fictional-password')
            account = accounts.get_by_email(f'NETWORK{i}@example.test')
            assert account.account_id == f'NCA-{i:05}'
            assert account.status == ('active' if i == 1 else 'suspended')
            assert account.connected_systems == {}
            finding = audits.get_finding(f'CAF-{i:05}')
            assert finding.run_id == f'CAR-{i:05}' and finding.status == 'new'
            assert audits.runs[finding.run_id].error == f'Fictional scan failure {i}'
            action, = actions.list_for_dealer(dealer_id)
            assert action.success is False and action.resulting_state is None
            assert action.push_error == f'Fictional failed push {i}'
    # Anonymous pool fixtures are deliberately unrelated to identified dealer/account IDs.
    if stage == 'seed':
        snapshots.upsert(NetworkSnapshot(pseudonym='fictional-anonymous-pool',
            submitted_at='2026-01-01T00:00:00+00:00', collected_at='2026-01-01T00:00:01+00:00',
            departments={'sales':{'count':7}}))
        provisioning.save_provisioning('storage/provisioning.json')
        save_network_snapshots('storage/network_snapshots.json')
        save_network_connect_accounts('storage/network_connect_accounts.json')
        save_code_audit_findings('storage/code_audit_findings.json')
        save_code_audit_runs('storage/code_audit_runs.json')
        save_dealer_ai_kill_switch_actions('storage/dealer_ai_kill_switch_actions.json')
    else:
        snapshot, = snapshots.list_all()
        assert snapshot.pseudonym == 'fictional-anonymous-pool'
        assert snapshot.departments == {'sales':{'count':7}}
        assert accounts.id_generator.generate() == 'NCA-00003'
        assert audits.next_finding_id() == 'CAF-00003'
        assert audits.next_run_id() == 'CAR-00003'
        assert actions.next_id() == 'AIKS-00003'


def post_restore_writes(client, stage):
    """New Hub JSON and personal SQLite writes must survive a second cold start."""
    from hub_core.dealer_contacts import registry as contacts
    from hub_core.hub_audit import hub_audit_log
    writing = stage == 'write_after_restore'
    state_path = Path('post-restore-expectations.json')
    expected = {} if writing else json.loads(state_path.read_text())
    admin = client.post('/hub/auth/login', json={'username':'synthetic-admin', 'password':PASSWORD})
    assert admin.status_code == 200
    headers = {'Authorization':'Bearer '+admin.json()['token']}
    if writing:
        result = client.post('/hub/dealer-management/users/DLR-00001', headers=headers,
                             json={'name':'Fictional Post-Restore Contact', 'role':'other',
                                   'email':'postrestore@example.test'})
        assert result.status_code == 200, result.text
    first = contacts.list_for_dealer('DLR-00001')
    assert [row.name for row in first] == ['Fictional Contact 1', 'Fictional Post-Restore Contact']
    assert [row.name for row in contacts.list_for_dealer('DLR-00002')] == ['Fictional Contact 2']
    assert len({row.contact_id for row in first}) == 2
    events = hub_audit_log.get_all()
    assert len([event for event in events if event.event_type == 'dealer_contact_added']) == 1
    assert len({event.id for event in events}) == len(events)
    assert any(event.summary == 'Fictional event 1' for event in events)

    for number in (1, 2):
        login = client.post('/mysales/login', json={'email':f'recovery{number}@example.test', 'password':PASSWORD})
        assert login.status_code == 200
        owner = {'Authorization':'Bearer '+login.json()['token']}
        title = f'Fictional post-restore follow-up {number}'
        if writing:
            created = client.post('/mysales/records/tasks', headers=owner,
                                  json={'title':title, 'due':'2026-10-08'})
            assert created.status_code == 200, created.text
            identifier = created.json()['id']
            updated = client.put('/mysales/records/tasks/'+identifier, headers=owner,
                                 json={'title':title, 'due':'2026-10-08', 'done':True})
            assert updated.status_code == 200
            expected[str(number)] = identifier
        tasks = client.get('/mysales/records/tasks', headers=owner).json()['items']
        assert len(tasks) == 1
        assert tasks[0]['id'] == expected[str(number)]
        assert tasks[0]['title'] == title and tasks[0]['done'] is True
        assert tasks[0]['due'] == '2026-10-08'
        if not writing:
            peer = expected[str(3-number)]
            assert client.put('/mysales/records/tasks/'+peer, headers=owner,
                              json={'title':'Forbidden post-restore change'}).status_code == 404
    if writing:
        state_path.write_text(json.dumps(expected))
    else:
        revoked = json.loads(Path('expectations.json').read_text())['revoked']
        assert client.get('/mysales/me', headers={'Authorization':'Bearer '+revoked}).status_code == 401


def worker(stage):
    from fastapi.testclient import TestClient
    from app import app
    from hub_core.dealer import Dealer
    from hub_core.dealer_registry import registry
    from hub_core.dealer_storage import save_dealers
    from hub_core.feature_flags import FeatureFlagOverride, registry as flags, resolve_flag
    from hub_core.feature_flags_storage import save_feature_flags

    from hub_core.auth import credential_store
    from hub_core.hub_credentials_storage import save_hub_credentials
    from hub_core.dealer_contacts import DealerContact, registry as contacts
    from hub_core.dealer_contacts_storage import save_dealer_contacts
    from hub_core.hub_audit import hub_audit_log
    from hub_core.hub_audit_storage import save_hub_audit_log
    if stage == 'seed':
        credential_store.set_credential('synthetic-admin', PASSWORD, 'ADMIN',
                                        must_change_password=False, email='admin@example.test')
        credential_store.set_credential('synthetic-sales', PASSWORD, 'SALES',
                                        must_change_password=False)
        save_hub_credentials('storage/hub_credentials.json')
    # Exercise the real credential-loading lifespan, replacing only its scheduler.
    with ExitStack() as stack:
        stack.enter_context(patch('app.start_code_auditor_scheduler'))
        stack.enter_context(patch('app.stop_code_auditor_scheduler'))
        client = stack.enter_context(TestClient(app))
        assert client.get('/hub/dealers').status_code == 401
        if stage in ('write_after_restore', 'verify_after_write'):
            post_restore_writes(client, stage)
            print(json.dumps({'stage':stage, 'result':'passed'}))
            return
        if stage == 'seed':
            assert not registry.list_all()
            for i in (1, 2):
                registry.add(Dealer(
                    dealer_id=f'DLR-{i:05}', slug=f'synthetic{i}', name=f'Fictional Dealer {i}',
                    contact_name='Fictional Operator', contact_email=f'dealer{i}@example.test',
                    contact_phone=None, address=None, city=None, state=None, plan_tier='Standard',
                    status='active', storage_dir=f'tenants/tenant{i}/dealer', network_opt_in=False,
                    api_base_url=None, created_by='synthetic-recovery'))
                flags.add(FeatureFlagOverride(
                    override_id=f'FFO-{i:05}', flag_key='synthetic.recovery', scope='dealer',
                    scope_target=f'DLR-{i:05}', enabled=(i == 1), note='Fictional only',
                    created_by='synthetic-recovery'))
            save_dealers('storage/dealers.json')
            save_feature_flags('storage/feature_flags.json')
            for i in (1, 2):
                contacts.add(DealerContact(contact_id=f'CONTACT-{i:05}', dealer_id=f'DLR-{i:05}',
                                          name=f'Fictional Contact {i}', role='other',
                                          email=f'contact{i}@example.test'))
                hub_audit_log.record('synthetic_recovery', f'Fictional event {i}',
                                     dealer_id=f'DLR-{i:05}', actor='synthetic-admin')
            save_dealer_contacts('storage/dealer_contacts.json')
            save_hub_audit_log('storage/hub_audit.json')
            sessions = []
            for i in (1, 2):
                response = client.post('/mysales/signup', json={
                    'name':f'Fictional Rep {i}', 'email':f'recovery{i}@example.test', 'password':PASSWORD})
                assert response.status_code == 200, response.text
                sessions.append(response.json()['token'])
            headers = {'Authorization':'Bearer '+sessions[0]}
            response = client.post('/mysales/records/contacts', headers=headers,
                                   json={'title':'Fictional Recovery Buyer'})
            assert response.status_code == 200, response.text
            record_id = response.json()['id']
            assert client.post('/mysales/logout', headers=headers).status_code == 200
            Path('expectations.json').write_text(json.dumps({'revoked':sessions[0], 'record_id':record_id}))
        else:
            expected = json.loads(Path('expectations.json').read_text())
            admin = client.post('/hub/auth/login', json={'username':'ADMIN@example.test', 'password':PASSWORD})
            assert admin.status_code == 200 and admin.json()['must_change_password'] is False
            admin_headers = {'Authorization':'Bearer '+admin.json()['token']}
            assert client.get('/hub/dealers', headers=admin_headers).status_code == 200
            sales = client.post('/hub/auth/login', json={'username':'synthetic-sales', 'password':PASSWORD})
            assert sales.status_code == 200
            assert client.get('/hub/dealers', headers={'Authorization':'Bearer '+sales.json()['token']}).status_code == 401
            assert client.post('/hub/auth/login', json={'username':'synthetic-admin', 'password':'wrong-synthetic'}).status_code == 401
            assert contacts.next_id() == 'CONTACT-00003'
            assert [(e.dealer_id, e.summary) for e in hub_audit_log.get_all()] == [
                ('DLR-00001', 'Fictional event 1'), ('DLR-00002', 'Fictional event 2')]
            previous_ids = {e.id for e in hub_audit_log.get_all()}
            event = hub_audit_log.record('synthetic_recovery', 'Fictional restored event')
            assert event.id not in previous_ids
            for i in (1, 2):
                assert [c.name for c in contacts.list_for_dealer(f'DLR-{i:05}')] == [f'Fictional Contact {i}']
            assert [d.name for d in registry.list_all()] == ['Fictional Dealer 1', 'Fictional Dealer 2']
            assert registry.id_generator.generate() == 'DLR-00003'
            for dealer in registry.list_all():
                assert (Path(dealer.storage_dir)/'graph.json').is_file()
            for i in (1, 2):
                resolved, error = resolve_flag('synthetic.recovery', f'DLR-{i:05}')
                assert error is None and resolved['resolved_enabled'] is (i == 1)
                login = client.post('/mysales/login', json={'email':f'recovery{i}@example.test', 'password':PASSWORD})
                assert login.status_code == 200, login.text
                headers = {'Authorization':'Bearer '+login.json()['token']}
                rows = client.get('/mysales/records/contacts', headers=headers).json()['items']
                assert ([r['id'] for r in rows] == [expected['record_id']]) if i == 1 else rows == []
                if i == 2:
                    assert client.put('/mysales/records/contacts/'+expected['record_id'], headers=headers,
                                      json={'title':'Forbidden'}).status_code == 404
            assert client.get('/mysales/me', headers={'Authorization':'Bearer '+expected['revoked']}).status_code == 401
            assert client.get('/hub/public/resolve/unknown-synthetic').status_code == 404
        dealer_configuration_stores(stage)
        operational_stores(stage)
        remaining_stores(stage)
        print(json.dumps({'stage':stage, 'result':'passed'}))


def snapshot_hashes(directory):
    """In-memory reference for this closed synthetic fixture, not signed provenance."""
    return {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob('*') if path.is_file()}


def verify_snapshot(directory, expected):
    if snapshot_hashes(directory) != expected:
        raise ValueError('Synthetic recovery snapshot is incomplete or changed')


def rehearse_snapshot_rejection(directory, expected):
    # No application process may boot while these copies are damaged. Restore
    # each original byte sequence even on failure, then check the whole fixture.
    cases = {
        'missing_hub_credentials': ('storage/hub_credentials.json', None),
        'changed_hub_registry': ('storage/dealers.json', b'{}'),
        'changed_tenant_graph': ('tenants/tenant1/dealer/graph.json', b'{}'),
        'damaged_personal_sqlite': ('mysales.sqlite3', b'not a SQLite database'),
    }
    for name, (relative, replacement) in cases.items():
        path = directory/relative
        original = path.read_bytes()
        try:
            if replacement is None:
                path.unlink()
            else:
                path.write_bytes(replacement)
            try:
                verify_snapshot(directory, expected)
            except ValueError:
                pass
            else:
                raise AssertionError(f'Recovery accepted {name}')
        finally:
            path.write_bytes(original)
        verify_snapshot(directory, expected)
    return {name: 'rejected_before_startup' for name in cases}


def rehearse(fixture):
    env = clean_environment(fixture)
    env['PYTHONPATH'] = os.pathsep.join([str(ROOT/'hub'), str(ROOT/'scripts')])
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    # The source writer must exit before copying JSON; SQLite uses its backup API.
    with tempfile.TemporaryDirectory(prefix='nxtdeal-hub-recovery-') as temporary:
        base = Path(temporary)
        source, restored = base/'source', base/'restored'
        source.mkdir()
        restored.mkdir()
        for directory in (source, restored):
            (directory/'recovery-fixture.json').write_text('{"scope":"synthetic-hub-recovery"}')
        def run(stage, directory):
            child_env = {**env, 'NXTDEAL_MYSALES_DB':str(directory/'mysales.sqlite3'),
                         'HUB_ADMIN_USERNAME':'synthetic-admin',
                         'HUB_ADMIN_PASSWORD':'Synthetic-bootstrap-must-not-reset-2026!'}
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker', stage],
                                    cwd=directory, env=child_env, text=True, capture_output=True, timeout=60)
            if result.returncode:
                raise RuntimeError(f'Hub recovery {stage} failed:\n{result.stderr}')
        from rehearse_tenant_recovery import run_tenants
        run_tenants(source, 'seed')
        run('seed', source)
        import ast
        inventory = ast.parse((ROOT/'hub/hub_core/hub_storage_status.py').read_text())
        declaration = next(node.value for node in inventory.body if isinstance(node, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == '_HUB_STORAGE_FILES' for t in node.targets))
        expected_files = {Path(path).name for _, path in ast.literal_eval(declaration)}
        actual_files = {path.name for path in (source/'storage').glob('*.json')}
        assert actual_files == expected_files, 'Recovery fixture does not cover every known JSON store'
        shutil.copytree(source/'storage', restored/'storage')
        shutil.copytree(source/'tenants', restored/'tenants')
        for path in (source/'tenants').rglob('*.json'):
            copy = restored/'tenants'/path.relative_to(source/'tenants')
            assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(copy.read_bytes()).digest()
        shutil.copy2(source/'expectations.json', restored/'expectations.json')
        with closing(sqlite3.connect(source/'mysales.sqlite3')) as database, closing(sqlite3.connect(restored/'mysales.sqlite3')) as target:
            database.backup(target)
            assert target.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        hashes = {}
        for path in (source/'storage').glob('*.json'):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            assert hashlib.sha256((restored/'storage'/path.name).read_bytes()).hexdigest() == digest
            hashes[path.name] = digest
        # Prove the fresh application can recover without the original files.
        assert source.resolve().parent == base.resolve()
        assert (base/'offline-source').resolve().parent == base.resolve()
        source.rename(base/'offline-source')
        expected_snapshot = snapshot_hashes(restored)
        rejected_snapshots = rehearse_snapshot_rejection(restored, expected_snapshot)
        verify_snapshot(restored, expected_snapshot)
        run('restore', restored)
        run_tenants(restored, 'restore')
        run('write_after_restore', restored)
        run_tenants(restored, 'write_after_restore')
        run('verify_after_write', restored)
        run_tenants(restored, 'verify_after_write')
    return {'stage':'full_hub_scoped_recovery', 'scope':'synthetic_only',
            'dealer_registrations':2, 'offline_tenant_graph_recovery':2,
            'cross_tenant_token_rejection':'passed', 'json_stores':sorted(hashes), 'sqlite_integrity':'ok',
            'post_restore_writes_and_second_restart':'passed_hub_json_personal_sqlite_two_tenant_graphs',
            'fresh_process_recovery':'passed', 'dealer_flag_isolation':'passed',
            'snapshot_preflight_negative_cases':rejected_snapshots,
            'personal_owner_isolation_and_revoked_session':'passed',
            'external_network':'blocked', 'all_hub_stores_certified':False, 'populated_json_stores':len(hashes),
            'staff_credentials_contacts_audit':'passed',
            'modules_onboarding_membership_integrations':'passed',
            'migration_support_ai_backup_history':'passed',
            'network_demo_provisioning_audit_kill_switch_history':'passed',
            'credential_loading_lifespan':'passed_with_scheduler_stubbed',
            'scheduler_and_provider_recovery':'not_exercised', 'production_readiness':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture', nargs='?')
    parser.add_argument('--worker', choices=['seed', 'restore', 'write_after_restore', 'verify_after_write'])
    args = parser.parse_args()
    if args.worker:
        if os.environ.get('NXTDEAL_SYNTHETIC') != 'true':
            raise SystemExit('Use the isolated rehearsal parent')
        marker = json.loads(Path('recovery-fixture.json').read_text())
        assert marker == {'scope':'synthetic-hub-recovery'}
        assert Path(os.environ['NXTDEAL_MYSALES_DB']).resolve() == Path.cwd()/'mysales.sqlite3'
        # No provider calls or remote data access even if application code changes.
        original_connect = socket.socket.connect
        original_connect_ex = socket.socket.connect_ex
        def local_connect(sock, address):
            # Windows asyncio uses a loopback socket pair internally.
            if not isinstance(address, tuple) or address[0] not in ('127.0.0.1', '::1'):
                raise RuntimeError('Synthetic external network disabled')
            return original_connect(sock, address)
        def local_connect_ex(sock, address):
            if not isinstance(address, tuple) or address[0] not in ('127.0.0.1', '::1'):
                raise RuntimeError('Synthetic external network disabled')
            return original_connect_ex(sock, address)
        with patch.object(socket.socket, 'connect', local_connect), patch.object(socket.socket, 'connect_ex', local_connect_ex):
            worker(args.worker)
    else:
        if not args.fixture:
            parser.error('fixture is required')
        print(json.dumps(rehearse(Path(args.fixture).resolve()), indent=2))


if __name__ == '__main__':
    main()
