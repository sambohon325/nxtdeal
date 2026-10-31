"""Reject incomplete or drifting synthetic image/source evidence."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location('synthetic_provenance', Path(__file__).resolve().parents[2] / 'scripts/check_synthetic_provenance.py')
provenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provenance)
REVISION = 'a' * 40


def records():
    return {name: {'image_id': 'sha256:' + str(i) * 64, 'revision': REVISION,
                   'source': provenance.SOURCE} for i, name in enumerate(provenance.SERVICES)}


def test_complete_build_labels_are_explicitly_not_attestation():
    report = provenance.validate(records(), REVISION)
    assert report['evidence_type'] == 'build_labels_not_signed_attestation'
    assert provenance.validate(records(), REVISION, report) == report


@pytest.mark.parametrize('key,value', [('revision', 'unknown'), ('revision', 'b' * 40),
                                     ('source', 'https://example.test/other'), ('image_id', 'tag:latest')])
def test_wrong_source_or_non_content_image_id_rejected(key, value):
    data = records()
    data['web'][key] = value
    with pytest.raises(ValueError):
        provenance.validate(data, REVISION)


def test_missing_service_and_abbreviated_commit_rejected():
    data = records()
    del data['seed']
    with pytest.raises(ValueError):
        provenance.validate(data, REVISION)
    with pytest.raises(ValueError):
        provenance.validate(records(), 'a' * 7)


def test_recreation_cannot_silently_change_image_with_same_source_label():
    before = provenance.validate(records(), REVISION)
    after = records()
    after['dealer']['image_id'] = 'sha256:' + 'f' * 64
    with pytest.raises(ValueError, match='recreation changed'):
        provenance.validate(after, REVISION, before)


def test_collect_reads_container_image_and_only_named_metadata():
    data = records()
    replies = []
    for service in provenance.SERVICES:
        replies.extend(['c' * 64, data[service]['image_id'], json.dumps(data[service])])
    with patch.object(provenance, 'command', side_effect=replies) as run:
        assert provenance.collect() == data
    assert len(run.call_args_list) == 15
    for i, service in enumerate(provenance.SERVICES):
        assert run.call_args_list[i * 3].args == ('docker', 'compose', 'ps', '--all', '--quiet', service)
        assert run.call_args_list[i * 3 + 1].args[-2:] == ('{{.Image}}', 'c' * 64)
        assert run.call_args_list[i * 3 + 2].args[-2:] == (provenance.IMAGE_FORMAT, data[service]['image_id'])


def test_collect_rejects_ambiguous_service_before_inspection():
    with patch.object(provenance, 'command', return_value='a' * 64 + '\n' + 'b' * 64) as run:
        with pytest.raises(ValueError, match='exactly one'):
            provenance.collect()
    assert run.call_count == 1
