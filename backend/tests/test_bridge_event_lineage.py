import pytest
from core import bridge_event_imports as imports, bridge_event_profiles as profiles, dealer_bridge as bridge
from core.dealeros import ledger
from tests.test_dealer_bridge import A, B, API, isolated  # noqa: F401
from tests.test_bridge_event_imports import staged
from tests.test_bridge_adf_discovery import ADF


def activated():
    system, profile, job = staged()
    profiles.approve(B, profile)
    imports.validate(A, job); imports.activate(B, job)
    return system, profile, job


def test_lineage_separates_current_values_from_original_creation_evidence():
    system, _, job = activated()
    result = imports.lineage(A, system, 'Provider', 'private-id')
    assert result['receipt_integrity'] == 'consistent'
    assert result['observation']['time_semantics'] == 'created'
    assert result['observation']['job_id'] == job
    ledger.get_entity(result['canonical_id']).attributes['first_name'] = 'Later edit'
    result = imports.lineage(API, system, 'Provider', 'private-id')
    assert result['current_values']['first_name'] == 'Later edit'
    assert result['observation']['values']['first_name'] == 'Private Name'
    assert result['legacy_conflicts']


def test_lineage_requires_exact_namespace_and_workspace():
    system, _, _ = activated()
    with pytest.raises(ValueError): imports.lineage(A, system, 'Other', 'private-id')
    with pytest.raises(PermissionError): imports.lineage({**A, 'workspace_id': 'other'}, system, 'Provider', 'private-id')


def test_changed_receipt_is_reported_and_broken_event_link_rejected():
    system, _, job = activated()
    bridge.get(job, 'BridgeEventJob')['activation_receipt']['activated_by'] = 'changed'
    assert imports.report(A, job)['receipt_integrity'] == 'changed'
    result = imports.lineage(A, system, 'Provider', 'private-id')
    assert result['receipt_integrity'] == 'changed'
    ledger.get_entity(result['observation']['event_id']).attributes['values']['first_name'] = 'changed'
    with pytest.raises(ValueError, match='inconsistent'): imports.lineage(A, system, 'Provider', 'private-id')


def test_job_pages_are_scoped_stable_and_do_not_include_source_values():
    system, profile, first = staged()
    second = imports.stage(API, profile, ADF)['id']
    third = imports.stage(API, profile, ADF)['id']
    page = imports.list_jobs(A, system, 2)
    assert [row['id'] for row in page['jobs']] == [third, second]
    assert page['next_before_id'] == second and page['total_jobs'] == 3
    assert 'private@example.com' not in str(page)
    next_page = imports.list_jobs(A, system, 2, page['next_before_id'])
    assert [row['id'] for row in next_page['jobs']] == [first]
    assert next_page['next_before_id'] is None
    other, _, other_job = staged()
    with pytest.raises(ValueError, match='cursor'): imports.list_jobs(A, other, 2, second)
    assert imports.list_jobs(A, other)['jobs'][0]['id'] == other_job


@pytest.mark.parametrize('limit', [0, 101, True, '2'])
def test_job_page_bounds(limit):
    system, _, _ = staged()
    with pytest.raises(ValueError): imports.list_jobs(A, system, limit)


def test_receipt_from_another_job_is_not_accepted_as_evidence():
    from copy import deepcopy
    _, profile, original = activated()
    replay = imports.stage(A, profile, ADF)["id"]
    imports.validate(A, replay); imports.activate(B, replay)
    job = bridge.get(replay, "BridgeEventJob")
    copied = deepcopy(job["activation_receipt"])
    copied["job_id"] = original
    copied["checksum"] = bridge.digest({key: value for key, value in copied.items() if key != "checksum"})
    job["activation_receipt"] = copied
    assert imports.report(A, replay)["receipt_integrity"] == "changed"


@pytest.mark.parametrize("field", ["rows", "source_evidence", "activated_by"])
def test_receipt_checks_current_job_evidence(field):
    _, _, job_id = activated()
    job = bridge.get(job_id, "BridgeEventJob")
    if field == "rows": job["rows"][0]["values"]["first_name"] = "Changed"
    elif field == "source_evidence": job[field]["byte_count"] += 1
    else: job[field] = "other-actor"
    assert imports.report(A, job_id)["receipt_integrity"] == "changed"
