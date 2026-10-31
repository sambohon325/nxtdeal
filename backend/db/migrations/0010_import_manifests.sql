-- Immutable proof and reconstruction metadata for controlled legacy imports.
CREATE TABLE nxtdeal.import_manifests (
    workspace_id uuid PRIMARY KEY REFERENCES nxtdeal.workspaces(id),
    manifest_digest text NOT NULL CHECK (manifest_digest ~ '^[0-9a-f]{64}$'),
    manifest jsonb NOT NULL CHECK (jsonb_typeof(manifest) = 'object'),
    entity_order jsonb NOT NULL CHECK (jsonb_typeof(entity_order) = 'array'),
    relationship_fields jsonb NOT NULL CHECK (jsonb_typeof(relationship_fields) = 'array'),
    audit_order jsonb NOT NULL CHECK (jsonb_typeof(audit_order) = 'array'),
    recorded_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE nxtdeal.import_manifests ENABLE ROW LEVEL SECURITY;
ALTER TABLE nxtdeal.import_manifests FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_scope ON nxtdeal.import_manifests
    USING (workspace_id = nullif(current_setting('nxtdeal.workspace_id', true), '')::uuid)
    WITH CHECK (workspace_id = nullif(current_setting('nxtdeal.workspace_id', true), '')::uuid);
CREATE TRIGGER immutable_import_manifest BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.import_manifests
FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation();
