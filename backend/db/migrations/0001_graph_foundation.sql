-- No application role or public grants are created by this migration.
CREATE SCHEMA nxtdeal;
REVOKE ALL ON SCHEMA nxtdeal FROM PUBLIC;

CREATE TABLE nxtdeal.organizations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE nxtdeal.workspaces (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES nxtdeal.organizations(id),
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX workspaces_organization_idx ON nxtdeal.workspaces(organization_id);
CREATE TABLE nxtdeal.accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject text NOT NULL UNIQUE CHECK (length(btrim(subject)) > 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE nxtdeal.memberships (
    workspace_id uuid NOT NULL REFERENCES nxtdeal.workspaces(id),
    account_id uuid NOT NULL REFERENCES nxtdeal.accounts(id),
    role text NOT NULL CHECK (length(btrim(role)) > 0),
    revoked_at timestamptz,
    PRIMARY KEY (workspace_id, account_id)
);
CREATE TABLE nxtdeal.rooftops (
    workspace_id uuid NOT NULL REFERENCES nxtdeal.workspaces(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    PRIMARY KEY (workspace_id, id)
);
CREATE TABLE nxtdeal.entities (
    workspace_id uuid NOT NULL REFERENCES nxtdeal.workspaces(id),
    id text NOT NULL CHECK (length(id) > 0),
    internal_id bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    entity_type text NOT NULL CHECK (length(entity_type) > 0),
    attributes jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(attributes) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, id)
);
CREATE INDEX entities_type_idx ON nxtdeal.entities(workspace_id, entity_type);
CREATE TABLE nxtdeal.relationships (
    workspace_id uuid NOT NULL REFERENCES nxtdeal.workspaces(id),
    id bigint GENERATED ALWAYS AS IDENTITY,
    source_id text NOT NULL,
    target_id text NOT NULL,
    relationship_type text NOT NULL CHECK (length(relationship_type) > 0),
    position bigint NOT NULL CHECK (position >= 0),
    -- Original provenance is preserved verbatim, including legacy timestamp strings.
    created_by text,
    created_at text,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, position),
    FOREIGN KEY (workspace_id, source_id) REFERENCES nxtdeal.entities(workspace_id, id),
    FOREIGN KEY (workspace_id, target_id) REFERENCES nxtdeal.entities(workspace_id, id)
);
CREATE INDEX relationships_source_idx ON nxtdeal.relationships(workspace_id, source_id);
CREATE INDEX relationships_target_idx ON nxtdeal.relationships(workspace_id, target_id);
CREATE INDEX relationships_type_idx ON nxtdeal.relationships(workspace_id, relationship_type);

CREATE TABLE nxtdeal.events (
    workspace_id uuid NOT NULL REFERENCES nxtdeal.workspaces(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    entity_id text,
    entity_type text,
    event_type text NOT NULL CHECK (length(event_type) > 0),
    schema_version integer NOT NULL CHECK (schema_version > 0),
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    actor text,
    source text NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    provenance jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(provenance) = 'object'),
    correlation_id text,
    causation_id text,
    idempotency_key text,
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, idempotency_key)
    -- Historical entity IDs need not exist in today's graph; do not fabricate entities.
);
CREATE INDEX events_type_time_idx ON nxtdeal.events(workspace_id, event_type, occurred_at);
CREATE INDEX events_entity_time_idx ON nxtdeal.events(workspace_id, entity_id, occurred_at);
CREATE TABLE nxtdeal.audit_events (
    workspace_id uuid NOT NULL REFERENCES nxtdeal.workspaces(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    action text NOT NULL,
    actor text,
    occurred_at timestamptz NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    PRIMARY KEY (workspace_id, id)
);
CREATE INDEX audit_events_time_idx ON nxtdeal.audit_events(workspace_id, occurred_at);

CREATE FUNCTION nxtdeal.reject_history_mutation() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    RAISE EXCEPTION 'History is append-only; record a correction event' USING ERRCODE = '55000';
END;
$$;
CREATE TRIGGER immutable_events BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.events
FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation();
CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.audit_events
FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation();

-- Defense in depth only: the future server must authorize membership BEFORE setting
-- this transaction-local context. It is not an authentication mechanism.
DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['memberships','rooftops','entities','relationships','events','audit_events'] LOOP
        EXECUTE format('ALTER TABLE nxtdeal.%I ENABLE ROW LEVEL SECURITY', tab);
        EXECUTE format('ALTER TABLE nxtdeal.%I FORCE ROW LEVEL SECURITY', tab);
        EXECUTE format('CREATE POLICY workspace_scope ON nxtdeal.%I USING (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid) WITH CHECK (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid)', tab);
    END LOOP;
END;
$$;
