"""Preview and explicit adoption of canonical synthetic mix assumptions."""
from fastapi import HTTPException
from chrono.shared.dealership import mixes, workflow
from . import service as lab, analysis


def describe(key, actor):
    with lab.LOCK:
        workspace = lab.serial(lab.workspace(key, actor))
        model = analysis.compile_inputs(workspace)
        return dict(workspace=workspace, mix=model['mix'], bodies=mixes.BODIES,
                    mode=model['workflow']['mode'], currency=model['profile']['currency'],
                    rooftops=model['rooftops'], bhph='BHPH' in model['dealership']['kind'])


def transform(workspace, draft, action, scope):
    model = analysis.compile_inputs(workspace)
    workflow.require_synthetic(model)
    if len(lab.json.dumps(draft, allow_nan=False)) > 600000:
        raise ValueError('Mix exceeds the supported size')
    model['mix'] = draft
    model = analysis.validate(model)
    if action != 'save-draft':
        model = mixes.action(dict(input=model, action=action, scope=scope, side='scenario'))
        if action == 'apply-customers' and not workspace.get('parent_id'):
            model = mixes.action(dict(input=model, action=action, scope=scope, side='baseline'))
    if action.startswith('apply-'):
        model['workflow']['setup_complete'] = False
        model['workflow']['setup_steps'] = [s for s in model['workflow']['setup_steps'] if s not in ('data', 'review')]
    return analysis.validate(model)


def change(key, actor, revision, draft, action, scope, commit=False, token=None):
    with lab.transaction() if commit else lab.LOCK:
        entity = lab.workspace(key, actor)
        if entity.attributes['revision'] != revision or entity.attributes['archived']:
            raise HTTPException(409, 'Reload an active workspace before changing its mix')
        try:
            model = transform(lab.serial(entity), draft, action, scope)
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc
        expected = lab.digest(dict(workspace_id=key, revision=revision, action=action, scope=scope, model=model))
        if commit:
            if token != expected:
                raise HTTPException(409, 'Preview these exact mix changes before saving')
            if entity.attributes.get('model_definition') != model:
                entity.attributes.update(model_definition=model, setup_managed=True, revision=revision+1, updated_at=lab.now().isoformat())
                lab.save_version(entity)
            return lab.serial(entity)
        return dict(token=expected, revision=revision, action=action, mix=model['mix'],
                    segments=model['segments'], finance=model['finance'],
                    shared_engine_commit=analysis.SHARED_VERSION,
                    basis='Synthetic samples only. Generation does not apply inventory or finance assumptions. Inventory adoption changes counts and average price/gross per rooftop; customer adoption changes explicit BHPH collection/default assumptions, never underwriting from credit or income.')
