"""Import model inputs as a new private plan, never foreign execution evidence."""
import hashlib
import json
import math
from datetime import timedelta

from fastapi import HTTPException
from . import analysis, service as lab

PREVIEW = 'DealershipLabImportPreview'
LIMIT = 1_000_000


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field: ' + key[:80])
        result[key] = value
    return result


def _finite(value):
    raise ValueError('JSON numbers must be finite')


def parse(content):
    if len(content.encode('utf-8')) > LIMIT:
        raise ValueError('Choose a JSON file of 1 MB or less')
    raw = json.loads(content, object_pairs_hook=_pairs, parse_constant=_finite)
    pending = [(raw, 0)]
    count = 0
    while pending:
        value, depth = pending.pop()
        count += 1
        if depth > 40 or count > 50000:
            raise ValueError('Experiment JSON is too complex')
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('JSON numbers must be finite')
        if isinstance(value, dict):
            pending.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            pending.extend((v, depth + 1) for v in value)
    if not isinstance(raw, dict):
        raise ValueError('Choose an experiment object or an export containing input')
    model = raw.get('input', raw)
    if not isinstance(model, dict):
        raise ValueError('The exported input must be an experiment object')
    normalized = analysis.validate(model)
    original_workflow = normalized['workflow']
    provenance = dict(file_sha256=hashlib.sha256(content.encode('utf-8')).hexdigest(),
                      input_schema=model.get('schema_version'),
                      claimed_data_path=original_workflow['mode'],
                      discarded_source_entries=len(original_workflow['calibration']),
                      discarded_baseline_review=original_workflow['review'] is not None)
    # Keep numeric hypotheses and the selected path, but require fresh local
    # setup/review. Foreign records, rewards and source certifications are not
    # authenticated by importing a file.
    normalized['workflow'] = dict(mode=original_workflow['mode'], selected=False,
                                  objective=original_workflow['objective'])
    normalized = analysis.validate(normalized)
    return normalized, provenance


def preview(actor, content):
    try:
        model, provenance = parse(content)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError, UnicodeError) as exc:
        raise HTTPException(422, 'Cannot import experiment: ' + str(exc)[:300]) from exc
    with lab.transaction():
        record = lab.create('LABI', PREVIEW, dict(owner=actor, input=model,
            provenance=provenance, shared_engine_commit=analysis.SHARED_VERSION,
            created_at=lab.now().isoformat(), expires_at=(lab.now() + timedelta(hours=24)).isoformat()))
        return dict(preview_id=record.id, input=lab.deepcopy(model), provenance=provenance,
                    expires_at=record.attributes['expires_at'], warnings=[
                        'Only model inputs are imported. Saved results, ownership and history are not imported.',
                        'Imported figures are unverified. Review the data path and starting figures before running.',
                        'Foreign source certifications, baseline reviews and completed checklist items are cleared.'])


def adopt(actor, preview_id, name):
    with lab.transaction():
        record = lab.ledger.get_entity(preview_id)
        if not record or record.entity_type != PREVIEW or record.attributes['owner'] != actor:
            raise HTTPException(404, 'Import preview not found')
        data = record.attributes
        existing = next((e for e in lab.items(lab.WORKSPACE)
                         if e.attributes['owner'] == actor and e.attributes.get('import_preview_id') == preview_id), None)
        if existing:
            if existing.attributes['import_name'] != name:
                raise HTTPException(409, 'This preview was already saved with a different name')
            return lab.serial(existing)
        if data['expires_at'] < lab.now().isoformat() or data['shared_engine_commit'] != analysis.SHARED_VERSION:
            raise HTTPException(409, 'Preview this file again before importing')
        sections = {k: {'values': {f: rule[2] for f, rule in s['fields'].items()},
                        'basis': 'assumed', 'note': '', 'reviewed_hash': None}
                    for k, s in lab.SECTIONS.items()}
        model = lab.deepcopy(data['input'])
        identity = sections['identity']['values']
        identity.update({k: model['profile'][k] for k in ('country', 'region', 'city', 'currency')})
        identity.update(name=model['profile']['name'], kind=model['dealership']['kind'], rooftops=model['rooftops'])
        saved = lab.create('LABW', lab.WORKSPACE, dict(owner=actor, name=name,
            parent_id=None, sections=sections, model_definition=model, setup_managed=True,
            revision=1, archived=False, created_at=lab.now().isoformat(), updated_at=lab.now().isoformat(),
            import_preview_id=preview_id, import_name=name, imported_from=data['provenance']))
        lab.save_version(saved)
        return lab.serial(saved)
