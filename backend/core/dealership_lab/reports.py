"""Private, revisioned monthly reports. No operational records are rewritten."""
from calendar import monthrange
from datetime import datetime, timezone
from fastapi import HTTPException
from chrono.shared.dealership import reported
from chrono.shared.dealership.monthly import MonthlyMetricModel
from chrono.shared.domain import Fact, SimulationRequest
from chrono.shared.engine import Engine
from chrono.shared.compute_admission import ComputeBusy
from . import service as lab, analysis

DATA, IMPORT, OUTLOOK = 'DealershipLabReports', 'DealershipLabImport', 'DealershipLabOutlook'


def state(key, actor):
    lab.workspace(key, actor)
    e = next((e for e in lab.items(DATA) if e.attributes['workspace_id'] == key and e.attributes['owner'] == actor), None)
    return lab.serial(e) if e else dict(workspace_id=key, owner=actor, revision=0, rows=[])


def view(key, actor):
    with lab.LOCK:
        d = state(key, actor)
        roofs, monthly = reported.aggregate(d['rows'])
        return dict(**d, fields=reported.FIELDS, template=reported.template(), roofs=roofs, monthly=monthly,
            kpis=[dict(month=m['month'], values=[dict(key=k,label=label,value=reported.ratio(m['values'],num,den,scale),unit=unit) for k,label,num,den,scale,unit in reported.KPI]) for m in monthly],
            imports=[lab.serial(e) for e in lab.items(IMPORT) if e.attributes['workspace_id']==key and e.attributes['owner']==actor],
            outlooks=[lab.serial(e) for e in lab.items(OUTLOOK) if e.attributes['workspace_id']==key and e.attributes['owner']==actor])


def preview(key, actor, revision, workspace_revision, csv, mapping, source):
    with lab.LOCK:
        w=lab.workspace(key,actor).attributes; d=state(key,actor)
        if w['archived']:raise HTTPException(409,'Restore the workspace before importing reports')
        if d['revision']!=revision or w['revision']!=workspace_revision:raise HTTPException(409,'Reports or workspace changed. Reload and preview again.')
        try:
            info,_=reported.inspect_csv(csv)
            raw=dict(csv=csv)
            if mapping is not None:raw['mapping']=mapping
            definition=analysis.compile_inputs(w)
            rows=reported.parse_import(raw,definition['profile'])
            merged={(r['month'],r['rooftop']):lab.deepcopy(r) for r in d['rows']}
            changes=[]
            for row in rows:
                ident=(row['month'],row['rooftop'])
                prior=merged.get(ident,dict(month=row['month'],rooftop=row['rooftop'],currency=row['currency'],values={},sources={}))
                if prior['currency']!=row['currency']:raise ValueError('Existing report currency differs; use a separate workspace')
                for metric,value in row['values'].items():
                    old=prior['values'].get(metric)
                    if old!=value:
                        changes.append(dict(month=row['month'],rooftop=row['rooftop'],metric=metric,before=old,after=value))
                        prior['values'][metric]=value
                        prior.setdefault('sources',{})[metric]=dict(source=source,revision=revision+1)
                merged[ident]=prior
            combined=sorted(merged.values(),key=lambda r:(r['month'],r['rooftop']))
            if len(combined)>2400:raise ValueError('This workspace supports at most 2,400 rooftop-month records')
            reported.validate_relationships(combined,definition['dealership']['kind'])
        except (ValueError,TypeError) as exc:raise HTTPException(422,str(exc)) from exc
        token=lab.digest(dict(workspace=key,workspace_revision=workspace_revision,revision=revision,rows=combined,source=source))
        return dict(token=token,revision=revision,workspace_revision=workspace_revision,changes=changes,rows=combined,inspection=info,
                    note='Only supplied numeric cells change. Blank cells preserve prior values. Reports are user asserted, not independently verified. No operational records change.')


def commit(key,actor,revision,workspace_revision,csv,mapping,source,token,acknowledge,request_id):
    with lab.transaction():
        lab.workspace(key,actor)
        intent=lab.digest(dict(key=key,revision=revision,workspace_revision=workspace_revision,csv=csv,mapping=mapping,source=source,token=token))
        prior=next((e for e in lab.items(IMPORT) if e.attributes['owner']==actor and e.attributes['request_id']==request_id),None)
        if prior:
            if prior.attributes['intent']!=intent:raise HTTPException(409,'Request identity already used for a different import')
            return lab.serial(prior)
        if not acknowledge:raise HTTPException(422,'Confirm these are your reported dealership figures, not simulated data')
        p=preview(key,actor,revision,workspace_revision,csv,mapping,source)
        if p['token']!=token:raise HTTPException(409,'Preview no longer matches; review again')
        if not p['changes']:raise HTTPException(422,'No changed numeric values to import')
        stamp=lab.now().isoformat()
        batch=lab.create('LABI',IMPORT,dict(owner=actor,workspace_id=key,revision=revision+1,request_id=request_id,intent=intent,
            source=source,created_at=stamp,changes=p['changes'],rows=p['rows'],workspace_revision=workspace_revision))
        for row in p['rows']:
            for lineage in row.get('sources',{}).values():
                if lineage['revision']==revision+1:lineage.update(import_id=batch.id,recorded_at=stamp)
        batch.attributes['rows']=lab.deepcopy(p['rows'])
        e=next((e for e in lab.items(DATA) if e.attributes['workspace_id']==key and e.attributes['owner']==actor),None)
        attrs=dict(owner=actor,workspace_id=key,revision=revision+1,rows=p['rows'],updated_at=stamp)
        if e:e.attributes.update(attrs)
        else:lab.create('LABD',DATA,attrs)
        return lab.serial(batch)


def outlook(key,actor,revision,metric,rooftop,months,seed,target,failure,request_id):
    with lab.LOCK:
        d=state(key,actor)
        if lab.workspace(key,actor).attributes['archived']:raise HTTPException(409,'Restore the workspace before running an outlook')
        intent=dict(workspace_id=key,revision=revision,metric=metric,rooftop=rooftop,months=months,seed=seed,target=target,failure=failure)
        prior=next((e for e in lab.items(OUTLOOK) if e.attributes['owner']==actor and e.attributes['request_id']==request_id),None)
        if prior:
            if prior.attributes['intent']!=intent:raise HTTPException(409,'Request identity already used')
            return lab.serial(prior)
        if d['revision']!=revision:raise HTTPException(409,'Reports changed. Reload first.')
        if metric not in reported.FIELDS:raise HTTPException(422,'Choose a supported metric')
        if failure>=target:raise HTTPException(422,'Failure threshold must be below target; this view evaluates higher-value goals')
        roofs,monthly=reported.aggregate(d['rows'],rooftop)
        if not roofs:raise HTTPException(422,'No reports for this rooftop')
        # Select the trailing complete sequence; never bridge a missing month.
        sequence=[]
        for row in reversed(monthly):
            if metric not in row['values'] or sequence and reported.add_month(row['month'],1)!=sequence[-1]['month']:break
            sequence.append(row)
        sequence.reverse()
        if len(sequence)<6:raise HTTPException(422,'Six consecutive complete trailing months are required for this metric and scope')
        unit=d['rows'][0]['currency'] if reported.FIELDS[metric]['unit'] in ('money','signed') else reported.FIELDS[metric]['unit']
        facts=[]
        for row in sequence:
            year,month=map(int,row['month'].split('-'))
            parents=[r['sources'][metric] for r in d['rows'] if r['month']==row['month'] and (rooftop is None or r['rooftop']==rooftop)]
            facts.append(Fact(id=lab.digest(dict(workspace=key,metric=metric,month=row['month'],parents=parents)),entity=key,metric=metric,value=row['values'][metric],unit=unit,kind='observed',
                valid_at=datetime(year,month,monthrange(year,month)[1],tzinfo=timezone.utc),recorded_at=max(datetime.fromisoformat(p['recorded_at']) for p in parents),
                evidence=dict(source='Private user-reported monthly imports',scope='own_company',method='Sum across selected rooftops with complete coverage; not independently verified.',parent_ids=tuple(sorted({p['import_id'] for p in parents})))))
    class Repository(analysis.PendingRepository):
        def history(self,entity,as_of,known_at,kind):
            return [f for f in facts if f.entity==entity and f.valid_at<=as_of and f.recorded_at<=known_at and f.kind==kind]
    repo=Repository()
    # The origin is explicit: this is a retrospective-origin scenario, never a current backtest.
    request=SimulationRequest(entity=key,as_of=facts[-1].valid_at,known_at=lab.now(),horizon=months,paths=500,seed=seed,
        goal=dict(target=dict(conditions=[dict(metric=metric,op='gte',value=target)]),outperformance=dict(conditions=[dict(metric=metric,op='gte',value=target)]),failure=dict(conditions=[dict(metric=metric,op='lt',value=failure)])))
    try:result=Engine(repo,MonthlyMetricModel(metric,unit,reported.FIELDS[metric]['unit']=='signed')).simulate(request)
    except ComputeBusy as exc:raise HTTPException(429,'Analysis is busy; retry shortly') from exc
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    with lab.transaction():
        if state(key,actor)['revision']!=revision:raise HTTPException(409,'Reports changed during calculation; rerun on the new revision')
        prior=next((e for e in lab.items(OUTLOOK) if e.attributes['owner']==actor and e.attributes['request_id']==request_id),None)
        if prior:
            if prior.attributes['intent']!=intent:raise HTTPException(409,'Request identity already used')
            return lab.serial(prior)
        return lab.serial(lab.create('LABO',OUTLOOK,dict(owner=actor,workspace_id=key,request_id=request_id,intent=intent,
            created_at=lab.now().isoformat(),unit=unit,origin_month=sequence[-1]['month'],shared_engine_commit=analysis.SHARED_VERSION,
            label='Reported-data model scenario from the displayed historical origin. Uses information available now; not an as-known-then backtest or balanced P&L.',
            payload=result.model_dump(mode='json'),models=repo.models,facts=[f.model_dump(mode='json') for f in facts])))


def calibration(key,actor,revision,workspace_revision,rooftop):
    with lab.LOCK:
        d=state(key,actor);w=lab.workspace(key,actor).attributes
        if d['revision']!=revision or w['revision']!=workspace_revision or w['archived']:
            raise HTTPException(409,'Reload an active workspace and reports before calibrating')
        if not d['rows']:raise HTTPException(422,'Import reviewed reports first')
        try:
            definition=analysis.compile_inputs(w)
            definition['workflow'].update(mode='hybrid',selected=True)
            proposal=reported.calibrate(definition,d['rows'],rooftop)
        except (ValueError,IndexError) as exc:raise HTTPException(422,str(exc)) from exc
        proposal['token']=lab.digest(dict(workspace=key,revision=revision,workspace_revision=workspace_revision,proposal=proposal))
        return proposal


def calibrated_option(key,actor,revision,workspace_revision,rooftop,token,name):
    with lab.transaction():
        proposal=calibration(key,actor,revision,workspace_revision,rooftop)
        if proposal['token']!=token:raise HTTPException(409,'Calibration preview changed. Review again.')
        # Replaying the same preview/name returns the existing fork.
        prior=next((e for e in lab.items(lab.WORKSPACE) if e.attributes['owner']==actor and e.attributes.get('report_calibration')==dict(token=token,name=name)),None)
        if prior:return lab.serial(prior)
        attrs=lab.deepcopy(lab.workspace(key,actor).attributes)
        attrs.pop('import_preview_id',None)
        attrs.pop('import_name',None)
        attrs.update(name=name,parent_id=key,revision=1,archived=False,model_definition=proposal['input'],
            report_calibration=dict(token=token,name=name),report_source=dict(workspace_id=key,revision=revision,month=proposal['month'],rooftop=rooftop),
            created_at=lab.now().isoformat(),updated_at=lab.now().isoformat())
        option=lab.create('LABW',lab.WORKSPACE,attrs);lab.save_version(option)
        return lab.serial(option)
