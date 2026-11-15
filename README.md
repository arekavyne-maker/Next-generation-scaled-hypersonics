# NGSH — Next-Generation Scaled Hypersonics

> **The digital lab for designing hypersonics.**

NGSH is one place where a hypersonic programme keeps its evidence. Requirements,
design baselines, factory runs, material lots, test results, suppliers, people and
threat models all live in a single append-only record, and everything you look at —
the digital thread, the search index, the datasets, the KPIs — is rebuilt from that
record. When someone asks "which configuration was tested?", "what lot is this part
made from?", "can we build forty a year?", the answer is a query, not an
investigation.

It covers both halves of the mission on the same substrate: the strike side
(design, manufacture, test, industrial scaling) and the shield side
(counter-hypersonic threat modelling, kill chains, engagement simulation). They
share the same types and the same record because they fail for the same reasons.

**Proprietary and confidential software of Crocell Company.** All rights reserved.
See [Licence](#licence) below and the `LICENSE` file.

---

## Contents

| | |
|---|---|
| [What this is](#what-this-is) | [Running it](#running-it) |
| [What this is not](#what-this-is-not) | [Worked examples](#worked-examples) |
| [Why it exists](#why-it-exists) | [Use cases](#use-cases) |
| [How it works](#how-it-works) | [What a run looks like](#what-a-run-looks-like) |
| [The data model](#the-data-model) | [Checking it yourself](#checking-it-yourself) |
| [The services](#the-services) | [Deployment](#deployment) |
| [The capabilities](#the-capabilities) | [Security posture](#security-posture) |
| [The interfaces](#the-interfaces) | [What is not finished](#what-is-not-finished) |
| [Why it is built this way](#why-it-is-built-this-way) | [Licence](#licence) |

---

## What this is

A working software platform, not a prototype. Sixteen services, a web console and an
edge agent, all built against one contract layer and one event log. Eight domains —
design, manufacturing, test, supply, workforce, threat, ranges, industrial scaling —
implemented as 34 capabilities, each with an endpoint that returns a real result and
a test that proves it.

The shortest honest summary: **it is the connective tissue**. It is not CAD, not a
PLM system, not a manufacturing execution system, not a CFD solver. It sits across
those tools and makes what they produce traceable, comparable and hard to fake.

Concretely, it does six things:

1. **Records facts as events.** Append-only, ordered, immutable. The log is the
   system of record.
2. **Derives every view.** Thread, search, datasets and KPIs are projections. Delete
   one and replay the log; it comes back identical.
3. **Enforces the contract.** Twenty-three entity types, ten relation types, eleven
   event types and nine cross-entity invariants, all defined as JSON Schema.
4. **Controls access.** Attribute-based, with the decision point separated from
   enforcement, explicit deny winning, and fail-closed defaults.
5. **Proves the record.** A hash-chained ledger where every entry commits to its
   predecessor, so a rewritten history is detectable.
6. **Refuses to pretend.** Missing evidence produces a named gap, not a filled-in
   number. A model without a fidelity score cannot be used. A conflicting pair of
   immutable records escalates to a human.

---

## What this is not

Worth being blunt, because the scope claims are easy to inflate:

- **Not the weapon.** No guidance, navigation, control, seeker or flight software.
- **Not accredited.** No authority to operate, no classified data, no certified
  deployment. It is built to be accreditable, not accredited.
- **Not connected to real systems.** The seven external interfaces have validated
  adapters with simulated counterparts. The real PLM, missile-defence, satellite,
  range, LMS and identity systems are supplied by the programme.
- **Not a modelling tool.** It stores and governs models; it does not run physics.
- **Not a replacement for command and control.** It tests and integrates with it.

What remains is listed in [What is not finished](#what-is-not-finished).

---

## Why it exists

Hypersonic programmes rarely fail on aerodynamics. They fail on the seams.

A design is analysed, then changed, and the test article is built to a mix of both.
A part is manufactured, then a process parameter drifts and nobody can tell which
lots were affected. A requirement is marked "verified" because a campaign passed,
but the campaign tested a different configuration. A single supplier of a single
material becomes the critical path, and the programme finds out during a shortage.
A simulation is used outside its validated envelope because the envelope was never
written down. The red team and the blue team model different threats and compare
the results anyway.

Every one of those is a data problem before it is an engineering problem. The
records exist; they are just scattered across tools that do not talk, and they can
be edited after the fact. NGSH's premise is that if you fix the record — one log,
one set of shapes, immutable evidence, derived views — most of that failure class
becomes structurally difficult rather than a matter of discipline.

That premise is enforced, not asserted. The event log is not a cache in front of a
database; it *is* the database. Evidence is append-only at the contract level. The
projection rebuild is a test. The audit chain is verified on demand.

---

## How it works

### The record is the product

Everything authoritative is an event. An event says what happened, who did it, when,
under what classification, and in which programme. It is validated against a schema,
appended to the fabric, committed to the ledger, and projected into the thread.

The event log is the only thing that must not be lost. Everything else — the graph,
the indexes, the lakehouse catalogue, the KPIs — is a function of it.

### Writes

```
caller
  │
  ▼
gateway ── /api/<service>/... ──▶  service
                                     │
                                     ├─ resolve the actor from the identity provider
                                     ├─ ask the policy service for a decision
                                     ├─ validate the payload against the contract layer
                                     ├─ apply the domain rules (pure functions)
                                     ├─ append the event to the fabric
                                     ├─ append the ledger entry
                                     └─ project the event into the thread
                                     │
                                     ▼
                                entity + decision
```

Two details matter. First, the ledger entry and the access decision are both
written; a decision produces an `access.decision.recorded` event *and* a chain
entry, because a ledger nobody can query and a queryable history that can be
rewritten are both weaker than the pair. Second, projection is a pure function of
the log, so the write path can always be replayed.

Derived reports — a surge assessment, a reconstitution playbook, a coverage
report — are stored as annotations on the entity they concern and published as
`entity.updated`. They are reproducible from the log and carry their provenance.

### Reads

Reads go to the projection, never to a service's private state:

```
console ──▶ gateway ──▶ thread ──▶ entities · relations · search · datasets
                                     ▲
                                     └── replay from fabric at any time
```

Because the projection is derived, deleting it is safe. That is tested: the
end-to-end suite ingests data, projects it, traces it, takes a policy decision,
verifies the audit chain, destroys the projection, replays the log, and asserts the
thread comes back identical.

### Who can do what

Access is attribute-based, and the decision point is separate from the enforcement
point so that a service cannot quietly invent its own policy. Four rules are
absolute:

1. **Explicit deny wins**, whatever the ordering.
2. **Unmatched means denied.** A resource type not named in an allow rule is
   unreachable.
3. **Ambiguity fails closed.** An unparseable classification is treated as *more*
   restricted, never less.
4. **Citizenship and clearance are checked at the point of use.** A credential
   cannot be issued to a person whose citizenship does not permit the activity, and
   no reference to a person is accepted without a current clearance record.

The ledger is a hash chain. Each entry commits to its predecessor, so an edit
breaks the chain and the verifier reports where.

### Determinism

Anything the platform computes twice from the same inputs produces the same answer.
Monte Carlo engagement draws are hash-derived, not random. Edge reconciliation is
deterministic. Variant generation and threat-model derivation are deterministic.
That is what makes a result reviewable years later, and what makes a rebuild a
proof rather than a hope.

---

## The data model

Twenty-three entity types, ten relation types, nine invariants and eleven event
types. They are defined as JSON Schema under `contracts/`, and the Python models are
generated from them with a staleness gate: if the committed models differ from a
fresh generation, the build fails.

The point of keeping the count small is that every type has to earn its place. New
capabilities are computed over these types; none of the 34 capabilities required
inventing a type to look complete.

### The 23 entity types

| Type | What it holds |
|---|---|
| `System` | Any engineered system of interest, at any level of the thread |
| `Variant` | A configuration-specific instance of a system; the unit of family generation |
| `Subsystem` | A decomposition node beneath a system |
| `Part` | A discrete hardware article |
| `Material` | A CMC lot, prepreg batch or billet — the join between materials and supply |
| `ProcessPlan` | A qualified recipe for producing a part from a material |
| `ProcessRun` | One execution of a process plan against a material lot |
| `TestArticle` | The as-built configuration subject to test |
| `TestCampaign` | A planned body of tests against one or more articles |
| `TestResult` | A test outcome with full configuration context; immutable once written |
| `Requirement` | A baselined engineering requirement; the root of verification |
| `Interface` | A controlled interface between two systems, versioned by ICD |
| `Model` | A simulation or ML model with provenance and a fidelity score |
| `ThreatSystem` | An adversarial system reconstructed from observations |
| `ThreatObservation` | One sensor observation of a threat system |
| `EngagementScenario` | A composed detect-to-engage scenario |
| `Supplier` | An external or internal supply node, scored for risk |
| `PartProvenance` | Chain of custody for a part across facilities and transfers |
| `Skill` | A defined occupational or technical skill |
| `Credential` | Evidence that a person holds a skill, with expiry and authority |
| `Person` | A cleared individual; PII-bearing, strictly retained |
| `Facility` | A manufacturing, test, range or training site with surge capability |
| `RangeSlot` | A bookable window of range capacity with instrumentation coverage |

### The 10 relation types

| Relation | Meaning |
|---|---|
| `satisfies` | A design element discharges a requirement |
| `verifies` | Test evidence verifies a requirement |
| `manufacturedBy` | An article is produced at a facility or supplied by a supplier |
| `characterizedBy` | Physics or ML characterisation of a material, run or part |
| `derivedFrom` | Derivation lineage between models, results and reconstructions |
| `threatens` | An adversarial system poses a threat to a defended asset |
| `engages` | A scenario exercises an engagement against a threat system |
| `requiresSkill` | An activity demands a skill; drives workforce gap analysis |
| `supplies` | A supplier provides a part, material or facility capability |
| `reconstitutes` | A recovery path that restores a lost critical node |

### The 9 invariants

These are checked at write time unless noted, and a violation is an error, not a
warning — except C-007, which flags a programme risk.

| Id | Rule |
|---|---|
| `C-001` | An entity's classification may never be lower than its type's floor |
| `C-002` | A relation may not cross a classification boundary unless its type permits it |
| `C-003` | A test result is immutable; a correction is a new event with `supersedesRef` |
| `C-004` | A model used in a safety-relevant prediction needs `approvedForUse` and a fidelity score |
| `C-005` | A credential's person must have citizenship that permits the activity and a current clearance |
| `C-006` | Every person referenced by a credential or process run must have a current clearance |
| `C-007` | A critical single-source part needs a reconstitution edge or must be flagged as risk |
| `C-008` | An engagement scenario is unreadable below its classification |
| `C-009` | A classification may not be lowered in place; a downgrade creates a new entity |

### The 11 event types

| Event | Meaning |
|---|---|
| `entity.created` | A new entity in the shared ontology |
| `entity.updated` | An existing entity mutated |
| `entity.relation.asserted` | A thread edge added |
| `entity.relation.retracted` | A thread edge withdrawn |
| `test.campaign.planned` | A campaign planned against requirements and articles |
| `test.result.recorded` | A test outcome recorded; immutable |
| `process.run.completed` | A manufacturing run finished |
| `model.validated` | A model scored against evidence; fidelity updated |
| `ingest.batch.accepted` | A bulk ingestion batch accepted |
| `access.decision.recorded` | An authorisation outcome recorded |
| `reconcile.conflict.recorded` | An edge reconciliation conflict escalated |

---

## The services

Every service has its own package, container image, Compose entry and Helm block.
That is deliberate: a programme can deploy the manufacturing pillar without the
threat pillar.

| Service | Port | Responsibility |
|---|---|---|
| gateway | 8080 | Single entry point: platform status, capability matrix, transparent `/api/<service>/...` proxy |
| ontology | 8081 | The contract layer: types, relations, invariants, validation |
| fabric | 8082 | The append-only event log — the system of record |
| policy | 8083 | The Policy Decision Point for attribute-based access control |
| audit | 8084 | The tamper-evident, hash-chained ledger |
| thread | 8085 | The digital-thread projection, traversal, search and dataset catalogue |
| ingest | 8086 | Batch admission, lineage, digests and content-addressed objects |
| edge-agent | 8087 | Edge annex: degraded capture, local reads, deterministic reconciliation |
| architecture | 8088 | Pillar A: baselines, interfaces, requirement traceability, SysML and ICD exchange |
| workforce | 8089 | Pillar E: skills, credentials, work authorisation, workforce gap |
| manufacturing | 8090 | Pillar B: travellers, process runs, genealogy, drift, production rate |
| testlab | 8091 | Pillars B, C and G: campaigns, results, anomalies, twin loop, ranges, fidelity |
| supply | 8092 | Pillar D: single-source exposure, reconstitution, surge |
| engagement | 8093 | Pillars F and G: threats, scenarios, engagement batches, co-simulation |
| industrial | 8094 | Pillar H: verified surge, measured reconstitution, affordability |
| analytics | 8095 | Programme KPIs computed from the thread |
| integration | 8096 | The interface register, direction enforcement, delivery records |

Every service exposes `/healthz`, `/readyz`, `/v1/service/info`, and OpenAPI
documentation at `/docs`.

The **edge agent** is the one that runs where the network does not. It captures
events while the fabric is unreachable, serves reads from a local cache, and
reconciles deterministically when the link returns. Where two immutable records
genuinely conflict, it escalates rather than picking a winner.

The **console** is a React and TypeScript application with seven routes: overview,
event stream, thread, requirements, audit, access and platform. All of its traffic
goes through the gateway in both development and the container topology, so it has
exactly one backend address. If the stack is down it falls back to a deterministic
mock dataset and says so — the degradation path is tested behaviour.

### Repository shape

```
contracts/         JSON Schema, the ontology registry, the event catalogue, the policy set
libs/ngsh-core/    Shared primitives: envelope, ontology, policy, audit, event log,
                   projection, identity, storage, and the pure engines for every pillar
services/          Sixteen independently deployable services
apps/web/          The console (React + TypeScript)
apps/edge-agent/   Edge annex agent
tests/             unit · integration · e2e · contract parity
tools/             Contract validator and code generator
deploy/            Compose, Helm, OpenTelemetry
docs/              Architecture notes, decision records, roadmap and planning
scripts/           run_stack · seed · demo · demo_programme · demo_full · demo_edge
```

A domain rule lives in `libs/ngsh-core` as a pure function, and the service is a thin
transport and persistence layer around it. That is why the unit tests can cover the
rules without a server, and why the HTTP tests only have to cover transport.

---

## The capabilities

Thirty-four capabilities across eight pillars. Each is a tested path, not a claim.
The list is defined once in code, and a unit test asserts that every endpoint it
names actually exists on the owning service's router.

### Pillar A — design and the thread core

| Id | Capability | Service | Path |
|---|---|---|---|
| A-1 | Digital twin backbone | architecture | `POST /v1/baselines`, `POST /v1/baselines/{id}/verify` |
| A-2 | Modularity engine | architecture | `POST /v1/variants/generate`, `POST /v1/variants/{id}/core-error` |
| A-3 | Requirements-to-test traceability | architecture | `GET /v1/requirements/{id}/coverage`, `GET /v1/requirements/gaps` |
| A-4 | Technology insertion planner | architecture | `POST /v1/insertion/assess` |
| A-5 | Digital engineering exchange | architecture | `POST /v1/icds/generate`, `GET /v1/sysml/export`, `POST /v1/sysml/import` |

### Pillar B — manufacturing and materials

| Id | Capability | Service | Path |
|---|---|---|---|
| B-1 | Defense MES | manufacturing | `POST /v1/travellers`, `POST /v1/process-runs`, `GET /v1/genealogy/{id}` |
| B-2 | CMC process characterisation | manufacturing | `POST /v1/drift`, `POST /v1/process-runs` |
| B-3 | Test capability management | testlab | `POST /v1/campaigns`, `GET /v1/campaigns/{id}/curation` |
| B-4 | Rate and cost simulation | manufacturing | `POST /v1/simulate-rate`, `POST /v1/production/simulate` |

### Pillar C — test and evaluation data

| Id | Capability | Service | Path |
|---|---|---|---|
| C-1 | Unified test data lake | ingest | `POST /v1/lakehouse/objects`, `GET /v1/lakehouse/objects/{digest}/verify` |
| C-2 | Automated reduction and anomaly detection | testlab | `POST /v1/anomalies/detect`, `POST /v1/test-results` |
| C-3 | Twin validation loop | testlab | `POST /v1/twin-validation`, `POST /v1/models/{id}/regenerate` |
| C-4 | Campaign management | testlab | `POST /v1/campaigns`, `POST /v1/schedule/optimise` |

### Pillar D — supply and scaling

| Id | Capability | Service | Path |
|---|---|---|---|
| D-1 | Multi-tier visibility | supply | `GET /v1/supply-risks`, `POST /v1/suppliers` |
| D-2 | Foreign dependency mapping | supply | `POST /v1/reconstitutes`, `GET /v1/supply-risks` |
| D-3 | Surge readiness twin | supply | `POST /v1/surge` |

### Pillar E — the cleared workforce

| Id | Capability | Service | Path |
|---|---|---|---|
| E-1 | Digital-twin training | workforce | `POST /v1/training/scenarios`, `GET /v1/training/coverage` |
| E-2 | Replicable curriculum engine | workforce | `POST /v1/curriculum/packages` |
| E-3 | Skills credentialing | workforce | `POST /v1/credentials`, `GET /v1/work-authorisation` |
| E-4 | Workforce demand model | workforce | `POST /v1/workforce/gap` |
| E-5 | Industry-academia sandbox | workforce | `POST /v1/extracts` |

### Pillar F — counter-hypersonic engineering

| Id | Capability | Service | Path |
|---|---|---|---|
| F-1 | Threat digital twins | engagement | `POST /v1/threats`, `POST /v1/threat-models` |
| F-2 | Kill-chain simulator | engagement | `POST /v1/scenarios/{id}/batch`, `GET /v1/kill-chain` |
| F-3 | Fire-control data quality scoring | engagement | `POST /v1/fire-control/measure`, `POST /v1/fire-control/quality` |
| F-4 | Interim architecture workbench | engagement | `POST /v1/candidates/evaluate` |
| F-5 | Golden Dome readiness | engagement | `POST /v1/plugins`, `POST /v1/plugins/{id}/run` |
| F-6 | Red/blue co-simulation | engagement | `POST /v1/co-simulation` |

### Pillar G — the test enterprise

| Id | Capability | Service | Path |
|---|---|---|---|
| G-1 | Virtual test range | thread | `GET /v1/datasets`, `GET /v1/datasets/{id}/lineage` |
| G-2 | Campaign digital twin | testlab | `POST /v1/range-capacity`, `POST /v1/schedule/optimise` |
| G-3 | Automated model validation | testlab | `POST /v1/twin-validation`, `POST /v1/models/{id}/regenerate` |
| G-4 | Fidelity registry | testlab | `GET /v1/fidelity/registry`, `POST /v1/fidelity/{id}/drift` |

### Pillar H — industrial surge and affordability

| Id | Capability | Service | Path |
|---|---|---|---|
| H-1 | Surge readiness command | industrial | `POST /v1/surge-readiness` |
| H-2 | Reconstitution planning | industrial | `POST /v1/reconstitution/assess` |
| H-3 | Affordability engineering | industrial | `POST /v1/affordability/trace`, `POST /v1/affordability/rate-curve` |

---

## The interfaces

Seven boundaries to the outside world. Each has a declared direction, payload
validation and a content-addressed receipt, so a retry is recognisable and a
duplicate is detectable.

| Id | Interface | Direction | Boundary |
|---|---|---|---|
| IF-1 | Prime PLM and MES APIs | bi-directional | REST with STEP AP242 and OPC-UA payloads |
| IF-2 | Missile-defence systems | bi-directional | Scenario exchange over a message bus |
| IF-3 | Satellite track feeds | inbound only | Inbound tracks accepted; outbound refused by rule |
| IF-4 | Range instrumentation | bi-directional | Test-article manifests and TDMS/HDF5 references |
| IF-5 | University LMS and AR/VR | outbound | Curriculum package export |
| IF-6 | Government identity (PIV/ICAM) | inbound | Signed assertion verified, then redacted before persistence |
| IF-7 | Analytics and BI | outbound | Programme report export |

"Adapter" is an honest word here. The platform ships a validated, deterministic
simulated counterpart and a stable contract. The real system is supplied and
accredited by the programme, and swapping it in changes configuration, not the
contract, the direction rule or the receipt shape.

For local development, the identity path issues an HMAC-signed assertion through a
simulated provider. Issuance is refused outside the `local` and `edge` profiles, and
the production provider fails closed without live metadata and verification
endpoints — it cannot be accidentally used as a shortcut.

---

## Why it is built this way

Eight decisions shape the build. Each was a choice between doing something
fashionable and doing something defensible.

**1. The event log is the system of record.** A graph database, a search index and a
lakehouse are all excellent read models and terrible sources of truth: they can be
rebuilt, so they should be treated as disposable. Keeping the log authoritative
means a corrupted projection is an inconvenience, not a data loss incident, and it
means history is auditable by construction.

**2. Contracts are data, not code.** Shapes live in JSON Schema, and the Python
models are generated. An ontology change is a reviewed artefact before it is a
commit. This is slower than editing a dataclass, and it is the only way eight teams
can share types without drifting.

**3. Deployment is platform-agnostic.** No domain package imports a cloud SDK. The
same image has to land in an accredited cloud, an on-prem enclave and a
disconnected range annex. Placement, storage and identity arrive through
configuration.

**4. Access control separates decision from enforcement.** Services enforce; one
policy service decides. Otherwise every service eventually grows its own opinion
about who counts as cleared, and the weakest one wins.

**5. The audit ledger is a hash chain.** Integrity you can demonstrate beats
integrity you assert. Each entry commits to its predecessor, and verification is an
endpoint.

**6. The edge degrades but does not lie.** A disconnected range or factory floor
keeps capturing and keeps serving reads. On reconnection it reconciles
deterministically, and where two immutable records genuinely conflict it raises a
review item rather than choosing. A silent merge would destroy the value of
immutability.

**7. Classification is a storage property.** Partitions are enforced below the
application, ambiguous input is treated as more restricted, and a downgrade creates
a new entity in a lower partition rather than editing one in place.

**8. A model must earn its use.** A model card, a fidelity score and a named
approval are prerequisites, not documentation. Regenerating a model from evidence
never approves it; a human releases it.

---

## Running it

You need Python 3.12 or newer and `uv` (the Python package manager). Docker is
optional and only needed for the container topology.

```bash
make setup          # install dependencies, create ./data
make verify         # lint, contracts, codegen gate, full test suite
make dev            # start the sixteen-service platform
```

In a second terminal:

```bash
make demo            # the foundation, end to end
make demo-programme  # all eight pillars in one thread traversal
make demo-full       # all 34 capabilities and 7 interfaces through the gateway
make demo-edge       # the edge annex capture and reconciliation flow
```

Then:

| Surface | URL |
|---|---|
| Gateway and API entry point | http://localhost:8080 |
| Platform status | http://localhost:8080/v1/platform/status |
| Capability matrix | http://localhost:8080/v1/platform/capabilities |
| API documentation | http://localhost:8080/docs |
| Console (dev server) | http://localhost:5173 |

To keep local state out of the working tree:

```bash
NGSH_DSN="sqlite:////tmp/ngsh-test.db" NGSH_DATA_DIR=/tmp/ngsh-data make dev
```

The defaults are deliberately unimpressive: SQLite, a development actor, and a
simulated identity provider. Those defaults are refused outside the `local` and
`edge` profiles, so a production-shaped deployment cannot silently inherit them.

---

## Worked examples

These run against the local stack with `make dev` active. They use the gateway,
which proxies `/api/<service>/...` to the owning service without rewriting the
domain. Examples that read the thread assume `make demo` has run once, because it
seeds the `REQ:DEMO-0001` requirement and its evidence.

### Ask the platform what it is

```bash
curl -s localhost:8080/v1/platform/status | jq
curl -s localhost:8080/v1/platform/capabilities | jq '.count, .pillarCount, .interfaceCount'
```

### Validate an entity against the contract

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

Change `outcome` to something outside the vocabulary and the response names the
failing path. The contract is the validator; the service is just a wrapper.

### Admit a batch of test data

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

The response reports accepted and rejected counts plus the batch digest, so the same
payload submitted twice is recognisably the same payload.

### Read the log and rebuild the thread

```bash
curl -s localhost:8080/api/fabric/v1/stats | jq '.total, .byType'

# replay the whole log into the projection
curl -s -X POST localhost:8080/api/thread/v1/project/replay | jq '.replayed, .stats'
```

Running this after deleting the projection is a complete rebuild. That is the
operational meaning of "the log is the system of record".

### Trace a requirement to its evidence

```bash
curl -s "localhost:8080/api/thread/v1/trace?root=Requirement:REQ:DEMO-0001&depth=3" | jq
curl -s -X POST localhost:8080/api/thread/v1/trace/requirements/REQ:DEMO-0001/coverage | jq
```

The coverage response says whether the requirement is verified and names every gap
that prevents it. It does not fill gaps with an assumption.

### Take an access decision

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

Change `citizenship` to anything outside the permitted set and the decision flips to
deny. There is no override parameter.

### Verify the ledger

```bash
curl -s localhost:8080/api/audit/v1/ledger/verify | jq
curl -s localhost:8080/api/audit/v1/ledger/head | jq
```

A single altered entry breaks the chain, and the verifier says where.

### Store and re-verify a dataset object

```bash
curl -s -X POST localhost:8080/api/ingest/v1/lakehouse/objects \
  -H 'content-type: application/json' \
  -d '{"content":"TkdTSCBkZW1v","encoding":"base64","mediaType":"application/octet-stream"}' | jq

DIGEST=$(curl -s localhost:8080/api/ingest/v1/lakehouse/objects | jq -r '.objects[0].digest')
curl -s "localhost:8080/api/ingest/v1/lakehouse/objects/$DIGEST/verify" | jq
```

Objects are content-addressed: the URI is `ngsh-lake://<sha256>`, and verification
re-hashes the stored bytes.

---

## Use cases

### Prove a requirement with evidence

A thermal requirement — survive 1800 K for 30 minutes — is baselined. A
plasma-arc-heater result is admitted against a specific configuration baseline and
asserted to verify it. The architecture service checks that the result is a reviewed
pass, that the article was built to the baselined configuration, and that it is not
superseded. If any of that fails, a review item is raised instead of a satisfied
requirement.

### Trace a defect to its lot and parameters

A process run drifts beyond its configured sigma limit. The manufacturing service
quarantines it for a human; it never dispositions automatically. Genealogy then walks
custody from the part back through the run to the material lot, naming any hop it
cannot resolve rather than skipping it.

### Close the simulation loop

A campaign produces residuals against model predictions. The test service reports
where the model is weakest, fits a per-quantity correction to the evidence, and
regenerates the model — recorded as unapproved. A named engineer releases it, the
previous approval is withdrawn, and every dependent is notified.

### Find the single point of failure first

The supply service ranks parts by single-source exposure, traces which suppliers and
facilities can reconstitute them, and produces a ranked playbook with cumulative
lead time. Recording a reconstitution path reduces the exposure count, visibly.

### Answer "can industry build this rate?"

A demand figure becomes an achievable rate with a two-sided confidence interval
derived from supplier risk. The figure is marked verified only when the interval, a
named owner and the twin run that produced it are all present. Otherwise the gaps
are named.

### Compare red and blue against the same threat

A threat is modelled once. Engagement batches run against it, the fire-control
scorer quantifies data-quality defects, and the co-simulation refuses to compare
traces that do not resolve to the same threat node. Comparing two different threats
is not a measure of the balance, and the platform will not pretend it is.

### Operate a disconnected range

The edge agent captures while the fabric is unreachable, serves reads locally, and
reconciles deterministically on reconnection. Genuine conflicts between immutable
records go to a human.

### License one pillar

Because each pillar has its own image, chart block and boundary, a programme can
deploy the workforce pillar without the threat pillar. The licensed pillar gets the
contract layer, the foundation it depends on and its own projections; it reaches
other pillars' data through the event feed, not a shared table.

---

## What a run looks like

Representative output, with identifiers elided because they are ULIDs and differ
between runs.

Foundation (`make demo`):

```
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

`demo-full` is a completeness gate, not a smoke test. It walks every capability and
every interface and exits non-zero if any is missing or returns an unexpected shape.

---

## Checking it yourself

| Gate | Command | Proves |
|---|---|---|
| Lint and format | `make lint` | Style and import hygiene |
| Contracts | `make contracts` | 279 checks: schemas, registry and invariants agree |
| Generated models | `make codegen-check` | No drift between contracts and Python |
| Unit and integration | `make test` | 466 tests: domain rules, HTTP surfaces, end to end |
| Everything | `make verify` | All of the above in one command |
| Live capability sweep | `make dev` + `make demo-full` | 34 of 34 capabilities, 7 of 7 interfaces, 15 services |
| Live traversal | `make dev` + `make demo-programme` | All eight pillars reachable from one root |

The end-to-end suite contains the assertion that matters most: it ingests data,
projects it, traces it, takes a policy decision, verifies the audit chain, destroys
the projection, rebuilds it from the log alone, and asserts the thread comes back
identical.

Static validation covers the Compose topology and the Helm chart. Running the
containers requires Docker and Helm, which are not part of the local default.

---

## Deployment

The same images run in four postures, chosen by configuration:

| Profile | Posture |
|---|---|
| `local` | Single process, SQLite, development actor, simulated identity |
| `il5` | Accredited cloud enclave, PostgreSQL, high availability, real identity |
| `il6` | On-prem classified node, dedicated storage, anti-affinity, no public ingress |
| `edge` | Factory floor or range annex, single replica, store-and-forward, later sync |

```bash
# container topology
docker compose -f deploy/compose/docker-compose.yml up -d --build

# Kubernetes
helm lint deploy/helm/ngsh
helm template ngsh deploy/helm/ngsh -f deploy/helm/ngsh/values.yaml
```

Nothing in a domain package knows which of these it is running in. That is the point
of the platform-agnostic rule: the placement decision belongs to the programme, not
to an import statement.

---

## Security posture

| Concern | How it is handled |
|---|---|
| Access control | Attribute-based; decision point separate from enforcement; explicit deny wins; unmatched is denied |
| Audit | Hash-chained ledger; every decision recorded as a ledger entry and as an event |
| Classification | Partitioned storage; cross-classification refusal; ambiguous input treated as more restricted |
| Identity | Verified actor per request; production provider fails closed without live endpoints |
| Model governance | Model card, fidelity score and named approval required before use; regeneration never self-approves |
| Evidence integrity | Append-only; corrections are superseding records with a reference to the original |
| Edge trust | Degraded capture, deterministic reconciliation, human escalation on genuine conflict |
| Portability | No cloud SDK in any domain package |

The system is designed to be accreditable. It is not accredited, and no
configuration in this repository changes that.

---

## What is not finished

Each item has a working adapter or an explicit fail-closed path, so the platform does
not pretend to have data or authority it does not have.

| Item | Current state | What a programme supplies |
|---|---|---|
| Government identity | Local signed assertion in `local` and `edge`; production provider fails closed | Accredited identity metadata and verification endpoints |
| Prime PLM and MES | Validated adapter with deterministic receipts | Endpoint, credentials and mapping |
| Missile-defence systems | Validated scenario exchange | Connectivity and accreditation |
| Satellite track feeds | Inbound-only boundary | Feed connection and approval for any outbound path |
| Range instrumentation | Validated manifests | Instrumentation streams and range network access |
| LMS and AR/VR | Outbound package export with verified reference coverage | Partner registration and identity federation |
| BI connectors | Outbound report export | Consumer endpoint and credential |
| PostgreSQL runtime | Dialect and backend implemented; tests run on SQLite | An accredited database service |
| Container runtime | Compose and Helm validated as files | A registry and a cluster |
| Classified data and authority to operate | Partitioning and denial paths implemented | Data, enclave and accreditation |

None of these requires a change to the contract layer. That is the test of whether
the boundary was drawn in the right place.

---

## Licence

NGSH is proprietary and confidential software owned by **Crocell Company**.

Copyright © 2026 Crocell Company. All rights reserved.

No licence, express or implied, is granted except by a separate written agreement
signed by an authorised representative of Crocell. Access to this repository does
not confer any right to copy, modify, distribute, sublicense or commercially exploit
the software. A limited, revocable right to view and evaluate the software applies
only where Crocell has granted access for that purpose.

The software may be subject to United States export control laws, including the
International Traffic in Arms Regulations and the Export Administration Regulations.
It must not be exported, re-exported or released to any prohibited destination,
entity or person, or to any person other than a U.S. person where an authorisation
is required.

Third-party open-source components remain governed by their own licences. The full
terms, including the warranty and liability provisions, are set out in the `LICENSE`
file.

Licensing and evaluation enquiries: Crocell Company, Legal Department.

---

*Classification handling: this document is CUI. The system it describes is designed
for accredited enclave operation.*
