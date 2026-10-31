-- Proposed governance evidence only: no runtime permissions or feature changes.
-- Future trusted writers must validate membership, authority, policy and consent.
CREATE TABLE nxtdeal.approval_requests (
    workspace_id uuid NOT NULL REFERENCES nxtdeal.workspaces(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    action_key text NOT NULL CHECK (length(btrim(action_key)) > 0),
    revision integer NOT NULL CHECK (revision > 0),
    action_type text NOT NULL CHECK (length(btrim(action_type)) > 0),
    requested_by text NOT NULL CHECK (length(btrim(requested_by)) > 0),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    -- The future writer must compute this from a defined canonical serialization.
    payload_digest text NOT NULL CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
    policy_key text NOT NULL CHECK (length(btrim(policy_key)) > 0),
    policy_revision integer NOT NULL CHECK (policy_revision > 0),
    policy_snapshot jsonb NOT NULL CHECK (jsonb_typeof(policy_snapshot) = 'object'),
    risk_level text NOT NULL CHECK (risk_level IN ('low','medium','high','critical')),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, action_key, revision),
    UNIQUE (workspace_id, idempotency_key),
    CHECK (expires_at > created_at)
);
CREATE INDEX approval_requests_action_idx ON nxtdeal.approval_requests(workspace_id, action_type, created_at);

CREATE TABLE nxtdeal.approval_decisions (
    workspace_id uuid NOT NULL,
    request_id uuid NOT NULL,
    sequence bigint NOT NULL CHECK (sequence > 0),
    decision text NOT NULL CHECK (decision IN ('approved','rejected','revoked')),
    decided_by uuid NOT NULL,
    authority_snapshot jsonb NOT NULL CHECK (jsonb_typeof(authority_snapshot) = 'object'),
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, request_id, sequence),
    UNIQUE (workspace_id, idempotency_key),
    FOREIGN KEY (workspace_id, request_id) REFERENCES nxtdeal.approval_requests(workspace_id, id),
    FOREIGN KEY (workspace_id, decided_by) REFERENCES nxtdeal.memberships(workspace_id, account_id)
);
CREATE INDEX approval_decisions_actor_idx ON nxtdeal.approval_decisions(workspace_id, decided_by, occurred_at);

CREATE TABLE nxtdeal.entitlement_revisions (
    workspace_id uuid NOT NULL REFERENCES nxtdeal.workspaces(id),
    capability_key text NOT NULL CHECK (length(btrim(capability_key)) > 0),
    revision integer NOT NULL CHECK (revision > 0),
    enabled boolean NOT NULL DEFAULT false,
    feature_level text NOT NULL CHECK (feature_level IN ('free','professional','enterprise')),
    -- NULL explicitly means unlimited; zero is a real zero quota.
    quota_limit bigint CHECK (quota_limit >= 0),
    quota_unit text NOT NULL CHECK (length(btrim(quota_unit)) > 0),
    quota_period text NOT NULL CHECK (quota_period IN ('concurrent','day','month','lifetime')),
    effective_at timestamptz NOT NULL,
    expires_at timestamptz,
    granted_by text NOT NULL CHECK (length(btrim(granted_by)) > 0),
    authority_snapshot jsonb NOT NULL CHECK (jsonb_typeof(authority_snapshot) = 'object'),
    reason text NOT NULL CHECK (length(btrim(reason)) > 0),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    PRIMARY KEY (workspace_id, capability_key, revision),
    UNIQUE (workspace_id, idempotency_key),
    CHECK (expires_at IS NULL OR expires_at > effective_at)
);
CREATE INDEX entitlement_revisions_effective_idx ON nxtdeal.entitlement_revisions(workspace_id, capability_key, effective_at);

DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['approval_requests','approval_decisions','entitlement_revisions'] LOOP
        EXECUTE format('ALTER TABLE nxtdeal.%I ENABLE ROW LEVEL SECURITY', tab);
        EXECUTE format('ALTER TABLE nxtdeal.%I FORCE ROW LEVEL SECURITY', tab);
        EXECUTE format('CREATE POLICY workspace_scope ON nxtdeal.%I USING (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid) WITH CHECK (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid)', tab);
        EXECUTE format('CREATE TRIGGER immutable_governance BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.%I FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation()', tab);
    END LOOP;
END;
$$;
