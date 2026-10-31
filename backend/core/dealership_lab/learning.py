"""App-wide learning milestones; no credit for clicks or client-supplied XP."""
from fastapi import HTTPException
from . import service as lab

# Versioned identities keep content changes from silently rewriting earned history.
LESSONS = [
    ('operations-handoff-v1', 'Operations', 'Close the loop',
     'A reliable handoff identifies the next owner, due time, source record and unresolved blockers.',
     'What makes a handoff ready?', ['A message marked urgent', 'An owner, due time and linked evidence', 'A higher priority score'], 1),
    ('sales-consent-v1', 'Sales', 'Follow up with purpose',
     'Use the customer record to check consent, channel availability and the agreed next step. A queued message is not proof of delivery.',
     'A sequence step is queued. What can you conclude?', ['The customer received it', 'Consent is automatic', 'Delivery still needs confirmation'], 2),
    ('marketing-measurement-v1', 'Marketing', 'Measure the outcome',
     'Keep campaign spend, delivery, responses, appointments and sales distinct. Attribute outcomes only when source evidence supports the connection.',
     'Which is a supported campaign result?', ['Sales linked to verified source records', 'Every sale during the campaign', 'The forecast shown before launch'], 0),
    ('inventory-readiness-v1', 'Inventory', 'Ready means verified',
     'A listed vehicle may still have title, inspection or reconditioning blockers. Check the source records before representing it as ready.',
     'A vehicle is listed. Is it ready for delivery?', ['Always', 'Only after its required readiness checks', 'If its price is competitive'], 1),
    ('service-capacity-v1', 'Service', 'Respect capacity',
     'Separate appointment requests from confirmed reservations. Technician time, bays, parts and promised completion all affect capacity.',
     'A customer requests a time. What follows?', ['Treat it as a guaranteed slot', 'Increase the completion forecast', 'Confirm available capacity before promising it'], 2),
    ('finance-cash-v1', 'Finance', 'Separate profit and cash',
     'Gross profit, net profit, receivables and available cash describe different things. A profitable deal can still await funding.',
     'A deal shows gross profit but is unfunded. Which is true?', ['The profit is not proof of cash received', 'Cash has already arrived', 'Receivables can be ignored'], 0),
    ('reporting-lineage-v1', 'Reporting', 'Read the evidence',
     'Check the reporting period, coverage, currency and source. Missing values are unknown, not zero. Scenario outputs are assumptions, not observed results.',
     'A source value is missing. How should it appear?', ['As zero', 'As unknown with a coverage gap', 'As the forecast median'], 1),
    ('lab-comparison-v1', 'Dealership Lab', 'Compare one decision',
     'Review the baseline and proposed assumptions, compare them with the same random seed, and retain input lineage. A simulated benefit is not a verified operational result.',
     'What does a paired scenario support?', ['A guaranteed outcome', 'A verified peer benchmark', 'A conditional comparison under recorded assumptions'], 2),
]


def catalog(actor):
    p = lab.profile(actor)
    rewards = p.attributes['rewards'] if p else {}
    return [dict(id=k, department=d, title=t, lesson=l, question=q, choices=c,
                 xp=100, complete='learning-'+k+':lifetime' in rewards)
            for k,d,t,l,q,c,_ in LESSONS]


def complete(actor, key, answer):
    lesson = next((x for x in LESSONS if x[0] == key), None)
    if not lesson:
        raise HTTPException(404, 'Learning milestone not found')
    if answer != lesson[6]:
        raise HTTPException(422, 'Review the lesson and try again. No progress was awarded.')
    with lab.transaction():
        p = lab.profile(actor, True).attributes
        reward = 'learning-'+key+':lifetime'
        p['rewards'].setdefault(reward, dict(id='learning-'+key, period='lifetime',
            title=lesson[1]+': '+lesson[2], xp=100, created=lab.now().isoformat(),
            basis='Knowledge check; not verified job completion or performance'))
        return lab.snapshot(actor)


DEPARTMENTS = ('Operations', 'Sales', 'Marketing', 'Inventory', 'Service', 'Finance')


def work_milestones(actor, claim=False, recurring=False):
    """Credit the recorded completing employee, never a client assertion or volume."""
    from core.workflow_catalog import get_workflow_def
    from core.workflow_definitions_v2 import get_workflow_def_v2
    eligible = {}
    for entity in lab.items('WorkflowInstance') + lab.items('WorkflowInstanceV2'):
        a = entity.attributes
        v2 = entity.entity_type == 'WorkflowInstanceV2'
        definition = (get_workflow_def_v2 if v2 else get_workflow_def)(a.get('workflow_key', ''))
        # Catalog identity, rather than mutable instance metadata, determines
        # which department can receive this milestone.
        department = definition['key'].split('.', 1)[0].capitalize() if definition else None
        history = a.get('history') or []
        if (department not in DEPARTMENTS or not definition or a.get('status') != 'completed'
                or not a.get('completed_at') or not history or
                history[-1].get('action') != 'completed' or history[-1].get('by') != actor):
            continue
        if v2:
            steps = a.get('steps') or []
            if ([s.get('key') for s in steps] != [s['key'] for s in definition['steps']]
                    or any(s.get('status') != 'completed' or not s.get('completed_at') for s in steps)):
                continue
        elif a.get('stages') != definition['stages'] or a.get('current_stage_index') != len(definition['stages'])-1:
            continue
        # Do not reward empty practice workflows created purely to collect points.
        linked = a.get('linked_entity_id')
        linked_record = lab.ledger.get_entity(linked) if linked else None
        if (not linked_record or linked_record.id == entity.id
                or linked_record.entity_type in {'WorkflowInstance', 'WorkflowInstanceV2'}
                or linked_record.entity_type.startswith('DealershipLab')):
            continue
        from .engagement import enabled_at
        if enabled_at(actor, a['completed_at']):
            previous = eligible.get(department)
            if not previous or previous.attributes['completed_at'] < a['completed_at']:
                eligible[department] = entity
    profile = lab.profile(actor, claim and bool(eligible))
    rewards = profile.attributes['rewards'] if profile else {}
    if claim:
        from .engagement import require_enabled
        require_enabled(actor)
        for department, source in eligible.items():
            key = 'work-'+department.lower()+':lifetime'
            rewards.setdefault(key, dict(id='work-'+department.lower(), period='lifetime',
                title=department+': first linked workflow completed', xp=150,
                created=lab.now().isoformat(), source_id=source.id,
                source_completed_at=source.attributes['completed_at'],
                basis='Recorded workflow completion; not independent quality or performance certification'))
    start, end = lab.periods(lab.now())['weekly']
    period = start.date().isoformat()
    weekly = {d:e for d,e in eligible.items() if start.isoformat() <= e.attributes['completed_at'] < end.isoformat()}
    if claim and recurring:
        for department, source in weekly.items():
            key = 'work-week-' + department.lower()
            rewards.setdefault(key + ':' + period, dict(id=key, period=period,
                title=department + ': this week’s completed work', xp=50,
                created=lab.now().isoformat(), source_id=source.id,
                source_completed_at=source.attributes['completed_at'],
                basis='One verified linked workflow per department per UTC week; no volume reward'))
    return [dict(department=d, xp=150, eligible=d in eligible,
                 complete='work-'+d.lower()+':lifetime' in rewards,
                 weekly_eligible=d in weekly,
                 weekly_complete='work-week-'+d.lower()+':'+period in rewards) for d in DEPARTMENTS]
