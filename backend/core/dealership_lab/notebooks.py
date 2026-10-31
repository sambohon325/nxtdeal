"""Private department learning notebooks over frozen Chrono evidence.

Human follow-up values remain labeled reports, never training facts or a peer
composite. Procedure locks are personal attestations, not operational approvals.
"""
import json
import math
from datetime import date
from pathlib import Path
from fastapi import HTTPException
from . import service as lab
from . import analysis

CATALOG=json.loads(Path(__file__).with_name('notebook_catalog.json').read_text())
REFERENCES=json.loads(Path(__file__).with_name('procedure_references.json').read_text())
BOOK,HISTORY='DealershipLabNotebook','DealershipLabNotebookVersion'


def controls(definition,department):
    profile=definition['profile'];country,region=profile['country'],profile['region']
    result=[dict(id=k,title=t,status='open',evidence='',source=None) for k,t in [('scope','Identify applicable national, regional, city and OEM requirements, qualified review and gaps.'),('sources','Confirm recorded inputs, synthetic assumptions and modeled results stay distinct.'),('department',CATALOG['topics'][department]),('costs','Review staffing, training, software and professional costs; document omissions.')]]
    def add(key,title):
        label,url=REFERENCES['sources'][key]
        result.append(dict(id=key,title=title,status='open',evidence='',source=dict(title=label,url=url,source_recorded_date=REFERENCES['checked'],status='Imported reference; current applicability and content must be reviewed.')))
    if country=='United States':
        add('security','Assess information-security requirements and applicability with a qualified reviewer.')
        if department=='sales':add('used','Review used-vehicle disclosure and delivery requirements.')
        if department in ('service','collision','facilities'):add('safety','Review applicable workshop hazards and required protections.')
        if region=='Texas' and department in ('fi','bhph','accounting'):add('tx','Review applicable sales-finance licensing and contract requirements.')
    elif country=='Canada':
        add('privacy','Review applicable privacy requirements, consent and information handling.')
        if region=='Ontario' and department in ('sales','marketing','fi'):add('on','Review applicable advertised pricing and disclosure requirements.')
        if region=='Ontario' and department in ('service','collision'):add('repair','Review repair estimates, pricing agreements and customer authorization.')
    return result


def get(key,actor):
    e=lab.ledger.get_entity(key)
    if not e or e.entity_type!=BOOK or e.attributes['owner']!=actor:
        raise HTTPException(404,'Notebook not found')
    return e


def frozen_input(run,side):
    if run.get('calculation_inputs'):return run['calculation_inputs'][side]
    model_id=run['payload'][side]['model_id']
    model=next((e for e in lab.items(analysis.MODEL) if e.attributes['owner']==run['owner'] and e.attributes['payload']['id']==model_id),None)
    if not model:raise HTTPException(409,'Frozen model input is unavailable; do not reconstruct it from current defaults')
    return model.attributes['payload']['parameters']['input']


def measures(run,side,months=None):
    n=months or run['intent']['months']
    if months is None:r=run['payload'][side]['terminal_expected']
    else:r={key:values[n] for key,values in run['payload']['expected_series'][side].items()}
    def avg(k):return r[k]/n if k in r else None
    def ratio(k,d,m=1):return r[k]/r[d]*m if k in r and r.get(d) else None
    definition=frozen_input(run,side)
    finance=definition['finance']['scenario']
    return dict(revenue=avg('revenue'),profit=avg('profit'),cash=(r['cash']-finance['opening_cash'])/n,
        sales=avg('sales'),front=ratio('gross','sales'),holding=avg('holding_cost'),
        ad_sale=definition['scenario']['spend']*definition['rooftops']*n/r['sales'] if r.get('sales') else None,
        conversion=ratio('sales','leads',100),unhandled=avg('unhandled_leads'),fi=ratio('fi_gross','sales'),
        ros=avg('service_ros'),ro_gross=ratio('service_gross','service_ros'),lost_ros=None,
        payroll=avg('payroll'),overhead=avg('overhead'),overload=None,
        collection=finance.get('collection_rate'),default=finance.get('monthly_default'),parts=None,collision=None)


def create(actor,run_id,department,kind):
    with lab.transaction():
        e=lab.ledger.get_entity(run_id)
        if not e or e.entity_type!=analysis.RUN or e.attributes['owner']!=actor:
            raise HTTPException(404,'Saved comparison not found')
        run=lab.serial(e)
        templates=CATALOG['templates'] if kind=='workbook' else CATALOG['departments']
        if department not in templates:raise HTTPException(422,'Choose a supported department')
        if department=='bhph' and 'BHPH' not in frozen_input(run,'proposed')['dealership']['kind']:
            raise HTTPException(422,'BHPH notebooks require a BHPH plan')
        a,b=measures(run,'baseline'),measures(run,'proposed');template=templates[department]
        projections=[]
        for days in (30,60,90,120):
            months=days//30
            available=months<=run['intent']['months'] and 'expected_series' in run['payload']
            rows=[]
            if available:
                left,right=measures(run,'baseline',months),measures(run,'proposed',months)
                for key in template[1]:
                    rows.append(dict(key=key,label=CATALOG['metrics'][key][0],unit=CATALOG['metrics'][key][1],baseline=left[key],proposed=right[key],delta=right[key]-left[key] if left[key] is not None and right[key] is not None else None))
            projections.append(dict(days=days,available=available,measures=rows))
        metrics=[]
        for key in template[1]:
            label,unit,direction,definition=CATALOG['metrics'][key]
            if key=='cash':definition='Average modeled monthly change in cash balance; includes entered principal payments, capex and draws. Not observed cash flow.'
            metrics.append(dict(key=key,label=label,unit=unit,direction=direction,definition=definition,baseline=a[key],proposed=b[key],target=None,manual=None,followup=None,source=''))
        value=dict(owner=actor,kind=kind,department=department,title=template[0],workspace_id=run['proposed']['id'],run_id=run_id,
            run_created=run['created_at'],engine_commit=run['shared_engine_commit'],currency=run['currency'],months=run['intent']['months'],
            question=template[2] if kind=='workbook' else CATALOG['topics'][department],
            evidence_note='Frozen model expectations, not actuals. Ratios divide expected totals. Unavailable metrics remain unknown. No peer ranking. Cash is average change in cash balance, including entered cash-flow assumptions.',
            measures=metrics,notes='',action='',responsible='',due='',status='draft',edition=1,revision=1,
            objective='',steps='',exceptions='',reviewer='',review_due='',
            location=lab.deepcopy(frozen_input(run,'proposed')['profile']),
            controls=controls(frozen_input(run,'proposed'),department),
            costs=dict(setup=0,monthly=0,hours=0,rate=0),cost_notes='',
            projections=projections,
            checkpoint_schedule='c30-c60-c90-c120-v2',
            checkpoints=[dict(days=d,action='',target='',actual='',evidence='',status='planned') for d in [30,60,90,120]],
            created_at=lab.now().isoformat(),updated_at=lab.now().isoformat())
        book=lab.create('LABB',BOOK,value);history(book);return lab.serial(book)


def review_state(book, actor):
    """Read-time cues only; never write changing dates/locations into evidence."""
    b=book.attributes
    today=lab.now().date().isoformat()
    notices=[]
    for field,label in [('due','Follow-up'),('review_due','Procedure review')]:
        due=b.get(field,'')
        if due and due<=today:
            notices.append(f'{label} {"due today" if due==today else "overdue"}: {due}')
    workspace=lab.ledger.get_entity(b.get('workspace_id',''))
    if not workspace or workspace.entity_type!=lab.WORKSPACE or workspace.attributes.get('owner')!=actor:
        notices.append('Current source plan unavailable; saved evidence is retained.')
    else:
        if workspace.attributes.get('archived'):notices.append('Source plan archived; saved evidence is retained.')
        try:
            current=analysis.compile_inputs(lab.serial(workspace))['profile']
            original=b.get('location',{})
            changed=[k for k in ('country','region','city') if original.get(k,'')!=current.get(k,'')]
            if changed:notices.append('Plan location changed ('+', '.join(changed)+'). Review applicability before using this saved procedure or workbook.')
        except (ValueError,KeyError,TypeError,HTTPException):
            notices.append('Current plan location could not be checked; saved evidence is retained.')
    return dict(as_of=today,notices=notices,needs_attention=bool(notices))


def history(book):lab.create('LABH',HISTORY,dict(notebook_id=book.id,**lab.deepcopy(book.attributes)))


def save(actor,key,revision,action,fields):
    def fail(message):raise HTTPException(422,message)
    def text(k,limit=4000):
        value=fields.get(k,'')
        if not isinstance(value,str) or len(value)>limit:fail('Invalid '+k)
        return value.strip()
    with lab.transaction():
        e=get(key,actor);b=e.attributes
        if b['revision']!=revision:raise HTTPException(409,'Notebook changed. Reopen it before saving.')
        if action=='upgrade-checkpoints':
            if b['kind']!='procedure' or [c['days'] for c in b['checkpoints']] != [30,60,90,365]:
                fail('Only a legacy 365-day procedure needs a C120 edition')
            # Preserve every old checkpoint verbatim. Never relabel a reported
            # annual outcome as a 120-day result or alter a historical edition.
            b.setdefault('checkpoint_migrations', []).append(dict(
                from_edition=b['edition'], from_revision=b['revision'],
                checkpoints=lab.deepcopy(b['checkpoints']), at=lab.now().isoformat()))
            b['checkpoints'] = lab.deepcopy(b['checkpoints'][:3]) + [dict(days=120,action='',target='',actual='',evidence='',status='planned')]
            b.update(status='draft', edition=b['edition']+1, reviewer='', review_due='',
                     checkpoint_schedule='c30-c60-c90-c120-v2')
            for c in b['controls']:c.update(status='open',evidence='')
        elif action=='revise':
            if b['status']!='locked':fail('Only a locked procedure needs a new edition')
            b.update(status='draft',edition=b['edition']+1,reviewer='',review_due='')
            for c in b['controls']:c.update(status='open',evidence='')
        else:
            if b['status']=='locked':raise HTTPException(409,'Locked evidence is immutable. Start a new edition.')
            for key,limit in [('title',160),('notes',4000),('action',2000),('responsible',120),('due',10),('objective',3000),('steps',12000),('exceptions',4000),('reviewer',120),('review_due',10)]:b[key]=text(key,limit)
            b['cost_notes']=text('cost_notes',2000)
            costs=fields.get('costs',dict(setup=0,monthly=0,hours=0,rate=0))
            if not isinstance(costs,dict) or set(costs)!=set(('setup','monthly','hours','rate')):fail('Preserve all rollout budget fields')
            if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1e7 for v in costs.values()):fail('Budget values must be finite non-negative amounts')
            b['costs']=lab.deepcopy(costs)
            for key in ('due','review_due'):
                if b[key]:
                    try:date.fromisoformat(b[key])
                    except ValueError:fail('Enter a valid '+key+' date')
            supplied=fields.get('measures',[])
            if not isinstance(supplied,list) or len(supplied)!=len(b['measures']):fail('Preserve all worksheet measures')
            for m,v in zip(b['measures'],supplied):
                if not isinstance(v,dict) or v.get('key')!=m['key']:fail('Worksheet measures cannot be replaced')
                for key in ('target','manual','followup'):
                    value=v.get(key)
                    if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or abs(value)>1e12 or m['unit']=='percent' and not 0<=value<=100):fail('Enter a finite measure or leave it unknown')
                    if key=='manual' and m['proposed'] is not None and value is not None:fail('Frozen model evidence cannot be overwritten')
                    m[key]=value
                source=v.get('source','')
                if not isinstance(source,str) or len(source)>500:fail('Invalid measure source')
                if (m['manual'] is not None or m['followup'] is not None) and len(source.strip())<5:fail('Add source and period for reported figures')
                m['source']=source
            if b['kind']=='procedure':
                controls=fields.get('controls');checkpoints=fields.get('checkpoints')
                if not isinstance(controls,list) or len(controls)!=len(b['controls']):fail('Preserve all review controls')
                for c,v in zip(b['controls'],controls):
                    if not isinstance(v,dict) or v.get('id')!=c['id'] or v.get('status') not in ('open','reviewed','not_applicable'):fail('Invalid control')
                    note=v.get('evidence','')
                    if not isinstance(note,str) or len(note)>2000 or (v['status']!='open' and len(note.strip())<10):fail('Record evidence or a reason for reviewed controls')
                    c.update(status=v['status'],evidence=note)
                if not isinstance(checkpoints,list) or len(checkpoints)!=4:fail('Preserve all four checkpoints')
                for c,v in zip(b['checkpoints'],checkpoints):
                    if not isinstance(v,dict) or v.get('days')!=c['days'] or v.get('status') not in ('planned','in_progress','complete'):fail('Invalid checkpoint')
                    for key in ('action','target','actual','evidence'):
                        if not isinstance(v.get(key),str) or len(v[key])>2000:fail('Invalid checkpoint '+key)
                        c[key]=v[key]
                    if (c['actual'] or v['status']=='complete') and len(c['evidence'].strip())<10:fail('Add evidence and period for reported completion')
                    c['status']=v['status']
                if action=='lock':
                    required = {'title':'title','responsible':'responsible person','reviewer':'recorded reviewer','review_due':'next review date','objective':'objective','steps':'procedure steps','exceptions':'exceptions and escalation'}
                    missing = [label for key,label in required.items() if not b[key]]
                    if missing:fail('Complete before locking: '+', '.join(missing)+'.')
                    if b['review_due']<=lab.now().date().isoformat():fail('Choose a future review date')
                    if any(c['status']=='open' for c in b['controls']) or any(not c['action'] or not c['target'] for c in b['checkpoints']):fail('Complete every review and checkpoint plan')
                    if fields.get('acknowledge') is not True:fail('Acknowledge personal attestation is not operational or legal approval')
                    b['status']='locked'
            elif action=='lock':fail('Workbook cannot be locked as a procedure')
        b.update(revision=revision+1,updated_at=lab.now().isoformat());history(e);return lab.serial(e)
