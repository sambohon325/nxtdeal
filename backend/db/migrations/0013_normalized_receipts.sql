CREATE TABLE nxtdeal.normalized_receipts (
    workspace_id uuid NOT NULL,
    generation bigint NOT NULL,
    PRIMARY KEY(workspace_id,generation),
    FOREIGN KEY(workspace_id,generation) REFERENCES nxtdeal.shadow_projections(workspace_id,generation)
);
ALTER TABLE nxtdeal.normalized_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE nxtdeal.normalized_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY workspace_scope ON nxtdeal.normalized_receipts
    USING (workspace_id = nullif(current_setting('nxtdeal.workspace_id',true),'')::uuid)
    WITH CHECK (workspace_id = nullif(current_setting('nxtdeal.workspace_id',true),'')::uuid);
CREATE TRIGGER immutable_normalized_receipts BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.normalized_receipts
FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation();
