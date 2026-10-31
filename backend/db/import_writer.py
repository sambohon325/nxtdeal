"""Transactional importer restricted to disposable nxtdeal_test_<uuid> databases.

No CLI or runtime integration. The caller supplies a dedicated connection and
explicit workspace; this test-only boundary is not production authorization.
"""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import re
from uuid import UUID, uuid4

import psycopg
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from db.import_package import ImportPackage, ImportRejected
from db.import_preflight import canonical


def _exact(text):
    return json.loads(text, parse_int=Decimal, parse_float=Decimal)


def _digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def export_imported(connection, workspace):
    """Reconstruct source shape in memory. Caller must hold the import locks."""
    row = connection.execute('''SELECT manifest::text,entity_order::text,relationship_fields::text,audit_order::text
        FROM nxtdeal.import_manifests WHERE workspace_id=%s''', (workspace,)).fetchone()
    if row is None:
        raise ImportRejected('manifest_missing')
    manifest, entity_order, relationship_fields, audit_order = map(json.loads, row)
    entities = connection.execute('SELECT id,entity_type,attributes::text FROM nxtdeal.entities WHERE workspace_id=%s', (workspace,)).fetchall()
    by_id = {identifier:{'id':identifier,'entity_type':kind,'attributes':_exact(attrs)} for identifier,kind,attrs in entities}
    if len(entities) != len(entity_order) or set(by_id) != set(entity_order):
        raise ImportRejected('entity_parity_failed')
    relationships = connection.execute('''SELECT source_id,target_id,relationship_type,created_by,created_at,position
        FROM nxtdeal.relationships WHERE workspace_id=%s ORDER BY position''', (workspace,)).fetchall()
    if len(relationships) != len(relationship_fields):
        raise ImportRejected('relationship_parity_failed')
    links = []
    for position, (source,target,kind,actor,stamp,stored_position) in enumerate(relationships):
        if position != stored_position:
            raise ImportRejected('relationship_order_failed')
        link = {'source_id':source,'target_id':target,'relationship_type':kind}
        optional = {'created_by':actor,'created_at':stamp}
        for key in relationship_fields[position]:
            link[key] = optional[key]
        # Unrepresented columns must remain NULL, not conceal post-import writes.
        if any(value is not None and key not in relationship_fields[position] for key,value in optional.items()):
            raise ImportRejected('relationship_provenance_failed')
        links.append(link)
    audits = connection.execute('SELECT id,payload::text,action,actor,occurred_at FROM nxtdeal.audit_events WHERE workspace_id=%s', (workspace,)).fetchall()
    if len(audits) != len(audit_order) or {str(r[0]) for r in audits} != set(audit_order):
        raise ImportRejected('audit_parity_failed')
    by_audit = {}
    for identifier,payload,action,actor,occurred_at in audits:
        original = _exact(payload)
        if action != original['event_type'] or actor != original['actor'] or occurred_at != datetime.fromisoformat(original['timestamp'].replace('Z','+00:00')):
            raise ImportRejected('audit_projection_failed')
        by_audit[str(identifier)] = original
    graph = {'entities':[by_id[key] for key in entity_order], 'relationships':links}
    audit = [by_audit[key] for key in audit_order] if 'audit' in manifest['sources'] else None
    if _digest(graph) != manifest['sources']['graph']['semantic_sha256']:
        raise ImportRejected('graph_digest_failed')
    if audit is not None and _digest(audit) != manifest['sources']['audit']['semantic_sha256']:
        raise ImportRejected('audit_digest_failed')
    return graph, audit, manifest


def import_into_test_database(connection, package, *, workspace_id):
    if type(package) is not ImportPackage:
        raise ImportRejected('validated_package_required')
    manifest = package.manifest()
    try:
        workspace = UUID(workspace_id)
    except (ValueError, AttributeError, TypeError):
        raise ImportRejected('invalid_workspace_uuid') from None
    if str(workspace) != manifest['workspace_id']:
        raise ImportRejected('workspace_mismatch')
    if not connection.autocommit or connection.info.transaction_status != TransactionStatus.IDLE:
        raise ImportRejected('dedicated_idle_connection_required')
    if not re.fullmatch(r'nxtdeal_test_[0-9a-f]{32}', connection.info.dbname):
        raise ImportRejected('disposable_test_database_required')
    graph, audit = package.payloads()
    try:
        with connection.transaction():
            connection.execute("SELECT set_config('nxtdeal.workspace_id',%s,true)", (str(workspace),))
            # Conservative table locks also exclude writers that ignore the workspace lock.
            connection.execute('''LOCK TABLE nxtdeal.entities,nxtdeal.relationships,nxtdeal.audit_events,
                nxtdeal.import_manifests IN SHARE ROW EXCLUSIVE MODE''')
            if connection.execute('SELECT id FROM nxtdeal.workspaces WHERE id=%s FOR UPDATE', (workspace,)).fetchone() is None:
                raise ImportRejected('workspace_missing')
            existing = connection.execute('SELECT manifest_digest FROM nxtdeal.import_manifests WHERE workspace_id=%s', (workspace,)).fetchone()
            if existing:
                if existing[0] != manifest['manifest_sha256']:
                    raise ImportRejected('manifest_conflict')
                _, _, stored = export_imported(connection, workspace)
                if stored != manifest:
                    raise ImportRejected('manifest_parity_failed')
                return {'status':'already_imported','manifest_sha256':existing[0]}
            for table in ('entities','relationships','audit_events'):
                if connection.execute(f'SELECT EXISTS(SELECT 1 FROM nxtdeal.{table} WHERE workspace_id=%s)', (workspace,)).fetchone()[0]:
                    raise ImportRejected('target_not_empty')
            for entity in graph['entities']:
                connection.execute('INSERT INTO nxtdeal.entities(workspace_id,id,entity_type,attributes) VALUES (%s,%s,%s,%s)',
                    (workspace,entity['id'],entity['entity_type'],Jsonb(entity['attributes'],dumps=canonical)))
            for position, link in enumerate(graph['relationships']):
                connection.execute('''INSERT INTO nxtdeal.relationships
                    (workspace_id,source_id,target_id,relationship_type,position,created_by,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                    (workspace,link['source_id'],link['target_id'],link['relationship_type'],position,link.get('created_by'),link.get('created_at')))
            audit_order = []
            for event in audit or []:
                identifier = uuid4()
                audit_order.append(str(identifier))
                connection.execute('''INSERT INTO nxtdeal.audit_events(workspace_id,id,action,actor,occurred_at,payload)
                    VALUES (%s,%s,%s,%s,%s,%s)''', (workspace,identifier,event['event_type'],event['actor'],
                    datetime.fromisoformat(event['timestamp'].replace('Z','+00:00')),Jsonb(event,dumps=canonical)))
            connection.execute('''INSERT INTO nxtdeal.import_manifests
                (workspace_id,manifest_digest,manifest,entity_order,relationship_fields,audit_order) VALUES (%s,%s,%s,%s,%s,%s)''',
                (workspace,manifest['manifest_sha256'],Jsonb(manifest),Jsonb([e['id'] for e in graph['entities']]),
                 Jsonb([[key for key in ('created_by','created_at') if key in link] for link in graph['relationships']]),Jsonb(audit_order)))
            _, _, stored = export_imported(connection,workspace)
            if stored != manifest:
                raise ImportRejected('manifest_parity_failed')
        return {'status':'imported','manifest_sha256':manifest['manifest_sha256']}
    except psycopg.Error:
        # Driver messages may echo row payloads or connection details.
        raise ImportRejected('database_import_failed') from None
