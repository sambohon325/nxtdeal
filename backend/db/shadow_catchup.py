"""Bounded disposable projection catch-up; never saves JSON or replays actions."""
import psycopg

from db.shadow_compare import ShadowRejected
from db.shadow_journal import _guard, _lock
from db.shadow_projection import apply_test_projection


def catch_up_test_projections(connection, *, workspace_id, batch_size=25):
    if type(batch_size) is not int or not 1 <= batch_size <= 100:
        raise ShadowRejected('invalid_catchup_batch_size')
    workspace, _ = _guard(connection, workspace_id, '00000000-0000-0000-0000-000000000000')
    try:
        # Capture a bounded work list and watermark. New commits belong to a
        # later invocation; this function never claims continuous/live parity.
        with connection.transaction():
            _lock(connection, workspace)
            committed = connection.execute('SELECT coalesce(max(generation),0) FROM nxtdeal.shadow_commits WHERE workspace_id=%s', (workspace,)).fetchone()[0]
            prepared = connection.execute('SELECT coalesce(max(generation),0) FROM nxtdeal.shadow_preparations WHERE workspace_id=%s', (workspace,)).fetchone()[0]
            tip = connection.execute('''SELECT s.generation,p.operation_id FROM nxtdeal.shadow_projections s
                JOIN nxtdeal.shadow_preparations p USING(workspace_id,generation)
                WHERE s.workspace_id=%s ORDER BY s.generation DESC LIMIT 1''', (workspace,)).fetchone()
            projected = tip[0] if tip else 0
            jobs = connection.execute('''SELECT generation,operation_id FROM nxtdeal.shadow_commits
                WHERE workspace_id=%s AND generation>%s AND generation<=%s
                ORDER BY generation LIMIT %s''', (workspace,projected,committed,batch_size)).fetchall()
        # Verify even an already-current tip rather than equating row presence
        # with valid evidence. Each job is independently atomic and retryable.
        if tip:
            apply_test_projection(connection, workspace_id=str(workspace),
                                  operation_id=str(tip[1]), expected_predecessor=tip[0]-1)
        for generation, operation in jobs:
            apply_test_projection(connection, workspace_id=str(workspace),
                                  operation_id=str(operation), expected_predecessor=generation-1)
            projected = generation
        return {'observed_committed_generation': committed,
                'verified_through_generation': projected,
                'processed_count': len(jobs),
                'remaining_at_capture': max(0,committed-projected),
                'unresolved_preparation_at_capture': prepared > committed,
                'json_written': False}
    except psycopg.Error:
        raise ShadowRejected('catchup_database_failed') from None
