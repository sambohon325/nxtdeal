"""Narrow finance replay compatibility backed by the prior bundle's file hashes."""
import hashlib
import json
from pathlib import Path

SHARED = Path(__file__).parents[2] / 'chrono/shared'
EVIDENCE = json.loads(Path(__file__).with_name('finance_replay_compatibility.json').read_text())


def unchanged_bundle(saved_commit):
    expected = EVIDENCE.get(saved_commit)
    if not expected:
        return False
    try:
        return all(hashlib.sha256((SHARED / name).read_bytes()).hexdigest() == digest
                   for name, digest in expected.items())
    except OSError:
        return False
