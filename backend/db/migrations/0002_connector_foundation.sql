-- Metadata only. Secret material belongs in an external managed secret store.
-- No adapters, application grants, credential resolution, or runtime activation.
CREATE TABLE nxtdeal.credential_references (
    workspace_id uuid NOT NULL REFERENCES nxtdeal.workspaces(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    secret_store text NOT NULL CHECK (length(btrim(secret_store)) > 0),
    secret_reference text NOT NULL CHECK (length(btrim(secret_reference)) > 0),
    secret_version text NOT NULL CHECK (length(btrim(secret_version)) > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    PRIMARY KEY (workspace_id, id),
    UNIQUE (workspace_id, secret_store, secret_reference, secret_version),
    CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);
CREATE TABLE nxtdeal.integrations (
    workspace_id uuid NOT NULL REFERENCES nxtdeal.workspaces(id),
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    name text NOT NULL CHECK (length(btrim(name)) > 0),
    provider text NOT NULL CHECK (length(btrim(provider)) > 0),
    category text NOT NULL CHECK (length(btrim(category)) > 0),
    method text NOT NULL CHECK (method IN ('csv','api','webhook','sftp','warehouse')),
    direction text NOT NULL CHECK (direction IN ('inbound','outbound','bidirectional')),
    cadence text NOT NULL CHECK (cadence IN ('manual','scheduled','event')),
    schedule_expression text,
    enabled boolean NOT NULL DEFAULT false,
    health text NOT NULL DEFAULT 'unknown' CHECK (health IN ('unknown','healthy','degraded','error')),
    credential_reference_id uuid,
    -- Non-secret connection options only; future writers must validate/redact.
    configuration jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(configuration) = 'object'),
    last_sync_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, id),
    FOREIGN KEY (workspace_id, credential_reference_id) REFERENCES nxtdeal.credential_references(workspace_id, id),
    CHECK ((cadence = 'scheduled' AND schedule_expression IS NOT NULL AND length(btrim(schedule_expression)) > 0)
        OR (cadence <> 'scheduled' AND schedule_expression IS NULL))
);
CREATE INDEX integrations_provider_idx ON nxtdeal.integrations(workspace_id, provider);
CREATE TABLE nxtdeal.integration_mappings (
    workspace_id uuid NOT NULL,
    integration_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    entity_type text NOT NULL CHECK (length(btrim(entity_type)) > 0),
    definition jsonb NOT NULL CHECK (jsonb_typeof(definition) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, integration_id, version),
    FOREIGN KEY (workspace_id, integration_id) REFERENCES nxtdeal.integrations(workspace_id, id)
);
CREATE TABLE nxtdeal.integration_runs (
    workspace_id uuid NOT NULL,
    integration_id uuid NOT NULL,
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    mapping_version integer NOT NULL,
    -- Mock success must remain distinguishable from a real provider operation.
    execution_mode text NOT NULL CHECK (execution_mode IN ('dry_run','mock','live')),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','succeeded','failed','cancelled')),
    idempotency_key text NOT NULL CHECK (length(btrim(idempotency_key)) > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    records_seen bigint NOT NULL DEFAULT 0 CHECK (records_seen >= 0),
    records_accepted bigint NOT NULL DEFAULT 0 CHECK (records_accepted >= 0),
    records_rejected bigint NOT NULL DEFAULT 0 CHECK (records_rejected >= 0),
    -- Codes only: do not persist provider bodies, credentials or customer PII here.
    error_code text,
    PRIMARY KEY (workspace_id, integration_id, id),
    UNIQUE (workspace_id, integration_id, idempotency_key),
    FOREIGN KEY (workspace_id, integration_id, mapping_version) REFERENCES nxtdeal.integration_mappings(workspace_id, integration_id, version),
    CHECK (records_accepted <= records_seen AND records_rejected <= records_seen - records_accepted),
    CHECK (started_at IS NULL OR started_at >= created_at),
    CHECK (finished_at IS NULL OR finished_at >= coalesce(started_at, created_at)),
    CHECK ((status = 'pending' AND started_at IS NULL AND finished_at IS NULL)
        OR (status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL)
        OR (status IN ('succeeded','failed') AND started_at IS NOT NULL AND finished_at IS NOT NULL)
        OR (status = 'cancelled' AND finished_at IS NOT NULL))
);
CREATE INDEX integration_runs_time_idx ON nxtdeal.integration_runs(workspace_id, integration_id, created_at);
CREATE TABLE nxtdeal.integration_records (
    workspace_id uuid NOT NULL,
    integration_id uuid NOT NULL,
    run_id uuid NOT NULL,
    position bigint NOT NULL CHECK (position >= 0),
    source_record_id text NOT NULL CHECK (length(btrim(source_record_id)) > 0),
    source_digest text NOT NULL CHECK (source_digest ~ '^[0-9a-f]{64}$'),
    outcome text NOT NULL CHECK (outcome IN ('accepted','rejected','skipped')),
    -- Historical references deliberately survive later graph changes.
    canonical_entity_id text,
    event_id uuid,
    error_code text,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (workspace_id, integration_id, run_id, position),
    FOREIGN KEY (workspace_id, integration_id, run_id) REFERENCES nxtdeal.integration_runs(workspace_id, integration_id, id),
    FOREIGN KEY (workspace_id, event_id) REFERENCES nxtdeal.events(workspace_id, id),
    CHECK (outcome <> 'rejected' OR (error_code IS NOT NULL AND length(btrim(error_code)) > 0))
);
CREATE INDEX integration_records_source_idx ON nxtdeal.integration_records(workspace_id, integration_id, source_record_id);
CREATE TRIGGER immutable_integration_mappings BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.integration_mappings
FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation();
CREATE TRIGGER immutable_integration_records BEFORE UPDATE OR DELETE OR TRUNCATE ON nxtdeal.integration_records
FOR EACH STATEMENT EXECUTE FUNCTION nxtdeal.reject_history_mutation();

-- Operational status may change, but run identities and credential locators
-- must not be rewritten underneath historical evidence.
CREATE FUNCTION nxtdeal.preserve_connector_identity() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    IF TG_TABLE_NAME = 'integration_runs' THEN
        IF ROW(NEW.workspace_id, NEW.integration_id, NEW.id, NEW.mapping_version,
               NEW.execution_mode, NEW.idempotency_key, NEW.created_at)
           IS DISTINCT FROM
           ROW(OLD.workspace_id, OLD.integration_id, OLD.id, OLD.mapping_version,
               OLD.execution_mode, OLD.idempotency_key, OLD.created_at) THEN
            RAISE EXCEPTION 'Run identity is immutable; create a new run' USING ERRCODE = '55000';
        END IF;
    ELSE
        IF ROW(NEW.workspace_id, NEW.id, NEW.secret_store, NEW.secret_reference, NEW.secret_version, NEW.created_at)
           IS DISTINCT FROM
           ROW(OLD.workspace_id, OLD.id, OLD.secret_store, OLD.secret_reference, OLD.secret_version, OLD.created_at) THEN
            RAISE EXCEPTION 'Credential reference is immutable; create a new version' USING ERRCODE = '55000';
        END IF;
        IF OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS DISTINCT FROM OLD.revoked_at THEN
            RAISE EXCEPTION 'Credential revocation cannot be undone' USING ERRCODE = '55000';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER preserve_run_identity BEFORE UPDATE ON nxtdeal.integration_runs
FOR EACH ROW EXECUTE FUNCTION nxtdeal.preserve_connector_identity();
CREATE TRIGGER preserve_credential_identity BEFORE UPDATE ON nxtdeal.credential_references
FOR EACH ROW EXECUTE FUNCTION nxtdeal.preserve_connector_identity();

DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['credential_references','integrations','integration_mappings','integration_runs','integration_records'] LOOP
        EXECUTE format('ALTER TABLE nxtdeal.%I ENABLE ROW LEVEL SECURITY', tab);
        EXECUTE format('ALTER TABLE nxtdeal.%I FORCE ROW LEVEL SECURITY', tab);
        EXECUTE format('CREATE POLICY workspace_scope ON nxtdeal.%I USING (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid) WITH CHECK (workspace_id = nullif(current_setting(''nxtdeal.workspace_id'', true), '''')::uuid)', tab);
    END LOOP;
END;
$$;
