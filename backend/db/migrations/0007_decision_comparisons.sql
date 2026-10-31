-- Saved comparisons and decision evidence; does not execute interventions.
ALTER TABLE nxtdeal.model_runs ADD CONSTRAINT model_runs_snapshot_binding
    UNIQUE (workspace_id, id, input_snapshot_id, status);

CREATE TABLE nxtdeal.experiments (
    workspace_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    input_snapshot_id uuid NOT NULL,
    baseline_run_id uuid NOT NULL,
    run_status text NOT NULL DEFAULT 'succeeded' CHECK (run_status = 'succeeded'),
    question text NOT NULL CHECK (length(btrim(question)) > 0),
    context jsonb NOT NULL CHECK (jsonb_typeof(context) = 'object'),
    unchanged_variables jsonb NOT NULL CHECK (jsonb_typeof(unchanged_variables) = 'object'),
    assumptions jsonb NOT NULL CHECK (jsonb_typeof(assumptions) = 'array'),
    limitations jsonb NOT NULL CHECK (jsonb_typeof(limitations) = 'array'),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, id, input_snapshot_id),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, baseline_run_id, input_snapshot_id, run_status)
        REFERENCES nxtdeal.model_runs(workspace_id, id, input_snapshot_id, status),
    FOREIGN KEY (workspace_id, created_by) REFERENCES nxtdeal.memberships(workspace_id, account_id)
);

CREATE TABLE nxtdeal.experiment_alternatives (
    workspace_id uuid NOT NULL,
    experiment_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    input_snapshot_id uuid NOT NULL,
    model_run_id uuid NOT NULL,
    run_status text NOT NULL DEFAULT 'succeeded' CHECK (run_status = 'succeeded'),
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    changed_variables jsonb NOT NULL CHECK (jsonb_typeof(changed_variables) = 'object' AND changed_variables <> '{}'::jsonb),
    assumptions jsonb NOT NULL CHECK (jsonb_typeof(assumptions) = 'array'),
    expected_results jsonb NOT NULL CHECK (jsonb_typeof(expected_results) = 'object'),
    estimated_cost_micros bigint CHECK (estimated_cost_micros >= 0),
    currency text CHECK (currency ~ '^[A-Z]{3}$'),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, experiment_id, id),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, experiment_id, input_snapshot_id)
        REFERENCES nxtdeal.experiments(workspace_id, id, input_snapshot_id),
    FOREIGN KEY (workspace_id, model_run_id, input_snapshot_id, run_status)
        REFERENCES nxtdeal.model_runs(workspace_id, id, input_snapshot_id, status),
    CHECK ((estimated_cost_micros IS NULL) = (currency IS NULL))
);

CREATE TABLE nxtdeal.decisions (
    workspace_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    experiment_id uuid NOT NULL,
    sequence bigint NOT NULL CHECK (sequence > 0),
    selection_kind text NOT NULL CHECK (selection_kind IN ('baseline','alternative')),
    selected_alternative_id uuid,
    decided_by uuid NOT NULL,
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    authority_snapshot jsonb NOT NULL CHECK (jsonb_typeof(authority_snapshot) = 'object'),
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, experiment_id, sequence),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, experiment_id) REFERENCES nxtdeal.experiments(workspace_id, id),
    FOREIGN KEY (workspace_id, experiment_id, selected_alternative_id)
        REFERENCES nxtdeal.experiment_alternatives(workspace_id, experiment_id, id),
    FOREIGN KEY (workspace_id, decided_by) REFERENCES nxtdeal.memberships(workspace_id, account_id),
    CHECK ((selection_kind = 'baseline') = (selected_alternative_id IS NULL))
);

DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['experiments','experiment_alternatives','decisions'] LOOP
        EXECUTE format('ALTER TABLE nxtdeal.%I ENABLE ROW LEVEL SECURITY', tab);
        EXECUTE format('ALTER TABLE nxtdeal.%I FORCE ROW LEVEL SECURITY', tab);
        EXECUTE format('CREATE POLICY workspace_scope ON nxtdeal.%I USING (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid) WITH CHECK (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid)', tab);
        EXECUTE format('CREATE TRIGGER immutable_decision BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.%I FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation()', tab);
    END LOOP;
END;
$$;
