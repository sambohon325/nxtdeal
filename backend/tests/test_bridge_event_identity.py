from copy import deepcopy

import pytest
from core import bridge_event_imports as imports, bridge_event_profiles as profiles, dealer_bridge as bridge
from core.dealeros import ledger
from core.entities import Entity
from tests.test_dealer_bridge import A, B, API, isolated  # noqa: F401
from tests.test_bridge_event_imports import staged


def candidate():
    _, profile, job = staged()
    profiles.approve(B, profile)
    ledger.add_entity(Entity('LEAD-existing', 'Lead', {"Email": "private@example.com", "FirstName": "Dealership name"}))
    row = imports.validate(A, job)["rows"][0]
    return job, row


def decide(job, row, action='link', actor=B):
    return imports.review_identity(actor, job, 1, action, 'LEAD-existing' if action == 'link' else None,
                                   'Reviewed original identity evidence', row['candidate_signature'])


def test_human_link_creates_history_without_overwriting_existing_values():
    job, row = candidate()
    before = deepcopy(ledger.get_entity('LEAD-existing').attributes)
    with pytest.raises(PermissionError): decide(job, row, actor=API)
    decision = decide(job, row)
    assert imports.validate(A, job)["rows"][0]["effect"] == "history_only"
    result = imports.activate(B, job)
    assert result["created"] == 0 and result["observations"] == 1
    assert ledger.get_entity('LEAD-existing').attributes == before
    event = bridge.chrono_observations(A)[0]
    assert event["entity_id"] == 'LEAD-existing' and event["identity_resolution"] == 'human_link'
    assert imports.report(A, job)["activation_receipt"]["identity_review_ids"] == [decision["id"]]


def test_keep_separate_is_explicit_and_does_not_merge():
    job, row = candidate()
    decide(job, row, 'keep_separate')
    assert imports.validate(A, job)["status"] == 'validated'
    assert imports.activate(B, job)["created"] == 1
    assert len([e for e in ledger.entities.values() if e.entity_type == 'Lead']) == 2


@pytest.mark.parametrize('change', ['name', 'email', 'new_candidate'])
def test_changed_candidates_invalidate_decisions_even_when_match_disappears(change):
    job, row = candidate()
    decide(job, row)
    if change == 'new_candidate':
        ledger.add_entity(Entity('LEAD-new', 'Lead', {"Email": "private@example.com"}))
    else:
        ledger.get_entity('LEAD-existing').attributes['Email' if change == 'email' else 'FirstName'] = 'Changed'
    result = imports.validate(A, job)
    assert result['status'] == 'blocked'
    assert result['rows'][0]['error_code'] == 'identity_review_stale'


def test_withdrawal_requires_revalidation_and_preserves_audit():
    job, row = candidate()
    decision = decide(job, row)
    imports.validate(A, job)
    with pytest.raises(PermissionError): imports.withdraw_identity(API, job, 1, 'Withdraw reviewed link')
    imports.withdraw_identity(B, job, 1, 'Withdraw reviewed link')
    assert bridge.get(decision['id'], 'BridgeEventIdentityReview')['status'] == 'withdrawn'
    assert imports.validate(A, job)['status'] == 'blocked'


def test_stale_review_token_and_non_candidates_cannot_be_linked():
    job, row = candidate()
    ledger.get_entity('LEAD-existing').attributes['FirstName'] = 'Changed'
    with pytest.raises(ValueError, match='changed'): decide(job, row)
    row = imports.validate(A, job)['rows'][0]
    with pytest.raises(ValueError, match='candidate'):
        imports.review_identity(B, job, 1, 'link', 'unrelated', 'Reviewed source identity', row['candidate_signature'])


def test_candidate_review_exposes_conflicting_identity_fields_only():
    job, _ = candidate()
    native = ledger.get_entity('LEAD-existing').attributes
    native['email'] = 'different@example.com'
    native['private_note'] = 'not part of identity review'
    row = imports.validate(A, job)['rows'][0]
    candidate_info = row['candidate_records'][0]
    assert candidate_info['legacy_conflicts'][0]['field'] == 'email'
    assert candidate_info['legacy_conflicts'][0]['legacy_value'] == 'private@example.com'
    assert candidate_info['values']['email'] == 'different@example.com'
    assert 'private_note' not in str(candidate_info)
