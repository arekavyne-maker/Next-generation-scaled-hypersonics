# NGSH — Local Development Topology

Local Compose topology for the six NGSH platform services, the operator console,
the datastore, and the OpenTelemetry Collector.

Everything here is **provider-neutral**: plain OCI images, plain Kubernetes-style
env vars, no cloud-provider SDKs and no provider-specific service calls. The
same images land unchanged in an accredited cloud enclave, an on-prem IL6
enclave, or a disconnected edge annex.

---

## 1. Contents

| Path | Purpose |
|---|---|
| `docker-compose.yml` | The full local topology: 6 services + console + Postgres + OTel Collector |
| `postgres/init.sql` | Extensions, the five foundation schemas, runtime roles and grants |
| `web/Dockerfile` | nginx image serving the static console build |
| `web/nginx.conf` | Console routing + `/api/<service>/` reverse proxy |
| `web/proxy_params_ngsh.conf` | Shared proxy headers (incl. W3C trace propagation) |
| `web/placeholder.html` | Shown when the console bundle has not been built yet |

---

## 2. Prerequisites

* Docker Engine with the **Compose v2 plugin, v2.24.0 or newer**.
  v2.24 is the first release that supports the long-form `env_file` entry
  (`path:` / `required:`) used here.
* Nothing else. There is no dependency on Neo4j, JanusGraph,
  Docker-in-Docker, or any managed cloud service.

---

## 3. Bring it up

```bash
cd deploy/compose

# 1. Optional: seed the interpolation variables.
#    The project-local .env is the source for every ${VAR:-default} in the
#    compose file. Copy the shared example file if it exists:
#    cp ../../.env.example .env   # then edit

# 2. Build and start.
docker compose up --build

# 3. Watch it come up.
docker compose ps
docker compose logs -f fabric-service
```

The stack starts in dependency order. `init-data` hands the named volumes to
the service uid and exits; the services then wait for Postgres and for each
other. Every edge of the service graph is a real
`condition: service_healthy` dependency, not a sleep.

To start only the platform (no console, no collector):

```bash
docker compose up -d postgres fabric-service ontology-service policy-service \
                    audit-service thread-service ingest-service
```

To include the disconnected edge annex (see §9):

```bash
docker compose --profile edge up -d
```

### Health endpoints

Every service exposes two endpoints, both returning `200` with a JSON body:

| Endpoint | Meaning | Used by |
|---|---|---|
| `GET /healthz` | Liveness — the process is up and the event loop is responsive | Compose healthcheck, Kubernetes liveness/startup probe, Helm test pod |
| `GET /readyz` | Readiness — dependencies are reachable and the service can serve traffic | Kubernetes readiness probe, load-balancer gating |

Example:

```bash
curl -fsS http://localhost:8082/healthz
# {"status":"ok","service":"fabric-service","profile":"local", ...}
```

The service images ship `curl`, which the healthchecks use. The console image
ships `wget` (busybox in the nginx image).

---

## 4. Tear down

```bash
docker compose down            # stop and remove containers, keep named volumes
docker compose down -v         # also remove the named volumes (data is lost)
docker compose --profile edge down -v
docker compose rm -f           # remove orphaned containers
```

Named volumes that survive a plain `down`:

`ngsh-data` (the shared platform database), `ngsh-pgdata`,
`ngsh-fabric-data`, `ngsh-ontology-data`, `ngsh-audit-data`,
`ngsh-graph-data`, `ngsh-ingest-data` and the `ngsh-edge-*` set.

To start from a clean database without deleting everything else, drop the
platform volume only:

```bash
docker compose down
docker volume rm ngsh-data
docker compose up -d
```

---

## 5. Port map

| Host port | Container | Service | Notes |
|---|---|---|---|
| 8080 | 8080 | `web` | nginx console, `/api/<service>/` proxy |
| 8081 | 8081 | `ontology-service` | shared ontology |
| 8082 | 8082 | `fabric-service` | event log (system of record) |
| 8083 | 8083 | `policy-service` | ABAC decisions |
| 8084 | 8084 | `audit-service` | immutable audit ledger |
| 8085 | 8085 | `thread-service` | digital thread / graph projection |
| 8086 | 8086 | `ingest-service` | bulk ingestion |
| 4317 | 4317 | `otel-collector` | OTLP gRPC |
| 4318 | 4318 | `otel-collector` | OTLP HTTP |
| 13133 | 13133 | `otel-collector` | collector health check extension |
| 5432 | 5432 | `postgres` | Postgres 16 |

Every host port is overridable, e.g. `WEB_HOST_PORT=18080 docker compose up -d`.

The edge annex publishes **no** host ports: it is an isolated segment reached
only from inside the Compose network.

---

## 6. Storage

### The local default is SQLite on a shared volume

All six services mount the `ngsh-data` volume at `/var/lib/ngsh/platform` and
open the same SQLite database:

```
NGSH_DSN=sqlite:////var/lib/ngsh/platform/ngsh.db
```

This is the platform's documented single-process development mode, reproduced
across containers: the SQLite executor enables WAL journalling and a busy
timeout specifically so that several services can share one file. It is
**development-only**. The PostgreSQL service is the platform's target
relational store and is provisioned in parallel (see below).

Both backends are implemented and the platform's repositories are identical
across them. The PostgreSQL schema and every statement the platform issues
are checked against the real PostgreSQL grammar by
`tests/integration/test_postgres_backend.py`, so a SQLite-only statement
cannot reach an accredited environment unnoticed.

### Postgres is provisioned and ready

The `postgres` service runs `postgres:16-alpine` and executes
`postgres/init.sql` on first start, which creates the five foundation schemas
(`ontology`, `fabric`, `audit`, `graph`, `ingest`), the runtime roles
(`ngsh_admin`, `ngsh_app`, `ngsh_readonly`) and the `pgcrypto`, `pg_trgm` and
`btree_gin` extensions.

Switching the platform onto it is a single environment variable:

```bash
NGSH_DSN="postgresql://ngsh_app:ngsh-dev-placeholder@postgres:5432/ngsh" \
  docker compose up -d
```

Both `NGSH_DSN` and `DATABASE_URL` are set to that value, because the
platform's configuration layer reads the first of the two that is present.

> The scheme is `postgresql://`, not `postgres://` — the platform's SQL driver
> accepts only the long form.
>
> The `psycopg` driver is a runtime dependency of `ngsh-core`, so it is
> present in the service images; no extra image build is required.
>
> The `ngsh-dev-placeholder` password matches the placeholder that
> `postgres/init.sql` assigns to the `ngsh_app` role. Both are local
> development placeholders, not credentials for anything real.

### Volume ownership

The service images run as uid/gid **65532**, while Docker creates named
volumes owned by root. The one-shot `init-data` container runs as root,
`chown`s every named volume to 65532:65532, and exits. It is not in the
request path and never serves traffic.

If you add a new named volume, mount it into `init-data` as well, or the
services will not be able to write to it.

---

## 7. Configuration

Three sources, in precedence order (later wins inside a service):

1. **`../../.env.example`** — the shared application env file. Loaded into
   every service via `env_file` with `required: false`, so a missing file never
   blocks `docker compose up`. Copy it to `deploy/compose/.env` for local
   overrides.
2. **`deploy/compose/.env`** — the Compose *interpolation* source. Every
   `${VAR:-default}` in `docker-compose.yml` is resolved from the shell
   environment first, then this file, then the default.
3. **`environment:` in `docker-compose.yml`** — structural values only: ports,
   in-cluster service URLs, OTel resource attributes, the DSN.

`environment:` wins over `env_file:` for the same key, so the structural
values above are deterministic across services — and the shared example file
cannot silently redirect the stack to a different store.

Key variables:

| Variable | Default | Meaning |
|---|---|---|
| `NGSH_ENVIRONMENT` | `local` | Deployment environment name |
| `NGSH_DEPLOYMENT_PROFILE` | `local` | `local` \| `il5` \| `il6` \| `edge` |
| `NGSH_DEPLOYMENT_ZONE` | `local-dev` | Zone label carried in telemetry |
| `NGSH_CLASSIFICATION_LEVEL` | `UNCLASSIFIED` | Highest handling caveat of the zone |
| `NGSH_TENANT` | `ngsh-local` | Tenant key; every query is tenant-scoped |
| `NGSH_HOST` | `0.0.0.0` | Listen address |
| `NGSH_PORT` / `PORT` | per service | Listen port. Both are set to the same value. |
| `NGSH_DSN` / `DATABASE_URL` | SQLite on `ngsh-data` | Storage DSN. The first one set wins. |
| `NGSH_IDENTITY_PROVIDER` | `stub` | `stub` (development actor) or `piv` (federation) |
| `NGSH_GRAPH_BACKEND` | `postgres` | `postgres` \| `neptune` \| `janusgraph` |
| `NGSH_GRAPH_URL` | `postgresql://postgres:5432/ngsh` | Graph adapter endpoint |
| `NGSH_FABRIC_URL` etc. | per service | In-cluster service URLs |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4317` | Where traces/metrics/logs go |
| `POSTGRES_SUPERUSER` / `POSTGRES_SUPERUSER_PASSWORD` | `ngsh_root` / `ngsh-dev-placeholder` | Bootstrap superuser. **Placeholder — local development only.** |

> The `stub` identity provider is a development actor with no credential
> requirement. The platform **refuses** it outside the `local` and `edge`
> deployment profiles, so this topology always runs in one of those two.

---

## 8. Seeding data

In the local topology the services share one SQLite database, so seeding is a
direct write through the platform's own API — there is no separate migration
step to run first. The domain schema is created by the services themselves on
first start.

```bash
# 1. Confirm the services are up.
docker compose ps
curl -fsS http://localhost:8082/healthz
curl -fsS http://localhost:8082/v1/service/info

# 2. Confirm the Postgres schemas and roles landed.
docker compose exec postgres psql -U ngsh_root -d ngsh -c '\dn'
#  ontology | fabric | audit | graph | ingest

docker compose exec postgres psql -U ngsh_root -d ngsh -c '\du'
#  ngsh_admin | ngsh_app | ngsh_readonly

# 3. Seed by ingesting events, not by inserting rows.
#    The fabric is the system of record; every other store is a projection.
#
#    POST /v1/events accepts either a single envelope or {"events": [...]}.
#    The envelope rejects unknown fields, and the service fills in the
#    event id and timestamps when they are omitted.
curl -fsS -X POST http://localhost:8082/v1/events \
  -H 'content-type: application/json' \
  -d '{
        "events": [
          {
            "eventType": "entity.created",
            "aggregateType": "System",
            "aggregateId": "SYS:SEED-0001",
            "sequence": 1,
            "tenant": "ngsh-local",
            "actor": {"subjectId": "PER:SEED", "kind": "service"},
            "classification": {"level": "UNCLASSIFIED"},
            "payload": {"type": "System", "id": "SYS:SEED-0001", "name": "Seed system"}
          }
        ]
      }'

#    Or admit a raw batch and let the ingest service publish the events:
curl -fsS -X POST http://localhost:8086/v1/ingest \
  -H 'content-type: application/json' \
  -d '{
        "source": "seed-script",
        "format": "NDJSON",
        "payload": "{\"type\":\"System\",\"id\":\"SYS:SEED-0002\",\"name\":\"Seed system 2\"}\n"
      }'

# 4. Read the log back.
curl -fsS http://localhost:8082/v1/events
curl -fsS http://localhost:8082/v1/stats

# 5. Watch the projections rebuild.
docker compose logs -f fabric-service thread-service ontology-service
```

Every event must satisfy `contracts/events/event-envelope.schema.json`; the
fabric rejects malformed envelopes at the boundary. The tenant is part of the
envelope, and the services default it from `NGSH_TENANT`.

---

## 9. Graph store: local stand-in and the path to Neptune/JanusGraph

**Local development uses the platform's relational store as a graph
stand-in.** The `graph` schema holds the property-graph projection (nodes and
edges as tables) — in the shared SQLite database locally, and in the
`graph` schema of PostgreSQL once the stack is pointed at it. This is
deliberate:

* No Docker-in-Docker, no extra privileged container, no second database to
  version and back up.
* The thread service is the *only* service that talks to the graph, and it
  reaches it through a single narrow adapter selected by two env vars:
  `NGSH_GRAPH_BACKEND` and `NGSH_GRAPH_URL`.
* The projection is a projection: it is rebuilt by replaying the event log, so
  a backend change never loses information.

**Migration path.** When an accredited graph engine becomes available:

1. Deploy the engine as a platform dependency (it is not part of the service
   set, and it is not deployed by this compose file).
2. Implement the graph adapter for the target engine behind the existing
   `NGSH_GRAPH_BACKEND` switch. The interface is fixed; only its
   implementation changes.
3. Set the env vars — nothing else changes:

   ```yaml
   environment:
     NGSH_GRAPH_BACKEND: neptune        # or: janusgraph
     NGSH_GRAPH_URL: <endpoint>
   ```

4. Backfill by replaying the event log into the new backend. Because the graph
   is a projection, the backfill is idempotent and does not require a
   migration window on the fabric.
5. Switch reads, verify, then retire the PostgreSQL graph tables.

The commented-out `graph:` block in `docker-compose.yml` shows the shape an
in-cluster graph engine would take, with no provider-specific fields.

---

## 10. The edge annex profile

```bash
docker compose --profile edge up -d
```

The edge profile starts `edge-postgres`, `edge-fabric-service` and
`edge-ingest-service` on the `ngsh-edge` network, which is declared
`internal: true`. That network has **no gateway and no egress**: edge nodes
cannot reach the central fabric, and the central fabric cannot reach them.

This is the intended topology, not a limitation of the demo. Reconciliation
between an edge annex and the central fabric is a sanctioned store-and-forward
transfer performed by operations — see `deploy/README.md`, "Data flows between
zones".

The edge services run with `NGSH_DEPLOYMENT_PROFILE=edge` and their own store
on the `ngsh-edge-data` volume. They never point at the central fabric's
database.

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `env_file ... required` error | Compose older than v2.24 | Upgrade the Compose plugin, or remove the `env_file` block |
| Service never becomes healthy | Image has no `curl`/`wget` | Add one to the image, or override the healthcheck |
| `Permission denied` writing the database | A new volume was not mounted into `init-data` | Mount it there so the chown covers it |
| `connection refused` on 8082 | Postgres still initialising | `docker compose logs postgres`; the first start runs `init.sql` |
| Console shows the placeholder page | `apps/web/dist` absent | `cd apps/web && npm ci && npm run build`, then rebuild the image |
| OTel exporter errors | `OTEL_EXPORTER_OTLP_ENDPOINT` points nowhere | Point it at a real OTLP backend, or leave it unset to use the debug exporter |
| Port already in use | Another process | Override the host port: `FABRIC_HOST_PORT=18082 docker compose up -d` |

Diagnostics:

```bash
docker compose ps
docker compose logs --tail=100 fabric-service
docker compose exec postgres psql -U ngsh_root -d ngsh -c '\dn'
docker compose exec postgres psql -U ngsh_root -d ngsh -c '\dt'
docker compose exec postgres psql -U ngsh_root -d ngsh -c 'SELECT count(*) FROM fabric.event_log;'
```

> The last query assumes the PostgreSQL executor has landed and the
> application migrations have created the domain tables in PostgreSQL. In the
> default (SQLite) topology the event log lives in the shared platform
> database instead; query it through the fabric's own API.
