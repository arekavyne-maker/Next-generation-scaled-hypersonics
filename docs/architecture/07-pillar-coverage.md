# Pillar Coverage — Nine Services, One Thread

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
| `architecture-service` | 8088 | A | A-1 baseline, A-2 variant generation, A-3 traceability, A-4 insertion assessment, A-5 interface/ICD catalogue | `ngsh_core.architecture`, `ngsh_core.modularity` |
| `workforce-service` | 8089 | E | E-1 live-thread training, E-2 reusable curriculum, E-3 skills credentialing, E-4 demand gap, E-5 controlled extracts | `ngsh_core.workforce`, `ngsh_core.training` |
| `manufacturing-service` | 8090 | B | B-1 traveller and genealogy, B-2 process control, B-3 rate and surge | `ngsh_core.manufacturing` |
| `testlab-service` | 8091 | C, G | C-1 campaign planning, C-2 configuration-gated result admission, C-3 anomaly surfacing, C-4 twin validation, G-2 range capacity and scheduling, G-4 fidelity registry | `ngsh_core.testlab` |
| `supply-service` | 8092 | D | D-1 single-source exposure (C-007), D-2 surge, D-3 reconstitution | `ngsh_core.supply` |
| `engagement-service` | 8093 | F, G | F-1 threat and kill chain, F-2 deterministic batches, F-3 fire-control quality, F-4 interim candidates, F-5 plug-in host, F-6 red/blue co-simulation, G-1 range slots | `ngsh_core.engagement` |
| `industrial-service` | 8094 | H | H-1 verified surge, H-2 measured reconstitution, H-3 affordability trace and rate curve | `ngsh_core.industrial` |
| `analytics-service` | 8095 | cross-cutting | PSDD section 12 programme measures, computed from the thread | `ngsh_core.analytics` |
| `integration-service` | 8096 | cross-cutting | IF-1..IF-7 register, direction enforcement and outbound admission | `ngsh_core.integration` |

The thread service additionally exposes search over the projection
(`ngsh_core.search`) and the test-data lake catalogue and lineage
(`ngsh_core.lakehouse`). Both are derived views; neither is a second source of
truth.

In front of these services, `gateway-service` (8080) provides the console's
single address, the live platform status, the capability matrix and a
transparent `/api/<service>/...` proxy. It is not a business service and owns no
authoritative fact.

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
* hierarchy rollup and a gap report;
* A-2 variant family generation from a common core, with a content-addressed
  core id, a complete bill of materials, library-rule refusals and core-defect
  propagation into every affected variant;
* A-4 technology-insertion assessment against recorded subsystem maturity and
  committed range/production slots, with a traceable change request;
* A-5 interface data sheets (ICDs) generated from a registered interface and
  verified against its digest, plus a reference-architecture catalogue that
  refuses to count an incomplete entry.

Not delivered: the SysML authoring environment, baseline branching and
merging, the design-change workflow, interface negotiation and a full
multi-language ICD renderer. The generated ICD is a structured data sheet, not
a formatted document.

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

Delivered beyond the credential rules:

* E-1 training scenarios that must reference live thread entities — a
  placeholder or simulator-only reference is named and refused;
* E-2 content-addressed curriculum packages with a reproducible digest, a
  restricted-source refusal and a reviewer/guard version;
* E-5 sanitised academic/partner extracts whose manifest is complete and
  anchored, with a refused extract still recorded in the audit ledger;
* training completions that map to the skill they exercised and expose live
  reference coverage.

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
  C-004 is enforced (the model must be approved and carry a fidelity score);
* G-2 range capacity computed from live facilities and bookings, including
  telemetry coverage, conflict detection and a reproducible priority scheduler
  that names what it could not place;
* G-4 a model fidelity registry with model-card completeness, approval ageing,
  a release gate, and drift that withdraws approval and notifies dependents by
  writing an `entity.updated` event back to the `Model`.

Not delivered: the AR/VR test-cell environment, range instrumentation
integration, the automated reduction pipeline itself (the result carries the
dataset URIs and the pipeline reference), and automated re-approval after a
drift fix.

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
* F-3 continuous fire-control quality: custody handover quality, track purity
  and solution error, computed from named observation measurements with
  thresholds and a breach list;
* F-4 interim candidate composition with a virtual-validation record that
  refuses an unapproved model or one outside its applicability envelope;
* F-5 an isolated plug-in host with a contract-version check, a host-envelope
  check, deterministic run keys and an unload that cannot touch the host;
* F-6 red/blue co-simulation against one identical threat node, refusing a
  duplicated threat model;
* virtual range bookings that refuse to overlap.

Not delivered: PSDD IF-3 outbound integration to SDA/PWSA, high-fidelity
threat models, hardware-in-the-loop, and the classified production
engagement studies. The inbound-only IF-3 position is a programme-office
decision recorded in the interface register. The plug-in host executes only
registered in-process handlers; it does not sandbox arbitrary native code.

## 8. Pillar H — industrial base

Delivered:

* H-1 a surge readiness that is `verified` only when a digital-twin run and a
  named owner exist, with a confidence interval, a binding supplier bottleneck
  and a list of what still prevents verification;
* H-2 a reconstitution assessment that distinguishes a plan from a measured
  exercise time, names the failure mode and escalates to the programme office;
* H-3 an affordability trace from requirement to the allocated element and cost
  estimate, with untraced requirements visible, plus a unit-cost learning curve
  with a fit quality;
* cost-estimate quality checks that refuse a parametric estimate presented as
  actual.

Not delivered: prime contractor cost data, live MES/ERP feeds and classified
production rates. Those are inputs the programme office supplies.

## 9. Thread search and the test-data lake

* `GET /v1/search` ranks projection entities against a query and returns the
  matched fields and score, so a hit explains itself.
* `GET /v1/datasets` catalogues datasets from admitted test results and marks a
  dataset unconfigured when any contributing result lacks a configuration
  snapshot.
* `GET /v1/datasets/{id}/lineage` resolves a dataset to its results,
  configurations and models.

Both are rebuildable projections over the event log, per ADR-0001.

## 10. Programme measures

The analytics service computes the PSDD section 12 outcomes from the thread,
not from slides: kill-chain latency against a baseline, virtual-to-physical
ratio, surge readiness, time to reconstitute, workforce gap, design-iterate
cycles and model-fidelity improvement. A measure that cannot be computed from
the thread is reported as `NOT_COMPUTED` with the missing input named; it is
never reported as zero. The workforce gap also requires the classified demand
as an explicit input, because that demand is not derivable from the thread.

## 11. External interface register

The integration service holds IF-1..IF-7 in one catalogue, reports the register
incomplete when a PSDD interface is missing, and enforces direction at the
boundary. An outbound submission to an interface recorded as inbound-only is
refused with the programme-office note, never silently dropped. An accepted
submission receives a deterministic transport key so a retry is recognisable.

## 12. The programme traversal

`tests/e2e/test_programme_traversal.py` and `scripts/demo_programme.py` walk
one programme through all nine pillar services on one platform database:

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
the programme has one thread, not a silo per pillar.

## 13. Verification

| Gate | Command | What it proves |
|---|---|---|
| Domain rules | `uv run pytest tests/unit` | Each rule, including its negative cases |
| Service behaviour | `uv run pytest tests/integration` | The HTTP surface, validation codes and projection reads |
| Programme traversal | `uv run pytest tests/e2e/test_programme_traversal.py` | All pillars on one log, plus a projection rebuild |
| Contracts | `uv run python tools/validate_contracts.py` | Schemas, registry and constraints agree |
| Generated models | `uv run python tools/codegen/generate.py --check` | No drift between contracts and Python |
| Lint | `uv run ruff check libs services apps tests tools scripts` | Style and import hygiene |
| Live demo | `make dev` then `make demo-programme` | The same traversal over HTTP against the running stack |
| Complete scope | `make dev` then `make demo-full` | Every one of the 34 capabilities and 7 interfaces through the gateway |

## 14. What this is not

The delivered services are a reference implementation of the platform's rules,
not accredited production software. The following remain open and are tracked
in the risk register:

* capabilities are runnable and tested, but programme acceptance against their
  operational exit criteria still requires real programme data and institutions
  (see [`08-complete-build.md`](08-complete-build.md) §7);
* no PostgreSQL server has been exercised at runtime in this environment,
  though the dialect is implemented and its SQL is checked;
* no Docker or Helm runtime is available locally; compose and chart rendering
  are validated statically;
* partner institutions, AR/VR hardware, range instrumentation, classified
  production demand and prime PLM/MES access are external dependencies for the
  real increment exits.

Where a statement here contradicts a contract file, the contract wins and this
document is the defect.
