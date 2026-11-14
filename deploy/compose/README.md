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
* Python 3.11+ is not required to run the stack, but the service images are
  expected to be Python-based.
* Nothing else. There is no dependency on Neo4j, JanusGraph, Docker-in-Docker,
  or any managed cloud service.

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

The stack starts in dependency order. `fabric-service` waits for Postgres,
`ontology-service` waits for `fabric-service`, and so on — every edge of the
graph is a real `condition: service_healthy` dependency, not a sleep.

To start only the platform (no console, no collector):

```bash
docker compose up -d postgres fabric-service ontology-service policy-service \
                    audit-service thread-service ingest-service
```

To include the disconnected edge annex (see §8):

```bash
docker compose --profile edge up -d
```

### Health endpoints

Every service exposes two endpoints, both returning `200` with a JSON body:

| Endpoint | Meaning | Used by |
|---|---|---|
| `GET /healthz` | Liveness — the process is up and the event loop is responsive | Compose healthcheck, Kubernetes liveness/startup probe, Helm test pod |
| `GET /readyz` | Readiness — dependencies are reachable and the service can serve traffic | Kubernetes readiness probe, load balancer gating |

Example:

```bash
curl -fsS http://localhost:8082/healthz
# {"status":"ok","service":"fabric-service","profile":"local", ...}
```

If a service image does not ship `wget` **or** `curl`, its Compose healthcheck
will fail. That is a deliberate contract, not a convenience: the image contract
is documented at the top of `docker-compose.yml`.

---

## 4. Tear down

```bash
docker compose down            # stop and remove containers, keep named volumes
docker compose down -v         # also remove the named volumes (data is lost)
docker compose --profile edge down -v
docker compose rm -f           # remove orphaned containers
```

Named volumes that survive a plain `down`:

`ngsh-pgdata`, `ngsh-fabric-data`, `ngsh-ontology-data`, `ngsh-audit-data`,
`ngsh-graph-data`, `ngsh-ingest-data` and the `ngsh-edge-*` set.

To start from a clean database without deleting everything else, drop the
Postgres volume only:

```bash
docker compose down
docker volume rm ngsh-pgdata
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

## 6. Configuration

Three sources, in precedence order (later wins inside a service):

1. **`../../.env.example`** — the shared application env file. Loaded into
   every service via `env_file` with `required: false`, so a missing file never
   blocks `docker compose up`. Copy it to `deploy/compose/.env` for local
   overrides.
2. **`deploy/compose/.env`** — the Compose *interpolation* source. Every
   `${VAR:-default}` in `docker-compose.yml` is resolved from the shell
   environment first, then this file, then the default.
3. **`environment:` in `docker-compose.yml`** — structural values only: ports,
   in-cluster service URLs, OTel resource attributes, the database URL.

`environment:` wins over `env_file:` for the same key, so the structural
values above are deterministic across services.

Key variables:

| Variable | Default | Meaning |
|---|---|---|
| `NGSH_ENVIRONMENT` | `local` | Deployment environment name |
| `NGSH_DEPLOYMENT_PROFILE` | `local` | `local` \| `il5` \| `il6` \| `edge` |
| `NGSH_DEPLOYMENT_ZONE` | `local-dev` | Zone label carried in telemetry |
| `NGSH_CLASSIFICATION_LEVEL` | `UNCLASSIFIED` | Highest handling caveat of the zone |
| `NGSH_TENANT` | `ngsh-local` | Tenant key; every query is tenant-scoped |
| `NGSH_GRAPH_BACKEND` | `postgres` | `postgres` \| `neptune` \| `janusgraph` |
| `NGSH_GRAPH_URL` | `postgresql://postgres:5432/ngsh` | Graph adapter endpoint |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4317` | Where traces/metrics/logs go |
| `POSTGRES_APP_USER` / `POSTGRES_APP_PASSWORD` | `ngsh_app` / `ngsh-dev-placeholder` | Runtime DB role. **Placeholder — local development only.** |
| `POSTGRES_SUPERUSER` / `POSTGRES_SUPERUSER_PASSWORD` | `ngsh_root` / `ngsh-dev-placeholder` | Bootstrap superuser. **Placeholder — local development only.** |

> The `*-dev-placeholder` passwords are literal development placeholders. They
> are not credentials for anything real. In a Helm deployment the application
> password comes from `values.secrets` (see `deploy/helm/ngsh/README.md`).

---

## 7. Seeding data

The schemas exist after the first `up`; the *domain tables* are created by the
application migrations that ship with each service, and the event log is
populated by ingesting events.

```bash
# 1. Confirm the schemas and roles landed.
docker compose exec postgres psql -U ngsh_root -d ngsh -c '\dn'
#  ontology | fabric | audit | graph | ingest

docker compose exec postgres psql -U ngsh_root -d ngsh -c '\du'
#  ngsh_admin | ngsh_app | ngsh_readonly

# 2. Run the application migrations (whatever the service teams ship —
#     Alembic, Django, Flyway, …). They own the domain tables.

# 3. Seed by ingesting events, not by inserting rows.
#    The fabric is the system of record; every other store is a projection.
curl -fsS -X POST http://localhost:8086/ingest/batches \
  -H 'content-type: application/json' \
  -H 'x-tenant: ngsh-local' \
  -d '{
        "source": "seed-script",
        "events": [
          {
            "eventType": "entity.created",
            "eventVersion": 1,
            "aggregateType": "System",
            "aggregateId": "SYS:SEED-0001",
            "sequence": 1,
            "occurredAt": "2026-01-01T00:00:00Z",
            "tenant": "ngsh-local",
            "actor": {"subjectId": "PER:SEED", "kind": "service"},
            "classification": {"level": "UNCLASSIFIED"},
            "payload": {"type": "System", "id": "SYS:SEED-0001", "name": "Seed system"}
          }
        ]
      }'

# 4. Watch the projections rebuild.
docker compose logs -f fabric-service thread-service ontology-service
```

Every event must satisfy `contracts/events/event-envelope.schema.json`; the
ingest service rejects malformed envelopes at the boundary.

---

## 8. Graph store: local stand-in and the path to Neptune/JanusGraph

**Local development uses PostgreSQL as a graph stand-in.** The `graph` schema
holds the property-graph projection (nodes and edges as tables). This is
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
   is a projection, the backfill is idempotent and does not require a migration
   window on the fabric.
5. Switch reads, verify, then retire the PostgreSQL graph tables.

The commented-out `graph:` block in `docker-compose.yml` shows the shape an
in-cluster graph engine would take, with no provider-specific fields.

---

## 9. The edge annex profile

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

Edge services are flagged with `NGSH_EDGE_MODE=true` and
`NGSH_EDGE_NODE_ID=<node>` so the application can stamp the `edge` block of
the event envelope (`nodeId`, `capturedAt`, `reconciledAt`, `clockSkewMs`).

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `env_file ... required` error | Compose older than v2.24 | Upgrade the Compose plugin, or remove the `env_file` block |
| Service never becomes healthy | Image has no `wget`/`curl` | Add one to the image, or override the healthcheck |
| `connection refused` on 8082 | Postgres still initialising | `docker compose logs postgres`; the first start runs `init.sql` |
| Console shows the placeholder page | `apps/web/dist` absent | `cd apps/web && npm ci && npm run build`, then rebuild the image |
| OTel exporter errors | `OTEL_EXPORTER_OTLP_ENDPOINT` points nowhere | Point it at a real OTLP backend, or leave it unset to use the debug exporter |
| Port already in use | Another process | Override the host port: `FABRIC_HOST_PORT=18082 docker compose up -d` |

Diagnostics:

```bash
docker compose ps
docker compose logs --tail=100 fabric-service
docker compose exec postgres psql -U ngsh_root -d ngsh -c '\dt fabric.*'
docker compose exec postgres psql -U ngsh_root -d ngsh -c 'SELECT count(*) FROM fabric.event_log;'
```
