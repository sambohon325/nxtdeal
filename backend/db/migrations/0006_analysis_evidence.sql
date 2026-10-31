-- Immutable analytical evidence, not an engine implementation or backfill.
CREATE TABLE nxtdeal.input_snapshots (
    workspace_id uuid NOT NULL REFERENCES nxtdeal.workspaces(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    schema_version integer NOT NULL CHECK (schema_version > 0),
    as_of timestamptz NOT NULL,
    captured_at timestamptz NOT NULL DEFAULT now(),
    source text NOT NULL CHECK (length(btrim(source)) > 0),
    -- Digest is writer-computed over a documented canonical serialization.
    content_digest text NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'),
    inputs jsonb NOT NULL CHECK (jsonb_typeof(inputs) = 'object'),
    provenance jsonb NOT NULL CHECK (jsonb_typeof(provenance) = 'object'),
    limitations jsonb NOT NULL CHECK (jsonb_typeof(limitations) = 'array'),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, idempotency_key)
);

CREATE TABLE nxtdeal.model_runs (
    workspace_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    input_snapshot_id uuid NOT NULL,
    engine_key text NOT NULL CHECK (length(btrim(engine_key)) > 0),
    engine_version text NOT NULL CHECK (length(btrim(engine_version)) > 0),
    model_key text NOT NULL CHECK (length(btrim(model_key)) > 0),
    model_version text NOT NULL CHECK (length(btrim(model_version)) > 0),
    adapter_version text NOT NULL CHECK (length(btrim(adapter_version)) > 0),
    runtime_manifest jsonb NOT NULL CHECK (jsonb_typeof(runtime_manifest) = 'object'),
    configuration jsonb NOT NULL CHECK (jsonb_typeof(configuration) = 'object'),
    assumptions jsonb NOT NULL CHECK (jsonb_typeof(assumptions) = 'array'),
    limitations jsonb NOT NULL CHECK (jsonb_typeof(limitations) = 'array'),
    reproducibility text NOT NULL CHECK (reproducibility IN ('deterministic','nondeterministic')),
    random_seed bigint,
    status text NOT NULL CHECK (status IN ('succeeded','failed')),
    outputs jsonb CHECK (jsonb_typeof(outputs) = 'object'),
    error_code text CHECK (length(btrim(error_code)) > 0),
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, id, status),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, input_snapshot_id) REFERENCES nxtdeal.input_snapshots(workspace_id, id),
    CHECK (completed_at >= started_at),
    CHECK ((status = 'succeeded' AND outputs IS NOT NULL AND error_code IS NULL)
        OR (status = 'failed' AND outputs IS NULL AND error_code IS NOT NULL)),
    CHECK (reproducibility <> 'nondeterministic' OR jsonb_array_length(limitations) > 0)
);

CREATE TABLE nxtdeal.predictions (
    workspace_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    model_run_id uuid NOT NULL,
    run_status text NOT NULL DEFAULT 'succeeded' CHECK (run_status = 'succeeded'),
    metric_key text NOT NULL CHECK (length(btrim(metric_key)) > 0),
    subject_reference text NOT NULL CHECK (length(btrim(subject_reference)) > 0),
    unit text NOT NULL CHECK (length(btrim(unit)) > 0),
    horizon_start timestamptz NOT NULL,
    horizon_end timestamptz NOT NULL,
    predicted_value numeric NOT NULL CHECK (predicted_value > '-Infinity'::numeric AND predicted_value < 'Infinity'::numeric),
    basis text NOT NULL DEFAULT 'MODELED' CHECK (basis = 'MODELED'),
    confidence numeric CHECK (confidence >= 0 AND confidence <= 1),
    confidence_kind text NOT NULL CHECK (confidence_kind IN ('unavailable','heuristic','calibrated_probability')),
    calibration_reference text CHECK (length(btrim(calibration_reference)) > 0),
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    limitations jsonb NOT NULL CHECK (jsonb_typeof(limitations) = 'array'),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, model_run_id, run_status) REFERENCES nxtdeal.model_runs(workspace_id, id, status),
    CHECK (horizon_end > horizon_start),
    CHECK ((confidence_kind = 'unavailable') = (confidence IS NULL)),
    CHECK ((confidence_kind = 'calibrated_probability') = (calibration_reference IS NOT NULL))
);
CREATE INDEX predictions_metric_horizon_idx ON nxtdeal.predictions(workspace_id, metric_key, horizon_end);
CREATE INDEX model_runs_snapshot_idx ON nxtdeal.model_runs(workspace_id, input_snapshot_id);

DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['input_snapshots','model_runs','predictions'] LOOP
        EXECUTE format('ALTER TABLE nxtdeal.%I ENABLE ROW LEVEL SECURITY', tab);
        EXECUTE format('ALTER TABLE nxtdeal.%I FORCE ROW LEVEL SECURITY', tab);
        EXECUTE format('CREATE POLICY workspace_scope ON nxtdeal.%I USING (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid) WITH CHECK (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid)', tab);
        EXECUTE format('CREATE TRIGGER immutable_analysis BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.%I FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation()', tab);
    END LOOP;
END;
$$;
