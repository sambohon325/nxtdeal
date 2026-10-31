-- Release evidence only: no artifact download, engine activation or deployment.
CREATE TABLE nxtdeal.chrono_releases (
    workspace_id uuid NOT NULL REFERENCES nxtdeal.workspaces(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    engine_version text NOT NULL CHECK (length(btrim(engine_version)) > 0),
    adapter_version text NOT NULL CHECK (length(btrim(adapter_version)) > 0),
    contract_version text NOT NULL CHECK (length(btrim(contract_version)) > 0),
    artifact_reference text NOT NULL CHECK (length(btrim(artifact_reference)) > 0),
    artifact_digest text NOT NULL CHECK (artifact_digest ~ '^[0-9a-f]{64}$'),
    configuration jsonb NOT NULL CHECK (jsonb_typeof(configuration) = 'object'),
    configuration_digest text NOT NULL CHECK (configuration_digest ~ '^[0-9a-f]{64}$'),
    changelog_reference text NOT NULL CHECK (length(btrim(changelog_reference)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, idempotency_key)
);

CREATE TABLE nxtdeal.chrono_release_checks (
    workspace_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    release_id uuid NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('passed','failed')),
    compatibility_passed boolean NOT NULL,
    staging_passed boolean NOT NULL,
    automotive_regression_passed boolean NOT NULL,
    suite_version text NOT NULL CHECK (length(btrim(suite_version)) > 0),
    evidence_reference text NOT NULL CHECK (length(btrim(evidence_reference)) > 0),
    evidence_digest text NOT NULL CHECK (evidence_digest ~ '^[0-9a-f]{64}$'),
    started_at timestamptz NOT NULL,
    completed_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, id, release_id, outcome),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, release_id) REFERENCES nxtdeal.chrono_releases(workspace_id, id),
    CHECK (completed_at >= started_at),
    CHECK ((outcome = 'passed') = (compatibility_passed AND staging_passed AND automotive_regression_passed))
);

CREATE TABLE nxtdeal.chrono_release_authorizations (
    workspace_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    release_id uuid NOT NULL,
    check_id uuid NOT NULL,
    check_outcome text NOT NULL DEFAULT 'passed' CHECK (check_outcome = 'passed'),
    request_id uuid NOT NULL,
    approval_sequence bigint NOT NULL,
    approval_state text NOT NULL DEFAULT 'approved' CHECK (approval_state = 'approved'),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, id, release_id),
    -- One logical approval request cannot authorize different release bundles.
    UNIQUE (workspace_id, request_id),
    FOREIGN KEY (workspace_id, check_id, release_id, check_outcome)
        REFERENCES nxtdeal.chrono_release_checks(workspace_id, id, release_id, outcome),
    FOREIGN KEY (workspace_id, request_id, approval_sequence, approval_state)
        REFERENCES nxtdeal.approval_decisions(workspace_id, request_id, sequence, decision)
);

CREATE TABLE nxtdeal.chrono_deployments (
    workspace_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    release_id uuid NOT NULL,
    authorization_id uuid NOT NULL,
    action text NOT NULL CHECK (action IN ('install','upgrade','rollback')),
    -- Records production attempts only; staging is evidence on the check record.
    outcome text NOT NULL CHECK (outcome IN ('succeeded','failed','unknown')),
    rollback_target_id uuid,
    rollback_target_outcome text NOT NULL DEFAULT 'succeeded' CHECK (rollback_target_outcome = 'succeeded'),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    evidence_reference text NOT NULL CHECK (length(btrim(evidence_reference)) > 0),
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, id, release_id, outcome),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, authorization_id, release_id)
        REFERENCES nxtdeal.chrono_release_authorizations(workspace_id, id, release_id),
    FOREIGN KEY (workspace_id, rollback_target_id, release_id, rollback_target_outcome)
        REFERENCES nxtdeal.chrono_deployments(workspace_id, id, release_id, outcome),
    CHECK ((action = 'rollback') = (rollback_target_id IS NOT NULL)),
    CHECK (rollback_target_id IS NULL OR rollback_target_id <> id),
    CHECK (completed_at IS NULL OR completed_at >= started_at),
    CHECK (outcome = 'unknown' OR completed_at IS NOT NULL)
);

DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['chrono_releases','chrono_release_checks','chrono_release_authorizations','chrono_deployments'] LOOP
        EXECUTE format('ALTER TABLE nxtdeal.%I ENABLE ROW LEVEL SECURITY', tab);
        EXECUTE format('ALTER TABLE nxtdeal.%I FORCE ROW LEVEL SECURITY', tab);
        EXECUTE format('CREATE POLICY workspace_scope ON nxtdeal.%I USING (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid) WITH CHECK (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid)', tab);
        EXECUTE format('CREATE TRIGGER immutable_release_evidence BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.%I FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation()', tab);
    END LOOP;
END;
$$;
