"""Legacy audit verification over already validated source objects; never repairs."""
import hashlib
import hmac
import json
import re
from datetime import datetime

FIELDS = ('id','event_type','entity_id','actor','summary','details','timestamp','prev_hash')
HEX = re.compile(r'^[0-9a-f]{64}$')
GENESIS = '0' * 64


def verify_audit(events, checkpoint=None, *, checkpoint_provided=False):
    """Use the legacy Python JSON hash encoding, not semantic import digests.

    Input event shapes have been checked by preflight. No runtime module imports,
    global audit state, event-ID output, source writes or inferred replacement hashes.
    """
    issues, verified, legacy = [], 0, 0
    previous = None

    def issue(source, code, row=None):
        issues.append({'source':source, 'code':code, 'row':row})

    for position, event in enumerate(events):
        digest, prior = event.get('hash', ''), event.get('prev_hash', '')
        if not digest:
            legacy += 1
            if previous is not None:
                issue('audit', 'unhashed_event_inside_chain', position)
            continue
        if not HEX.fullmatch(digest) or not HEX.fullmatch(prior):
            issue('audit', 'invalid_hash_encoding', position)
            previous = digest
            continue
        if previous is None:
            if legacy == 0 and prior != GENESIS:
                issue('audit', 'broken_genesis', position)
        elif prior != previous:
            issue('audit', 'broken_link', position)
        payload = {key:event.get(key, '') for key in FIELDS}
        encoded = json.dumps(payload, sort_keys=True, default=str, allow_nan=False).encode('utf-8')
        if hmac.compare_digest(hashlib.sha256(encoded).hexdigest(), digest):
            verified += 1
        else:
            issue('audit', 'content_hash_mismatch', position)
        previous = digest

    checkpoint_status = 'missing'
    if checkpoint is not None or checkpoint_provided:
        required = {'event_count','last_event_id','last_hash','checkpointed_at'}
        valid_shape = isinstance(checkpoint, dict) and checkpoint.keys() == required
        if valid_shape:
            valid_shape = (type(checkpoint['event_count']) is int and checkpoint['event_count'] >= 0
                and (checkpoint['last_event_id'] is None or isinstance(checkpoint['last_event_id'],str))
                and isinstance(checkpoint['last_hash'],str) and isinstance(checkpoint['checkpointed_at'],str))
        if valid_shape:
            try:
                stamp = datetime.fromisoformat(checkpoint['checkpointed_at'].replace('Z','+00:00'))
                valid_shape = stamp.tzinfo is not None and stamp.utcoffset() is not None
            except ValueError:
                valid_shape = False
        if not valid_shape:
            issue('checkpoint', 'invalid_checkpoint_shape')
            checkpoint_status = 'invalid'
        else:
            tail = events[-1] if events else None
            expected = (len(events), tail['id'] if tail else None, tail.get('hash','') if tail else GENESIS)
            actual = (checkpoint['event_count'],checkpoint['last_event_id'],checkpoint['last_hash'])
            checkpoint_status = 'matched' if expected == actual else 'mismatched'
            if checkpoint_status == 'mismatched':
                issue('checkpoint', 'checkpoint_mismatch')

    status = ('invalid' if issues else 'legacy_unverifiable' if legacy else
              'empty' if not events else 'chain_and_checkpoint_match' if checkpoint_status == 'matched' else 'chain_only')
    return {'status':status, 'verified_events':verified, 'legacy_events':legacy,
            'checkpoint':checkpoint_status, 'issues':issues}
