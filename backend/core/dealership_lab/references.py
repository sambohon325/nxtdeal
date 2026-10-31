"""Read-only dated public references for an employee-owned saved model."""
import hashlib
import json
from pathlib import Path
from fastapi import HTTPException
from chrono.shared.dealership import peers
from . import service as lab, analysis


def describe(key, actor, revision):
    with lab.LOCK:
        workspace = lab.serial(lab.workspace(key, actor))
        if workspace['revision'] != revision:
            raise HTTPException(409, 'This model changed. Reload before viewing references.')
        model = analysis.compile_inputs(workspace)
    root = Path(peers.__file__).parent
    return dict(workspace_id=key, revision=revision, name=workspace['name'],
                source_hash=lab.digest(model), shared_engine_commit=analysis.SHARED_VERSION,
                reference_hash=hashlib.sha256((root/'peer_data.json').read_bytes()).hexdigest(),
                provenance=json.loads((root/'PEER_SOURCE.json').read_text()),
                basis='Historical public employer aggregates; modeled baseline staff and inventory. No automatic adoption.',
                comparison=peers.comparison(model))
