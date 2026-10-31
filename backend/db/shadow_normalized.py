"""Disposable normalized graph application. Not a runtime repository adapter."""
import psycopg
from psycopg.types.json import Jsonb

from db.import_preflight import canonical
from db.import_writer import _exact, _digest
from db.shadow_compare import ShadowRejected
from db.shadow_journal import _guard, _lock


def _readback(connection, workspace, template):
    rows = connection.execute('SELECT id,entity_type,attributes::text FROM nxtdeal.entities WHERE workspace_id=%s', (workspace,)).fetchall()
    entities = {key:dict(id=key,entity_type=kind,attributes=_exact(data)) for key,kind,data in rows}
    order = [entity['id'] for entity in template['entities']]
    if set(entities) != set(order):
        raise ShadowRejected('normalized_parity_failed')
    rows = connection.execute('''SELECT source_id,target_id,relationship_type,position,created_by,created_at
        FROM nxtdeal.relationships WHERE workspace_id=%s ORDER BY position''',(workspace,)).fetchall()
    if len(rows) != len(template['relationships']):
        raise ShadowRejected('normalized_parity_failed')
    links = []
    for index, (row, source) in enumerate(zip(rows,template['relationships'])):
        a,b,kind,position,actor,stamp = row
        if position != index:
            raise ShadowRejected('normalized_parity_failed')
        link = dict(source_id=a,target_id=b,relationship_type=kind)
        for key,value in (('created_by',actor),('created_at',stamp)):
            if key in source:
                link[key] = value
            elif value is not None:
                raise ShadowRejected('normalized_parity_failed')
        links.append(link)
    result = dict(entities=[entities[key] for key in order],relationships=links)
    if _digest(result) != _digest(template):
        raise ShadowRejected('normalized_parity_failed')
    return result


def load_test_normalized(connection, *, workspace_id):
    """Return a verified detached capture; no runtime fallback or inferred history."""
    workspace,_ = _guard(connection,workspace_id,'00000000-0000-0000-0000-000000000000')
    try:
        with connection.transaction():
            connection.execute('LOCK TABLE nxtdeal.entities,nxtdeal.relationships,nxtdeal.import_manifests IN SHARE MODE')
            _lock(connection,workspace)
            latest = connection.execute('SELECT max(generation) FROM nxtdeal.normalized_receipts WHERE workspace_id=%s',(workspace,)).fetchone()[0]
            if latest is None:
                raise ShadowRejected('normalized_snapshot_missing')
            graph = _readback(connection,workspace,_snapshot(connection,workspace,latest))
            return latest, graph
    except psycopg.Error:
        raise ShadowRejected('normalized_database_failed') from None


def _snapshot(connection, workspace, generation):
    row = connection.execute('''SELECT s.graph::text,s.semantic_digest,p.semantic_digest
        FROM nxtdeal.shadow_projections s JOIN nxtdeal.shadow_preparations p USING(workspace_id,generation)
        WHERE s.workspace_id=%s AND s.generation=%s''',(workspace,generation)).fetchone()
    if row is None:
        raise ShadowRejected('projection_required')
    graph = _exact(row[0])
    if row[1] != row[2] or _digest(graph) != row[2]:
        raise ShadowRejected('projection_parity_failed')
    return graph


def apply_test_normalized(connection, *, workspace_id, generation):
    workspace,_ = _guard(connection,workspace_id,'00000000-0000-0000-0000-000000000000')
    if type(generation) is not int or not 1 <= generation < 2**63:
        raise ShadowRejected('invalid_generation')
    try:
        with connection.transaction():
            # Match the importer's lock order and exclude noncooperating table
            # writers. Deliberately coarse until runtime concurrency is designed.
            connection.execute('LOCK TABLE nxtdeal.entities,nxtdeal.relationships,nxtdeal.import_manifests IN SHARE ROW EXCLUSIVE MODE')
            _lock(connection,workspace)
            if connection.execute('SELECT 1 FROM nxtdeal.import_manifests WHERE workspace_id=%s',(workspace,)).fetchone():
                raise ShadowRejected('imported_workspace_requires_handoff')
            latest = connection.execute('SELECT max(generation) FROM nxtdeal.normalized_receipts WHERE workspace_id=%s',(workspace,)).fetchone()[0]
            graph = _snapshot(connection,workspace,generation)
            if latest is not None:
                _readback(connection,workspace,_snapshot(connection,workspace,latest))
                if generation == latest:
                    return {'status':'already_applied','generation':generation}
            if generation != (latest or 0)+1:
                raise ShadowRejected('normalized_predecessor_mismatch')
            if latest is None:
                _readback(connection,workspace,dict(entities=[],relationships=[]))
            connection.execute('DELETE FROM nxtdeal.relationships WHERE workspace_id=%s',(workspace,))
            ids = [item['id'] for item in graph['entities']]
            connection.execute('DELETE FROM nxtdeal.entities WHERE workspace_id=%s AND NOT (id=ANY(%s::text[]))',(workspace,ids))
            for item in graph['entities']:
                connection.execute('''INSERT INTO nxtdeal.entities(workspace_id,id,entity_type,attributes)
                    VALUES (%s,%s,%s,%s) ON CONFLICT(workspace_id,id) DO UPDATE
                    SET entity_type=EXCLUDED.entity_type,attributes=EXCLUDED.attributes,updated_at=now()''',
                    (workspace,item['id'],item['entity_type'],Jsonb(item['attributes'],dumps=canonical)))
            for position,link in enumerate(graph['relationships']):
                connection.execute('''INSERT INTO nxtdeal.relationships
                    (workspace_id,source_id,target_id,relationship_type,position,created_by,created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                    (workspace,link['source_id'],link['target_id'],link['relationship_type'],position,link.get('created_by'),link.get('created_at')))
            _readback(connection,workspace,graph)
            connection.execute('INSERT INTO nxtdeal.normalized_receipts VALUES (%s,%s)',(workspace,generation))
            if connection.execute('SELECT 1 FROM nxtdeal.normalized_receipts WHERE workspace_id=%s AND generation=%s',
                                  (workspace,generation)).fetchone() is None:
                raise ShadowRejected('normalized_receipt_missing')
            return {'status':'applied','generation':generation}
    except psycopg.Error:
        raise ShadowRejected('normalized_database_failed') from None
