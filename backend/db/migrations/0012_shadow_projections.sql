-- Isolated whole-graph shadow projections; not canonical entity storage.
CREATE TABLE nxtdeal.shadow_projections (
    workspace_id uuid NOT NULL,
    generation bigint NOT NULL,
    predecessor bigint,
    graph jsonb NOT NULL CHECK (jsonb_typeof(graph) = 'object'),
    semantic_digest text NOT NULL CHECK (semantic_digest ~ '^[0-9a-f]{64}$'),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id,generation),
    FOREIGN KEY (workspace_id,generation) REFERENCES nxtdeal.shadow_commits(workspace_id,generation),
    FOREIGN KEY (workspace_id,predecessor) REFERENCES nxtdeal.shadow_projections(workspace_id,generation),
    CHECK ((generation = 1 AND predecessor IS NULL) OR
           (generation > 1 AND predecessor IS NOT NULL AND predecessor = generation - 1))
);
ALTER TABLE nxtdeal.shadow_projections ENABLE ROW LEVEL SECURITY;
ALTER TABLE nxtdeal.shadow_projections FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_scope ON nxtdeal.shadow_projections
    USING (workspace_id = nullif(current_setting('nxtdeal.workspace_id',true),'')::uuid)
    WITH CHECK (workspace_id = nullif(current_setting('nxtdeal.workspace_id',true),'')::uuid);
CREATE TRIGGER immutable_shadow_projections BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.shadow_projections
FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation();
