-- Test-stage journal: no application grants or runtime activation.
CREATE TABLE nxtdeal.shadow_preparations (
    workspace_id uuid NOT NULL REFERENCES nxtdeal.workspaces(id),
    generation bigint NOT NULL CHECK (generation > 0),
    operation_id uuid NOT NULL,
    predecessor bigint,
    snapshot bytea NOT NULL CHECK (octet_length(snapshot) BETWEEN 1 AND 33554432),
    semantic_digest text NOT NULL CHECK (semantic_digest ~ '^[0-9a-f]{64}$'),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id,generation),
    UNIQUE (workspace_id,operation_id),
    UNIQUE (workspace_id,generation,operation_id,semantic_digest),
    CHECK ((generation = 1 AND predecessor IS NULL) OR
           (generation > 1 AND predecessor IS NOT NULL AND predecessor = generation - 1))
);
CREATE TABLE nxtdeal.shadow_commits (
    workspace_id uuid NOT NULL,
    generation bigint NOT NULL,
    operation_id uuid NOT NULL,
    semantic_digest text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id,generation),
    FOREIGN KEY (workspace_id,generation,operation_id,semantic_digest)
        REFERENCES nxtdeal.shadow_preparations(workspace_id,generation,operation_id,semantic_digest)
);
-- A new preparation cannot skip an unresolved predecessor.
ALTER TABLE nxtdeal.shadow_preparations ADD CONSTRAINT committed_predecessor
    FOREIGN KEY (workspace_id,predecessor) REFERENCES nxtdeal.shadow_commits(workspace_id,generation);
ALTER TABLE nxtdeal.shadow_preparations ENABLE ROW LEVEL SECURITY;
ALTER TABLE nxtdeal.shadow_preparations FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_scope ON nxtdeal.shadow_preparations
    USING (workspace_id = nullif(current_setting('nxtdeal.workspace_id',true),'')::uuid)
    WITH CHECK (workspace_id = nullif(current_setting('nxtdeal.workspace_id',true),'')::uuid);
ALTER TABLE nxtdeal.shadow_commits ENABLE ROW LEVEL SECURITY;
ALTER TABLE nxtdeal.shadow_commits FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_scope ON nxtdeal.shadow_commits
    USING (workspace_id = nullif(current_setting('nxtdeal.workspace_id',true),'')::uuid)
    WITH CHECK (workspace_id = nullif(current_setting('nxtdeal.workspace_id',true),'')::uuid);
CREATE TRIGGER immutable_shadow_preparations BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.shadow_preparations
FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation();
CREATE TRIGGER immutable_shadow_commits BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.shadow_commits
FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation();
