"""Immutable source capture and policy-bound manifest for a future DB writer."""
from dataclasses import dataclass, field
import hashlib
import json
from uuid import UUID

from db.import_preflight import decode_source, preflight, read_source_bytes


class ImportRejected(ValueError):
    """Fixed error codes only: never include input payloads, paths or credentials."""


@dataclass(frozen=True)
class ImportPackage:
    workspace_id: str
    audit_policy: str
    graph_bytes: bytes = field(repr=False)
    audit_bytes: bytes | None = field(default=None, repr=False)
    checkpoint_bytes: bytes | None = field(default=None, repr=False)

    def validate(self):
        if self.audit_policy not in ('strict', 'acknowledge_limited', 'graph_only'):
            raise ImportRejected('invalid_audit_policy')
        if any(type(value) is not bytes for value in (self.graph_bytes, self.audit_bytes, self.checkpoint_bytes) if value is not None):
            raise ImportRejected('immutable_bytes_required')
        if self.graph_bytes is None:
            raise ImportRejected('graph_required')
        try:
            workspace = str(UUID(self.workspace_id))
        except (ValueError, AttributeError, TypeError):
            raise ImportRejected('invalid_workspace_uuid') from None
        sources = {'graph':self.graph_bytes, 'audit':self.audit_bytes, 'checkpoint':self.checkpoint_bytes}
        report = preflight('graph', workspace,
            'audit' if self.audit_bytes is not None else None,
            'checkpoint' if self.checkpoint_bytes is not None else None,
            _reader=lambda name, **options: decode_source(sources[name], **options))
        if not report['valid']:
            raise ImportRejected('source_discrepancies')
        if self.audit_policy == 'graph_only':
            if self.audit_bytes is not None or self.checkpoint_bytes is not None:
                raise ImportRejected('graph_only_excludes_audit')
        elif self.audit_bytes is None:
            raise ImportRejected('audit_required')
        elif self.audit_policy == 'strict' and report['audit_integrity'] not in ('chain_and_checkpoint_match','empty'):
            raise ImportRejected('audit_evidence_incomplete')
        return report

    def manifest(self):
        report = self.validate()
        # Only immutable source identity and recorded policy enter the manifest.
        # No filenames, customer attributes, event IDs, timestamps or credentials.
        manifest = {'format_version':1, 'workspace_id':report['workspace_id'],
                    'audit_policy':self.audit_policy, 'audit_integrity':report['audit_integrity'],
                    'sources':report['sources'], 'counts':report['counts']}
        encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode('utf-8')
        return {**manifest, 'manifest_sha256':hashlib.sha256(encoded).hexdigest()}

    def payloads(self):
        self.validate()
        # Fresh exact-decimal trees; modifying a returned tree cannot modify capture.
        graph = decode_source(self.graph_bytes)[0]
        audit = decode_source(self.audit_bytes)[0] if self.audit_bytes is not None else None
        return graph, audit


def prepare_import(graph_path, workspace_id, *, audit_path=None, checkpoint_path=None, audit_policy='strict'):
    """Capture each supplied file once, then validate only the captured bytes.

    A manifest is not target authorization. Future writers must revalidate the
    package and separately authorize workspace/database scope before any writes.
    """
    try:
        graph = read_source_bytes(graph_path)
        audit = read_source_bytes(audit_path) if audit_path is not None else None
        checkpoint = read_source_bytes(checkpoint_path) if checkpoint_path is not None else None
    except (OSError, ValueError):
        raise ImportRejected('source_capture_failed') from None
    package = ImportPackage(workspace_id, audit_policy, graph, audit, checkpoint)
    package.validate()
    return package
