# Pillar Coverage — Six Services, One Thread

## Purpose

This document states what the pillar services in this repository actually
deliver, capability by capability, and what they deliberately leave to a later
increment or to an external institution. It is the companion to
[`06-pillar-a-first-slice.md`](06-pillar-a-first-slice.md), which covers the
first Pillar A slice in depth.

The rule the services are built to is the platform rule: **the event log is the
system of record, and the graph is a projection**. A pillar never keeps a
private table of authoritative facts. A credential, a process run, a test
result, a supplier risk and an engagement scenario are all appended as events
and read back through the thread.

## 1. Service map

| Service | Port | Pillar | Primary capabilities | Domain rules |
|---|---|---|---|---|
| `architecture-service` | 8088 | A | A-1 configuration baseline, interface registry, A-3 traceability | `ngsh_core.architecture` |
| `workforce-service` | 8089 | E | E-3 skills credentialing, E-4 cleared-workforce demand | `ngsh_core.workforce` |
| `manufacturing-service` | 8090 | B | B-1 traveller and genealogy, B-2 process control, B-3 rate and surge | `ngsh_core.manufacturing` |
| `testlab-service` | 8091 | C | C-1 campaign planning, C-2 configuration-gated result admission, C-3 anomaly surfacing, C-4 twin validation | `ngsh_core.testlab` |
| `supply-service` | 8092 | D | D-1 single-source exposure (C-007), D-2 surge, D-3 reconstitution | `ngsh_core.supply` |
| `engagement-service` | 8093 | F, G | F-1 threat and kill chain, F-2 deterministic engagement batches, G-1 virtual range slots | `ngsh_core.engagement` |

Every service is independently deployable and independently licensable: it has
its own `pyproject.toml`, its own container image, its own Helm values block
and its own compose service. A programme can run Pillar B without Pillar F.

## 2. Pillar A — architecture

Delivered:

* content-addressed configuration baselines over part revisions, variants,
  interfaces and software builds;
* baseline resolution from a `TestArticle`, and a reproducibility proof;
* the interface registry with rate, latency, timing and envelope validation;
* requirement verification status computed from `verifies` evidence —
  `PASS` only counts when reviewed, and `MARGINAL`, `INCONCLUSIVE`,
  unreviewed `PASS` and `NOT_RUN` become review items;
* hierarchy rollup and a gap report.

Not delivered: the SysML authoring environment, baseline branching and
merging, the design-change workflow, interface negotiation and the automated
ICD conformance harness. The full Pillar A scope completes in Increment 5.

## 3. Pillar E — workforce

The rules are the ones the pillar is assessed on:

| Rule | Enforcement |
|---|---|
| C-005 citizenship | A credential is refused when the person's citizenship is outside `NGSH_PERMITTED_CITIZENSIONS` (default `US`) |
| C-006 clearance currency | A missing expiry is **not** current; an expired clearance cannot issue, authorise or operate |
| Skill clearance floor | A credential is refused when the person's clearance is below the skill's `clearanceRequired` |
| Lifecycle | `ACTIVE → SUSPENDED → ACTIVE`, `ACTIVE/SUSPENDED → REVOKED`; revocation is terminal, suspension is not |
| Effective state | `EXPIRED` is derived from `expiresAt`, even while the stored status still says `ACTIVE` |
| Demand gap | Supply counts credentialed people by region and trade; nominal headcount is reported but never substituted |

Not delivered: the curriculum delivery system, the training-record exchange
with partner institutions, and the PIV/ICAM adapter (the service consumes a
verified identity; it does not perform the verification).

## 4. Pillar B — manufacturing

Delivered:

* a traveller built from the released `ProcessPlan` revision, with
  `PENDING → BLOCKED → IN_PROGRESS → COMPLETE` and `NONCONFORMING` states;
  an operation cannot start before its predecessor completes;
* process runs recorded with operator, facility, parameters and disposition,
  with C-006 checked against the operator at write time;
* drift detection against the process's own history at a configurable sigma
  limit; a flagged run is quarantined for a human, never auto-dispositioned;
* genealogy assembled from `PartProvenance.chainOfCustody`, with every missing
  hop named rather than skipped;
* an explicit, inspectable rate model that names its binding constraint.

Not delivered: prime PLM/MES integration, machine-level control, the full
B-4 digital-factory simulation, and spindle-level sensor ingestion.

## 5. Pillar C — test lab

Delivered:

* campaign planning with range-slot conflict detection;
* write-time admission that refuses a `TestResult` without a configuration
  snapshot naming a `variantId` and a `baselineId` (or software build) — a
  result that cannot name its build is not evidence;
* anomaly surfacing against the result's own limits and, when history exists,
  against the campaign's variation; anomalies are flags, not dispositions;
* campaign curation into a reusable dataset with a pass rate and a
  configuration-coverage flag;
* twin validation producing a `model.validated` fact with a causation chain to
  the test result, and a `derivedFrom` edge from the result to the model;
  C-004 is enforced (the model must be approved and carry a fidelity score).

Not delivered: the AR/VR test-cell environment, range instrumentation
integration, and the automated reduction pipeline itself (the result carries
the dataset URIs and the pipeline reference).

## 6. Pillar D — supply

Delivered:

* C-007 as a computed programme risk: a `CRITICAL`, single-source part with no
  `reconstitutes` edge is a finding;
* a surge plan that degrades capacity by the supply base's risk and names the
  longest lead time as the bottleneck;
* a reconstitution playbook ranked by lead time and then risk, with cumulative
  days and residual risk;
* a `reconstitutes` link endpoint so a qualified path clears the C-007 finding.

Not delivered: supplier portals, contract and pricing data, and the
multi-tier bill-of-materials explosion beyond the declared dependencies.

## 7. Pillars F and G — engagement and virtual range

Delivered:

* threat systems, observations and engagement scenarios that name their
  sensor and effector chains;
* a deterministic Monte Carlo batch: each draw is derived from a hash of the
  seed and the run index, so two machines agree on the result and a study is
  reproducible from its inputs;
* statistics computed from the batch (mean, p10, median, p90, intercept and
  detection probabilities) and a measured throughput;
* a kill-chain view that names the missing stage rather than averaging over
  it;
* virtual range bookings that refuse to overlap.

Not delivered: PSDD IF-3 outbound integration to SDA/PWSA, high-fidelity
threat models, hardware-in-the-loop, and the classified production
engagement studies. The inbound-only IF-3 position is a programme-office
decision recorded in the interface register.

## 8. The programme traversal

`tests/e2e/test_programme_traversal.py` and `scripts/demo_programme.py` walk
one programme through all six services on one platform database:

```
Requirement ──satisfies── Part ──manufacturedBy── Facility
     ▲                     │
     │ verifies            ├──supplies──── Supplier ──reconstitutes──▶ Part
     │                     │
 TestResult ──derivedFrom── Model
     ▲                     │
     │ characterizedBy     ├──threatens── ThreatSystem ──derivedFrom── ThreatObservation
     │                     │
 ProcessRun                └──engages──── EngagementScenario
```

The end-to-end test asserts that a **single traversal rooted at the part**
reaches every pillar's evidence, and that the same traversal survives a
projection rebuild from the log. That is the platform claim in one assertion:
the programme has one thread, not six silos.

## 9. Verification

| Gate | Command | What it proves |
|---|---|---|
| Domain rules | `uv run pytest tests/unit` | Each rule, including its negative cases |
| Service behaviour | `uv run pytest tests/integration` | The HTTP surface, validation codes and projection reads |
| Programme traversal | `uv run pytest tests/e2e/test_programme_traversal.py` | All pillars on one log, plus a projection rebuild |
| Contracts | `uv run python tools/validate_contracts.py` | Schemas, registry and constraints agree |
| Generated models | `uv run python tools/codegen/generate.py --check` | No drift between contracts and Python |
| Lint | `uv run ruff check libs services apps tests tools scripts` | Style and import hygiene |
| Live demo | `make dev` then `make demo-programme` | The same traversal over HTTP against the running stack |

## 10. What this is not

The delivered services are a reference implementation of the platform's rules,
not accredited production software. The following remain open and are tracked
in the risk register:

* PSDD capabilities are not yet verified against their exit criteria (34 of
  them remain unverified);
* no PostgreSQL server has been exercised at runtime in this environment,
  though the dialect is implemented and its SQL is checked;
* no Docker or Helm runtime is available locally; compose and chart rendering
  are validated statically;
* partner institutions, AR/VR hardware, range instrumentation, classified
  production demand and prime PLM/MES access are external dependencies for the
  real increment exits.

Where a statement here contradicts a contract file, the contract wins and this
document is the defect.
