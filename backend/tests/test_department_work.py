from datetime import datetime, timedelta, timezone
import pytest
from core import agent_fabric as f
from core import department_work as w
from core.dealeros import ledger
from core.entities import Entity
from core.department_agents import PACKS
from api.routers.agent_fabric import DealerPolicy

ADMIN = {'employee_id': 'admin', 'role': 'ADMIN'}
REVIEWER = {'employee_id': 'reviewer', 'role': 'ADMIN'}
FUTURE = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()

@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    old = ledger.entities, ledger.relationships
    ledger.entities, ledger.relationships = {}, []
    monkeypatch.setattr(f, 'persist', lambda: None)
    monkeypatch.setattr('core.auth.credential_store.get_record', lambda employee: {'role': 'ADMIN'} if employee in {'admin', 'reviewer'} else None)
    monkeypatch.setattr('core.ai_spend.dealer_ai_enabled', lambda: True)
    monkeypatch.setattr('core.ai_kill_switch.is_bot_enabled', lambda: True)
    monkeypatch.setattr('core.ai_kill_switch.is_workflow_automation_enabled', lambda: True)
    monkeypatch.setattr('core.ai_kill_switch.get_ai_kill_switches', lambda: {})
    monkeypatch.setattr('core.appointments.save_graph', lambda path: None)
    for ident in ('admin', 'reviewer'):
        ledger.add_entity(Entity(ident, 'Employee', {'role': 'ADMIN', 'department': 'Operations', 'password_hash': 'secret'}))
    yield
    ledger.entities, ledger.relationships = old

def create(department, record_id='source', key='one'):
    return f.invoke(ADMIN, department, department+'.work.create', {
        'record_id': record_id, 'title': 'Review observed exception', 'assigned_to': 'admin',
        'due_at': FUTURE, 'category': 'training' if department == 'hr' else 'follow_up'}, idempotency_key=key)

def execute(p):
    f.approve(REVIEWER, p['id'])
    return f.execute(ADMIN, p['id'])

@pytest.mark.parametrize('department', list(PACKS))
def test_all_departments_have_real_review_and_accountable_work_lifecycle(department):
    source = Entity('source', w.SOURCES[department][0], {'status': 'open', 'password_hash': 'secret', 'ssn': 'secret'})
    ledger.add_entity(source)
    before = dict(source.attributes)
    report = f.run_automation(ADMIN, department+'.daily_review', None, 'nxtdeal', 'review')
    assert report['department'] == department
    assert report['totals']['records'] >= 1
    assert 'secret' not in str(report)
    proposal = create(department)
    assert proposal['approval_required']
    with pytest.raises(PermissionError): f.execute(ADMIN, proposal['id'])
    result = execute(proposal)
    work_id = result['result']['work_item_id']
    assert create(department)['id'] == proposal['id']
    assert f.execute(ADMIN, proposal['id'])['result']['work_item_id'] == work_id
    update = f.invoke(ADMIN, department, department+'.work.update', {'record_id': work_id, 'status': 'completed', 'resolution': 'Reviewed; evidence DOC-1'}, idempotency_key='two')
    execute(update)
    assert source.attributes == before
    assert f.read(ADMIN, department+'.workbench.read', department=department)['totals']['completed_work'] == 1
    with pytest.raises(ValueError):
        f.invoke(ADMIN, department, department+'.work.update', {'record_id': work_id, 'status': 'in_progress', 'resolution': 'reopen'}, idempotency_key='three')

def test_department_source_and_work_cannot_cross_boundaries():
    ledger.add_entity(Entity('source', 'Employee', {'role': 'SALES'}))
    with pytest.raises(PermissionError): create('inventory')
    result = execute(create('hr'))
    with pytest.raises(PermissionError):
        f.invoke(ADMIN, 'inventory', 'inventory.work.update', {'record_id': result['result']['work_item_id'], 'status': 'completed', 'resolution': 'x'}, idempotency_key='x')
    with pytest.raises(PermissionError):
        f.invoke({'employee_id': 'sales', 'role': 'SALES'}, 'hr', 'hr.workbench.read', {})

def test_policy_and_oauth_limits_apply_to_new_tools():
    ledger.add_entity(Entity('source', 'Vehicle', {'status': 'available'}))
    actor = {**ADMIN, 'principal': 'oauth', 'oauth_departments': ['inventory'], 'oauth_scopes': ['nxtdeal:read']}
    assert f.invoke(actor, 'inventory', 'inventory.workbench.read', {})['totals']['records'] == 1
    with pytest.raises(PermissionError): f.invoke(actor, 'hr', 'hr.workbench.read', {})
    with pytest.raises(PermissionError): f.invoke(actor, 'inventory', 'inventory.work.create', {})
    f.set_policy(ADMIN, DealerPolicy(disabled=['inventory.workbench.read']).model_dump())
    with pytest.raises(PermissionError): f.invoke(ADMIN, 'inventory', 'inventory.workbench.read', {})

def test_rechecks_source_and_assignee_after_approval():
    ledger.add_entity(Entity('source', 'Vehicle', {}))
    p = create('inventory'); f.approve(REVIEWER, p['id'])
    ledger.get_entity('admin').attributes['disabled'] = True
    with pytest.raises(ValueError): f.execute(ADMIN, p['id'])
    assert not any(e.entity_type == 'DepartmentWorkItem' for e in ledger.get_all().values())

def test_stale_work_update_requires_new_proposal():
    ledger.add_entity(Entity('source', 'Vehicle', {}))
    work_id = execute(create('inventory'))['result']['work_item_id']
    p = f.invoke(ADMIN, 'inventory', 'inventory.work.update', {'record_id': work_id, 'status': 'completed', 'resolution': 'done'}, idempotency_key='update')
    f.approve(REVIEWER, p['id'])
    ledger.get_entity(work_id).attributes['title'] = 'Scope changed'
    with pytest.raises(ValueError): f.execute(ADMIN, p['id'])

def test_reports_use_observations_not_missing_value_defaults():
    for ident, values in [('unknown', {}), ('aged', {'DaysOnLot': 90, 'Year': 2020, 'Make': 'A', 'Model': 'B'}), ('sold', {'status':'sold','DaysOnLot':90})]:
        ledger.add_entity(Entity(ident,'Vehicle', values))
    report=f.read(ADMIN, 'inventory.workbench.read', department='inventory')
    reasons={r['record_id']:r['reasons'] for r in report['exceptions']}
    assert 'sold' not in reasons
    assert any('not recorded' in r for r in reasons['unknown'])
    assert any('60 days' in r for r in reasons['aged'])

def test_accounting_and_parts_reports_never_post_or_order():
    ledger.add_entity(Entity('payment', 'Payment', {'status':'approved', 'posting_status':'unposted', 'bank_account':'secret'}))
    ledger.add_entity(Entity('part', 'Part', {'QuantityOnHand': 0, 'vendor_token': 'secret'}))
    assert f.read(ADMIN, 'accounting.workbench.read', department='accounting')['totals']['exceptions'] == 1
    assert f.read(ADMIN, 'parts.workbench.read', department='parts')['totals']['exceptions'] == 1
    assert ledger.get_entity('payment').attributes['posting_status']=='unposted'

def test_service_creates_native_service_booking_after_review():
    ledger.add_entity(Entity('customer','Customer',{}))
    end=(datetime.fromisoformat(FUTURE)+timedelta(hours=1)).isoformat()
    p=f.invoke(ADMIN,'service','service.appointment.create',{'customer_id':'customer','scheduled_start':FUTURE,'scheduled_end':end},idempotency_key='booking')
    result=execute(p)
    appointment=ledger.get_entity(result['result']['appointment_id'])
    assert appointment.attributes['department']=='Service'
    assert appointment.attributes['customer_id']=='customer'
    assert 'appointment.create' not in PACKS['service'].capabilities
    assert f.read(ADMIN,'bdc.workbench.read',department='bdc')['totals']['records']==0

def test_report_handles_malformed_fields_and_bounds_results():
    for i in range(110): ledger.add_entity(Entity(str(i), 'Vehicle', {'Make':{'token':'secret'},'DaysOnLot':float('nan')}))
    report=f.read(ADMIN,'inventory.workbench.read',department='inventory')
    assert report['truncated'] and len(report['records'])==100
    assert 'secret' not in str(report)
    assert len(f.read(ADMIN,'inventory.workbench.read','105','inventory')['records'])==1


def test_assignee_role_comes_from_current_credentials(monkeypatch):
    ledger.add_entity(Entity('source', 'Vehicle', {}))
    monkeypatch.setattr('core.auth.credential_store.get_record', lambda employee: {'role': 'SALES'})
    with pytest.raises(ValueError): create('inventory')


def test_malformed_parts_request_data_does_not_crash_report():
    ledger.add_entity(Entity('ro', 'ServiceRecord', {'parts_requests': 99}))
    assert f.read(ADMIN, 'parts.workbench.read', department='parts')['totals']['records'] == 1
