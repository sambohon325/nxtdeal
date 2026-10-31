"""Goal requirements evaluated exclusively through the shared Chrono engine."""
from fastapi import HTTPException
from chrono.shared.assumptions import AssumptionEngine
from chrono.shared.compute_admission import numerical_jobs, ComputeBusy
from chrono.shared.dealership.adapter import DealershipModel
from chrono.shared.dealership.planner import requirements
from chrono.shared.domain import SimulationRequest
from . import service as lab, analysis

PREVIEW='DealershipLabGoalPreview'

def history(key, actor):
    with lab.LOCK:
        lab.workspace(key,actor)
        fields=('source_revision','created_at','metric','target','months','seed','shared_engine_commit')
        records=[dict(id=r.id,**{f:r.attributes[f] for f in fields}) for r in lab.items(PREVIEW)
                 if r.attributes['owner']==actor and r.attributes['source_id']==key]
        return dict(previews=sorted(records,key=lambda r:(r['created_at'],r['id']),reverse=True))


def read(key, actor, preview_id):
    with lab.LOCK:
        source=lab.workspace(key,actor)
        record=lab.ledger.get_entity(preview_id)
        if not record or record.entity_type!=PREVIEW or record.attributes['owner']!=actor or record.attributes['source_id']!=key:
            raise HTTPException(404,'Goal preview not found')
        value=lab.serial(record)
        option=next((w for w in lab.items(lab.WORKSPACE) if w.attributes['owner']==actor and w.attributes.get('goal_preview_id')==preview_id),None)
        return dict(**value,adopted_option=lab.serial(option) if option else None,
                    can_adopt=not source.attributes['archived'] and source.attributes['revision']==value['source_revision'] and value['shared_engine_commit']==analysis.SHARED_VERSION)


def preview(key, actor, revision, metric, target, months, seed, sales_per_person):
    with lab.LOCK:
        source=lab.serial(lab.workspace(key,actor))
        if source['revision']!=revision or source['archived']:
            raise HTTPException(409,'Reload an active source before goal planning')
        model=analysis.compile_inputs(source)
    model.update(months=months,seed=seed)
    at=lab.now();repo=analysis.PendingRepository();engine=AssumptionEngine(repo,DealershipModel())
    engine_metric='revenue' if metric=='vehicle_revenue' else 'contribution'
    request=SimulationRequest.model_validate(dict(entity=key,as_of=at,known_at=at,horizon=months,paths=100,seed=seed,
        goal=dict(name='Average monthly planning goal',target=dict(conditions=[dict(metric=engine_metric,op='gte',value=target*months)]),
                  outperformance=dict(conditions=[dict(metric=engine_metric,op='gte',value=target*months*1.2)]),failure=dict(conditions=[dict(metric='cash',op='lt',value=0)]))))
    def evaluate(inputs):
        # Admission is held across the entire bounded reverse search below.
        result,paths=engine._evaluate_assumptions(request,inputs)
        return {name:(paths[key][:,-1]/months).tolist() for name,key in [('vehicle_revenue','revenue'),('contribution','contribution'),('sales','sales')]}
    try:
        with numerical_jobs.enter():
            proposal=requirements(dict(input=model,metric=metric,target=target,action='reverse',sales_per_person=sales_per_person),evaluate)
            final,_=engine._evaluate_assumptions(request,proposal['input'])
            stressed=lab.deepcopy(proposal['input']);stressed['profile']['market_index']*=.8
            stress,_=engine._evaluate_assumptions(request,stressed)
    except ComputeBusy as exc:
        raise HTTPException(503,str(exc),headers={'Retry-After':'5'}) from exc
    except (ValueError,KeyError,TypeError) as exc:
        raise HTTPException(422,str(exc)) from exc
    with lab.transaction():
        current=lab.workspace(key,actor)
        if current.attributes['revision']!=revision or current.attributes['archived']:
            raise HTTPException(409,'Source changed during planning. Preview again.')
        record=lab.create('LABG',PREVIEW,dict(owner=actor,source_id=key,source_revision=revision,source_hash=lab.digest(model),
            source=source,created_at=at.isoformat(),shared_engine_commit=analysis.SHARED_VERSION,metric=metric,target=target,
            months=months,seed=seed,sales_per_person=sales_per_person,proposal=proposal,
            result=final.model_dump(mode='json'),stress=stress.model_dump(mode='json'),
            basis='Required demand, stock, capacity and Sales staffing are hypotheses, not acquired demand. Target is average monthly vehicle revenue or operating contribution across the horizon, not net profit or cash. 100 shared seeded trials; stress reduces demand index20%. Other costs and conversion assumptions remain fixed. No adoption until a separate option is created.'))
        return lab.serial(record)

def adopt(key, actor, preview_id, revision, name):
    with lab.transaction():
        source=lab.workspace(key,actor)
        record=lab.ledger.get_entity(preview_id)
        if not record or record.entity_type!=PREVIEW or record.attributes['owner']!=actor or record.attributes['source_id']!=key:
            raise HTTPException(404,'Goal preview not found')
        value=record.attributes
        prior=next((w for w in lab.items(lab.WORKSPACE) if w.attributes['owner']==actor and w.attributes.get('goal_preview_id')==preview_id),None)
        if prior:
            if prior.attributes['name']!=name:raise HTTPException(409,'Preview already adopted with another name')
            return lab.serial(prior)
        if source.attributes['revision']!=revision or revision!=value['source_revision'] or source.attributes['archived']:
            raise HTTPException(409,'Source changed. Preview the goal again before adoption.')
        if value['shared_engine_commit']!=analysis.SHARED_VERSION:
            raise HTTPException(409,'Engine changed. Preview again before adoption.')
        model=lab.deepcopy(value['proposal']['input'])
        model['workflow']['setup_complete']=False
        model['workflow']['setup_steps']=[s for s in model['workflow']['setup_steps'] if s not in ('operations','data','review')]
        option=lab.create('LABW',lab.WORKSPACE,dict(owner=actor,name=name,parent_id=key,revision=1,archived=False,
            sections=lab.deepcopy(source.attributes['sections']),setup_managed=True,model_definition=model,goal_preview_id=preview_id,
            created_at=lab.now().isoformat(),updated_at=lab.now().isoformat()))
        if source.attributes.get('imported_from'):
            option.attributes['imported_from']=lab.deepcopy(source.attributes['imported_from'])
        lab.save_version(option)
        return lab.serial(option)
