-- =============================================================================
-- NGSH — PostgreSQL bootstrap for the local development datastore
-- =============================================================================
--
-- Scope
-- -----
-- This script establishes the *platform plumbing* the deployment layer owns:
--   * the extensions the foundation relies on
--   * the five foundation schemas
--   * the runtime roles and their grants
--
-- It deliberately does NOT create the domain tables. Those are owned by the
-- application migrations that ship with each service (ontology, fabric,
-- audit, graph, ingest). Keeping the two apart means an application migration
-- can evolve the domain model without a database rebuild, and it keeps the
-- deployment layer free of domain logic — a hard rule for this repository.
--
-- The expected application-owned tables are listed at the bottom of this file
-- as a commented contract, so the next engineer can see the intended shape
-- without the deployment layer enforcing it.
--
-- Execution
-- ----------
--   Mounted at /docker-entrypoint-initdb.d/10-ngsh-init.sql, which the
--   official postgres image runs exactly once, on first initialisation of an
--   empty data directory. Re-running it against an existing cluster is safe:
--   every statement is guarded.
--
-- Credentials
-- -----------
-- The password below is a LOCAL DEVELOPMENT PLACEHOLDER. It is a literal
-- 'ngsh-dev-placeholder' and is not a credential for anything real. Real
-- deployments must source the application password from the platform secret
-- store and rotate it; see deploy/helm/ngsh/values.yaml (secrets.*).
-- =============================================================================

-- This file is plain SQL: the postgres entrypoint runs it with
-- `psql -v ON_ERROR_STOP=1`, so a failing statement aborts the bootstrap.

-- -----------------------------------------------------------------------------
-- 1. Extensions
-- -----------------------------------------------------------------------------
-- pgcrypto : gen_random_uuid() for correlation ids, digest() for the sha256
--            integrity checks the event envelope relies on.
-- pg_trgm  : trigram indexes for entity id / label lookups.
-- btree_gin: composite GIN support used by the jsonb indexes on payloads.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- -----------------------------------------------------------------------------
-- 2. Roles
-- -----------------------------------------------------------------------------
-- ngsh_admin     : owns the schemas. NOLOGIN. The migration role uses it.
-- ngsh_app       : the runtime identity every NGSH service connects as.
-- ngsh_readonly  : reporting / BI reader. SELECT only, never a writer.
DO $$
DECLARE
  r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['ngsh_admin', 'ngsh_app', 'ngsh_readonly'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      IF r = 'ngsh_admin' THEN
        EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT', r);
      ELSIF r = 'ngsh_app' THEN
        EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT', r);
      ELSE
        EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT', r);
      END IF;
    END IF;
  END LOOP;
END
$$;

-- Local development password. PLACEHOLDER — never a real secret.
ALTER ROLE ngsh_app WITH PASSWORD 'ngsh-dev-placeholder';
ALTER ROLE ngsh_readonly WITH PASSWORD 'ngsh-dev-placeholder';

-- The application role must not be able to create databases, roles, or
-- extensions, and must not be able to bypass row-level security.
ALTER ROLE ngsh_app NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER ROLE ngsh_readonly NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- -----------------------------------------------------------------------------
-- 3. Foundation schemas
-- -----------------------------------------------------------------------------
-- ontology : the shared ontology — entity types, relation types, registry.
-- fabric   : the append-only event log (system of record) and its indexes.
-- audit    : the immutable audit ledger and access-decision records.
-- graph    : the property-graph projection consumed by the thread service.
-- ingest   : ingestion batches, staging area and reconciliation bookkeeping.
CREATE SCHEMA IF NOT EXISTS ontology AUTHORIZATION ngsh_admin;
CREATE SCHEMA IF NOT EXISTS fabric   AUTHORIZATION ngsh_admin;
CREATE SCHEMA IF NOT EXISTS audit    AUTHORIZATION ngsh_admin;
CREATE SCHEMA IF NOT EXISTS graph    AUTHORIZATION ngsh_admin;
CREATE SCHEMA IF NOT EXISTS ingest   AUTHORIZATION ngsh_admin;

COMMENT ON SCHEMA ontology IS 'Shared ontology: entity types, relation types, registry. Owner: application migrations.';
COMMENT ON SCHEMA fabric   IS 'Append-only event log. System of record; all projections are rebuilt by replay. Owner: application migrations.';
COMMENT ON SCHEMA audit    IS 'Immutable audit ledger and recorded access decisions. Owner: application migrations.';
COMMENT ON SCHEMA graph    IS 'Property-graph projection (local stand-in for Neptune/JanusGraph). Owner: thread service.';
COMMENT ON SCHEMA ingest   IS 'Ingestion batches, staging and store-and-forward reconciliation bookkeeping. Owner: application migrations.';

-- -----------------------------------------------------------------------------
-- 4. Grants
-- -----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA ontology, fabric, audit, graph, ingest TO ngsh_app;
GRANT USAGE ON SCHEMA ontology, fabric, audit, graph, ingest TO ngsh_readonly;

-- Future objects created by the migration role are grantable automatically, so
-- an application migration never has to remember to re-issue grants.
ALTER DEFAULT PRIVILEGES FOR ROLE ngsh_admin IN SCHEMA ontology GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ngsh_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ngsh_admin IN SCHEMA fabric   GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ngsh_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ngsh_admin IN SCHEMA audit    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ngsh_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ngsh_admin IN SCHEMA graph    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ngsh_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ngsh_admin IN SCHEMA ingest   GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ngsh_app;

ALTER DEFAULT PRIVILEGES FOR ROLE ngsh_admin IN SCHEMA ontology GRANT SELECT ON TABLES TO ngsh_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE ngsh_admin IN SCHEMA fabric   GRANT SELECT ON TABLES TO ngsh_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE ngsh_admin IN SCHEMA audit    GRANT SELECT ON TABLES TO ngsh_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE ngsh_admin IN SCHEMA graph    GRANT SELECT ON TABLES TO ngsh_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE ngsh_admin IN SCHEMA ingest   GRANT SELECT ON TABLES TO ngsh_readonly;

-- Sequences are needed by the runtime role for identity columns.
ALTER DEFAULT PRIVILEGES FOR ROLE ngsh_admin IN SCHEMA ontology GRANT USAGE, SELECT ON SEQUENCES TO ngsh_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ngsh_admin IN SCHEMA fabric   GRANT USAGE, SELECT ON SEQUENCES TO ngsh_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ngsh_admin IN SCHEMA audit    GRANT USAGE, SELECT ON SEQUENCES TO ngsh_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ngsh_admin IN SCHEMA graph    GRANT USAGE, SELECT ON SEQUENCES TO ngsh_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ngsh_admin IN SCHEMA ingest   GRANT USAGE, SELECT ON SEQUENCES TO ngsh_app;

-- The public schema is not a place for platform objects.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO ngsh_app;
GRANT USAGE ON SCHEMA public TO ngsh_readonly;

-- -----------------------------------------------------------------------------
-- 5. Application-owned schema contract (documentation only — NOT created here)
-- -----------------------------------------------------------------------------
-- The application migrations own the domain tables. The intended shape, for
-- coordination between the platform and the service teams:
--
--   fabric.event_log(
--     sequence        bigserial PRIMARY KEY,     -- global ordering
--     event_id        uuid        NOT NULL UNIQUE, -- ULID in the envelope
--     event_type      text        NOT NULL,
--     event_version   integer     NOT NULL,
--     aggregate_type  text        NOT NULL,
--     aggregate_id    text        NOT NULL,
--     seq             bigint      NOT NULL,        -- per-aggregate sequence
--     tenant          text        NOT NULL,
--     program         text,
--     actor           jsonb       NOT NULL,
--     classification  jsonb       NOT NULL,
--     payload         jsonb       NOT NULL,
--     causation_id    uuid,
--     correlation_id  uuid,
--     transaction_id  uuid,
--     occurred_at     timestamptz NOT NULL,
--     recorded_at     timestamptz NOT NULL,
--     edge            jsonb,
--     UNIQUE (aggregate_type, aggregate_id, seq)
--   )
--
--   ontology.entity(id, type, version, tenant, program, classification,
--                    body jsonb, created_at, updated_at)
--   ontology.relation(id, type, from_id, to_id, ...)
--
--   audit.access_log(...)          -- append-only; no UPDATE, no DELETE
--   audit.access_decision(...)     -- recorded access.decision.recorded events
--
--   graph.node(id, type, tenant, classification, properties jsonb)
--   graph.edge(from_id, to_id, type, tenant, properties jsonb)
--
--   ingest.batch(id, source, received_at, accepted_count, status)
--   ingest.reconciliation(node_id, batch_id, state, clock_skew_ms, ...)
--
-- Immutability of fabric.event_log and audit.* is enforced by the application
-- layer and by database triggers owned by the application migrations. The
-- deployment layer states no domain rules.
-- =============================================================================
