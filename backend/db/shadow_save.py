"""Disposable test coordinator. No runtime imports or automatic crash recovery."""
from db.shadow_compare import GraphObservation, ShadowRejected
from db.shadow_file import locked_test_file
from db.shadow_journal import prepare, record_json_commit


def save_test_snapshot(connection, *, directory, workspace_id, operation_id,
                       graph_bytes, expected_bytes, expected_generation=None):
    """Serialize a fresh snapshot's preparation, durable file save and receipt.

    Retrying an operation is deliberately rejected even when its bytes match.
    Any interruption after preparation needs inspection/manual reconciliation.
    This is storage coordination, never permission to replay a business action.
    """
    GraphObservation(workspace_id, 1, graph_bytes).evidence()
    with locked_test_file(directory, workspace_id) as store:
        current = store.read()
        if type(expected_bytes) is not bytes and expected_bytes is not None:
            raise ShadowRejected('immutable_bytes_required')
        if current != expected_bytes:
            raise ShadowRejected('stale_file_snapshot')
        generation = prepare(connection, workspace_id=workspace_id,
                             operation_id=operation_id, graph_bytes=graph_bytes,
                             require_new=True, previous_graph_bytes=current,
                             expected_previous_generation=expected_generation)
        observation = GraphObservation(workspace_id, generation, graph_bytes)
        store.replace(observation, expected_bytes=current)
        try:
            record_json_commit(connection, workspace_id=workspace_id,
                               operation_id=operation_id, observation=observation)
        except ShadowRejected:
            # The file is already durable. A lost DB acknowledgement could mean
            # the receipt committed; do not overwrite or infer it either way.
            raise ShadowRejected('json_saved_receipt_uncertain') from None
        return {'status': 'json_committed', **observation.evidence(),
                'postgres_graph_applied': False}
