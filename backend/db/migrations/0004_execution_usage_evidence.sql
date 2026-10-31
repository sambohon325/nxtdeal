-- Evidence only. A future transactional service must authorize and reserve
-- capacity before dispatch; these tables do not execute or authorize actions.
ALTER TABLE nxtdeal.approval_decisions ADD CONSTRAINT approval_decisions_binding
    UNIQUE (workspace_id, request_id, sequence, decision);

CREATE TABLE nxtdeal.execution_intents (
    workspace_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    request_id uuid NOT NULL,
    approval_sequence bigint NOT NULL,
    approval_state text NOT NULL DEFAULT 'approved' CHECK (approval_state = 'approved'),
    executor_key text NOT NULL CHECK (length(btrim(executor_key)) > 0),
    execution_mode text NOT NULL CHECK (execution_mode IN ('mock','dry_run','live')),
    -- Reuse this stable key on retries; provider-side idempotency is still required.
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, request_id, approval_sequence, approval_state)
        REFERENCES nxtdeal.approval_decisions(workspace_id, request_id, sequence, decision)
);
CREATE INDEX execution_intents_request_idx ON nxtdeal.execution_intents(workspace_id, request_id);

CREATE TABLE nxtdeal.execution_events (
    workspace_id uuid NOT NULL,
    execution_id uuid NOT NULL,
    sequence bigint NOT NULL CHECK (sequence > 0),
    event_type text NOT NULL CHECK (event_type IN ('dispatched','succeeded','failed','unknown','cancelled')),
    attempt integer NOT NULL CHECK (attempt > 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    -- References/codes only, never raw provider responses or credentials.
    result_reference text CHECK (length(btrim(result_reference)) > 0),
    error_code text CHECK (length(btrim(error_code)) > 0),
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, execution_id, sequence),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, execution_id) REFERENCES nxtdeal.execution_intents(workspace_id, id),
    CHECK (event_type <> 'failed' OR error_code IS NOT NULL)
);

CREATE TABLE nxtdeal.usage_reservations (
    workspace_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    execution_id uuid NOT NULL,
    capability_key text NOT NULL,
    entitlement_revision integer NOT NULL,
    reserved_units bigint NOT NULL CHECK (reserved_units > 0),
    -- Explicit accounting bucket, interpreted using the pinned entitlement's unit/period.
    bucket_key text NOT NULL CHECK (length(btrim(bucket_key)) > 0),
    reserved_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, id, reserved_units),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, execution_id) REFERENCES nxtdeal.execution_intents(workspace_id, id),
    FOREIGN KEY (workspace_id, capability_key, entitlement_revision)
        REFERENCES nxtdeal.entitlement_revisions(workspace_id, capability_key, revision),
    CHECK (expires_at > reserved_at)
);
CREATE INDEX usage_reservations_bucket_idx ON nxtdeal.usage_reservations(workspace_id, capability_key, bucket_key);

CREATE TABLE nxtdeal.usage_settlements (
    workspace_id uuid NOT NULL,
    reservation_id uuid NOT NULL,
    reserved_units bigint NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('consumed','released','expired')),
    consumed_units bigint NOT NULL CHECK (consumed_units >= 0 AND consumed_units <= reserved_units),
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    actor text NOT NULL CHECK (length(btrim(actor)) > 0),
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    -- One immutable terminal settlement prevents duplicate consumption/release.
    PRIMARY KEY (workspace_id, reservation_id),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, reservation_id, reserved_units)
        REFERENCES nxtdeal.usage_reservations(workspace_id, id, reserved_units),
    CHECK (outcome = 'consumed' OR consumed_units = 0)
);

DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['execution_intents','execution_events','usage_reservations','usage_settlements'] LOOP
        EXECUTE format('ALTER TABLE nxtdeal.%I ENABLE ROW LEVEL SECURITY', tab);
        EXECUTE format('ALTER TABLE nxtdeal.%I FORCE ROW LEVEL SECURITY', tab);
        EXECUTE format('CREATE POLICY workspace_scope ON nxtdeal.%I USING (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid) WITH CHECK (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid)', tab);
        EXECUTE format('CREATE TRIGGER immutable_execution_usage BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.%I FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation()', tab);
    END LOOP;
END;
$$;
