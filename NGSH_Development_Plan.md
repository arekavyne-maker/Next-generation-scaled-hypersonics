# NGSH Development Plan

**Next-Generation Scaled Hypersonics (NGSH)**
Programme Software Delivery Plan

| Field | Value |
|---|---|
| Document ID | NGSH-DSP-001 |
| Version | 1.0 |
| Date | 2026-11-14 |
| Status | Baseline for Increment 0 execution; open for review |
| Inputs | `NGSH_Preliminary_Software_Design_Document.md` v0.1 (PSDD); `docs/adr/`; `contracts/` |
| Classification | CUI (document). The system it plans is designed for IL5/IL6 operation |

---

## 1. Purpose

This plan turns the NGSH Preliminary Software Design Document into an
executable delivery programme. It answers four questions:

1. **What is built, in what order, and to what standard of done?**
2. **Who builds it, and how does the organisation scale?**
3. **What could go wrong, and what is the early warning for each?**
4. **How do we know it is working?**

It does not restate the architecture — that lives in `docs/architecture/` and
the ADRs. It does not restate the requirements — those live in the PSDD and
are traceable through the ontology.

### 1.1 Relationship to the PSDD

The PSDD defines an eight-pillar platform. This plan sequences that platform.
The mapping is deliberately explicit so that no capability can be claimed as
delivered without a work package and an exit criterion behind it:

| PSDD pillar | Capability IDs | First increment | Delivery vehicle |
|---|---|---|---|
| A — MBSE & Digital Thread | A-1 … A-5 | Increment 0 (thread foundation), Increment 1 (full MBSE) | Internal + RNI |
| B — Smart Manufacturing | B-1 … B-4 | Increment 2 | Internal + prime partners |
| C — Test & Flight Data | C-1 … C-4 | Increment 1 | Internal + range partners |
| D — Supply Chain & Scaling | D-1 … D-3 | Increment 3 | Internal + DASH-MOT |
| E — Cleared Workforce | E-1 … E-5 | Increment 1 | WISH-type OTA |
| F — Kill-Chain Engineering | F-1 … F-6 | Increment 4 | MDA ecosystem |
| G — Test Enterprise & M&S | G-1 … G-4 | Increment 2 (core), Increment 4 (federation) | Internal + HAMTC |
| H — Surge & Affordability | H-1 … H-3 | Increment 3 | SHY RNI response |

---

## 2. Delivery strategy

### 2.1 The central decision: foundation before pillars

**Increment 0 is the shared foundation, not a pillar.**

The PSDD describes eight pillars sharing "one ontology and one data fabric"
(PSDD §4.1). That shared substrate is not a description of an aspiration; it
is the load-bearing structure. If each pillar is built with its own data
model and its own integration layer, the platform becomes eight point tools
with a conference call between them — precisely the outcome the PSDD argues
against at §4.1: *"Point-tool competitors will serve one side; NGSH is the
only environment serving both."*

Building the foundation first is more expensive up front and cheaper in
total. The concrete cost of getting it wrong:

- **Ontology debt.** If Pillars A and C each define their own `TestResult`,
  the first cross-pillar question ("does this wind-tunnel run verify the
  nosecap requirement?") requires a bespoke join that will never be
  maintained. This is the single most expensive mistake available to us.
- **Integration debt.** Eight pillars × N integrations each, versus N
  integrations against one substrate. The substrate is the only version of
  this problem that scales.
- **Classification debt.** Access control, partitioning and audit cannot be
  retrofitted consistently across eight independently developed stacks
  without re-architecting all of them.
- **Evidence debt.** CMMC L2+ and programme protection evidence must be
  generated from lineage, and lineage cannot be reconstructed after the fact.

The cost of the decision: Increment 0 delivers no directly customer-visible
capability. It is funded as infrastructure and it must be justified on the
basis of what it makes possible, not on its own features. Section 9
addresses this with the exit criteria that matter.

### 2.2 Increments

Six increments. Each has a single sentence of intent, a set of capabilities,
and exit criteria that are testable by someone who did not build the thing.

---

#### Increment 0 — Shared Foundation

**Intent:** build the shared substrate that every pillar stands on, and prove
it end to end before any pillar depends on it.

| Work package | Capability | Size |
|---|---|---|
| WP-0.1 | Contract substrate and code-generation pipeline | 110 EW |
| WP-0.2 | Ontology registry and validation service | 80 EW |
| WP-0.3 | Event log and fabric service | 140 EW |
| WP-0.4 | Thread projection and trace service | 130 EW |
| WP-0.5 | Policy decision point and enforcement points | 150 EW |
| WP-0.6 | Audit ledger and verification tooling | 110 EW |
| WP-0.7 | Ingest service and adapters | 140 EW |
| WP-0.8 | Edge agent and reconciliation | 130 EW |
| WP-0.9 | Classification partitioning and guard service | 130 EW |
| WP-0.10 | Identity integration and clearance attributes | 90 EW |
| WP-0.11 | Platform pipeline, observability and supply chain | 120 EW |
| WP-0.12 | Model registry and fidelity service | 90 EW |
| WP-0.13 | Console shell, API gateway and client library | 100 EW |

**Increment 0 total: 1,520 engineer-weeks across 13 work packages**, with a
peak demand of about 8.3 pod-equivalents. Detail, dependencies and per-package
acceptance criteria are in [`docs/roadmap/work-packages.md`](docs/roadmap/work-packages.md).

**Exit criteria.** The authoritative criteria are I0-1 to I0-10 in
[`docs/roadmap/increments.md`](docs/roadmap/increments.md). They are all binary
and demonstrable, and each names its measurement rather than its intent:

1. A `TestResult` ingested from a range file appears in the digital thread
   with its configuration context, and the same entity can be traced to the
   requirement it verifies. *(Demonstrated: `tests/e2e/test_vertical_slice.py`)*
2. The graph projection can be deleted and rebuilt from the event log alone,
   producing an identical thread. *(Demonstrated: same test, final step.)*
3. A subject lacking clearance, need-to-know or citizenship is denied, and
   the denial is recorded in the ledger. *(Demonstrated: `tests/unit/test_policy.py`, `tests/e2e/test_vertical_slice.py`.)*
4. The audit chain verifies, and deliberate tampering with a historical entry
   is detected and localised to the exact sequence number.
5. The contract layer passes its own validator: schema validity, reference
   resolution, registry agreement, catalogue agreement, and Python-binding
   parity. *(Demonstrated: `make contracts`, `tests/integration/test_contract_parity.py`.)*
6. Every service runs unmodified in all four deployment profiles, and no
   domain module imports a cloud-provider SDK.
7. The edge agent captures events while disconnected and reconciles them
   deterministically, with clock skew measured and reported.

**Risks retired.** R-07 integration debt across pillars, R-08 contract drift,
R-20 event log and projection divergence, R-16 multi-tenant isolation
failure, and R-14 key-personnel concentration in part. The full register is in
[`docs/risk-register.md`](docs/risk-register.md).

**Duration.** At the ~25-engineer reference organisation the increment runs
4–5 pods. 1,520 engineer-weeks is roughly 30 weeks of build capacity at that
staffing, and the exit criteria — a 10⁹-event replay, a 72-hour disconnected
edge run, a 30-day access-decision soak and a four-profile image — are not
all build time. Realistic elapsed time is 9–12 months, and the plan should
be judged on the exit criteria rather than on the calendar.

---

#### Increment 1 — Workforce Pipeline of Record

**Intent:** deliver the first externally visible capability and prove the
platform serves a real customer, while standing up the test data lake.

**Capabilities:** E-1 digital-twin training, E-2 curriculum engine, E-3
skills credentialing, E-5 industry–academia sandbox (PSDD Phase 1);
C-1 unified test data lake, C-4 campaign management; A-1 digital twin
backbone (minimum), A-3 requirements-to-test traceability.

**Why E first.** PSDD §13 identifies Pillar E as the least sensitive data and
therefore the lowest-friction entry wedge into partners and institutions. It
is also the capability most directly tied to PSDD §2.2 P7 (cleared workforce
supply), which is durable across budget cycles. Deploying it early buys a
funded customer relationship while the rest of the platform is still being
built.

**Exit criteria.**

1. A trainee completes a digital-twin qualification task on a real CMC cell
   and the resulting credential appears in the digital thread against the
   `Skill` and `ProcessPlan` nodes it qualifies for.
2. A curriculum package deploys to two institutions and one Navy laboratory
   without modification, and the sanitised extract path is exercised end to
   end across the cross-domain boundary.
3. A full flight or qualification campaign's telemetry, manifests and
   results are queryable in the data lake with configuration context
   attached, and the lineage from raw file to `TestResult` is navigable.
4. A requirement in the baseline shows a computed verification coverage
   figure and a list of its gaps, derived from the thread rather than
   assembled by hand.

**Risks retired.** The "does the substrate work for a real user?" question;
the partner trust question at the least-sensitive end; the sanitised-extract
path, proven before the platform touches classified data.

---

#### Increment 2 — Manufacturing and Test Data

**Intent:** make the factory and the range feed the thread automatically, and
make the models trustworthy.

**Capabilities:** B-1 defense MES, B-2 CMC process characterisation, B-3 test
capability management, B-4 rate and cost simulation; C-2 automated reduction
and anomaly detection, C-3 twin validation loop; G-1 virtual test range,
G-3 automated model validation, G-4 fidelity registry.

**Exit criteria.**

1. A CMC process run's measured parameters are linked to its material lot,
   its microstructure characterisation and its test results, and the chain is
   traversable in either direction.
2. The drift model detects a deliberately injected parameter excursion on
   held-out production data before the associated lot is dispositioned, and
   reports a false-positive rate the quality organisation has accepted.
3. Every model in the fidelity registry carries provenance, a fidelity score
   computed against named test evidence, an applicability envelope, and a
   model card. A model without these is rejected at write time.
4. A test result automatically updates the fidelity score of every model that
   claimed it as evidence, with the before and after values recorded.

**Risks retired.** The M&S fidelity shortfall (the single largest technical
risk in PSDD §13); the test-coupling gap named at PSDD §2.1 P5.

---

#### Increment 3 — Supply Chain and Surge

**Intent:** answer the SHY question continuously rather than per RNI.

**Capabilities:** D-1 multi-tier visibility, D-2 foreign dependency mapping,
D-3 surge readiness twin; H-1 surge readiness command, H-2 reconstitution
planning, H-3 affordability engineering; A-2 modularity engine, A-4
technology insertion planner.

**Exit criteria.**

1. Every critical single-source node is identified with a reconstitution
   playbook and a measured time-to-reconstitute.
2. A surge scenario can be simulated against the verified production model
   and the output is traceable to the `Facility` capacity and `Skill` supply
   assumptions it depends on.
3. A family-of-systems variant is generated from a common core with a
   complete and consistent bill of material, and the configuration engine
   refuses to emit a variant whose interfaces are inconsistent.
4. Cost is traced from an individual design decision to unit cost at a
   stated production rate.

---

#### Increment 4 — Kill Chain and Virtual Range

**Intent:** engineer the counter-hypersonic kill chain on software timelines,
validated against the 2027 flight test.

**Capabilities:** F-1 threat digital twins, F-2 kill-chain simulator, F-3
fire-control data quality scoring, F-4 interim architecture workbench, F-5
Golden Dome readiness, F-6 red/blue co-simulation; G-2 campaign digital twin.

**This increment is the one with a hard external date.** PSDD §11 Phase 4
names the 2027 Maverick flight test as its validation event. That is a
scheduling constraint the plan cannot ignore, and Section 8 treats it
explicitly.

**Exit criteria.**

1. A candidate architecture (HBTSS cueing → Aegis/GPI → effector) is
   simulated end to end, with 10 000 Monte Carlo runs completing within the
   4-hour budget of PSDD §8.
2. Every simulation input and output traces to a named model version, a
   fidelity score and an applicability envelope. A run whose inputs fall
   outside their envelope is refused, not warned about.
3. Fire-control data quality is measured as a continuous score against
   thresholds, and a candidate requirement expressed in those terms becomes
   a testable metric with defined pass criteria.
4. The virtual range consumes a real campaign's telemetry and reproduces the
   flight result within an agreed tolerance, or explains why not.

---

#### Increment 5 — Full Stack and Flight Demonstration

**Intent:** be the test and integration environment of record for the
prototype programme.

**Capabilities:** full-stack integration, A-4/A-5 at depth, G-2 cross-DoD
range scheduling, and the transition interface to Golden Dome / GPI
(PSDD Phase 6).

**Exit criteria.** A complete digital thread exists for every article on the
flight vehicle, from material lot through process run, test article, flight
result and requirement verification — and that thread is reconstructable
from the event log alone.

---

### 2.3 What each increment deliberately does not do

Stating the exclusions is as important as stating the scope, because scope
pressure arrives from partners.

| Increment | Explicitly excluded | Why |
|---|---|---|
| 0 | Any pillar capability; any CUI-and-above deployment | The substrate must be proven before it carries a payload |
| 1 | Classified threat data; the BOM interface | The sanitised-extract path is not yet proven |
| 2 | Production MES replacement of a prime's MES | The complement posture (PSDD §4.2 #2) is contractual, not aspirational |
| 3 | Predictive claims about real supplier behaviour | Surrogate confidence is not yet defensible to a supply-chain assessor |
| 4 | Live fire-control data from fielded systems | PSI-3 certification of a live feed is a separate programme of work |
| 5 | Replacing BMC3 or any fielded system | Never in scope (PSDD §3.2) |

---

## 3. Architecture decisions

Eight decisions shape everything downstream. Each is recorded in
`docs/adr/` with its alternatives and consequences. In summary:

| ADR | Decision | One-line rationale |
|---|---|---|
| 0001 | The event log is the system of record; everything else is a projection | A graph that can be rebuilt from its source can never be the place an authoritative fact lives |
| 0002 | JSON Schema contracts, not shared source libraries | Polyglot services without a language monoculture, with a single reviewable contract |
| 0003 | Platform-agnostic, hybrid-first deployment | The platform must land in an accredited cloud, an on-prem enclave, or a disconnected range annex without change |
| 0004 | ABAC with separated decision and enforcement points | Clearance alone is insufficient; a policy that drifts between services cannot be attested |
| 0005 | A separate hash-chained audit ledger | Replay — the event log's core operation — is exactly what would rewrite history |
| 0006 | Edge degraded mode with deterministic reconciliation | The factory floor and the range must work when the network does not |
| 0007 | Physical storage partitioning by classification | Application-layer filtering alone is not a classification control |
| 0008 | Model cards and a fidelity registry as first-class entities | Test-coupled M&S (PSDD §4.2 #4) requires fidelity to be recorded, not asserted |

Two consequences deserve emphasis because they constrain everything else:

**Contract-first, not code-first.** An ontology change is a reviewed artefact
before it is a code change. `make contracts` is a merge gate. The Python,
TypeScript and (planned) Go bindings are generated from the same contract and
are checked against it in CI. This is why the contract-parity test exists.

**Fail closed, everywhere.** An unparseable classification is treated as more
restricted. An unmatched policy is a denial. A resource type not named in an
allow rule is unreachable. A model without a fidelity score is rejected. Each
of these is a deliberate choice against convenience, and each of them will be
questioned at least once.

---

## 4. Work breakdown

The full breakdown — 49 work packages, each with a description, deliverables,
acceptance criteria, dependencies, size and pod type — is in
[`docs/roadmap/work-packages.md`](docs/roadmap/work-packages.md). The sizes
there are the estimate of record and the summary below is derived from them
rather than maintained by hand, so the two cannot drift; a test enforces
that.

| Increment | Work packages | Total size (EW) | Peak pod-equivalents | Lead capabilities |
|---|---|---|---|---|
| 0 — Foundation | 13 | 1,520 | 8.3 | Foundation services, contracts, partitioning |
| 1 — Workforce and test evidence | 7 | 830 | 4.4 | E-1..E-5, A-1, A-3 (first slice) |
| 2 — Manufacturing and M&S | 8 | 1,310 | 5.9 | B-1..B-4, C-1..C-4 |
| 3 — Supply chain and surge | 6 | 770 | 3.6 | D-1..D-3, H-1..H-3 |
| 4 — Kill chain and virtual range | 10 | 1,600 | 7.2 | F-1..F-6, G-1..G-4 |
| 5 — Integration and flight demo | 5 | 1,100 | 4.5 | A-2, A-4, A-5, full stack |
| **Total** | **49** | **7,130** | **~8.3** | All 34 PSDD capability ids |

**Total programme effort is 7,130 engineer-weeks across 49 work packages.**
The numbers are not a promise of a date. They are the size of the work, and
the calendar follows from the organisation that is stood up to do it (§5).

### Increment 0 in detail

| WP | Title | Size (EW) | Pod |
|---|---|---|---|
| WP-0.1 | Contract substrate and code-generation pipeline | 110 | Ontology |
| WP-0.2 | Ontology registry and validation service | 80 | Ontology |
| WP-0.3 | Event log and fabric service | 140 | Platform |
| WP-0.4 | Thread projection and trace service | 130 | Ontology |
| WP-0.5 | Policy decision point and enforcement points | 150 | Security |
| WP-0.6 | Audit ledger and verification tooling | 110 | Security |
| WP-0.7 | Ingest service and adapters | 140 | Platform |
| WP-0.8 | Edge agent and reconciliation | 130 | Edge / Field |
| WP-0.9 | Classification partitioning and guard service | 130 | Security |
| WP-0.10 | Identity integration and clearance attributes | 90 | Security |
| WP-0.11 | Platform pipeline, observability and supply chain | 120 | Platform |
| WP-0.12 | Model registry and fidelity service | 90 | MLOps |
| WP-0.13 | Console shell, API gateway and client library | 100 | Platform |

**On contingency.** A plan that carries no contingency is a plan that has
not thought about the unknown, and one that carries 30% is a plan whose
estimates are not real. Increment 0 carries roughly 12% above the derived
estimate, which is appropriate for a first increment whose interfaces are
unproven — and deliberately not more, because contingency that is never
consumed is not contingency, it is optimism.

## 5. Staffing

### 5.1 The pod

A **pod** is 6–9 engineers with a single accountable outcome, and it is the
unit at which the programme scales. Work is pulled into pods, not assigned
to individuals across pillars.

| Pod type | Composition | Accountable for |
|---|---|---|
| **Platform** | 3–4 backend, 1–2 infrastructure, 1 SRE | The fabric, the event log, the projection pipeline |
| **Ontology / Data** | 2 domain engineers, 2 data engineers, 1 systems engineer | The shared ontology, the contract layer, the stores |
| **Security & Compliance** | 2 security engineers, 1 compliance officer, 1 cleared SME | Classification partitioning, ABAC, audit, CMMC/PPP evidence |
| **Pillar-X** | 3 domain engineers, 2 data/ML engineers, 1 systems engineer, 1 UX engineer | One pillar's capabilities end to end |
| **Test & Qualification** | 2 test engineers, 1 M&S engineer, 1 domain SME | Verification, regression, model validation, range liaison |
| **MLOps** | 2–3 ML engineers, 1 platform engineer | Model registry, fidelity scoring, drift monitoring, approval gates |
| **Edge / Field** | 2 embedded engineers, 1 infrastructure engineer | Edge annex, degraded mode, field support |

### 5.2 Rules for composing a programme

These are constraints, not preferences. Violating them is how the programme
loses a year.

1. **Security and compliance is embedded, never a silo.** A compliance officer
   sits in every pillar pod. A central security team that reviews artefacts
   after the fact reviews them too late.
2. **Every pillar pod contains a systems engineer and a test engineer.** The
   first two features of most ML-enabled platforms are a model that cannot be
   traced to a requirement and a feature with no acceptance criterion.
3. **Every pillar pod contains a cleared workforce member.** This is the WISH
   and JHTO constraint at PSDD §2.2 P7, and it is also the practical
   mechanism by which cleared-workforce pipelines are built rather than
   procured.
4. **One pod owns one ontology change at a time.** Concurrent ontology edits
   from multiple pods are the mechanism by which ontology debt is created.
   Changes are queued through the Ontology / Data pod.
5. **MLOps is a service to the pillars, not a gate they wait on.** A model
   that takes three weeks to register is a model that does not get used.

### 5.3 Reference organisations

Scale-agnostic: the plan is expressed in work packages, and the pods below
are the configurations that consume them. The authoritative compositions are
in [`docs/staffing.md`](docs/staffing.md) §5–§7.

**~25 engineers — 4 to 5 pods.** Optimised for the foundation and the Pillar E
revenue event, not for breadth.

| Pod | Size |
|---|---|
| Platform | 7 |
| Ontology / Data | 7 |
| Security & Compliance | 6 |
| Test & Qualification | 4 |
| Leadership, product, architecture | 4 |

**~60 engineers — 8 to 9 pods.** Two pillars in flight at once, with the
foundation and the verification function properly staffed.

| Pod | Size |
|---|---|
| Platform | 8 |
| Ontology / Data | 7 |
| Security & Compliance | 7 |
| Pillar E (workforce) | 8 |
| Pillar C (test data) | 8 |
| Test & Qualification | 6 |
| MLOps | 4 |
| Edge / Field | 4 |
| Leadership, product, architecture | 8 |

**~120 engineers — 15 to 17 pods.** Four pillars in parallel. At this size
the binding constraint stops being engineering capacity and becomes partner
access and accreditation throughput (R-02, R-10, R-18).

**The scaling observation.** From 25 engineers, the highest-value addition is
not another pillar pod. It is a **Test & Qualification pod and an MLOps pod**.
The programme's largest quality risks — R-07 integration debt, R-08 contract
drift, R-11 fidelity shortfall — are all verification risks, and they are
cheap to retire with verification capacity and expensive to retire without.

### 5.4 Hiring and clearance

Clearance sponsorship is the long pole and must start on day one.

- Sponsorship requests are filed at Increment 0 for the whole programme,
  not per increment. A sponsorship filed in Increment 3 is a sponsorship that
  arrives in Increment 6.
- Roles requiring clearance are separated from roles that do not, so that
  clearance lag does not block the unclassified parts of the work.
- The WISH consortium is a clearance-pipeline instrument as much as a
  training instrument (PSDD §5.5 E-2, §14). Treat university partnerships as
  workforce development, not just as distribution.

---

## 6. Engineering practices

| Practice | Rule | Rationale |
|---|---|---|
| Contract-first | No entity or event shape is defined in code. It is defined in `contracts/` and generated. | One reviewable artefact; no drift between languages |
| Test-first at the boundary | Every write path has a test that proves what it refuses | Most of the platform's value is in what it will not accept |
| No service holds a foreign key | Services reference entity ids, never rows | Prevents the graph from becoming a distributed monolith |
| Idempotency everywhere | Every write accepts an idempotency key | Edge reconciliation re-delivers by design |
| Immutability of evidence | Test results are append-only; corrections are superseding records | Constraint C-003; an evidence trail that can be edited is not evidence |
| Explicit provenance | Every derived value names its source, method and confidence | CMMC evidence and model credibility are the same requirement |
| Model cards for every model | Including non-ML physics models | A model without a fidelity score and applicability envelope is unusable for safety-relevant output |
| Human approval for safety-relevant output | Enforced at the model registry, not by convention | PSDD §8 AI/ML requirement |
| 15-minute pipeline, 1-hour release | Exceptions require the security pod's lead | Classification and audit changes cannot wait a week; they also cannot be rushed |
| Every service ships with `/healthz`, `/readyz` and OpenAPI | Non-negotiable | Operational uniformity across an accredited estate |

---

## 7. Environments and data

| Environment | Data | Purpose |
|---|---|---|
| Local | Synthetic | Development; no real data ever reaches a developer machine |
| CI | Synthetic | Contract validation, unit, integration, e2e |
| Integration | Synthetic + sanitised extracts | Cross-service behaviour, partner onboarding |
| Staging | Sanitised extracts | Release candidate validation, console rehearsal |
| Accredited cloud (IL5) | CUI, sanitised | Programme operation |
| On-prem (IL6) | RESTRICTED and above, threat data | Classified work, fire-control data |
| Edge annex | Local, classified | Factory floor and range operation, disconnected |

**Rule:** no real programme data is used anywhere except the accredited cloud,
the on-prem node and the edge annex. Synthetic data is generated, not
scrubbed, so that no scrubbed artefact can be mistaken for a sanitised
release.

---

## 8. The 2027 validation event

Increment 4 carries a hard external constraint that the plan must not
discover late.

The PSDD §11 Phase 4 validation event is the 2027 Maverick flight test.
Three consequences:

1. **The simulation harness, not the simulator, is the critical path.** The
   Monte Carlo engine can be improved for years; a harness that cannot be
   validated against a real flight result before the event is a schedule
   failure. WP-4.2 (harness and benchmark suite) therefore precedes WP-4.3
   (the simulator proper) in the dependency graph, against the instinct to
   build the interesting thing first.
2. **A mid-increment capability freeze at T-9 months.** The kill-chain
   simulator and the threat-twin pipeline enter validation-only mode for the
   final quarter. Feature work stops; defect correction and evidence
   assembly continue.
3. **The 10 000-run / 4-hour budget (PSDD §8) is a test, not a target.** It
   is enforced as a regression test from WP-4.3 onward, and the surrogate
   acceleration path (PSDD §9.5) exists to protect it rather than to be
   clever.

If the schedule cannot absorb the freeze, the correct response is to
descope a capability, not to move the freeze. The validation event is the
one date in the programme that other dates move for.

---

## 9. Measurement

### 9.1 Programme outcomes (from PSDD §12)

| Outcome | Metric | Baseline | Target |
|---|---|---|---|
| Compress the kill chain | Simulated detection→custody time per architecture; reduction vs. baseline | Established at Increment 4 | 50% reduction on the baseline architecture |
| Stretch defense dollars | Virtual engagements per flight test consumed | 1 | ≥ 10× |
| Deter by capacity | Verified surge production rate; cost-per-effect trajectory | Established at Increment 3 | Trajectory agreed with the customer |
| Sustain under attack | Time-to-reconstitute for critical nodes | Estimated at Increment 3 | Agreed per node |
| Guarantee the workforce | Cleared-skills supply vs. classified demand gap, by region and trade | Established at Increment 1 | Gap closed for priority trades |
| Accelerate development | Design-iterate cycles per flight test; model fidelity improvement per campaign | Baseline at Increment 2 | 5× iterate; fidelity +0.10 per campaign |

### 9.2 Delivery health

Measured monthly, reviewed at the programme board, and acted on when a
trend moves rather than when a single point does.

| Metric | Target |
|---|---|
| Lead time from merged change to deployed in the accredited environment | ≤ 5 working days |
| Change failure rate | ≤ 8% |
| Contract drift incidents (code and contract disagreeing) | 0 |
| Classification defects found in audit | 0 |
| Audit chain verification failures | 0 |
| Mean time to detect and revoke an entitlement | ≤ 15 minutes |
| Ontology change lead time | ≤ 10 working days |
| MLOps registration lead time for a new model | ≤ 3 working days |
| Test suite runtime (unit → e2e) | ≤ 5 minutes |
| Open critical and high risks without a named owner | 0 |

### 9.3 The metrics that matter most

Two numbers predict whether NGSH succeeds, and neither is a delivery metric:

- **Ontology reuse.** The proportion of entities created by a pillar that
  already existed in the shared ontology. Below 80%, the platform is
  fragmenting; the pillars are building point tools with a shared database.
- **Thread completeness.** The proportion of verification evidence reachable
  from a requirement through the thread without manual assembly. Below 90%,
  the digital thread is a diagram rather than a system.

---

## 10. Risks

The authoritative register — 26 risks with likelihood, impact, inherent and
residual exposure, owner role, mitigation, contingency, early-warning
indicator and the scoring method — is in
[`docs/risk-register.md`](docs/risk-register.md). Seven risks carry an
inherent exposure of 9 and dominate the programme's exposure:

| Rank | ID | Risk | L | I | Inherent | Residual | Owner | Leading indicator |
|---|---|---|---|---|---|---|---|---|
| 1 | R-07 | Integration debt across pillars | H | H | 9 | 4 | Chief Architect | Two pillars defining the same concept independently |
| 2 | R-10 | Classified-access latency (clearance and accreditation throughput) | H | H | 9 | 6 | Programme Director | Sponsorship processing exceeds six months |
| 3 | R-11 | M&S fidelity shortfall | H | H | 9 | 6 | Data and MLOps Lead | Fidelity plateau after three campaigns |
| 4 | R-13 | Schedule risk of the 2027 validation event | H | H | 9 | 6 | Programme Director | Harness benchmark misses target at T-6 months |
| 5 | R-15 | Test-environment scarcity | H | H | 9 | 6 | Pillar G Lead | Range slots unbookable at campaign planning |
| 6 | R-02 | Prime data-sharing resistance | H | H | 9 | 6 | Business Development Lead | A partner declines a data exchange at first review |
| 7 | R-18 | Cleared-workforce pipeline shortfall | H | H | 9 | 6 | Programme Director | Credential pipeline below the demand curve |

Aggregate inherent exposure is 162 and aggregate residual exposure is 96. The
mitigation set retires 66 exposure points, and no risk's residual sits below
its band floor without an explicit acceptance.

Three of these are worth stating in the plan's own voice, because they change
what the plan does rather than merely describing a hazard:

**R-07 is the risk the foundation exists to retire.** Integration debt is not
mitigated by discipline; it is mitigated by making the shared contract the
only coupling mechanism between pillars, so that integration is subscription
to an event group rather than a bespoke interface. Increment 0 builds that
mechanism, and the exit criterion is a conformance suite rather than a
promise.

**R-13 cannot be mitigated by working harder.** The 2027 validation event is
fixed. The mitigations are structural: the simulation harness precedes the
simulator in the dependency graph, a capability freeze lands at T-9 months,
and the correct response to a schedule that will not fit is to descope a
capability, never to move the date.

**R-10 and R-18 are constraints on the programme's shape, not its pace.**
Clearance and accreditation throughput are external and slow. Sponsorship is
filed for the whole programme at Increment 0 rather than per increment, roles
requiring clearance are separated from roles that do not, and the university
consortium is treated as a clearance pipeline as much as a training one.

---

## 11. Governance

| Forum | Cadence | Purpose | Decision rights |
|---|---|---|---|
| Programme board | Monthly | Increment entry/exit, risk acceptance, scope changes | Programme sponsor, architect, all pod leads |
| Architecture review | Fortnightly | ADR proposals, contract changes, cross-pod interface decisions | Architect, ontology pod lead, security pod lead |
| Increment review | At each exit | Evidence against exit criteria | Programme board |
| Security and compliance review | Monthly | Classification handling, audit findings, CMMC evidence | Compliance officer (authority to stop a release) |
| Partner synchronization | Per partner | Interface status, data-exchange readiness | Business development with the pod lead |

**Decision latency targets:** architecture review decisions within five
working days; contract changes within ten; release approvals within two.

**One rule that matters more than the rest:** the security and compliance
pod has an unconditional veto on a release that touches classification
handling. This is not a committee. It is a single named individual who can
stop a release without consensus, and it is written into the release
procedure rather than left to custom.

---

## 12. Governance of the ontology

The shared ontology is the programme's most valuable asset and its most
likely source of conflict. Its change process is therefore explicit:

1. A change request states the capability it enables, the entity or relation
   affected, and whether any existing pillar is affected.
2. The Ontology / Data pod assesses the change against: does it extend an
   existing type, does it require a new type, does it change the
   classification floor, does it affect a pillar's write path.
3. A new type is admitted only with a classification floor, an id prefix, an
   owning pillar and at least one relation to an existing type. A type with
   no relation to the existing ontology is a rejected candidate: it is a
   table, not a concept.
4. Contract changes require a version bump. A change that alters the meaning
   of an existing field is a major bump and requires a migration plan for
   every pillar that reads it.
5. Generated bindings are rebuilt and the contract-parity test must pass
   before merge.

**Rejection criteria, stated in advance so they are not negotiated under
pressure:** a request that cannot name the capability it serves; a request
that would weaken a classification floor; a request that would make an
existing pillar's data unreadable without migration.

---

## 13. Immediate next steps

Increment 0 is the executable starting point. The following are the first
sixty days.

| # | Action | Owner | Done when |
|---|---|---|---|
| 1 | Review this plan and the eight ADRs; record decisions, objections and required changes | Architect, programme sponsor | Signed ADR dispositions |
| 2 | Confirm the pod model and name pod leads; file clearance sponsorships for the full programme | Programme sponsor | Every pod has a lead; sponsorships filed |
| 3 | Run the foundation stack locally; walk `scripts/demo.py` end to end | Platform pod | Demo completes on a clean checkout with one command |
| 4 | Complete WP-0.7 (PIV/ICAM) to a working adapter against a test directory | Security pod | An assertion from the test IdP yields the correct attributes |
| 5 | Complete WP-0.9 (edge agent) with the reconciliation algorithm specified, not merely implemented | Platform pod | A written specification plus a conformance test |
| 6 | Define the contract generation pipeline for TypeScript and Go | Ontology pod | `make codegen` emits codecs; parity test covers them |
| 7 | Establish the synthetic data generator | Ontology pod | No hand-written fixtures in the integration or e2e suites |
| 8 | Baseline the measurement set in §9 | Programme architect | Baselines recorded; dashboard available |

**What must not happen in the first sixty days:** any pillar feature work.
The temptation to start Pillar E because it is the first sellable increment
is strong and should be resisted until the substrate is agreed. A pillar
built on a foundation that is still moving is a pillar that is rebuilt.

---

## 14. Reconciliation decisions

The contract layer was reviewed against the PSDD and the ADRs after the
foundation was built. The items below were disagreements, and each is now
resolved in the contract rather than left as an open question. They are
recorded here because a reader comparing this plan with the PSDD will notice
the differences.

| Item | Decision | Where |
|---|---|---|
| `Interface` shared the `IF` id prefix with PSDD §7's `IF-1`..`IF-7` external interfaces | The entity prefix is `IFC` | `contracts/ontology/registry.json` |
| `RESTRICTED` is a classification level the PSDD never enumerates | It is the IL6-annex level: the level at which classified threat and fire-control data is held. The storage partition boundary sits between `CUI` and `RESTRICTED`, which is why the threat types carry a `RESTRICTED` floor | `docs/architecture/04-security-architecture.md` |
| `FOUNDATION` meant both the PSDD §4.1 foundation layer (Pillars A–D) and the foundation services | The catalog's `owner: FOUNDATION` denotes the services; the note is in the catalog itself | `contracts/events/catalog.json` |
| Nothing stopped an entity's classification being lowered in place | Constraint **C-009** is declared and enforced, on updates and on edge merges | `contracts/ontology/registry.json`, `libs/ngsh-core/ngsh_core/ontology.py` |
| The edge envelope could not distinguish a fast-forward from a duplicate | The `edge` block carries `localSequence` and `branchedFromSeq` | `contracts/events/event-envelope.schema.json` |
| Reconciliation conflicts had no first-class representation | `reconcile.conflict.recorded` is a catalogued event | `contracts/events/catalog.json` |
| The audit ledger's entry shape existed only in prose | It is a contract | `contracts/audit/ledger-entry.schema.json` |
| An access decision did not record which enforcement point made it | `enforcementPoint` is on the event and the ledger entry | `contracts/events/access.decision.recorded.schema.json` |
| Every access decision produced a ledger entry but not an event | Both are produced, and the cross-check is a release criterion (I0-4) | `services/policy-service/` |
| `Person` was owned by Pillar E alone, but C-006 requires one for a `ProcessRun` | Pillar B consumes it as well | `contracts/ontology/registry.json` |
| Pillar E could not prove a sanitised extract held nothing classified | `pillarE` subscribes to `access.*` | `contracts/events/catalog.json` |

Two items are noted rather than resolved, because they are PSDD questions
rather than contract defects:

* **IF-3 is inbound-only** in PSDD §7, but the platform needs to exchange
  engagement scenarios and quality metrics with SDA/PWSA. No outbound
  interface is defined. This is raised with the programme office as an
  interface-definition task, and it is a prerequisite for Increment 4 rather
  than a defect in the platform.
* **`FidelityScore` is a value object, not an entity type.** PSDD §6.1's
  phrasing — "`Model` (with `FidelityScore`)" — can be misread as implying a
  twenty-fourth entity type. The registry defines 23, and the phrase means
  that `Model` carries one.

---

## 15. Document control

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-11-14 | Initial development plan. Increment 0 implemented as a working foundation; Increments 1–5 specified with exit criteria. |
| 1.1 | 2026-11-14 | Reconciled against the contract layer: work-package sizes, effort totals, risk identifiers, increment titles and pod names now agree with the roadmap, staffing and risk documents. Reconciliation decisions recorded in §14. |

### Related artefacts

| Artefact | Location |
|---|---|
| Preliminary Software Design Document | `NGSH_Preliminary_Software_Design_Document.md` |
| Architecture decision records | `docs/adr/` |
| Architecture documentation | `docs/architecture/` |
| Increment and work-package detail | `docs/roadmap/` |
| Staffing model | `docs/staffing.md` |
| Risk register | `docs/risk-register.md` |
| Contract layer | `contracts/` |
| Foundation implementation | `libs/`, `services/`, `apps/` |
| Tests | `tests/` |

*Next artefacts: partner-facing capability statement; Increment 0 exit
evidence pack; WP-0.9 reconciliation specification; TypeScript and Go
contract-generation pipeline.*
