"""Read-only, standard-library preflight for copied legacy JSON; no runtime imports."""
import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
from uuid import UUID

MAX_BYTES = 32 * 1024 * 1024
MAX_DEPTH = 100
MISSING = object()


class InvalidSource(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidSource('duplicate_object_key')
        result[key] = value
    return result


def _constant(_):
    raise InvalidSource('nonfinite_number')


def _join(parts, opening, closing):
    collected, size = [], 2
    for part in parts:
        size += len(part) + 1
        if size > MAX_BYTES:
            raise InvalidSource('canonical_size_limit')
        collected.append(part)
    return opening + ','.join(collected) + closing


def canonical(value, depth=0):
    """Version 1 semantic encoding: sorted object keys, ordered arrays, exact numbers."""
    if depth > MAX_DEPTH:
        raise InvalidSource('nesting_limit')
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise InvalidSource('nonfinite_number')
        _, digits, exponent = value.as_tuple()
        if max(len(digits) + exponent, 0) > 131072 or max(-exponent, 0) > 16383:
            raise InvalidSource('numeric_out_of_range')
        if value == 0:
            return '0'
        result = format(value, 'f')
        return result.rstrip('0').rstrip('.') if '.' in result else result
    if isinstance(value, str):
        if '\x00' in value or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise InvalidSource('invalid_jsonb_text')
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return _join((canonical(v, depth+1) for v in value), '[', ']')
    if isinstance(value, dict):
        # Mutable sessions can supply native keys that JSON decoding never does.
        # Never coerce them: 1 and "1" could otherwise collide or change meaning.
        if any(not isinstance(key, str) for key in value):
            raise InvalidSource('nonstring_object_key')
        return _join((canonical(k, depth+1)+':'+canonical(value[k], depth+1) for k in sorted(value)), '{', '}')
    raise InvalidSource('unsupported_value')


def read_source_bytes(path):
    # One bounded read; do not use a separate stat/read sequence or repair the input.
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise InvalidSource('file_size_limit')
    return raw


def decode_source(raw, *, legacy_numbers=False):
    if len(raw) > MAX_BYTES:
        raise InvalidSource('file_size_limit')
    value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_pairs,
                       parse_int=Decimal, parse_float=Decimal, parse_constant=_constant)
    semantic = canonical(value).encode('utf-8')
    if legacy_numbers:
        # Hashes were written with Python's native JSON number serialization.
        # Reparse the SAME bytes only after exact-decimal compatibility checks.
        def finite_float(token):
            number = float(token)
            if not math.isfinite(number):
                raise InvalidSource('legacy_number_unverifiable')
            return number
        value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_pairs,
                           parse_float=finite_float, parse_constant=_constant)
    return value, {'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest(),
                   'semantic_sha256':hashlib.sha256(semantic).hexdigest()}


def read_source(path, *, legacy_numbers=False):
    return decode_source(read_source_bytes(path), legacy_numbers=legacy_numbers)


def preflight(graph_path, workspace_id, audit_path=None, checkpoint_path=None, *, _reader=None):
    # UUID syntax is not permission: future import must authorize this target.
    workspace = str(UUID(workspace_id))
    reader = _reader or read_source
    report = {'mode':'dry_run', 'format_version':1, 'workspace_id':workspace,
              'sources':{}, 'counts':{}, 'discrepancies':[],
              'audit_integrity':'not_verified', 'database_written':False}

    def issue(source, code, row=None):
        report['discrepancies'].append({'source':source, 'code':code, 'row':row})

    def load(path, label):
        try:
            value, metadata = reader(path, legacy_numbers=label in ('audit','checkpoint'))
            report['sources'][label] = metadata
            return value
        except InvalidSource as error:
            issue(label, str(error))
        except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError, OverflowError, InvalidOperation):
            issue(label, 'invalid_json')
        except OSError:
            issue(label, 'unreadable_source')
        return MISSING

    def shape(row, required, optional, label, index):
        if not isinstance(row, dict) or not required <= row.keys() or row.keys() - required - optional:
            issue(label, 'unexpected_fields_or_shape', index)
            return False
        return True

    def text(value):
        return isinstance(value, str) and bool(value.strip())

    graph = load(graph_path, 'graph')
    if graph is not MISSING:
        if not shape(graph, {'entities','relationships'}, set(), 'graph', None):
            pass
        elif not isinstance(graph['entities'], list) or not isinstance(graph['relationships'], list):
            issue('graph', 'expected_arrays')
        else:
            entities, relationships = graph['entities'], graph['relationships']
            report['counts'].update(entities=len(entities), relationships=len(relationships))
            ids = set()
            for index, row in enumerate(entities):
                if not shape(row, {'id','entity_type','attributes'}, set(), 'entities', index):
                    continue
                if not text(row['id']) or not text(row['entity_type']) or not isinstance(row['attributes'], dict):
                    issue('entities', 'invalid_entity', index)
                    continue
                if row['id'] in ids:
                    issue('entities', 'duplicate_entity_id', index)
                ids.add(row['id'])
            for index, row in enumerate(relationships):
                if not shape(row, {'source_id','target_id','relationship_type'}, {'created_by','created_at'}, 'relationships', index):
                    continue
                if not all(text(row[k]) for k in ('source_id','target_id','relationship_type')):
                    issue('relationships', 'invalid_relationship', index)
                    continue
                if row['source_id'] not in ids or row['target_id'] not in ids:
                    issue('relationships', 'dangling_endpoint', index)
                if any(row.get(k) is not None and not isinstance(row[k], str) for k in ('created_by','created_at')):
                    issue('relationships', 'invalid_provenance', index)
    if checkpoint_path is not None and audit_path is None:
        issue('checkpoint', 'audit_required')
    if audit_path is not None:
        audit_errors_before = len(report['discrepancies'])
        audit = load(audit_path, 'audit')
        if audit is not MISSING:
            if not isinstance(audit, list):
                issue('audit', 'expected_array')
            else:
                report['counts']['audit_events'] = len(audit)
                audit_ids = set()
                for index, row in enumerate(audit):
                    if not shape(row, {'id','event_type','entity_id','actor','summary','details','timestamp'}, {'hash','prev_hash'}, 'audit', index):
                        continue
                    if not all(text(row[k]) for k in ('id','event_type','timestamp')) or not isinstance(row['details'], dict):
                        issue('audit', 'invalid_event', index)
                        continue
                    if row['id'] in audit_ids:
                        issue('audit', 'duplicate_audit_id', index)
                    audit_ids.add(row['id'])
                    if not isinstance(row['summary'], str) or any(row[k] is not None and not isinstance(row[k], str) for k in ('actor','entity_id')):
                        issue('audit', 'invalid_event', index)
                    if any(k in row and not isinstance(row[k], str) for k in ('hash','prev_hash')):
                        issue('audit', 'invalid_hash_shape', index)
                    try:
                        instant = datetime.fromisoformat(row['timestamp'].replace('Z','+00:00'))
                        if instant.tzinfo is None or instant.utcoffset() is None:
                            raise ValueError()
                    except ValueError:
                        issue('audit', 'invalid_or_ambiguous_timestamp', index)
        if len(report['discrepancies']) == audit_errors_before:
            from db.import_audit import verify_audit
            checkpoint = load(checkpoint_path, 'checkpoint') if checkpoint_path is not None else None
            if checkpoint is not MISSING:
                verification = verify_audit(audit, checkpoint, checkpoint_provided=checkpoint_path is not None)
                report['audit_integrity'] = verification['status']
                report['audit_verification'] = verification
                for problem in verification['issues']:
                    issue(problem['source'], problem['code'], problem['row'])
    report['valid'] = not report['discrepancies']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', required=True)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--audit')
    parser.add_argument('--checkpoint')
    args = parser.parse_args()
    try:
        result = preflight(args.graph, args.workspace, args.audit, args.checkpoint)
    except (ValueError, AttributeError):
        # Never echo malformed arguments, paths, source values or exception details.
        print(json.dumps({'valid':False, 'error':'invalid_workspace_uuid'}))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
