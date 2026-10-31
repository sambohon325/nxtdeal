"""Record synthetic container image IDs and verify declared source revisions.

Labels are build metadata, not signed provenance or production parity evidence.
Only image IDs and the two named OCI labels are inspected; no environment is read.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

SERVICES = ('seed', 'dealer', 'hub', 'web', 'gateway')
SOURCE = 'https://github.com/sambohon325/dealerOS'
IMAGE_FORMAT = ('{"image_id":{{json .Id}},'
                '"revision":{{json (index .Config.Labels "org.opencontainers.image.revision")}},'
                '"source":{{json (index .Config.Labels "org.opencontainers.image.source")}}}')


def command(*args):
    return subprocess.check_output(args, text=True, timeout=30).strip()


def validate(records, expected_revision, baseline=None):
    if not re.fullmatch(r'[0-9a-f]{40}', expected_revision):
        raise ValueError('Expected a complete Git commit ID')
    if set(records) != set(SERVICES):
        raise ValueError('Expected all five synthetic services')
    for service, record in records.items():
        if record.get('revision') != expected_revision or record.get('source') != SOURCE:
            raise ValueError(f'{service}: source labels do not match the tested checkout')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', record.get('image_id', '')):
            raise ValueError(f'{service}: missing image content ID')
    report = {'scope': 'synthetic_only', 'source_revision': expected_revision,
              'evidence_type': 'build_labels_not_signed_attestation', 'services': records}
    if baseline is not None and report != baseline:
        raise ValueError('Container recreation changed image identity or source metadata')
    return report


def collect():
    records = {}
    for service in SERVICES:
        containers = command('docker', 'compose', 'ps', '--all', '--quiet', service).splitlines()
        if len(containers) != 1 or not re.fullmatch(r'[0-9a-f]{12,64}', containers[0]):
            raise ValueError(f'{service}: expected exactly one synthetic container')
        image_id = command('docker', 'inspect', '--type', 'container', '--format', '{{.Image}}', containers[0])
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
            raise ValueError(f'{service}: invalid container image ID')
        records[service] = json.loads(command('docker', 'image', 'inspect', '--format', IMAGE_FORMAT, image_id))
        if records[service].get('image_id') != image_id:
            raise ValueError(f'{service}: inspected image ID changed')
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text()) if args.baseline else None
    report = validate(collect(), args.expected_revision, baseline)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Synthetic image revisions and content IDs verified.')


if __name__ == '__main__':
    main()
