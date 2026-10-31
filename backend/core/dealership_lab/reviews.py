"""Private prepared period reviews over reported aggregates, never model forecasts."""
from fastapi import HTTPException
from . import service as lab, reports, analysis

REVIEW,HISTORY='DealershipLabPeriodReview','DealershipLabPeriodReviewVersion'


def closed_periods(today):
    last=today.year*12+today.month-2
    quarter=today.year*12+((today.month-1)//3)*3-3
    def month(i):return f'{i//12:04d}-{i%12+1:02d}'
    return [('monthly',month(last),[month(last)]),('quarterly',f'{quarter//12}-Q{quarter%12//3+1}',[month(quarter+i) for i in range(3)])]


def history(record):
    lab.create('LABU',HISTORY,dict(review_id=record.id,**lab.deepcopy(record.attributes)))


def versions(key,actor):
    with lab.LOCK:
        record=lab.ledger.get_entity(key)
        if not record or record.entity_type!=REVIEW or record.attributes['owner']!=actor:
            raise HTTPException(404,'Review not found')
        lab.workspace(record.attributes['workspace_id'],actor)
        return dict(versions=sorted([lab.serial(e) for e in lab.items(HISTORY) if e.attributes['review_id']==key and e.attributes['owner']==actor],key=lambda e:e['revision']))


def listing(key,actor,manage):
    with lab.LOCK:
        lab.workspace(key,actor)
        return dict(can_manage=manage,scope='Private to this plan owner; publication does not share with other employees or dealerships.',
                    reviews=[lab.serial(e) for e in lab.items(REVIEW) if e.attributes['owner']==actor and e.attributes['workspace_id']==key and (manage or e.attributes['status']=='published')])


def prepare(key,actor,revision,report_revision):
    with lab.transaction():
        w=lab.serial(lab.workspace(key,actor));data=reports.state(key,actor)
        if w['revision']!=revision or data['revision']!=report_revision or w['archived']:
            raise HTTPException(409,'Plan or reported figures changed. Reload before preparing.')
        model=analysis.compile_inputs(w)
        if model['workflow']['mode']=='simulation':
            raise HTTPException(422,'Choose a Real or Hybrid data path for reported period reviews.')
        changed=[]
        for cadence,period,months in closed_periods(lab.now().date()):
            rows=[lab.deepcopy(r) for r in data['rows'] if r['month'] in months]
            roofs=sorted({r['rooftop'] for r in data['rows']})
            gaps=[]
            if len(roofs)!=model['rooftops']:gaps.append(f'{len(roofs)} imported rooftop identifiers; plan expects {model["rooftops"]}. Confirm scope.')
            missing=[f'{m} / {roof}' for m in months for roof in roofs if not any(r['month']==m and r['rooftop']==roof for r in rows)]
            if missing:gaps.append('Missing rooftop-months: '+', '.join(missing))
            if not rows:gaps.append('No imported figures for this period. Data-readiness review only.')
            snapshot=dict(name=w['name'],workspace_revision=revision,report_revision=report_revision,currency=model['profile']['currency'],months=months,rows=rows,gaps=gaps,
                          fields=reports.reported.FIELDS,basis='User-reported monthly aggregates only; not independently audited. Missing metrics are unknown, not zero. Balance-sheet values are not summed across months. Model assumptions are excluded.')
            prior=next((r for r in lab.items(REVIEW) if r.attributes['owner']==actor and r.attributes['workspace_id']==key and r.attributes['cadence']==cadence and r.attributes['period']==period),None)
            if prior:
                if prior.attributes['status']=='published' or prior.attributes['snapshot']==snapshot:continue
                prior.attributes.update(snapshot=snapshot,revision=prior.attributes['revision']+1,updated_at=lab.now().isoformat())
                record=prior
            else:
                record=lab.create('LABQ',REVIEW,dict(owner=actor,workspace_id=key,cadence=cadence,period=period,status='draft',revision=1,notes='',snapshot=snapshot,created_at=lab.now().isoformat(),updated_at=lab.now().isoformat()))
            history(record);changed.append(record.id)
        return dict(changed=changed)


def update(key,actor,revision,action,notes,reviewed):
    with lab.transaction():
        record=lab.ledger.get_entity(key)
        if not record or record.entity_type!=REVIEW or record.attributes['owner']!=actor:raise HTTPException(404,'Review not found')
        value=record.attributes
        lab.workspace(value['workspace_id'],actor)
        if value['revision']!=revision or value['status']=='published':raise HTTPException(409,'Review changed or already published. Reload.')
        if action=='publish' and (not reviewed or len(notes.strip())<20):raise HTTPException(422,'Add an assessment and confirm sources, scope and gaps were reviewed.')
        if action=='publish':
            workspace=lab.workspace(value['workspace_id'],actor)
            data=reports.state(value['workspace_id'],actor)
            if workspace.attributes['archived'] or workspace.attributes['revision']!=value['snapshot']['workspace_revision'] or data['revision']!=value['snapshot']['report_revision']:
                raise HTTPException(409,'Source plan or reports changed. Prepare the draft again and review refreshed evidence.')
        value.update(notes=notes,revision=revision+1,status='published' if action=='publish' else 'draft',updated_at=lab.now().isoformat())
        if action=='publish':value.update(published_at=lab.now().isoformat(),reviewer=actor)
        history(record)
        return lab.serial(record)
