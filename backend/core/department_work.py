"""Department operating reports and accountable work. No external provider required.

All outputs are allowlisted observations; exceptions are review prompts, never
credit, employment, pricing or compliance decisions. Work completion records a
human-reported outcome and never silently closes the underlying business record.
"""
from datetime import datetime, timezone
from math import isfinite
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

SOURCES = {
    'sales': ('Lead', 'Vehicle', 'Appointment'),
    'marketing': ('Campaign', 'Vehicle'),
    'gm': ('Lead', 'Deal', 'Vehicle', 'ServiceRecord', 'OperationsTask'),
    'bdc': ('Lead', 'Appointment'),
    'fi': ('Deal', 'FinanceContract'),
    'accounting': ('Payment', 'AccountingPeriod', 'Deal'),
    'service': ('ServiceRecord', 'Appointment'),
    'parts': ('Part', 'ServiceRecord'),
    'inventory': ('Vehicle',),
    'operations': ('OperationsTask', 'Vehicle', 'Deal'),
    'hr': ('Employee',),
    'compliance': ('ComplianceAlert', 'Consent'),
}
FIELDS = {
    'Lead': ('status', 'created_at', 'last_activity_at', 'assigned_to'),
    'Vehicle': ('year', 'make', 'model', 'status', 'days_in_stock'),
    'Appointment': ('department', 'status', 'scheduled_start', 'scheduled_end', 'assigned_to'),
    'Deal': ('status', 'financing_status', 'created_at', 'updated_at'),
    'FinanceContract': ('Status', 'created_at'),
    'Payment': ('status', 'posting_status', 'payment_date'),
    'AccountingPeriod': ('period_key', 'status'),
    'ServiceRecord': ('status', 'ro_stage', 'parts_status', 'Technician', 'created_at'),
    'Part': ('PartNumber', 'QuantityOnHand', 'ReorderPoint'),
    'OperationsTask': ('status', 'priority', 'assigned_to', 'target_date', 'owner_bucket'),
    'Employee': ('department', 'status'),
    'Campaign': ('name', 'status', 'created_at'),
    'ComplianceAlert': ('status', 'action', 'created_at'),
    'Consent': ('channel', 'status', 'occurred_at'),
}
WORK_FIELDS = ('department', 'record_id', 'category', 'title', 'assigned_to', 'due_at',
               'status', 'resolution', 'created_at', 'updated_at', 'completed_at')

class StrictInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class WorkCreate(StrictInput):
    record_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=240)
    category: Literal['follow_up', 'document_review', 'reconciliation', 'parts_follow_up',
                      'inventory_review', 'onboarding', 'training', 'policy_review', 'exception'] = 'follow_up'
    assigned_to: str = Field(min_length=1, max_length=160)
    due_at: str = Field(min_length=1, max_length=80)

class WorkUpdate(StrictInput):
    record_id: str = Field(min_length=1, max_length=160)
    status: Literal['in_progress', 'blocked', 'completed', 'cancelled']
    resolution: str = Field(min_length=1, max_length=500)

class ServiceAppointment(StrictInput):
    customer_id: str = Field(min_length=1, max_length=160)
    scheduled_start: str
    scheduled_end: str
    appointment_type: Literal['service', 'waiter', 'drop_off', 'recall', 'other'] = 'service'

MODELS = {f'{d}.work.create': WorkCreate for d in SOURCES}
MODELS.update({f'{d}.work.update': WorkUpdate for d in SOURCES})
MODELS['service.appointment.create'] = ServiceAppointment

def stamp():
    return datetime.now(timezone.utc).isoformat()

def _ledger():
    from core.dealeros import ledger
    return ledger

def _time(value):
    from core.agent_context import parse_observed_time
    return parse_observed_time(value)

def _number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (ValueError, TypeError, OverflowError):
        return None

def _scalar_fields(entity, fields):
    from core.agent_context import attributes
    # Malformed nested source fields must not become a covert arbitrary-data export.
    return {k: v for k, v in attributes(entity, fields).items()
            if v is None or isinstance(v, (str, bool, int)) or isinstance(v, float) and isfinite(v)}

def _accessible(actor, department, entity):
    from core.security import can_access_entity
    if not entity or entity.entity_type not in SOURCES[department] or not can_access_entity(actor['role'], entity.entity_type):
        return False
    if entity.entity_type == 'Appointment':
        return entity.attributes.get('department') == ('Service' if department == 'service' else 'Sales')
    return True

def _work(actor, department, record_id):
    entity = _ledger().get_entity(record_id)
    if not entity or entity.entity_type != 'DepartmentWorkItem' or entity.attributes.get('department') != department:
        raise PermissionError('Work item is unavailable in this department')
    source = _ledger().get_entity(entity.attributes.get('record_id'))
    if not _accessible(actor, department, source):
        raise PermissionError('The source record is no longer accessible')
    return entity

def validate(actor, capability, data):
    from core.department_agents import PACKS
    from core.agent_actions import require_record
    value = MODELS[capability].model_validate(data).model_dump()
    department = capability.split('.')[0]
    if actor.get('role') not in PACKS[department].roles:
        raise PermissionError('Department access required')
    for field in ('title', 'resolution'):
        if field in value and not value[field].strip():
            raise ValueError('Work text cannot be blank')
    if capability == 'service.appointment.create':
        require_record(actor, value['customer_id'], {'Customer'})
        start, end = _time(value['scheduled_start']), _time(value['scheduled_end'])
        if not start or not end or start <= datetime.now(timezone.utc) or end <= start:
            raise ValueError('A future timezone-aware appointment range is required')
    elif capability.endswith('.create'):
        source = _ledger().get_entity(value['record_id'])
        if not _accessible(actor, department, source):
            raise PermissionError('Record is unavailable in this department')
        if not _time(value['due_at']):
            raise ValueError('Due date must include a timezone')
        owner = _ledger().get_entity(value['assigned_to'])
        if not owner or owner.entity_type != 'Employee' or owner.attributes.get('disabled') or str(owner.attributes.get('status', 'active')).lower() in {'inactive', 'disabled', 'terminated'}:
            raise ValueError('Select an active employee')
        # Same role vocabulary as the native authentication model.
        from core.auth import credential_store
        credential = credential_store.get_record(owner.id)
        if not credential or credential.get('disabled'):
            raise ValueError('Assignee must have an active NXTDeal account')
        role = credential.get('role')
        if role not in PACKS[department].roles:
            raise ValueError('Assignee must have access to this department')
        if value['category'] in {'onboarding', 'training'} and department != 'hr':
            raise ValueError('Employee development work belongs in HR')
    else:
        work = _work(actor, department, value['record_id'])
        if work.attributes.get('status') in {'completed', 'cancelled'}:
            raise ValueError('Closed work cannot be changed')
    return value

def execute(actor, capability, value, proposal_id):
    from core.entities import Entity
    if capability == 'service.appointment.create':
        from core.appointments import create_appointment
        result = create_appointment('Service', value['appointment_type'], value['scheduled_start'],
                                    actor['employee_id'], assigned_to=actor['employee_id'],
                                    customer_id=value['customer_id'], scheduled_end=value['scheduled_end'])
        if isinstance(result, dict):
            raise ValueError('Service appointment could not be created')
        return {'appointment_id': result.id, 'department': 'Service', 'status': 'scheduled', 'sent': False}
    department = capability.split('.')[0]
    if capability.endswith('.create'):
        entity = Entity('DWORK-' + uuid4().hex, 'DepartmentWorkItem', {
            **value, 'department': department, 'status': 'open', 'created_by': actor['employee_id'],
            'created_at': stamp(), 'updated_at': stamp(), 'proposal_id': proposal_id,
            'history': [{'status': 'open', 'by': actor['employee_id'], 'at': stamp()}],
        })
        _ledger().add_entity(entity)
    else:
        entity = _work(actor, department, value['record_id'])
        entity.attributes.update(status=value['status'], resolution=value['resolution'], updated_at=stamp())
        if value['status'] in {'completed', 'cancelled'}:
            entity.attributes['completed_at'] = stamp()
        entity.attributes.setdefault('history', []).append({'status': value['status'], 'by': actor['employee_id'],
                                                           'at': stamp(), 'proposal_id': proposal_id})
    # Gateway persists the business outcome together with proposal/receipt state.
    return {'work_item_id': entity.id, 'status': entity.attributes['status'], 'source_changed': False}

def _reasons(entity, department, fields):
    kind, a = entity.entity_type, entity.attributes
    status = str(fields.get('status') or '').lower()
    reasons = []
    if kind == 'Lead' and status not in {'sold', 'lost', 'closed', 'converted'}:
        from core.agent_context import stale_lead
        if not fields.get('assigned_to'): reasons.append('No assigned owner observed')
        if not _time(fields.get('last_activity_at')): reasons.append('Activity timestamp missing or invalid')
        elif stale_lead(entity)[0]: reasons.append('At least 48 hours without observed activity')
    if kind == 'Vehicle' and status not in {'sold', 'wholesale', 'disposed'}:
        age = _number(fields.get('days_in_stock'))
        if age is None: reasons.append('Inventory age not recorded')
        elif age >= 60: reasons.append('Observed inventory age is at least 60 days')
        if any(not fields.get(k) for k in ('year', 'make', 'model')): reasons.append('Merchandising identity incomplete')
    if kind == 'Deal' and status not in {'funded', 'cancelled', 'closed'}:
        reasons.append('Open deal requires readiness review')
        checklist = a.get('delivery_checklist')
        if not isinstance(checklist, dict) or not checklist: reasons.append('Delivery checklist not recorded')
    if kind == 'Payment' and status == 'approved' and fields.get('posting_status') != 'posted':
        reasons.append('Approved payment has not been marked posted')
    if kind == 'ServiceRecord' and status not in {'closed', 'completed', 'cancelled'} and a.get('ro_stage') not in {'closed', 'completed'}:
        if not a.get('Technician'): reasons.append('No technician assigned')
        if a.get('parts_status') in {'waiting', 'ordered', 'needed'}: reasons.append('Parts follow-up required')
        requests = a.get('parts_requests')
        if department == 'parts' and isinstance(requests, list) and any(isinstance(r, dict) and r.get('status') not in {'received', 'installed', 'cancelled'} for r in requests):
            reasons.append('Open repair-order parts requests')
    if kind == 'Part':
        quantity, reorder = _number(fields.get('QuantityOnHand')), _number(fields.get('ReorderPoint'))
        if quantity is None: reasons.append('Stock quantity not recorded')
        elif quantity <= 0: reasons.append('No stock on hand')
        elif reorder is not None and quantity <= reorder: reasons.append('At or below recorded reorder point')
    if kind == 'OperationsTask' and status not in {'closed', 'completed', 'cancelled'}:
        if not fields.get('assigned_to'): reasons.append('Unassigned operating task')
        due = _time(fields.get('target_date'))
        if due and due < datetime.now(timezone.utc): reasons.append('Operating task overdue')
    if kind == 'Appointment':
        due = _time(fields.get('scheduled_start'))
        if status == 'no_show': reasons.append('Missed appointment needs follow-up')
        elif status in {'scheduled', 'confirmed'} and due and due < datetime.now(timezone.utc): reasons.append('Past appointment needs outcome recorded')
    if kind == 'ComplianceAlert' and status == 'open': reasons.append('Open compliance exception for human review')
    if kind == 'Consent' and not _time(fields.get('occurred_at')): reasons.append('Consent observation has no valid timestamp')
    if kind == 'Campaign' and status == 'draft': reasons.append('Draft campaign awaits review')
    return reasons

def workbench(actor, department, record_id=None):
    from core.department_agents import PACKS
    if department not in SOURCES or actor.get('role') not in PACKS[department].roles:
        raise PermissionError('Department access required')
    records, work, exceptions = [], [], []
    for entity in sorted(_ledger().get_all().values(), key=lambda e: e.id):
        if entity.entity_type == 'DepartmentWorkItem' and entity.attributes.get('department') == department:
            try: _work(actor, department, entity.id)
            except PermissionError: continue
            if record_id and record_id not in {entity.id, entity.attributes.get('record_id')}: continue
            item = {'id': entity.id, **_scalar_fields(entity, WORK_FIELDS)}
            due = _time(item.get('due_at'))
            item['overdue'] = bool(due and due < datetime.now(timezone.utc) and item.get('status') not in {'completed', 'cancelled'})
            work.append(item)
        elif _accessible(actor, department, entity) and (not record_id or entity.id == record_id):
            fields = _scalar_fields(entity, FIELDS[entity.entity_type])
            records.append({'id': entity.id, 'entity_type': entity.entity_type, 'attributes': fields})
            reasons = _reasons(entity, department, fields)
            if reasons: exceptions.append({'record_id': entity.id, 'reasons': reasons})
    if record_id and not records and not work:
        raise ValueError('No accessible record in this department')
    limit = 100
    return {'department': department, 'evidence_kind': 'derived', 'method': 'observed_records_and_explicit_rules',
            'as_of': stamp(), 'records': records[:limit], 'exceptions': exceptions[:limit], 'work_items': work[:limit],
            'totals': {'records': len(records), 'exceptions': len(exceptions), 'open_work': sum(w.get('status') not in {'completed', 'cancelled'} for w in work),
                       'overdue_work': sum(w['overdue'] for w in work), 'completed_work': sum(w.get('status') == 'completed' for w in work)},
            'limit': limit, 'truncated': any(len(v) > limit for v in (records, exceptions, work)),
            'source_records': [r['id'] for r in records[:limit]],
            'limitations': ['Review signals are not compliance certification, forecasts or authorization to change source records.',
                            'Training/onboarding completion is recorded evidence, not inferred from employee activity.']}
