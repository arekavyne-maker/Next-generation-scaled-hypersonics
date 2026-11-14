# NGSH — Deployment Strategy

How the NGSH platform is deployed across its operating environments, and the
rules that govern data movement between them.

This directory contains the **deployment and packaging layer** only:

| Directory | Contents |
|---|---|
| `compose/` | Local development topology (Compose) — see `compose/README.md` |
| `helm/ngsh/` | Kubernetes chart with four deployment profiles — see `helm/ngsh/README.md` |
| `otel/` | OpenTelemetry Collector configuration and the telemetry conventions |

Nothing here contains domain logic. See [§7](#7-the-deployment-layer-contains-no-domain-logic).

---

## 1. The hybrid-first decision

NGSH is designed to run **the same binaries** in three very different places:

* an **accredited cloud** (AWS GovCloud, Azure Government, or equivalent),
* an **on-prem classified enclave**,
* a **disconnected edge node** at a factory floor or a test range.

This is a hard architectural constraint, not a preference. It has direct
consequences for this directory:

* **No cloud-provider SDKs and no provider-specific service calls** appear in
  any manifest. There is no `AWS::`, no `resources.azure.com`, no
  `googleapis.com`, and no CRD from a cloud operator.
* Everything is a plain OCI image, a plain Kubernetes object, and an
  environment variable. Which cloud a workload lands in is decided by the
  image registry and the ingress/storage class — never by the manifest.
* The **same** Compose topology and the **same** Helm chart serve all three
  zones. The differences are expressed as values, not as separate charts.

The consequence is a deliberate constraint on our own flexibility: we cannot
use a managed queue, a managed graph database, or a provider identity service
as a platform dependency without a portable equivalent. Where no portable
equivalent exists yet, the dependency is documented and the integration point
is kept to one adapter (see the graph store, §6).

---

## 2. The three zones

```
                    +----------------------------------------------+
                    |            ZONE 1 — CENTRAL FABRIC           |
                    |  Authoritative platform. The event log and   |
                    |  the ontology are the system of record.      |
                    |  Highest accreditation. No public ingress.   |
                    |  Always-on.                                  |
                    +-----------------+---------------------------+
                                      |  (1) one-way sanitized extract
                                      |      (cross-domain guard)
                                      v
                    +----------------------------------------------+
                    |      ZONE 2 — ACCREDITED CLOUD ENCLAVE      |
                    |  GovCloud / Azure Government / equivalent.  |
                    |  IL5. Elastic: console, analytics, training |
                    |  sandbox, extract pipeline.                  |
                    |  Internal ingress only.                     |
                    +----------------------------------------------+

                    +----------------------------------------------+
                    |       ZONE 3 — SEGREGATED EDGE ANNEX         |
                    |  Factory floor / test range.                 |
                    |  Single node, physically or logically        |
                    |  disconnected from everything else.         |
                    |  Local event log + local audit spool.        |
                    +------------------+---------------------------+
                                       |  (2) store-and-forward
                                       |      reconciliation
                                       v
                                 back to ZONE 1
```

### Zone 1 — Central fabric

The authoritative platform. The event log, the shared ontology, the policy
engine and the audit ledger live here. This is the system of record; every
other store in every zone is a projection rebuilt by replaying the log.

* Always-on. Every request path is served from here.
* No public ingress. Operators reach it through the console (zone 2) or
  through a management segment.
* Highest accreditation of the three; in practice this is where the IL6
  deployment profile applies for the classified portion.

### Zone 2 — Accredited cloud enclave

An accredited cloud enclave hosting the *elastic* part of the platform:
the operator console, analytics and reporting projections, the workforce
training sandbox, and the sanitized-extract pipeline.

* IL5 baseline.
* **Internal ingress only.** The console is reachable from inside the
  enclave's private network, never from the public internet. The chart's IL5
  profile pins the ingress class to `internal` for exactly this reason.
* Horizontally scalable: the request-serving services carry an HPA; the
  bulk ingest path is scaled to zero and woken per batch.
* It holds no authority of record. Everything in it is either a projection of
  zone 1 or a sanitized extract produced by the guard service.

### Zone 3 — Segregated edge annex

A single node at a factory floor, a test range, or a depot.

* One replica of everything, on a node selected by an edge-hardware label.
* Node-local ReadWriteOnce storage.
* **No route to anything.** No external egress, no collector egress, no
  ingress. Telemetry, events and audit records accumulate locally and leave
  only through a sanctioned reconciliation.
* It can operate for weeks without contact.

---

## 3. Data flows between zones

There are exactly two flows. Neither is a live connection.

### (1) One-way sanitized extracts — zone 1 → zone 2

The central fabric produces sanitized extracts for the accredited cloud
enclave (and for external partners such as universities). Extracts are
produced by a cross-domain guard service, which is a platform dependency and
not part of this deployment layer.

Properties:

* **One-way.** Data leaves; nothing flows back. The extract sink has no
  write path into the fabric.
* **De-classified or downgraded.** An extract never carries a record above
  the level the destination is accredited for. `CUI//REL` becomes `CUI`;
  `RESTRICTED` threat records never leave at all.
* **Minimised.** No person identifiers, no clearance records, no raw
  telemetry. Where an aggregate would serve, an aggregate is used.
* **Marked and provenance-bearing.** Every extract carries the source
  classification, the guard decision, and the lineage of every record in it,
  so a consumer can answer "how did this get here".
* Extracts are consumed as **projections**: they are rebuilt from the log,
  not hand-curated, so an extract can be regenerated at any time.

### (2) Store-and-forward reconciliation — zone 3 → zone 1

An edge annex accumulates events in its local log while disconnected. When a
sanctioned transfer becomes available, the annex exports batches, and the
central fabric imports them.

Properties:

* **At-least-once delivery, idempotent application.** Every event carries a
  ULID `eventId` that doubles as the idempotency key; the fabric deduplicates
  on it, so a retried transfer is harmless.
* **Causality and correlation are preserved.** The envelope's `causationId`
  and `correlationId` survive the transfer, so the causal chain is intact
  even though the events were captured hours apart.
* **Clock skew is recorded, not corrected.** The `edge` block of the envelope
  carries `nodeId`, `capturedAt`, `reconciledAt` and `clockSkewMs`. The
  platform records the discrepancy; it does not silently rewrite timestamps.
* **Per-aggregate ordering is preserved.** The envelope's per-aggregate
  `sequence` is what ordering is enforced on. Global ordering across the
  transfer is not meaningful and is not asserted.
* **Traces break, data does not.** A disconnected node cannot extend a live
  trace. It opens a new trace per reconciled batch and links it with the
  envelope's correlation identifiers. See `otel/README.md`, §3.

### What does *not* happen

* **No direct edge-to-edge traffic.** Two edge annexes never talk to each
  other, directly or through the cloud. Every edge node's only counterpart
  is the central fabric.
* **No edge-to-cloud traffic.** An edge annex never dials the accredited
  cloud enclave. If a site needs data from the enclave, the enclave's data
  reaches the site through the central fabric's reconciliation path.
* **No live replication from an edge node.** The annex is disconnected by
  design; a "connected edge" mode would defeat its purpose.
* **No unclassified data crossing a classified boundary** without the guard
  service in the path.

---

## 4. Service posture by zone

| Service | Zone 1 — Central fabric | Zone 2 — Accredited cloud enclave | Zone 3 — Edge annex |
|---|---|---|---|
| `ontology-service` (8081) | **Always-on.** Authoritative shared ontology; 2 replicas, pod anti-affinity across hosts. | **Always-on.** Projection of the central ontology, rebuilt by replay; HPA-managed. | **Edge-resident.** Local copy of the ontology slice the site needs. |
| `fabric-service` (8082) | **Always-on.** The event log is the system of record; 2–3 replicas, quorum-preserving. | **Always-on.** Subscription-only projection; HPA-managed. | **Edge-resident.** The local log. This is the annex's system of record until reconciliation. |
| `policy-service` (8083) | **Always-on.** The authorization point. Never scaled to zero — an authorization gap is a security gap. | **Always-on.** Same reasoning; enforcement is not a workload to be shed. | **Edge-resident.** Evaluates against locally cached policy. Deny-by-default when the policy cache is stale or empty. |
| `audit-service` (8084) | **Always-on.** The audit ledger must have no gaps; 2 replicas, append-only. | **Always-on.** Projection for reporting. | **Edge-resident.** Local append-only audit spool, flushed with the reconciliation. |
| `thread-service` (8085) | **Always-on.** Digital-thread graph projection; the heaviest read path; HPA-managed. | **Always-on.** Read-only projection for the console and analytics. | **Edge-resident.** Local graph over the site's own data. |
| `ingest-service` (8086) | **Always-on** in the classification-bearing zone; **scaled-to-zero** where bulk loading is batch-triggered and the data is a projection. | **Scaled-to-zero.** Woken for the duration of a batch, then scaled back down. Batch-triggered, not continuously served. | **Edge-resident.** Always listening on the site's own instrumentation; it is the source of the reconciliation batches. |
| `web` console (8080) | **Always-on.** Served from the accredited enclave, not from the classified zone. | **Always-on.** 2 replicas behind an **internal** ingress class. | **Edge-resident.** Static bundle served on the site's local segment. No ingress; no public listener anywhere. |

### Reading the table

* **Always-on** — the workload is always deployed and serving.
* **Scaled-to-zero** — the Deployment exists but runs 0 replicas until a
  trigger scales it up. The chart expresses this as `replicaCount: 0`; there
  is no HPA, because there is nothing to scale against.
* **Edge-resident** — the workload runs at the edge, not in the fabric, and
  reconciles.

A service is never *absent* from a zone where its data lives. The
`audit-service` is edge-resident rather than absent precisely because an
audit trail with a hole is worse than a delayed one.

---

## 5. IL5 versus IL6

The two accreditation levels are not a slider; they are different deployment
shapes.

| | IL5 — accredited cloud enclave | IL6 — on-prem classified enclave |
|---|---|---|
| Where | GovCloud, Azure Government, equivalent | On-premises, inside the accredited perimeter |
| Profile | `il5` | `il6` |
| Networking | Overlay network; private ingress class | **`hostNetwork: true`** — the pods take the enclave's own interfaces so the enclave's egress control applies to them directly |
| DNS | `ClusterFirst` | `ClusterFirstWithHostNet` |
| Node placement | Zone spreading across availability zones | **Required pod anti-affinity per host** — a host loss must not take a service with it |
| Storage | `ngsh-encrypted-retain` — encrypted, retained | **`ngsh-classified-local`** — dedicated local storage, never shared infrastructure |
| Capacity | Elastic; HPA on the request-serving services | **Planned, not elastic.** Autoscaling is off: a classified enclave runs on capacity that has been sized and accredited |
| Ingress | Internal ingress class only | **None.** No ingress controller in the enclave; the console is reached through an operator jump host |
| Egress | Allowed to an approved endpoint list | Denied beyond the enclave's own segments |
| Disruption budget | On | On |
| Handling | CUI | SECRET / TOP SECRET material |

Two consequences worth stating plainly:

1. **An IL6 deployment is not an IL5 deployment with a bigger storage class.**
   The host networking, the anti-affinity requirement and the absence of an
   ingress controller are structural differences. You cannot promote an IL5
   release into an IL6 enclave by changing values alone and expecting it to
   be accredited — the accreditation covers the topology.
2. **An IL5 release is not a downgrade of an IL6 release.** The IL5 profile
   runs an elastic, ingress-fronted, zone-spread topology. An IL6 profile
   runs a fixed-capacity, host-networked, anti-affinity topology. Each is
   correct for its own zone.

The `edge` profile is a third shape again, and is *not* an IL5/IL6 variant:
one replica, no host networking, node-local storage, no ingress, no egress.

---

## 6. The graph store

The digital thread is a property graph; the platform's own data model calls
for a graph database. For local development, and for any zone where a graph
engine is not yet accredited, the graph is projected into PostgreSQL.

This is a deployment decision with a strict boundary:

* **Only the `thread-service` talks to the graph.** Every other service
  reaches the graph through the thread service's API, or not at all.
* The selection is **two environment variables** (`NGSH_GRAPH_BACKEND`,
  `NGSH_GRAPH_URL`), so moving to Neptune or JanusGraph is a configuration
  change plus one adapter implementation.
* Because the graph is a **projection of the event log**, the migration is a
  backfill-and-replay, not a data migration. Nothing is lost by switching.

See `compose/README.md`, §8 for the full migration path.

---

## 7. The deployment layer contains no domain logic

**Rule.** This directory states *where* something runs, *how many* copies,
*what it may talk to*, and *how it is configured*. It never states *what the
platform means*.

Concretely, the following are forbidden here, and are reviewed for:

| Forbidden in this directory | Why | Where it belongs |
|---|---|---|
| Classification rules (e.g. "a RESTRICTED record may not be written to CUI storage") | Domain logic. Enforcing it in the manifest would mean it is enforced in only one deployment shape. | The ontology contract and the policy service. |
| Entity validation, relation rules, immutability triggers | Domain logic. | Application migrations, which own the domain tables. |
| Retention periods, lineage rules, lineage computation | Domain logic. | The services and the contracts. |
| Business-level routing or feature flags that encode policy | Domain logic. | Service configuration, injected through `config.extra`. |
| Any credential, key or connection string | Secrets do not belong in a repository. | The platform secret manager; `values.secrets` holds placeholders only. |

What *is* allowed, and what this directory does:

* Topology: replicas, node placement, anti-affinity, spreading.
* Networking: which ports, which selectors, which egress is permitted.
* Storage: size, class, access mode.
* Identity: service accounts, projected tokens, minimal RBAC.
* Configuration: environment variables, ConfigMap contents, secret
  references.
* Observability: collector wiring and telemetry conventions.

The test for a change here is simple: **could this statement be true of a
service in a different pillar, a different zone, or a different
classification — without being false?** If yes, it belongs here. If a
statement would only ever be true for one domain concept, it does not.

The `postgres/init.sql` script illustrates the boundary precisely: it creates
extensions, the five foundation schemas, the runtime roles and their grants.
It does **not** create the domain tables — the application migrations own
those, and the script documents the expected shape in comments only.

---

## 8. Health endpoints

Every platform service exposes two endpoints:

| Endpoint | Meaning | Consumed by |
|---|---|---|
| `GET /healthz` | Liveness — the process is up and responsive | Compose healthchecks, Kubernetes liveness/startup probes, the Helm test pod |
| `GET /readyz` | Readiness — dependencies are reachable and the service can serve | Kubernetes readiness probes, load-balancer gating |

Both return `200` with a JSON body. This is an image contract: every service
image must also provide `/bin/sh` and at least one of `wget` or `curl` so
that container healthchecks can be expressed portably.

---

## 9. Choosing a deployment

| Situation | Use |
|---|---|
| Day-to-day development | `compose/` — `docker compose up` |
| CI | `compose/` with `--profile edge` for the annex path; the chart's `local` profile for manifest checks |
| Accredited cloud enclave | Helm chart, `deploymentProfiles.activeProfile=il5`, `existingSecret` set, internal ingress class |
| On-prem classified enclave | Helm chart, `deploymentProfiles.activeProfile=il6`, `existingSecret` set, no ingress |
| Factory floor / test range | Helm chart, `deploymentProfiles.activeProfile=edge`, installed on the annex's single node, no egress |

```bash
# Render a profile before committing to it
helm template ngsh deploy/helm/ngsh --set deploymentProfiles.activeProfile=il6 | less

# Apply and verify
helm upgrade --install ngsh deploy/helm/ngsh -n ngsh \
  --set deploymentProfiles.activeProfile=il5 \
  --set existingSecret=ngsh-prod-secret
helm test ngsh -n ngsh --logs
```

---

## 10. Repository map

```
deploy/
├── README.md                     this document
├── compose/                      local development topology
│   ├── docker-compose.yml        6 services + console + Postgres + OTel collector
│   ├── postgres/init.sql         extensions, schemas, roles, grants
│   ├── web/                      console image, nginx config, proxy headers
│   └── README.md
├── helm/ngsh/                    Kubernetes chart
│   ├── Chart.yaml
│   ├── values.yaml               base values + the four deployment profiles
│   ├── values.schema.json        values shape validation
│   ├── templates/                all rendered objects
│   └── README.md
└── otel/
    ├── otel-collector.yaml       OTLP in, generic OTLP out
    └── README.md                 trace/metric/log conventions, cardinality rules
```
