# NGSH — Next-Generation Scaled Hypersonics

**A dual-mission digital engineering, test and industrial-readiness platform for the
American hypersonic enterprise.**

NGSH is the connective infrastructure between the organisations that design, build,
test and sustain hypersonic systems. It gives the strike side — model-based systems
engineering, digital-thread manufacturing, ceramic-matrix-composite process
intelligence and surge readiness — and the shield side — counter-hypersonic
kill-chain engineering, threat digital twins and the virtual test enterprise — one
shared ontology, one event-sourced record of truth, and one zero-trust data fabric.

> **This repository is the complete reference build.** All 34 capabilities across
> eight pillars, all seven external interface boundaries and the shared foundation
> are implemented, runnable and tested. External counterpart systems, classified
> data and accreditation are programme-supplied; the software side of every
> connection is finished and waiting. See
> [`docs/architecture/08-complete-build.md`](docs/architecture/08-complete-build.md).

**Proprietary and confidential software of Crocell Company.** All rights reserved.
Use is governed by the [LICENSE](LICENSE) in this repository.

---

## At a glance

| | |
|---|---|
| **Product** | NGSH — Next-Generation Scaled Hypersonics |
| **Owner** | Crocell Company |
| **Purpose** | One shared digital thread for the design, manufacture, test and sustainment of hypersonic systems, on both the strike and the shield side of the mission |
| **Scope delivered** | 34 capabilities · 8 pillars · 7 external interfaces · 23 entity types · 10 relation types · 11 event types · 9 cross-entity invariants |
| **Runtime** | 16 independently deployable services, a web console, and an edge annex agent |
| **Posture** | Event-sourced, contract-first, zero-trust, platform-agnostic (local / IL5 / IL6 / edge) |
| **Verification** | 466 automated tests · 279 contract checks · codegen gate · two live end-to-end demonstrations |
| **Licence** | Proprietary — Crocell Company |

---

## Contents

| | |
|---|---|
| [1. Executive summary](#1-executive-summary) | [10. Use cases](#10-use-cases) |
| [2. The problem](#2-the-problem) | [11. Demonstration](#11-demonstration) |
| [3. What NGSH is](#3-what-ngsh-is) | [12. Verification](#12-verification) |
| [4. How the platform works](#4-how-the-platform-works) | [13. Deployment profiles](#13-deployment-profiles) |
| [5. Capability catalogue](#5-capability-catalogue) | [14. Security and governance posture](#14-security-and-governance-posture) |
| [6. External interface boundary](#6-external-interface-boundary) | [15. What remains programme-supplied](#15-what-remains-programme-supplied) |
| [7. Working implementation](#7-working-implementation) | [16. Documentation map](#16-documentation-map) |
| [8. Quick start](#8-quick-start) | [17. Licence](#17-licence) |
| [9. Worked examples](#9-worked-examples) | |

---

## 1. Executive summary

Hypersonic programmes fail for reasons that are rarely aerodynamic. They fail
because the design that was analysed is not the design that was built, because the
part that was built is not the part that was tested, because the test data that
proved the requirement cannot be found three years later, because a single
supplier of a single material quietly became the programme's critical path, or
because nobody can state — with evidence — that the industrial base can produce
the required rate.

NGSH addresses that class of failure directly. It is not a modelling tool, a CAD
package, a PLM system or a manufacturing execution system. It is the **connective
layer** that sits across them and makes their outputs trustworthy, traceable and
comparable:

* **Every fact is an event.** Design decisions, factory runs, test results,
  supplier changes and engagement outcomes are appended to one immutable log. The
  log is the system of record.
* **Every view is derived.** The digital thread, search indexes, lakehouse
  catalogue and programme KPIs are projections rebuilt from that log. A projection
  can be destroyed and reconstructed without loss.
* **Every shape is a contract.** The 23 entity types, 10 relation types and 11
  event types live in JSON Schema under [`contracts/`](contracts/). Code is
  generated from them and a staleness gate fails the build on drift.
* **Every action is governed.** Attribute-based access control with explicit-deny
  precedence and fail-closed defaults; a hash-chained, tamper-evident ledger; and
  classification partitioning enforced at the storage boundary.
* **Every derived value names its source.** Provenance, method and confidence are
  mandatory on derived results. A model without fidelity evidence cannot be used.

The result is a platform on which a programme can answer, with evidence: *what is
flying, what is it made of, who built it, what proved it, what does it cost, and
can we build more of it.*

---

## 2. The problem

A modern hypersonic programme is a network of specialised organisations: prime
contractors, material suppliers, national laboratories, test ranges, university
partners and government programme offices. Each runs its own tools and keeps its
own records. The seams between them are where programmes lose time and money:

| Failure mode | Consequence |
|---|---|
| Design intent diverges from as-built configuration | Tests validate a vehicle that was never manufactured |
| Test evidence is filed per campaign, not per requirement | Verification status is asserted rather than demonstrated |
| Material and process history is incomplete | A defect cannot be traced to a lot, a run or a parameter |
| Supplier exposure is discovered during a shortage | Schedule slips before mitigation can start |
| Simulation models are used beyond their validated envelope | Decisions rest on unquantified error |
| Threat and interceptor models evolve separately | Red and blue are not measuring the same threat |
| Access control is application-specific and inconsistent | Classified and controlled data leak across programme boundaries |
| Records can be edited after the fact | Audit and accreditation become an exercise in trust |

NGSH is designed so that each of those failures becomes structurally difficult
rather than a matter of discipline.

---

## 3. What NGSH is

The platform has three layers, and the boundaries between them are deliberate.

### 3.1 The contract layer — `contracts/`

The contract layer is the single source of truth for every shape in the platform.
It is data, not code:

```
contracts/
  ontology/
    registry.json         23 entity types · 10 relation types · 9 invariants
    entities.schema.json  per-type attribute schemas
    relations.schema.json per-type endpoint and cardinality rules
    common.schema.json    identifiers, classifications, provenance, confidence
  events/
    envelope.schema.json  the event envelope every event must satisfy
    catalogue.json        the 11 event types and their payload schemas
  policy/
    access-policy.json    the ABAC rule set, expressed as data
  audit/
    ledger.schema.json    the hash-chained ledger entry
```

Nothing in the platform may invent a shape outside this layer. Changing an entity
type, a relation, an event payload or a policy rule is a **reviewed contract
change** before it is a code change; `make contracts` and `make codegen-check` are
merge gates. Typed Python models are generated from the schemas, and the build
fails if the committed models drift from a fresh generation.

### 3.2 The foundation — six services

The foundation is the substrate every pillar stands on. It is deliberately small
and deliberately boring, because it is the part that cannot be retrofitted once
eight pillars depend on it.

| Service | Responsibility |
|---|---|
| `ontology` | Serves the contract layer; validates entities and relations against it |
| `fabric` | The append-only event log — the system of record |
| `policy` | The Policy Decision Point for attribute-based access control |
| `audit` | The tamper-evident, hash-chained ledger |
| `thread` | The digital-thread projection, traversal and search |
| `ingest` | Bulk admission, lineage, digests and content-addressed storage |

### 3.3 The pillars — eight domains

Each pillar is a set of domain rules expressed as pure functions in
`libs/ngsh-core`, exposed by its own deployable service. A pillar writes
authoritative facts as events, reads them back through the projection, and can be
deployed and licensed independently.

| Pillar | Domain | Service(s) |
|---|---|---|
| **A** | MBSE, configuration and the digital thread core | `architecture` |
| **B** | Manufacturing and materials process intelligence | `manufacturing`, `testlab` |
| **C** | Test, evaluation and flight-demonstration data | `ingest`, `testlab` |
| **D** | Supply chain and production scaling | `supply` |
| **E** | Cleared workforce pipeline of record | `workforce` |
| **F** | Counter-hypersonic kill-chain engineering | `engagement` |
| **G** | Test enterprise and M&S federation | `testlab`, `thread` |
| **H** | Industrial surge and affordability | `industrial` |

---

## 4. How the platform works

### 4.1 The write path

Every authoritative fact follows one path. There is no second write path, and no
pillar keeps its own authoritative table.

```
caller
  │
  ▼
gateway  ── /api/<service>/... ──▶  pillar or foundation service
                                        │
                                        ├─ 1. resolve the actor from the identity provider
                                        ├─ 2. ask the policy service for a decision (PDP)
                                        ├─ 3. validate the payload against the contract layer
                                        ├─ 4. apply the pillar's domain rules (pure functions)
                                        ├─ 5. append the event to the fabric (system of record)
                                        ├─ 6. append the ledger entry (hash-chained audit)
                                        └─ 7. project the event into the digital thread
                                        │
                                        ▼
                                   entity + decision returned
```

Two attributes of this path matter:

* **Steps 5 and 6 are not optional.** An access decision produces both a ledger
  entry and an `access.decision.recorded` event. Either alone is a weaker
  assurance: a ledger nobody can query, or a history that can be rewritten
  undetected.
* **Step 7 is repeatable.** Projection is a pure function of the log. Replaying
  the log from cursor zero reconstructs the graph exactly.

### 4.2 The read path

Reads never go to a service's private state. They go to the projection:

```
console / caller ──▶ gateway ──▶ thread ──▶ projection (entities, relations, search)
                                     ▲
                                     └── rebuilt from fabric at any time
```

Because the projection is derived, it is safe to delete. The e2e suite does
exactly that: it ingests data, projects it, traces it, **destroys the projection,
rebuilds it from the event log alone**, and asserts the thread comes back
identical.

### 4.3 Policy and audit

Access control is attribute-based, with the Policy Decision Point separated from
the enforcement point (ADR-0004). Four rules are absolute:

1. **Explicit deny wins** over any allow, regardless of ordering.
2. **Anything unmatched is denied.** A resource type not named in an allow rule is
   unreachable.
3. **Ambiguity fails closed.** An unparseable classification is treated as *more*
   restricted, never less.
4. **Every decision is recorded twice** — as a ledger entry and as an event — so
   the assurance is both tamper-evident and queryable.

The ledger is a hash chain: each entry commits to its predecessor. Rewriting
history is detectable, and `GET /api/audit/v1/ledger/verify` proves the chain.

### 4.4 Determinism and rebuild

Anything the platform computes twice with the same inputs produces the same
answer. That applies to Monte Carlo engagement batches (draws are hash-derived,
not random), edge reconciliation, variant generation and threat-model derivation.
Determinism is what makes a result reviewable years later, and what makes a
projection rebuild a proof rather than a hope.

### 4.5 System diagram

```
                       ┌──────────────────────────────────────┐
                       │        NGSH CONTROL CONSOLE          │
                       │  event stream · digital thread ·     │
                       │  ledger · policy · ontology          │
                       └──────────────────┬───────────────────┘
                                          │
                                   ┌──────▼───────┐
                                   │   gateway    │  one address, one proxy
                                   │     :8080    │
                                   └──────┬───────┘
                                          │
┌─────────────────────────────────────────┼─────────────────────────────────────────┐
│                    ZERO-TRUST DATA FABRIC (CUI · ABAC · audit · partition)        │
│                                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   ontology   │  │    fabric    │  │    policy    │  │    audit     │          │
│  │  23 types    │  │  event log   │  │   PDP/PEP    │  │ hash chain   │          │
│  │  10 relations│  │  system of   │  │  explicit    │  │ tamper-      │          │
│  │  9 invariants│  │  record      │  │  deny wins   │  │ evident      │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         └─────────────────┴─────────────────┴─────────────────┘                   │
│                                    ┌──────────────┐                              │
│                                    │    thread    │  projection + traversal      │
│                                    └──────┬───────┘                              │
│                                           │        ┌──────────────┐              │
│                         ┌─────────────────┴────────┤    ingest    │              │
│                         │                          │  lineage +   │              │
│              ┌──────────┴──────────┐               │  digest +    │              │
│              │     EDGE ANNEX      │               │  classification             │
│              │ degraded mode,      │               └──────────────┘              │
│              │ store-and-forward   │                                             │
│              └─────────────────────┘                                             │
└──────────────────────────────────────────────────────────────────────────────────┘
```

The foundation services are independently deployable, communicate over plain HTTP,
and store their state behind a small executor interface that runs on SQLite
locally and PostgreSQL in an accredited environment. **No domain module imports a
cloud-provider SDK** (ADR-0003): the same image lands in an accredited cloud, an
on-prem enclave or a disconnected range annex without change.

---

## 5. Capability catalogue

Thirty-four capabilities across eight pillars. Each is reachable through a tested
path; the matrix is defined once in
[`libs/ngsh-core/ngsh_core/capabilities.py`](libs/ngsh-core/ngsh_core/capabilities.py)
and a unit test asserts that every declared endpoint exists on the owning
service's router.

### Pillar A — MBSE and the digital thread core

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| A-1 | Digital twin backbone | `architecture` | `POST /v1/baselines`, `POST /v1/baselines/{id}/verify` |
| A-2 | Modularity engine | `architecture` | `POST /v1/variants/generate`, `POST /v1/variants/{id}/core-error` |
| A-3 | Requirements-to-test traceability | `architecture` | `GET /v1/requirements/{id}/coverage`, `GET /v1/requirements/gaps` |
| A-4 | Technology insertion planner | `architecture` | `POST /v1/insertion/assess` |
| A-5 | Digital engineering exchange | `architecture` | `POST /v1/icds/generate`, `GET /v1/sysml/export`, `POST /v1/sysml/import` |

### Pillar B — manufacturing and materials process intelligence

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| B-1 | Defense MES | `manufacturing` | `POST /v1/travellers`, `POST /v1/process-runs`, `GET /v1/genealogy/{id}` |
| B-2 | CMC process characterisation | `manufacturing` | `POST /v1/drift`, `POST /v1/process-runs` |
| B-3 | Test capability management | `testlab` | `POST /v1/campaigns`, `GET /v1/campaigns/{id}/curation` |
| B-4 | Rate and cost simulation | `manufacturing` | `POST /v1/simulate-rate`, `POST /v1/production/simulate` |

### Pillar C — test, evaluation and flight-demonstration data

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| C-1 | Unified test data lake | `ingest` | `POST /v1/lakehouse/objects`, `GET /v1/lakehouse/objects/{digest}/verify` |
| C-2 | Automated reduction and anomaly detection | `testlab` | `POST /v1/anomalies/detect`, `POST /v1/test-results` |
| C-3 | Twin validation loop | `testlab` | `POST /v1/twin-validation`, `POST /v1/models/{id}/regenerate` |
| C-4 | Campaign management | `testlab` | `POST /v1/campaigns`, `POST /v1/schedule/optimise` |

### Pillar D — supply chain and production scaling

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| D-1 | Multi-tier visibility | `supply` | `GET /v1/supply-risks`, `POST /v1/suppliers` |
| D-2 | Foreign dependency mapping | `supply` | `POST /v1/reconstitutes`, `GET /v1/supply-risks` |
| D-3 | Surge readiness twin | `supply` | `POST /v1/surge` |

### Pillar E — cleared workforce pipeline of record

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| E-1 | Digital-twin training | `workforce` | `POST /v1/training/scenarios`, `GET /v1/training/coverage` |
| E-2 | Replicable curriculum engine | `workforce` | `POST /v1/curriculum/packages` |
| E-3 | Skills credentialing | `workforce` | `POST /v1/credentials`, `GET /v1/work-authorisation` |
| E-4 | Workforce demand model | `workforce` | `POST /v1/workforce/gap` |
| E-5 | Industry-academia sandbox | `workforce` | `POST /v1/extracts` |

### Pillar F — counter-hypersonic kill-chain engineering

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| F-1 | Threat digital twins | `engagement` | `POST /v1/threats`, `POST /v1/threat-models` |
| F-2 | Kill-chain simulator | `engagement` | `POST /v1/scenarios/{id}/batch`, `GET /v1/kill-chain` |
| F-3 | Fire-control data quality scoring | `engagement` | `POST /v1/fire-control/measure`, `POST /v1/fire-control/quality` |
| F-4 | Interim architecture workbench | `engagement` | `POST /v1/candidates/evaluate` |
| F-5 | Golden Dome readiness | `engagement` | `POST /v1/plugins`, `POST /v1/plugins/{id}/run` |
| F-6 | Red/blue co-simulation | `engagement` | `POST /v1/co-simulation` |

### Pillar G — test enterprise and M&S federation

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| G-1 | Virtual test range | `thread` | `GET /v1/datasets`, `GET /v1/datasets/{id}/lineage` |
| G-2 | Campaign digital twin | `testlab` | `POST /v1/range-capacity`, `POST /v1/schedule/optimise` |
| G-3 | Automated model validation | `testlab` | `POST /v1/twin-validation`, `POST /v1/models/{id}/regenerate` |
| G-4 | Fidelity registry | `testlab` | `GET /v1/fidelity/registry`, `POST /v1/fidelity/{id}/drift` |

### Pillar H — industrial surge and affordability

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| H-1 | Surge readiness command | `industrial` | `POST /v1/surge-readiness` |
| H-2 | Reconstitution planning | `industrial` | `POST /v1/reconstitution/assess` |
| H-3 | Affordability engineering | `industrial` | `POST /v1/affordability/trace`, `POST /v1/affordability/rate-curve` |

---

## 6. External interface boundary

Seven interfaces, each with a declared direction, payload validation and a
deterministic, content-addressed receipt so that a retry is recognisable and a
duplicate is detectable.

| Id | Interface | Direction | Boundary |
|---|---|---|---|
| IF-1 | Prime PLM/MES APIs | bi-directional | REST + STEP AP242 / OPC-UA payloads |
| IF-2 | MDA/Aegis systems | bi-directional | Scenario exchange over a message bus |
| IF-3 | SDA PWSA / HBTSS feeds | inbound only | Inbound tracks accepted; outbound is refused by rule |
| IF-4 | Range instrumentation | bi-directional | Test-article manifests and TDMS/HDF5 references |
| IF-5 | University LMS / AR-VR clients | outbound | Curriculum package export |
| IF-6 | Government identity (PIV/ICAM) | inbound | Signed assertion verified, then redacted before persistence |
| IF-7 | Analytics / BI | outbound | Programme report export |

**`ADAPTER` is an honest word.** The platform supplies a validated, deterministic
simulated counterpart and a stable contract; the real counterpart is supplied and
accredited by the programme. Replacing the simulation with the real system changes
configuration, not the contract, the direction rule or the receipt shape.

The local IF-6 path issues an HMAC-signed assertion through the `piv-sim` identity
provider. Issuance is refused outside the `local` and `edge` profiles, and the
production provider fails closed without live metadata and verification endpoints.

---

## 7. Working implementation

### 7.1 Service topology

Every service has its own `pyproject.toml`, container image, Compose service and
Helm values block. A programme can deploy Pillar B without Pillar F.

| Service | Port | Responsibility |
|---|---|---|
| gateway | 8080 | Single entry point: platform status, capability matrix, transparent `/api/<service>/...` proxy |
| ontology | 8081 | The contract layer: types, relations, invariants, validation |
| fabric | 8082 | The append-only event log — the system of record |
| policy | 8083 | The Policy Decision Point for ABAC |
| audit | 8084 | The tamper-evident, hash-chained ledger |
| thread | 8085 | Digital-thread projection, traversal, search and dataset catalogue |
| ingest | 8086 | Batch admission, lineage, digests and content-addressed objects |
| edge-agent | 8087 | Edge annex: degraded capture, local reads, deterministic reconciliation |
| architecture | 8088 | Pillar A: baselines, interfaces, requirement traceability, SysML/ICD exchange |
| workforce | 8089 | Pillar E: skills, credentials, work authorisation, workforce gap |
| manufacturing | 8090 | Pillar B: travellers, process runs, genealogy, drift, production rate |
| testlab | 8091 | Pillars B/C/G: campaigns, results, anomalies, twin loop, ranges, fidelity |
| supply | 8092 | Pillar D: single-source exposure, reconstitution, surge |
| engagement | 8093 | Pillars F/G: threats, scenarios, engagement batches, co-simulation |
| industrial | 8094 | Pillar H: verified surge, measured reconstitution, affordability |
| analytics | 8095 | Programme KPIs computed from the digital thread |
| integration | 8096 | The IF-1…IF-7 register, direction enforcement, delivery records |

Every service exposes `/healthz`, `/readyz`, `/v1/service/info` and OpenAPI
documentation at `/docs`.

### 7.2 Repository layout

```
contracts/            Contract layer — JSON Schema, registry, policy, event catalogue
libs/ngsh-core/       Shared domain primitives: envelope, ontology, policy, audit,
                      event log, projection, identity, storage, and the pure domain
                      engines for every pillar
services/             Sixteen independently deployable services
apps/web/             The engineering console (React + TypeScript)
apps/edge-agent/      Edge annex agent — degraded mode and reconciliation
tests/                unit · integration · e2e · contract parity
tools/                Contract validator and code generator
deploy/               Platform-agnostic deployment: Compose, Helm, OpenTelemetry
docs/                 ADRs, architecture, roadmap, staffing, risk register
scripts/              run_stack · seed · demo · demo_programme · demo_full · demo_edge
```

### 7.3 Engineering rules the code enforces

These are not conventions. Each is enforced in code, in a contract or in a test.

1. **The event log is the system of record.** Graph, search, lakehouse catalogue
   and KPIs are projections rebuilt by replay. Delete a projection and it returns.
2. **Contracts, not code, define shapes.** An ontology change is a reviewed
   artefact before it is a code change.
3. **Fail closed.** Unparseable classification is treated as more restricted; an
   unmatched policy is a denial; a model without a fidelity score is rejected.
4. **Evidence is immutable.** Test results are append-only. A correction is a new
   superseding record, never an edit.
5. **Everything derived names its source.** Provenance, method and confidence are
   required on every derived value.
6. **No cloud SDK in a domain package.** Placement, storage and identity arrive
   through configuration and opaque connection strings.
7. **Regeneration never self-approves.** A model regenerated from evidence is
   recorded as `approvedForUse: false` until a named human releases it.
8. **Conflicting immutable evidence escalates.** Edge reconciliation resolves
   deterministically where it can, and raises a human review item where two
   immutable records genuinely conflict.

---

## 8. Quick start

Requirements: [uv](https://docs.astral.sh/uv/), Python 3.12+. Docker is optional.

```bash
git clone <repository-url> ngsh
cd ngsh

make setup          # install dependencies, create ./data
make verify         # lint + contracts + codegen + the full test suite
make dev            # start the sixteen-service platform
```

In a second terminal:

```bash
make demo            # the foundation, end to end
make demo-programme  # all eight pillars in one thread traversal
make demo-full       # all 34 capabilities and 7 interfaces through the gateway
make demo-edge       # the edge annex capture and reconciliation flow
```

The platform is then live at:

| Surface | URL |
|---|---|
| Gateway / API entry point | http://localhost:8080 |
| Platform status | http://localhost:8080/v1/platform/status |
| Capability matrix | http://localhost:8080/v1/platform/capabilities |
| API documentation | http://localhost:8080/docs |
| Console (dev server) | http://localhost:5173 |

To keep test data out of the working tree:

```bash
NGSH_DSN="sqlite:////tmp/ngsh-test.db" NGSH_DATA_DIR=/tmp/ngsh-data make dev
```

---

## 9. Worked examples

All examples below run against the local stack with `make dev` active. They use
the gateway, which proxies `/api/<service>/...` to the owning service without
rewriting the domain. Examples that read the thread assume `make demo` has been
run at least once, since it seeds the `REQ:DEMO-0001` requirement and its
verification evidence.

### 9.1 Ask the platform what it is

```bash
curl -s localhost:8080/v1/platform/status | jq
curl -s localhost:8080/v1/platform/capabilities | jq '.count, .pillarCount, .interfaceCount'
```

### 9.2 Validate an entity against the contract layer

```bash
curl -s -X POST localhost:8080/api/ontology/v1/ontology/validate \
  -H 'content-type: application/json' \
  -d '{
    "kind": "entity",
    "entity": {
      "id": "TR:DEMO-0001",
      "type": "TestResult",
      "tenant": "ngsh",
      "version": 1,
      "createdAt": "2026-11-14T00:00:00Z",
      "updatedAt": "2026-11-14T00:00:00Z",
      "classification": {"level": "CUI"},
      "attributes": {
        "testMethod": "plasma-arc-heater",
        "outcome": "PASS",
        "measurements": [
          {"name": "peak_temperature", "value": 1840.0, "unit": "K"}
        ]
      }
    }
  }' | jq
```

A conforming entity returns `"valid": true`. Change `"outcome"` to a value outside
the vocabulary and the response names the failing path — the contract is the
validator, not the service.

### 9.3 Admit a batch of test data

```bash
curl -s -X POST localhost:8080/api/ingest/v1/ingest \
  -H 'content-type: application/json' \
  -d '{
    "source": "plasma-arc-heater.itc",
    "format": "NDJSON",
    "entityType": "TestResult",
    "classification": {"level": "CUI"},
    "payload": "{\"id\":\"TR:DEMO-0002\",\"testMethod\":\"plasma-arc-heater\",\"outcome\":\"MARGINAL\"}\n{\"id\":\"TR:DEMO-0003\",\"testMethod\":\"tensile\",\"outcome\":\"PASS\"}"
  }' | jq
```

The response reports accepted and rejected counts plus the SHA-256 of the batch, so
the same payload submitted twice is recognisably the same payload.

### 9.4 Read the event log and rebuild the thread

```bash
curl -s localhost:8080/api/fabric/v1/stats | jq '.total, .byType'

# replay the whole log into the projection
curl -s -X POST localhost:8080/api/thread/v1/project/replay | jq '.replayed, .stats'
```

Deleting the projection and running this endpoint is a complete rebuild. That is
the operational meaning of "the log is the system of record".

### 9.5 Trace a requirement to its evidence

```bash
curl -s "localhost:8080/api/thread/v1/trace?root=Requirement:REQ:DEMO-0001&depth=3" | jq
curl -s -X POST localhost:8080/api/thread/v1/trace/requirements/REQ:DEMO-0001/coverage | jq
```

The coverage response states whether the requirement is verified, and names every
gap that prevents it. It does not fill gaps with an assumption.

### 9.6 Take an access decision

```bash
curl -s -X POST localhost:8080/api/policy/v1/decisions \
  -H 'content-type: application/json' \
  -d '{
    "subject": {
      "subjectId": "usr:engineer", "kind": "user", "clearance": "TOP SECRET",
      "citizenship": "US", "tenant": "ngsh",
      "programs": ["NGSH-SHY"], "needToKnow": ["NGSH-SHY"]
    },
    "action": "read",
    "resource": {
      "type": "TestResult", "id": "TR:0001",
      "classification": {"level": "CUI"},
      "tenant": "ngsh", "program": "NGSH-SHY"
    }
  }' | jq
```

Change `"citizenship"` to a value outside `NGSH_PERMITTED_CITIZENSHIPS` (default
`US`) and the decision flips to deny. There is no override parameter.

### 9.7 Verify the audit ledger

```bash
curl -s localhost:8080/api/audit/v1/ledger/verify | jq
curl -s localhost:8080/api/audit/v1/ledger/head | jq
```

A single altered entry breaks the chain, and the verifier reports where.

### 9.8 Store and re-verify a lakehouse object

```bash
curl -s -X POST localhost:8080/api/ingest/v1/lakehouse/objects \
  -H 'content-type: application/json' \
  -d '{"content":"TkdTSCBkZW1v","encoding":"base64","mediaType":"application/octet-stream"}' | jq

DIGEST=$(curl -s localhost:8080/api/ingest/v1/lakehouse/objects | jq -r '.objects[0].digest')
curl -s "localhost:8080/api/ingest/v1/lakehouse/objects/$DIGEST/verify" | jq
```

The object is content-addressed; its URI is `ngsh-lake://<sha256>` and the verify
endpoint re-hashes the stored bytes.

---

## 10. Use cases

Each use case below is implemented, exercised by a demonstration script, and
covered by tests.

### 10.1 Prove a requirement with evidence, not assertion

A thermal-protection requirement — *the nosecap shall survive 1800 K for 30
minutes* — is baselined. A plasma-arc-heater result is admitted against a specific
configuration baseline and asserted to `verify` the requirement. The architecture
service checks that the result is a reviewed `PASS`, that the test article was
built to the baselined configuration, and that the result is not superseded. If
any of those fail, a review item is raised rather than a requirement satisfied.

*Capabilities: A-1, A-3, C-2 · Path: `POST /v1/test-results`, `GET /v1/requirements/{id}/coverage`*

### 10.2 Trace a defect to its lot, run and parameters

A process run drifts beyond the configured sigma limit. The manufacturing service
quarantines it for a human — it never auto-dispositions. Genealogy then walks the
chain of custody from the part back through the process run to the material lot,
naming any hop that cannot be resolved instead of skipping it.

*Capabilities: B-1, B-2 · Path: `POST /v1/drift`, `GET /v1/genealogy/{id}`*

### 10.3 Close the simulation-validation loop

A campaign produces residuals against model predictions. The testlab service
reports where the model is weakest, applies a per-quantity correction fitted to
the evidence, and regenerates the model — recorded as *unapproved*. A named
engineer releases it, and the fidelity registry shows the previous approval
withdrawn and every dependent notified.

*Capabilities: C-3, G-3, G-4 · Path: `POST /v1/models/{id}/residuals`, `POST /v1/models/{id}/regenerate`*

### 10.4 Find the single point of failure before it fails

The supply service ranks parts by single-source exposure, traces which suppliers
and facilities reconstitute them, and produces a ranked playbook with cumulative
lead time. When a reconstitution path is recorded, the exposure count drops — and
the change is visible, not inferred.

*Capabilities: D-1, D-2 · Path: `GET /v1/supply-risks`, `POST /v1/reconstitutes`*

### 10.5 Answer "can industry build this rate?"

The industrial service converts a demand figure into an achievable rate with a
two-sided confidence interval derived from supplier risk. The figure is reported
*and* marked verified only when a confidence interval, a named owner and the twin
run that produced it are all present. Otherwise the gaps are named.

*Capabilities: H-1, H-2 · Path: `POST /v1/surge-readiness`*

### 10.6 Compare red and blue against the same threat

A threat system is modelled once. The kill-chain simulator runs engagement batches
against it, the fire-control scorer quantifies data-quality defects, and the
co-simulation refuses to compare red and blue traces that do not resolve to the
same threat node. A comparison between two different threats is not a measure of
the balance, and the platform will not pretend otherwise.

*Capabilities: F-1, F-2, F-3, F-6 · Path: `POST /v1/co-simulation`*

### 10.7 Operate a disconnected range or factory floor

The edge agent captures events while the fabric is unreachable, serves reads from
a local cache, and reconciles deterministically when the link returns. Where two
immutable records genuinely conflict, it escalates to a human rather than picking
a winner (ADR-0006).

*Service: `edge-agent` · Path: `make demo-edge`*

### 10.8 License one pillar, not the platform

Because each pillar has its own image, chart block and service boundary, a
programme can deploy and license Pillar E (workforce) without Pillars F or G. The
licensed pillar receives the contract layer, the foundation it depends on and its
own projections; it reaches other pillars' data through the event feed, not
through a shared table.

---

## 11. Demonstration

### 11.1 Five commands

```bash
make verify          # prove the code is correct
make dev             # start the platform (terminal A)
make demo            # foundation, end to end (terminal B)
make demo-programme  # eight pillars, one thread
make demo-full       # 34 capabilities, 7 interfaces, 15 services
```

`demo-full` is a completeness gate, not a smoke test. It walks every capability and
every interface through the gateway and **exits non-zero** if any of them is
missing or returns an unexpected shape.

### 11.2 Representative transcripts

Foundation (`make demo`):

```
NGSH foundation — end-to-end demonstration

[1] Ontology
    ok  ontology v1.0.0: 23 entity types, 10 relation types, 9 invariants
[2] Validate a TestResult against the contract layer
    ok  entity conforms to the TestResult contract
[3] Ingest a batch of test data
    ok  batch BATCH:…: 2 accepted, 0 rejected
[4] Confirm the events reached the fabric
    ok  N events in the log across M aggregates
[5] Project into the digital thread
    ok  replayed N events; projection at cursor …
[6] Trace a requirement to its verification evidence
    ok  trace from REQ:DEMO-0001 reached 2 nodes via 1 edge
        TR:DEMO-0001 --verifies--> REQ:DEMO-0001
    ok  requirement verified=True coverage=1.0
[7] Evaluate an access decision
    ok  decision ALLOW for usr:demo read TestResult
[8] Verify the audit chain
    ok  ledger chain verified across N entries
```

Programme traversal (`make demo-programme`):

```
== Fabric: publish the programme baseline
  ok  14 events accepted
== Thread: rebuild the projection from the log
  ok  N entities, M relations projected
== Pillar E: credential the operator
  ok  credential CRD:… active, authorisation allowed=True
== Pillar A: pin the configuration baseline
  ok  baseline BL:… (…)
== Pillar C: admit the test result against that baseline
  ok  result TR:… admitted, requirement verified=True
== Pillar B: record the run and check the traveller
  ok  run PR:… recorded, next operation OP2, days required 3
== Pillar C: close the twin loop from the evidence
  ok  model fidelity 0.7 -> 0.72
== Pillar D: exposure, reconstitution and surge
  ok  C-007 findings … -> …; bottleneck SUP:…
== Pillars F and G: engage the threat
  ok  20000 runs in ~0.05s, mean Pk 0.7992, kill chain complete=True
== Thread: one traversal reaches every pillar
  ok  10 nodes and 10 edges across all pillars

Programme traversal complete.
```

Complete build (`make demo-full`):

```
== Gateway: the platform reports itself
  ok  34 capabilities across 8 pillars, 7 interfaces, 15 services healthy
...
== Interfaces: IF-1 to IF-7 cross the boundary
  ok  IF-1..IF-7 accepted: IF-1, IF-2, IF-3, IF-4, IF-5, IF-6, IF-7
== Cross-cutting reads: analytics, search and one end-to-end trace
  ok  7 KPI(s); 3 search hit(s); 15 traced node(s)

Complete-build traversal finished: 34/34 capabilities, 7/7 interfaces, 15 services.
```

*(Identifiers are ULIDs and differ between runs; counts and outcomes do not.)*

### 11.3 The console

`apps/web` is a React/TypeScript console with seven routes:

| Route | Shows |
|---|---|
| `/` | Programme overview and platform health |
| `/events` | The live event stream |
| `/thread` | The digital thread and traversal |
| `/requirements` | Requirement verification coverage |
| `/audit` | The hash chain and ledger entries |
| `/access` | Policy decisions and the rule set |
| `/platform` | Live service health, the 34-capability matrix and the 7-interface register |

All traffic is routed through the gateway in both development (Vite proxy) and the
container topology (nginx upstream), so the console has exactly one backend
address. If the stack is not running, the console degrades to a deterministic mock
dataset **and says so** — the degradation path is a tested behaviour, not a bug.

```bash
cd apps/web
npm ci
npm run lint     # type check
npm run dev      # http://localhost:5173, proxies /api to the gateway
```

---

## 12. Verification

| Gate | Command | Proves |
|---|---|---|
| Lint and format | `make lint` | Style and import hygiene |
| Contracts | `make contracts` | 279 checks: schemas, registry and invariants agree |
| Generated models | `make codegen-check` | No drift between contracts and Python |
| Unit and integration | `make test` | 466 tests: domain rules, HTTP surfaces, e2e |
| Everything | `make verify` | All of the above in one command |
| Live capability sweep | `make dev` + `make demo-full` | 34/34 capabilities, 7/7 interfaces, 15 services |
| Live programme traversal | `make dev` + `make demo-programme` | All eight pillars reachable from one root |

The e2e suite contains the assertion that matters most: it ingests data, projects
it, traces it, takes a policy decision, verifies the audit chain, **destroys the
projection and rebuilds it from the event log alone**, and asserts the thread comes
back identical.

Static deployment validation covers the Compose topology (23 services) and the Helm
chart (17 service blocks across four profiles). Docker and Helm runtime execution
requires an environment where those tools are installed.

---

## 13. Deployment profiles

Platform-agnostic by construction. The same images run in four postures:

| Profile | Posture |
|---|---|
| `local` | Single process, SQLite, development actor, simulated IF-6 |
| `il5` | Accredited cloud enclave, PostgreSQL, HA, PIV/ICAM |
| `il6` | On-prem classified node, dedicated storage, anti-affinity, no public ingress |
| `edge` | Factory floor or range annex, single replica, store-and-forward, later sync |

```bash
# containerised topology
docker compose -f deploy/compose/docker-compose.yml up -d --build

# Kubernetes
helm lint deploy/helm/ngsh
helm template ngsh deploy/helm/ngsh -f deploy/helm/ngsh/values.yaml
```

See [`docs/architecture/05-deployment-architecture.md`](docs/architecture/05-deployment-architecture.md)
and [`deploy/`](deploy/).

---

## 14. Security and governance posture

| Concern | Implementation | Decision |
|---|---|---|
| Access control | ABAC with PDP/PEP separation; explicit deny wins; fail-closed defaults | ADR-0004 |
| Audit | Hash-chained ledger; every decision recorded as entry **and** event | ADR-0005 |
| Classification | Storage partitioning; cross-classification refusal; ambiguous input treated as more restricted | ADR-0007 |
| Identity | Verified actor resolved per request; PIV/ICAM adapter fails closed without live endpoints | ADR-0004 |
| Model governance | Model card + fidelity evidence required before use; regeneration never self-approves | ADR-0008 |
| Data integrity | Append-only evidence; corrections are superseding records | ADR-0001 |
| Edge trust | Degraded capture, deterministic reconciliation, human escalation on conflicting immutable evidence | ADR-0006 |
| Portability | No cloud SDK in any domain package | ADR-0003 |

The full record is in [`docs/adr/`](docs/adr/).

---

## 15. What remains programme-supplied

The platform does not pretend to have data, authority or accreditation it does not
have. Each item below has a working adapter or an explicit fail-closed path.

| Item | Current state | Programme supplies |
|---|---|---|
| PIV/ICAM | Local signed assertion in `local`/`edge`; production provider fails closed | Accredited IdP metadata and verification endpoints |
| Prime PLM/MES | Validated IF-1 adapter with deterministic receipts | The prime's endpoint, credentials and mapping |
| MDA/Aegis | Validated IF-2 exchange | Gateway connectivity and accreditation |
| SDA/PWSA | Inbound-only IF-3 boundary | Feed connection and approval for any outbound path |
| Range instrumentation | Validated IF-4 manifests | Instrumentation streams and range network access |
| LMS / AR-VR | Outbound IF-5 package export | Partner registration and identity federation |
| BI connectors | Outbound IF-7 report export | Consumer endpoint and credential |
| PostgreSQL runtime | Dialect and backend implemented; tests run on SQLite | An accredited database service |
| Container runtime | Compose and Helm validated as files | A registry and cluster |
| Classified data and ATO | Partitioning and denial paths implemented | Data, enclave and authority to operate |

Nothing in this list requires a change to the contract layer.

---

## 16. Documentation map

| Document | Purpose |
|---|---|
| [`NGSH_Preliminary_Software_Design_Document.md`](NGSH_Preliminary_Software_Design_Document.md) | The authoritative design document (PSDD v0.1) |
| [`NGSH_Development_Plan.md`](NGSH_Development_Plan.md) | Delivery plan: increments, work packages, staffing, risk, measurement |
| [`docs/architecture/08-complete-build.md`](docs/architecture/08-complete-build.md) | The complete build: 34 capabilities, 7 interfaces and their runnable paths |
| [`docs/architecture/01-system-context.md`](docs/architecture/01-system-context.md) | Scope, actors, invariants |
| [`docs/architecture/02-ontology-model.md`](docs/architecture/02-ontology-model.md) | The 23 types, 10 relations and 9 invariants |
| [`docs/architecture/03-foundation-services.md`](docs/architecture/03-foundation-services.md) | The substrate in depth |
| [`docs/architecture/04-security-architecture.md`](docs/architecture/04-security-architecture.md) | Zero-trust, ABAC, classification, audit |
| [`docs/architecture/05-deployment-architecture.md`](docs/architecture/05-deployment-architecture.md) | Topology and profiles |
| [`docs/architecture/07-pillar-coverage.md`](docs/architecture/07-pillar-coverage.md) | Each pillar's rules, and what it deliberately does not do |
| [`docs/roadmap/`](docs/roadmap/) | Increments and the full work breakdown |
| [`docs/risk-register.md`](docs/risk-register.md) | 26 risks with owners and leading indicators |
| [`docs/adr/`](docs/adr/) | Eight architecture decision records |

---

## 17. Licence

NGSH is proprietary and confidential software owned by **Crocell Company**.

Copyright © 2026 Crocell Company. All rights reserved.

No licence, express or implied, is granted except by a separate written agreement
signed by an authorised representative of Crocell. Access to this repository does
not confer any right to copy, modify, distribute, sublicense or commercially
exploit the software. The software is subject to United States export control laws;
see [LICENSE](LICENSE) for the full terms, including the export control, warranty
and liability provisions.

Third-party open-source components incorporated by the software remain governed by
their own licences. A written offer to provide applicable notices is available from
Crocell on request.

Licensing and evaluation enquiries: Crocell Company, Legal Department.

---

*Classification handling: this document is CUI. The system it describes is designed
for IL5/IL6 operation. See
[`docs/architecture/04-security-architecture.md`](docs/architecture/04-security-architecture.md).*
