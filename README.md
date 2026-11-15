# NGSH — Next-Generation Scaled Hypersonics

**The digital lab for designing hypersonics.**

NGSH is the connective tissue of a hypersonic programme. Design baselines, factory
runs, material lots, test results, suppliers, people and threat models all live in
one append-only record. Every view — the digital thread, search, datasets, KPIs — is
rebuilt from that record, so any claim can be traced back to its evidence.

It serves both halves of the mission on one substrate: the strike side (design,
manufacture, test, industrial scaling) and the shield side (threat modelling, kill
chains, engagement simulation). They share the same types because they fail for the
same reasons.

**Proprietary and confidential software of Crocell Company.** See [Licence](#licence).

---

## The problem

Hypersonic programmes fail at the seams, not in the physics.

- The design that was analysed is not the configuration that was built or tested.
- A process parameter drifts and nobody can identify the affected lots.
- Requirements are marked verified against evidence that no longer applies.
- A single-source supplier becomes the critical path during a shortage.
- Simulation models are used beyond their validated envelope.
- Red and blue teams model different threats and compare the results anyway.
- Records can be edited after the fact, so audit becomes an act of trust.

These are data problems before they are engineering problems. NGSH fixes the record
so they become structurally difficult.

---

## The platform

**One record. Every view derived. Every claim traceable.**

Six principles define the build:

1. **The event log is the system of record.** Graph, search, lakehouse and KPIs are
   projections. Delete one, replay the log, get it back identical.
2. **Contracts are data.** Twenty-three entity types, ten relations, eleven events
   and nine invariants live in JSON Schema. Python models are generated; drift fails
   the build.
3. **Evidence is immutable.** A test result is never edited. A correction is a new
   record that supersedes the old one.
4. **Access fails closed.** Explicit deny wins; unmatched requests are denied;
   ambiguous classification is treated as more restricted.
5. **Nothing derived is anonymous.** Provenance, method and confidence are required
   on every computed value.
6. **The platform is portable.** No domain package imports a cloud SDK. The same
   image runs in an accredited cloud, an on-prem enclave or a disconnected range.

---

## How it works

### Writes

```
caller ─▶ gateway ─▶ service
                       ├─ resolve actor from identity provider
                       ├─ ask the policy service for a decision
                       ├─ validate payload against the contract layer
                       ├─ apply domain rules (pure functions)
                       ├─ append event to the fabric
                       ├─ append ledger entry (hash chain)
                       └─ project event into the thread
```

The ledger and the access decision are both written: a decision produces a
`access.decision.recorded` event *and* a chain entry. Derived reports are stored as
annotations on the entity they concern, so they rebuild from the log like everything
else.

### Reads

Reads go to the projection, never to private service state. Because the projection
is a pure function of the log, it is disposable. The end-to-end test proves this by
destroying it and rebuilding from the log alone.

### Access and audit

The policy service decides; services enforce. The ledger is a hash chain — each
entry commits to its predecessor, so a rewritten history is detectable and
verification is an endpoint, not a promise.

### Determinism

Monte Carlo draws are hash-derived, not random. Reconciliation, variant generation
and threat derivation are deterministic. Same inputs, same answer, years later.

---

## Scope

### Eight pillars, 34 capabilities

| Pillar | Services | Capabilities |
|---|---|---|
| **A** — design and the thread core | architecture | A-1 Baselines · A-2 Modularity · A-3 Requirement traceability · A-4 Technology insertion · A-5 SysML and ICD exchange |
| **B** — manufacturing and materials | manufacturing, testlab | B-1 Defense MES · B-2 CMC characterisation · B-3 Test capability management · B-4 Rate and cost simulation |
| **C** — test and evaluation data | ingest, testlab | C-1 Test data lake · C-2 Anomaly detection · C-3 Twin validation loop · C-4 Campaign management |
| **D** — supply and scaling | supply | D-1 Multi-tier visibility · D-2 Foreign dependency mapping · D-3 Surge readiness twin |
| **E** — cleared workforce | workforce | E-1 Digital-twin training · E-2 Curriculum engine · E-3 Credentialing · E-4 Demand model · E-5 Industry-academia sandbox |
| **F** — counter-hypersonic engineering | engagement | F-1 Threat twins · F-2 Kill-chain simulator · F-3 Fire-control quality · F-4 Architecture workbench · F-5 Golden Dome readiness · F-6 Red/blue co-simulation |
| **G** — test enterprise | testlab, thread | G-1 Virtual test range · G-2 Campaign twin · G-3 Model validation · G-4 Fidelity registry |
| **H** — industrial surge | industrial | H-1 Surge command · H-2 Reconstitution planning · H-3 Affordability engineering |

Every capability has a tested endpoint. A unit test asserts that every path the
matrix advertises exists on the owning service's router.

### The data model

**23 entity types** — `System`, `Variant`, `Subsystem`, `Part`, `Material`,
`ProcessPlan`, `ProcessRun`, `TestArticle`, `TestCampaign`, `TestResult`,
`Requirement`, `Interface`, `Model`, `ThreatSystem`, `ThreatObservation`,
`EngagementScenario`, `Supplier`, `PartProvenance`, `Skill`, `Credential`, `Person`,
`Facility`, `RangeSlot`.

**10 relations** — `satisfies`, `verifies`, `manufacturedBy`, `characterizedBy`,
`derivedFrom`, `threatens`, `engages`, `requiresSkill`, `supplies`, `reconstitutes`.

**11 events** — `entity.created`, `entity.updated`, `entity.relation.asserted`,
`entity.relation.retracted`, `test.campaign.planned`, `test.result.recorded`,
`process.run.completed`, `model.validated`, `ingest.batch.accepted`,
`access.decision.recorded`, `reconcile.conflict.recorded`.

**9 invariants**, enforced at write time unless noted:

| Id | Rule |
|---|---|
| C-001 | Classification may never fall below the type's floor |
| C-002 | Relations may not cross a classification boundary unless the type permits it |
| C-003 | Test results are immutable; corrections supersede |
| C-004 | A model in a safety-relevant prediction needs approval and a fidelity score |
| C-005 | A credential requires citizenship that permits the activity and a current clearance |
| C-006 | Every referenced person needs a current clearance record |
| C-007 | A critical single-source part needs a reconstitution path or is flagged as risk |
| C-008 | Engagement scenarios are unreadable below their classification |
| C-009 | Classification may not be lowered in place; a downgrade creates a new entity |

New capabilities are computed over these types. None of the 34 required inventing
one.

### Seven interfaces

| Id | Interface | Direction |
|---|---|---|
| IF-1 | Prime PLM and MES | bi-directional |
| IF-2 | Missile-defence systems | bi-directional |
| IF-3 | Satellite track feeds | inbound only |
| IF-4 | Range instrumentation | bi-directional |
| IF-5 | University LMS and AR/VR | outbound |
| IF-6 | Government identity (PIV/ICAM) | inbound |
| IF-7 | Analytics and BI | outbound |

Each boundary validates its payload, enforces its direction and returns a
content-addressed receipt, so retries are recognisable and duplicates detectable.
An adapter is a validated simulated counterpart; swapping in the real system changes
configuration, not the contract.

---

## The services

Every service has its own package, image, Compose entry and Helm block, so a
programme can deploy one pillar without the others.

| Service | Port | Responsibility |
|---|---|---|
| gateway | 8080 | Single entry point: status, capability matrix, `/api/<service>/...` proxy |
| ontology | 8081 | The contract layer: types, relations, invariants, validation |
| fabric | 8082 | The append-only event log — system of record |
| policy | 8083 | The Policy Decision Point |
| audit | 8084 | The hash-chained ledger |
| thread | 8085 | Digital-thread projection, traversal, search, datasets |
| ingest | 8086 | Batch admission, lineage, content-addressed objects |
| edge-agent | 8087 | Degraded capture, local reads, deterministic reconciliation |
| architecture | 8088 | Baselines, interfaces, requirement traceability, SysML and ICD exchange |
| workforce | 8089 | Skills, credentials, work authorisation, workforce gap |
| manufacturing | 8090 | Travellers, process runs, genealogy, drift, production rate |
| testlab | 8091 | Campaigns, results, anomalies, twin loop, ranges, fidelity |
| supply | 8092 | Single-source exposure, reconstitution, surge |
| engagement | 8093 | Threats, scenarios, engagement batches, co-simulation |
| industrial | 8094 | Verified surge, measured reconstitution, affordability |
| analytics | 8095 | Programme KPIs from the thread |
| integration | 8096 | Interface register, direction enforcement, delivery records |

Every service exposes `/healthz`, `/readyz`, `/v1/service/info` and OpenAPI at
`/docs`.

A domain rule is a pure function in `libs/ngsh-core`; the service is transport and
persistence around it. Unit tests cover the rules, HTTP tests cover the transport.

---

## Running it

Requires Python 3.12+ and `uv`. Docker is optional.

```bash
make setup          # install, create ./data
make verify         # lint, contracts, codegen gate, full test suite
make dev            # start the sixteen-service platform
```

In a second terminal:

```bash
make demo            # the foundation, end to end
make demo-programme  # all eight pillars in one thread traversal
make demo-full       # 34 capabilities and 7 interfaces through the gateway
make demo-edge       # the edge capture and reconciliation flow
```

| Surface | URL |
|---|---|
| Gateway | http://localhost:8080 |
| Platform status | http://localhost:8080/v1/platform/status |
| API documentation | http://localhost:8080/docs |
| Console | http://localhost:5173 |

Keep state out of the tree with `NGSH_DSN="sqlite:////tmp/ngsh.db" NGSH_DATA_DIR=/tmp/ngsh-data make dev`.

### Two examples

Validate against the contract:

```bash
curl -s -X POST localhost:8080/api/ontology/v1/ontology/validate \
  -H 'content-type: application/json' \
  -d '{"kind":"entity","entity":{"id":"TR:1","type":"TestResult","tenant":"ngsh","version":1,
       "createdAt":"2026-11-14T00:00:00Z","updatedAt":"2026-11-14T00:00:00Z",
       "classification":{"level":"CUI"},"attributes":{"testMethod":"plasma-arc-heater",
       "outcome":"PASS","measurements":[{"name":"peak_temperature","value":1840.0,"unit":"K"}]}}}' | jq
```

Ask for an access decision:

```bash
curl -s -X POST localhost:8080/api/policy/v1/decisions \
  -H 'content-type: application/json' \
  -d '{"subject":{"subjectId":"usr:engineer","kind":"user","clearance":"TOP SECRET",
       "citizenship":"US","tenant":"ngsh","programs":["NGSH-SHY"],"needToKnow":["NGSH-SHY"]},
       "action":"read","resource":{"type":"TestResult","id":"TR:1",
       "classification":{"level":"CUI"},"tenant":"ngsh","program":"NGSH-SHY"}}' | jq
```

---

## Proof

| Gate | Command | Result |
|---|---|---|
| Lint and format | `make lint` | Clean |
| Contracts | `make contracts` | 279 checks |
| Generated models | `make codegen-check` | No drift |
| Tests | `make test` | 466 passing |
| Everything | `make verify` | All gates |
| Live sweep | `make dev` + `make demo-full` | 34/34 capabilities, 7/7 interfaces, 15 services |

`demo-full` is a completeness gate: it exits non-zero if any capability or interface
is missing.

```
Complete-build traversal finished: 34/34 capabilities, 7/7 interfaces, 15 services.
```

The e2e suite ingests data, projects it, traces it, takes a policy decision, verifies
the audit chain, destroys the projection, rebuilds it from the log and asserts the
thread returns identical.

---

## Deployment

The same images run in four postures, chosen by configuration.

| Profile | Posture |
|---|---|
| `local` | Single process, SQLite, development actor |
| `il5` | Accredited cloud enclave, PostgreSQL, HA, real identity |
| `il6` | On-prem classified node, anti-affinity, no public ingress |
| `edge` | Factory floor or range annex, single replica, store-and-forward |

```bash
docker compose -f deploy/compose/docker-compose.yml up -d --build
helm lint deploy/helm/ngsh
```

No domain package knows which posture it is in. Placement belongs to the programme,
not to an import statement.

### Security posture

| Concern | Handling |
|---|---|
| Access | ABAC, decision separate from enforcement, explicit deny, fail closed |
| Audit | Hash chain; every decision is both a ledger entry and an event |
| Classification | Partitioned storage, cross-boundary refusal, ambiguous input treated as more restricted |
| Models | Card, fidelity score and named approval before use; regeneration never self-approves |
| Evidence | Append-only; corrections supersede with a reference to the original |
| Edge | Degraded capture, deterministic reconciliation, human escalation on genuine conflict |

Designed to be accreditable. Not accredited.

---

## What is not finished

Each item has a working adapter or an explicit fail-closed path.

| Item | State | Programme supplies |
|---|---|---|
| Government identity | Local signed assertion; production provider fails closed | Accredited metadata and verification endpoints |
| Prime PLM and MES | Validated adapter | Endpoint, credentials, mapping |
| Missile-defence systems | Validated exchange | Connectivity and accreditation |
| Satellite feeds | Inbound-only boundary | Feed and approval for any outbound path |
| Range instrumentation | Validated manifests | Streams and network access |
| LMS and AR/VR | Outbound package export | Partner registration and federation |
| BI connectors | Outbound report export | Consumer endpoint and credential |
| PostgreSQL runtime | Dialect implemented; tests run on SQLite | Accredited database service |
| Container runtime | Compose and Helm validated as files | Registry and cluster |
| Classified data and ATO | Partitioning and denial paths implemented | Data, enclave and authority to operate |

None of these requires a change to the contract layer.

---

## Licence

Proprietary and confidential software of **Crocell Company**.
Copyright © 2026 Crocell Company. All rights reserved.

No licence, express or implied, is granted except by a separate written agreement
signed by an authorised representative of Crocell. Access does not confer any right
to copy, modify, distribute, sublicense or commercially exploit the software. A
limited, revocable right to view and evaluate applies only where Crocell has granted
access for that purpose.

The software may be subject to U.S. export control law, including ITAR and the EAR.
It must not be exported, re-exported or released to any prohibited destination,
entity or person, or to any person other than a U.S. person where an authorisation is
required.

Third-party open-source components remain governed by their own licences. Full terms,
including warranty and liability, are in the `LICENSE` file.

Licensing enquiries: Crocell Company, Legal Department.

---

*Classification handling: CUI. The system described is designed for accredited
enclave operation.*
