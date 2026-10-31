-- Intended actions and later observations remain separate from predictions.
ALTER TABLE nxtdeal.decisions ADD CONSTRAINT decisions_selection_binding
    UNIQUE (workspace_id, id, experiment_id, selected_alternative_id);

CREATE TABLE nxtdeal.interventions (
    workspace_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    decision_id uuid NOT NULL,
    experiment_id uuid NOT NULL,
    alternative_id uuid NOT NULL,
    -- Historical references to existing dealership systems of record, not new goals.
    initiative_reference text CHECK (length(btrim(initiative_reference)) > 0),
    objective_reference text CHECK (length(btrim(objective_reference)) > 0),
    intended_action jsonb NOT NULL CHECK (jsonb_typeof(intended_action) = 'object' AND intended_action <> '{}'::jsonb),
    planned_start timestamptz NOT NULL,
    planned_end timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, decision_id, experiment_id, alternative_id)
        REFERENCES nxtdeal.decisions(workspace_id, id, experiment_id, selected_alternative_id),
    CHECK (planned_end > planned_start)
);

CREATE TABLE nxtdeal.intervention_events (
    workspace_id uuid NOT NULL,
    intervention_id uuid NOT NULL,
    sequence bigint NOT NULL CHECK (sequence > 0),
    event_type text NOT NULL CHECK (event_type IN ('scheduled','started','completed','cancelled','failed','unknown')),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    source text NOT NULL CHECK (length(btrim(source)) > 0),
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    domain_event_id uuid,
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, intervention_id, sequence),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, intervention_id) REFERENCES nxtdeal.interventions(workspace_id, id),
    FOREIGN KEY (workspace_id, domain_event_id) REFERENCES nxtdeal.events(workspace_id, id)
);

CREATE TABLE nxtdeal.outcome_observations (
    workspace_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    -- The target metric, subject, unit and horizon are inherited from this prediction.
    prediction_id uuid NOT NULL,
    evidence_snapshot_id uuid NOT NULL,
    observed_value numeric NOT NULL CHECK (observed_value > '-Infinity'::numeric AND observed_value < 'Infinity'::numeric),
    basis text NOT NULL CHECK (basis IN ('ACTUAL','DERIVED')),
    source text NOT NULL CHECK (length(btrim(source)) > 0),
    method_version text NOT NULL CHECK (length(btrim(method_version)) > 0),
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    limitations jsonb NOT NULL CHECK (jsonb_typeof(limitations) = 'array'),
    observed_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    -- A correction appends a new record; a chain cannot branch or change its target.
    supersedes_id uuid,
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    supersedes_revision integer,
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, id, prediction_id, revision),
    UNIQUE (workspace_id, supersedes_id),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, prediction_id) REFERENCES nxtdeal.predictions(workspace_id, id),
    FOREIGN KEY (workspace_id, evidence_snapshot_id) REFERENCES nxtdeal.input_snapshots(workspace_id, id),
    FOREIGN KEY (workspace_id, supersedes_id, prediction_id, supersedes_revision)
        REFERENCES nxtdeal.outcome_observations(workspace_id, id, prediction_id, revision),
    CHECK ((supersedes_id IS NULL AND supersedes_revision IS NULL AND revision = 1)
        OR (supersedes_id IS NOT NULL AND supersedes_revision IS NOT NULL AND supersedes_revision > 0 AND revision - 1 = supersedes_revision)),
    CHECK (supersedes_id IS NULL OR supersedes_id <> id)
);
CREATE INDEX outcome_observations_prediction_idx ON nxtdeal.outcome_observations(workspace_id, prediction_id);

DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['interventions','intervention_events','outcome_observations'] LOOP
        EXECUTE format('ALTER TABLE nxtdeal.%I ENABLE ROW LEVEL SECURITY', tab);
        EXECUTE format('ALTER TABLE nxtdeal.%I FORCE ROW LEVEL SECURITY', tab);
        EXECUTE format('CREATE POLICY workspace_scope ON nxtdeal.%I USING (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid) WITH CHECK (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid)', tab);
        EXECUTE format('CREATE TRIGGER immutable_outcome BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.%I FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation()', tab);
    END LOOP;
END;
$$;
