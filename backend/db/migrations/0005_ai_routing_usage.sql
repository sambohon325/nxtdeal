-- Versioned metadata and evidence only; no model activation or provider calls.
CREATE TABLE nxtdeal.ai_model_revisions (
    workspace_id uuid NOT NULL REFERENCES nxtdeal.workspaces(id),
    model_key text NOT NULL CHECK (length(btrim(model_key)) > 0),
    revision integer NOT NULL CHECK (revision > 0),
    provider text NOT NULL CHECK (length(btrim(provider)) > 0),
    provider_model text NOT NULL CHECK (length(btrim(provider_model)) > 0),
    provider_version text NOT NULL CHECK (length(btrim(provider_version)) > 0),
    capabilities jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(capabilities) = 'object'),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, model_key, revision)
);

CREATE TABLE nxtdeal.ai_route_revisions (
    workspace_id uuid NOT NULL,
    route_key text NOT NULL CHECK (length(btrim(route_key)) > 0),
    revision integer NOT NULL CHECK (revision > 0),
    model_key text NOT NULL,
    model_revision integer NOT NULL,
    enabled boolean NOT NULL DEFAULT false,
    credential_reference_id uuid,
    -- Non-secret options only. Future writers must validate/redact these fields.
    parameters jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(parameters) = 'object'),
    policy_snapshot jsonb NOT NULL CHECK (jsonb_typeof(policy_snapshot) = 'object'),
    recorded_by text NOT NULL CHECK (length(btrim(recorded_by)) > 0),
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    effective_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, route_key, revision),
    FOREIGN KEY (workspace_id, model_key, model_revision)
        REFERENCES nxtdeal.ai_model_revisions(workspace_id, model_key, revision),
    FOREIGN KEY (workspace_id, credential_reference_id)
        REFERENCES nxtdeal.credential_references(workspace_id, id)
);

CREATE TABLE nxtdeal.ai_usage_records (
    workspace_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    route_key text NOT NULL,
    route_revision integer NOT NULL,
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    execution_mode text NOT NULL CHECK (execution_mode IN ('mock','dry_run','live')),
    outcome text NOT NULL CHECK (outcome IN ('succeeded','failed','cancelled','unknown')),
    provider_request_reference text CHECK (length(btrim(provider_request_reference)) > 0),
    -- Unknown measurements stay NULL, never fabricated zeros.
    measurement_basis text NOT NULL CHECK (measurement_basis IN ('reported','estimated','unavailable')),
    input_tokens bigint CHECK (input_tokens >= 0),
    output_tokens bigint CHECK (output_tokens >= 0),
    cost_micros bigint CHECK (cost_micros >= 0),
    currency text CHECK (currency ~ '^[A-Z]{3}$'),
    measurement_source text NOT NULL CHECK (length(btrim(measurement_source)) > 0),
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, route_key, route_revision)
        REFERENCES nxtdeal.ai_route_revisions(workspace_id, route_key, revision),
    CHECK ((cost_micros IS NULL) = (currency IS NULL)),
    CHECK (completed_at IS NULL OR completed_at >= started_at),
    CHECK (outcome = 'unknown' OR completed_at IS NOT NULL),
    CHECK ((measurement_basis = 'unavailable' AND input_tokens IS NULL AND output_tokens IS NULL AND cost_micros IS NULL)
        OR (measurement_basis <> 'unavailable' AND (input_tokens IS NOT NULL OR output_tokens IS NOT NULL OR cost_micros IS NOT NULL)))
);
CREATE INDEX ai_usage_route_time_idx ON nxtdeal.ai_usage_records(workspace_id, route_key, started_at);
CREATE INDEX ai_usage_actor_time_idx ON nxtdeal.ai_usage_records(workspace_id, actor, started_at);

DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['ai_model_revisions','ai_route_revisions','ai_usage_records'] LOOP
        EXECUTE format('ALTER TABLE nxtdeal.%I ENABLE ROW LEVEL SECURITY', tab);
        EXECUTE format('ALTER TABLE nxtdeal.%I FORCE ROW LEVEL SECURITY', tab);
        EXECUTE format('CREATE POLICY workspace_scope ON nxtdeal.%I USING (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid) WITH CHECK (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid)', tab);
        EXECUTE format('CREATE TRIGGER immutable_ai_evidence BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.%I FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation()', tab);
    END LOOP;
END;
$$;
