# NGSH Risk Register

## Purpose

This document is the programme risk register for NGSH. It covers the programme and political risks identified in PSDD §13 and the software delivery, security, data and workforce risks that the platform's own architecture and delivery model create. Every row carries a numeric exposure so that the register can be ranked, budgeted for and reviewed. Each entry states the owner role rather than a named individual, because a risk owned by a person leaves when the person leaves.

## Contents

1. [How to read this register](#1-how-to-read-this-register)
2. [Exposure summary](#2-exposure-summary)
3. [Programme and political risks](#3-programme-and-political-risks)
4. [Technical and delivery risks](#4-technical-and-delivery-risks)
5. [Security, compliance and accreditation risks](#5-security-compliance-and-accreditation-risks)
6. [Workforce and organisational risks](#6-workforce-and-organisational-risks)
7. [Data, rights and environment risks](#7-data-rights-and-environment-risks)
8. [Aggregate exposure profile](#8-aggregate-exposure-profile)
9. [Review, ownership and escalation](#9-review-ownership-and-escalation)
10. [References](#10-references)

## 1. How to read this register

### 1.1 Scoring

| Likelihood | Value | Definition |
|---|---|---|
| **Low** | 1 | Would require an unusual combination of circumstances; no precedent in comparable programmes |
| **Medium** | 2 | Plausible within the programme's normal operating conditions; a comparable programme would probably experience it |
| **High** | 3 | Expected to occur at least once during the programme's life unless actively addressed |

| Impact | Value | Definition |
|---|---|---|
| **Low** | 1 | Absorbed within the increment; ≤ 5 working days of schedule slip; no programme-level consequence |
| **Medium** | 2 | Costs one increment of schedule or requires a re-plan; requires a sponsor-level decision; recoverable |
| **High** | 3 | Costs a milestone or a revenue event; requires a programme-level re-plan; or has a compliance, safety or national-security consequence |

**Exposure = Likelihood × Impact**, range 1–9.

| Exposure | Band | Treatment |
|---|---|---|
| 7–9 | **Critical** | Named owner, funded mitigation, reported at every programme board, contingency exercised at least once |
| 4–6 | **High** | Named owner, funded mitigation, reported monthly |
| 1–3 | **Moderate** | Named owner, monitored, mitigation embedded in normal work |
| 1 | **Low** | Monitored; no dedicated mitigation |

### 1.2 Fields

| Field | Meaning |
|---|---|
| **Inherent exposure** | Likelihood × Impact before the programme's mitigation is applied. This is the number that justifies the mitigation spending |
| **Residual exposure** | Likelihood × Impact after the mitigation is in place and has been verified to work. A residual that has not been re-scored since the mitigation landed is a stale number |
| **Owner role** | The accountable role, not a name. The role must exist in the staffing model ([`staffing.md`](staffing.md)); a risk owned by a role that does not exist is an orphan |
| **Mitigation** | What the programme is doing, and it must be funded work, not an intention |
| **Contingency** | What the programme does if the risk occurs despite the mitigation. A contingency that has not been rehearsed is a hope |
| **Trigger** | The observable condition that means the risk is materialising. A trigger must be measurable, or it is a mood |

### 1.3 Register conventions

| Convention | Meaning |
|---|---|
| **R-nn** | Risk identifier. Never reused |
| **PSDD §13** | A programme risk carried directly from the PSDD risk table |
| **Retired** | The mitigation has landed and the residual exposure has been re-scored and accepted |
| **Accepted** | The residual exposure is accepted by the programme board with no further mitigation planned |
| **Escalated** | The residual exposure exceeds the tolerance for the risk's band; escalated to the sponsor |

## 2. Exposure summary

Ranked by inherent exposure, then by residual.

| Rank | ID | Risk | Category | L | I | Inherent | Residual | Owner role |
|---|---|---|---|---|---|---|---|---|
| 1 | R-07 | Integration debt across pillars | Technical | H | H | **9** | 4 | Chief Architect |
| 2 | R-10 | Classified-access latency (clearance and accreditation throughput) | Security | H | H | **9** | 6 | Programme Director |
| 3 | R-11 | M&S fidelity shortfall | Technical | H | H | **9** | 6 | Data and MLOps Lead |
| 4 | R-13 | Schedule risk of the 2027 validation event | Programme | H | H | **9** | 6 | Programme Director |
| 5 | R-15 | Test-environment scarcity | Data / environment | H | H | **9** | 6 | Pillar G Lead |
| 6 | R-02 | Prime data-sharing resistance | Programme | H | H | **9** | 6 | Business Development Lead |
| 7 | R-18 | Cleared-workforce pipeline shortfall | Workforce | H | H | **9** | 6 | Programme Director |
| 8 | R-01 | Classification and CUI friction slows delivery | Programme | H | M | **6** | 4 | Security Lead |
| 9 | R-04 | Threat-model data access is a chokepoint | Programme | M | H | **6** | 4 | Business Development Lead |
| 10 | R-08 | Contract drift between schemas and services | Technical | M | H | **6** | 4 | Chief Architect |
| 11 | R-12 | Data rights and intellectual property | Data / rights | M | H | **6** | 4 | Business Development Lead |
| 12 | R-14 | Key-personnel concentration | Workforce | M | H | **6** | 3 | Programme Director |
| 13 | R-16 | Multi-tenant isolation failure | Security | M | H | **6** | 3 | Security Lead |
| 14 | R-19 | Edge node compromise or spoofed telemetry | Security | M | H | **6** | 3 | Edge and Field Lead |
| 15 | R-20 | Event log and projection divergence | Technical | M | H | **6** | 2 | Platform Lead |
| 16 | R-21 | Model drift undetected | Technical | M | H | **6** | 3 | Data and MLOps Lead |
| 17 | R-23 | Key management and HSM unavailability | Security | M | H | **6** | 3 | Security Lead |
| 18 | R-03 | Defence-side budget thinness | Programme | M | H | **6** | 4 | Programme Director |
| 19 | R-06 | Budget cyclicality | Programme | M | H | **6** | 4 | Programme Director |
| 20 | R-05 | MDA / SDA integration politics | Programme | M | M | **4** | 2 | Business Development Lead |
| 21 | R-09 | Single-vendor lock-in | Technical | M | M | **4** | 2 | Platform Lead |
| 22 | R-22 | Ingestion throughput shortfall | Technical | M | M | **4** | 2 | Platform Lead |
| 23 | R-24 | Scope creep toward replacing fielded systems | Programme | M | M | **4** | 2 | Chief Architect |
| 24 | R-25 | Performance target unachievable at required fidelity | Technical | M | M | **4** | 2 | Platform Lead |
| 25 | R-26 | Ontology type proliferation | Technical | M | M | **4** | 2 | Chief Architect |
| 26 | R-17 | Supply-chain component compromise | Security | L | H | **3** | 3 | Platform Lead |

**Distribution.** Seven critical risks (inherent exposure 9), twelve high (6), six moderate (4), one low (3). Aggregate inherent exposure 162; aggregate residual exposure 96. The mitigation set retires 66 exposure points, and no risk's residual is below its band floor without an explicit acceptance.

## 3. Programme and political risks

### R-01 — Classification and CUI friction slows delivery

| Field | Value |
|---|---|
| **Source** | PSDD §13 — "Classification/CUI friction slows delivery" |
| **Category** | Programme / compliance |
| **Description** | The friction of handling CUI content — tagging at ingestion, partition-aware queries, cleared access, review gates — consumes engineering time and schedule in a way that is easy to underestimate and easy to route around. The specific failure mode is that a pillar quietly reduces its classification need to unblock itself, which produces an incorrect classification that is discovered late, or that a pillar is delivered with the classification machinery stubbed, which produces a platform that cannot hold what it is supposed to hold |
| **Likelihood** | High (3) |
| **Impact** | Medium (2) |
| **Inherent exposure** | **6** |
| **Owner role** | Security Lead |
| **Mitigation** | Physical partitioning from Increment 0, so the friction is paid once and early rather than per pillar ([ADR-0007](adr/ADR-0007-classification-partitioning.md)). The guard and the one-way extract pipeline built in Increment 0 as a foundation capability rather than as an Increment 1 deliverable. Classification resolved at ingestion with a default-deny to the most restrictive partition, so the cost of uncertainty is a higher partition and not a disclosure. The embedded security engineer in every pod (composition rule CR-1 in [`staffing.md`](staffing.md)) so the friction is absorbed inside the team rather than escalated |
| **Contingency** | A pillar that cannot meet its classification obligations within its increment delivers into a reduced partition with an explicit scope limitation and a re-plan date, rather than shipping with stubbed controls. The scope limitation is disclosed to the sponsor, because a reduced-scope pillar is a normal outcome and a hidden one is not |
| **Trigger** | Any of: a pillar's design review records two or more "we will sort classification out later" decisions; the classification estimate in the ingest path returns `INDETERMINATE` for more than 5% of a batch; a request arrives to relax a `classificationFloor`; a released artefact contains a classification marking that a later automated check disagrees with |
| **Residual exposure** | **4** (L=M 2, I=M 2). The friction is reduced, not eliminated. It is permanently present in a classified platform's delivery |

### R-02 — Prime data-sharing resistance

| Field | Value |
|---|---|
| **Source** | PSDD §13 — "Prime data-sharing resistance"; mitigation "Open APIs, complement posture, teaming agreements; Pillar E (least sensitive data) as entry wedge" |
| **Category** | Programme / commercial |
| **Description** | Primes hold the authoritative part, BOM and process data, and have legitimate commercial and contractual reasons not to share it. The consequence for NGSH is that the strike-side digital thread cannot be completed for the parts that matter most, and the platform becomes a thin analytics layer over data it does not control. The specific failure mode is that the integration is agreed in principle and never delivered, leaving the platform without the data that makes it valuable |
| **Likelihood** | High (3) |
| **Impact** | High (3) |
| **Inherent exposure** | **9** |
| **Owner role** | Business Development Lead |
| **Mitigation** | The PSDD §13 entry wedge: Pillar E is delivered first with the least sensitive data, establishing a working relationship before any prime data is at stake. The complement-not-replace posture (PSDD §4.2 principle 2, §3.2) is the negotiating position, and it is credible because the platform does not propose to replace the prime's PLM. Open APIs and a published contract layer make the integration a small piece of work for the prime. The reference integration from Increment 2 is an artefact the second prime can see |
| **Contingency** | If a prime refuses, the platform proceeds with the parts it does have and demonstrates the thread on government-owned and academic CMC content. The Pillar E and D-H increments proceed on that basis, and the strike-side trace is delivered for the subset. The missing integration is disclosed as a named programme limitation, not absorbed silently |
| **Trigger** | A teaming agreement passes 90 days without a data-access schedule; a prime requests exclusivity; the first IF-1 integration slips more than one increment; fewer than 50% of the agreed IF-1 data elements are delivered in the pilot |
| **Residual exposure** | **6** (L=M 2, I=H 3). Some share will not happen, and the platform's strike-side value depends on which parts it covers |

### R-03 — Defence-side budget thinness

| Field | Value |
|---|---|
| **Source** | PSDD §13 — "Defense-side budgets thin ($200.6M vs $3.9B)"; mitigation "Pillar F wins on leverage (multiplies existing sensor/effector value), not on competing with hardware primes" |
| **Category** | Programme / funding |
| **Description** | Defence spending on hypersonics is an order of magnitude smaller than offence spending. A platform sold on defence-side software value competes for a small budget against large programmes and will be deprioritised. The consequence is that Pillar F, which is the platform's most differentiated capability, is the hardest to fund |
| **Likelihood** | Medium (2) |
| **Impact** | High (3) |
| **Inherent exposure** | **6** |
| **Owner role** | Programme Director |
| **Mitigation** | Position Pillar F on leverage — it multiplies the value of sensors and effectors that are already funded — rather than on capability that competes with funded hardware. The Golden Dome reference-architecture plug-in framework (F-5) is deliberately shaped so that a funded homeland programme can adopt it as a component. Pillar H, D and E serve the industrial base, which is the larger budget and a durable framing across budget cycles (PSDD §13) |
| **Contingency** | Sequence the revenue events so that the industrial-base pillars fund the platform's continuity while the defence-side work continues at a reduced rate. The platform is not stopped by a defence-side budget pause; only its growth rate changes |
| **Trigger** | A defence-side funding line is created below a level that sustains the planned Increment 4 pod loading; a competing defence-side platform reaches a demonstration milestone; the pipeline value for defence-side opportunities falls below the total pipeline target for two consecutive quarters |
| **Residual exposure** | **4** (L=M 2, I=M 2). Mitigated by the sequencing, but the exposure to a defence-side pause is never removed |

### R-04 — Threat-model data access is a chokepoint

| Field | Value |
|---|---|
| **Source** | PSDD §13 — "Threat-model data access is chokepoint"; mitigation "SCI annex architecture early; collateral handling procedures; partnerships with intel community integrators" |
| **Category** | Programme / access |
| **Description** | The shield side's value is proportional to the quality and currency of the threat data. Access to classified threat observations is controlled by authorities outside the programme, on timelines the programme cannot influence, and a single withheld approval can stall Pillar F entirely. The failure mode is a Pillar F that demonstrates on synthetic threat data and is then dismissed as unreal |
| **Likelihood** | Medium (2) |
| **Impact** | High (3) |
| **Inherent exposure** | **6** |
| **Owner role** | Business Development Lead |
| **Mitigation** | The SCI annex architecture is delivered in Increment 0, so the process is proven before the data arrives, not after. Collateral handling procedures are drafted with the security office in Increment 0. Partnerships with intelligence-community integrators are established in Increment 1, in parallel with the technical build, so the access path is not a dependency discovered late. `ThreatSystem` and `ThreatObservation` are modelled with a `RESTRICTED` floor from the registry's first version, so the platform is ready to receive them |
| **Contingency** | Proceed on synthetic and unclassified threat data for the engineering development of F-1 and F-2, with synthetic data explicitly marked as such in the `Provenance.source` field and never presented as a reconstruction of a real system. The integration is demonstrated on unclassified surrogates. The programme does not represent synthetic-data results to the sponsor as threat-reconstruction results |
| **Trigger** | A threat-data access request is outstanding for more than 60 days; fewer than two approved access paths exist by the end of Increment 2; the collateral handling procedure is not signed by the end of Increment 1 |
| **Residual exposure** | **4** (L=M 2, I=M 2). Access approval remains partly outside the programme's control, so the residual cannot go to zero |

### R-05 — MDA / SDA integration politics

| Field | Value |
|---|---|
| **Source** | PSDD §13 — "MDA/SDA integration politics"; mitigation "Explicit non-replacement posture for BMC3; sensor/prime partner on teaming list" |
| **Category** | Programme / political |
| **Description** | An environment that could be read as a threat to a fielded command-and-control system's primacy will encounter institutional resistance that has nothing to do with the software. The failure mode is that integration is technically specified and never operationally exercised |
| **Likelihood** | Medium (2) |
| **Impact** | Medium (2) |
| **Inherent exposure** | **4** |
| **Owner role** | Business Development Lead |
| **Mitigation** | The non-replacement posture is written into the architecture, not just the marketing: BMC3 is out of scope in PSDD §3.2, IF-2 delivers scenario definitions *for* BMC3 test rather than competing with it, and the console never presents a tactical picture. At least one sensor or prime partner is on the teaming list (PSDD §14), which removes the "pure software challenger" framing |
| **Contingency** | Work through the sensor or prime partner rather than directly, so the first integration is a partner-to-partner relationship that the programme supports rather than a proposal to replace |
| **Trigger** | A stakeholder describes the platform as a replacement rather than a test and integration environment; an integration review requests a tactical display; a sensor partner declines a teaming invitation citing competitive concern |
| **Residual exposure** | **2** (L=L 1, I=M 2). Low, because the platform genuinely does not replace anything, and because a demonstrated integration is a strong argument |

### R-06 — Budget cyclicality

| Field | Value |
|---|---|
| **Source** | PSDD §13 — "Budget cyclicality"; mitigation "Workforce + industrial-base framings (WISH/SHY) are durable across budget cycles" |
| **Category** | Programme / funding |
| **Description** | Hypersonic funding is subject to shifting national priorities. A programme framed on a single vehicle or a single threat can lose its funding between increments, and the engineering team disperses |
| **Likelihood** | Medium (2) |
| **Impact** | High (3) |
| **Inherent exposure** | **6** |
| **Owner role** | Programme Director |
| **Mitigation** | The workforce and industrial-base framings (WISH/SHY) are the durable ones across budget cycles, and they are the Increment 1 and Increment 3 revenue events. Each increment produces a standalone, revenue-capable product (PSDD §11), so the programme has a deliverable to sell at any point rather than only at the end. The pod model keeps the team in coherent units that are re-usable if the funding moves |
| **Contingency** | Reduce to the Increment 1 and Increment 3 pods — approximately 5.5 pods, 27 to 33 engineers — which is the smallest organisation that delivers a standalone product. The foundation is retained, because a programme that loses its foundation loses its ability to restart |
| **Trigger** | Two consecutive funding quarters with no new opportunity; a hypersonic programme cancellation in the sponsor's portfolio; a hiring freeze without an offsetting revenue event |
| **Residual exposure** | **4** (L=M 2, I=M 2). A durable framing reduces the probability; it does not remove the exposure |

### R-13 — Schedule risk of the 2027 validation event

| Field | Value |
|---|---|
| **Source** | PSDD §11 Phase 4 — "validation event: 2027 Maverick flight test" |
| **Category** | Programme / schedule |
| **Description** | The 2027 flight test falls inside the window in which Increment 4 is expected to deliver Pillars F and G. The programme therefore has a fixed public date at which some capability must be demonstrated, against a foundation that does not complete until the end of Increment 0. The failure modes are: (a) compressing the schedule in a way that compromises the ontology and the contract layer, which cannot be un-compromised later; (b) building a parallel "Maverick edition" with its own model, which creates a second digital thread; (c) missing the date and being measured against it |
| **Likelihood** | High (3) |
| **Impact** | High (3) |
| **Inherent exposure** | **9** |
| **Owner role** | Programme Director |
| **Mitigation** | A decision at the end of Increment 0 on whether the 2027 event requires the full platform or accepts a reduced configuration, taken while the architecture is still cheap to adjust. The design treats the event as a *design and data* event: the threat-model ingestion path, the `EngagementScenario` structure and the IF-2 scenario output can be exercised against 2027 data on the Increment 0 foundation. The one-ontology argument is protected by an explicit prohibition on a separate edition (see [`roadmap/increments.md`](roadmap/increments.md) §10) |
| **Contingency** | Deliver the reduced configuration: the scenario definition and the evidence chain for the 2027 flight, produced by the Increment 0 foundation in a CUI or unclassified configuration, with the threat-model lineage established but the full Pillar F capability deferred. The demonstration is scoped and labelled as what it is, and the platform claim is not overstated |
| **Trigger** | The Increment 0 exit review is more than 3 months behind; a request appears for "a quick Maverick-specific build"; the Increment 0 foundation scope is renegotiated downward; a stakeholder asks for a capability in Increment 0 that only Increment 4 delivers |
| **Residual exposure** | **6** (L=M 2, I=H 3). The date is immovable and the delivery is not fully in the programme's control |

### R-24 — Scope creep toward replacing fielded systems

| Field | Value |
|---|---|
| **Source** | PSDD §3.2 (out of scope) and §13 ("Explicit non-replacement posture for BMC3") |
| **Category** | Programme / scope |
| **Description** | A sponsor's or a user's request to add capability that crosses the out-of-scope line — a tactical display, a weapon interface, a flight-control hook. The failure mode is a slow accretion, each increment individually reasonable, that produces a platform with a larger accreditation surface, a larger export-control exposure and a different product than the one that was sold |
| **Likelihood** | Medium (2) |
| **Impact** | Medium (2) |
| **Inherent exposure** | **4** |
| **Owner role** | Chief Architect |
| **Mitigation** | The scope boundaries are written into the architecture ([`architecture/01-system-context.md`](architecture/01-system-context.md) §7) with a stated reason for each, so a request is evaluated against a written boundary rather than a recollection. `Interface` entities hold the ICD to fielded systems, so the integration is represented without the platform owning the interface. The Chief Architect owns the boundary and the programme director is informed of every request that touches it |
| **Contingency** | Refuse the increment-scope change and offer the closest in-scope alternative: a scenario definition delivered through IF-2 for the fielded system to consume, or a test campaign that demonstrates the fielded system's behaviour |
| **Trigger** | A requirement mentions a weapon interface, a fire-control solution or a tactical display; an architecture review is asked to approve a control path that did not exist in the design; a change request adds an entity type with a `classificationFloor` above `CUI` without an accreditation consequence analysis |
| **Residual exposure** | **2** (L=L 1, I=M 2). The boundary is explicit and the request volume is low |

## 4. Technical and delivery risks

### R-07 — Integration debt across pillars

| Field | Value |
|---|---|
| **Source** | Software delivery risk |
| **Category** | Technical / architecture |
| **Description** | Eight pillars and six foundation services, developed by separate pods against a shared ontology, will accumulate integration debt: bespoke interfaces that bypass the contract layer, direct access to another pillar's store, duplicated domain logic that drifts between the pillar and the ontology. The consequence is that the "one ontology" thesis becomes true only on paper, and the platform's cross-pillar queries stop being answerable |
| **Likelihood** | High (3) |
| **Impact** | High (3) |
| **Inherent exposure** | **9** |
| **Owner role** | Chief Architect |
| **Mitigation** | The contract layer and the event catalogue are the only sanctioned coupling; the subscription groups in `contracts/events/catalog.json` define exactly what each pillar may consume. [ADR-0002](adr/ADR-0002-json-schema-contracts-over-shared-libraries.md) removes the shared-library temptation. A cross-pillar architectural test in CI fails the build on a pillar importing another pillar's service or store. The cross-pillar query in Increment 5 (WP-5.4) is built early enough to expose debt while it is cheap to fix. The Ontology / Data pod owns the ontology and arbitrates type changes |
| **Contingency** | A cross-pillar integration debt register, reviewed at each increment gate, with a funded remediation plan and an explicit statement in the increment's exit report of which cross-pillar queries are answerable. The debt is disclosed with its size rather than absorbed |
| **Trigger** | Two or more pillars implement the same domain rule differently; a pillar requests a direct database connection to another pillar's store; the count of events in the `foundation` subscription group consumed by a pillar exceeds what its stated capability needs; a type change is made without the shared change-control path |
| **Residual exposure** | **4** (L=M 2, I=M 2). Integration debt is not eliminated by a contract layer; it is bounded and made visible |

### R-08 — Contract drift between schemas and services

| Field | Value |
|---|---|
| **Source** | Software delivery risk |
| **Category** | Technical / contracts |
| **Description** | The contract layer, the generated codecs and the service implementations drift apart. The failure is silent: a service accepts a payload the schema rejects, or rejects one the schema allows, and the discrepancy appears in production as an unexplained projection divergence |
| **Likelihood** | Medium (2) |
| **Impact** | High (3) |
| **Inherent exposure** | **6** |
| **Owner role** | Chief Architect |
| **Mitigation** | Codegen from a single source, with a CI staleness check that fails the build when the committed generated code differs from a fresh generation ([ADR-0002](adr/ADR-0002-json-schema-contracts-over-shared-libraries.md) GEN-2). The conformance fixtures are generated too and are a release gate for every service (GEN-10). Decode implies validate (GEN-4), so validation cannot be skipped in business logic. A published schema diff on every contract change (GEN-9). Closed enums with total decoding (GEN-5) so an unseen value fails loudly rather than defaulting |
| **Contingency** | Freeze the contract at the last verified version, revert the drifting service, and re-release against the pinned contract. The version pins in each service's release metadata make the revert a configuration change rather than a code change |
| **Trigger** | The codegen staleness check has been bypassed more than once in an increment; a conformance fixture is skipped in a pipeline; a service's schema version differs from the catalog version it claims; a bug report describes a validation error that the schema does not produce |
| **Residual exposure** | **4** (L=M 2, I=M 2). The mechanical enforcement is strong; the residual is in services that bypass the generated codec, which the architectural test catches but cannot entirely prevent |

### R-09 — Single-vendor lock-in

| Field | Value |
|---|---|
| **Source** | Software delivery risk |
| **Category** | Technical / supply chain |
| **Description** | The platform becomes dependent on one provider's identity, storage, orchestration or ML stack, so that a change of provider is a re-platforming rather than an adapter swap. In an accredited context the exposure is worse than usual, because the migration must be re-accredited |
| **Likelihood** | Medium (2) |
| **Impact** | Medium (2) |
| **Inherent exposure** | **4** |
| **Owner role** | Platform Lead |
| **Mitigation** | Rule P-1 of [ADR-0003](adr/ADR-0003-platform-agnostic-hybrid-deployment.md) prohibits cloud SDKs in domain code, enforced by a CI dependency-boundary check that scans transitive dependencies. All storage, identity and orchestration access is through ports with adapters. The platform runs on four deployment profiles, two of which have no cloud control plane at all, so an exit path is exercised continuously rather than theoretically. The contract layer means a partner can build an adapter without our code |
| **Contingency** | The adapters behind the ports are the migration surface. A provider change is an adapter rewrite, and the four-profile matrix provides an interim target while the rewrite happens |
| **Trigger** | A domain package acquires a cloud SDK import; a service's behaviour differs between two profiles for a reason other than a declared capability; a provider's proprietary feature is required to meet a performance target; more than 20% of the platform's runtime behaviour depends on one provider's extension |
| **Residual exposure** | **2** (L=L 1, I=M 2). The rule is enforced mechanically and the exit path is exercised |

### R-11 — M&S fidelity shortfall

| Field | Value |
|---|---|
| **Source** | PSDD §4.2 principle 4; PSDD §5.7 **G-3**, **G-4**; PSDD §12 KPI "model fidelity improvement per campaign" |
| **Category** | Technical / AI-ML |
| **Description** | The models the platform depends on — aero, thermal, plasma, CMC process, threat kinematic, engagement — do not achieve or maintain a fidelity sufficient to support the decisions being made with them. The consequence is that a platform whose central claim is test-coupled M&S produces confidently wrong answers, and the credibility damage is to the whole programme rather than to one model. The specific failure modes are: a model that was never scored and carries an invented number; a model whose envelope does not cover the regime in which it is used; and a model whose fidelity has decayed as new evidence has arrived |
| **Likelihood** | High (3) |
| **Impact** | High (3) |
| **Inherent exposure** | **9** |
| **Owner role** | Data and MLOps Lead |
| **Mitigation** | The fidelity registry is a foundation capability built in Increment 0 (WP-0.12), not a pillar feature added later, so the discipline is established before the first production model exists ([ADR-0008](adr/ADR-0008-model-card-and-fidelity-registry.md)). Every model carries provenance, a `FidelityScore` with an applicability envelope, and a model card, and a model without a complete card fails the release gate. C-004 is enforced as a hard precondition at the point of use. Out-of-envelope use is refused rather than clamped. Fidelity is recomputed automatically whenever new test evidence arrives, so it cannot silently decay. The approval workflow enforces separation of duties, so a model is not approved by its author. The envelope narrows automatically on new evidence — the platform gets safer as evidence accumulates |
| **Contingency** | Where a model type's fidelity cannot be established against the evidence available, the model is not admitted to a safety-relevant use and the capability that depends on it is delivered in an explicitly exploratory form, with the outputs marked `EXPLORATORY` and excluded from requirement verification evidence. Where a decision has already been taken on a model that is later found to be out of envelope, the affected outputs are identified — because every model-derived output records the model version, the fidelity at the time of use and the operating point — and are quarantined for review. The decision is revisited against the corrected evidence |
| **Trigger** | A model is in use with a `fidelity.overall` below its configured floor; a model has no `applicabilityEnvelope`; a model card is missing or incomplete; the fidelity improvement per campaign KPI fails to improve for two consecutive campaigns; two or more models in the same class have incomparable `method` values; a domain authority declines to approve a model for lack of evidence |
| **Residual exposure** | **6** (L=M 2, I=H 3). Fidelity is a judgement about a physical world, and the judgement can be wrong. The mitigation converts a silent error into a refusal or an escalation, but it cannot make the underlying physics correct |

### R-20 — Event log and projection divergence

| Field | Value |
|---|---|
| **Source** | Software delivery risk arising from [ADR-0001](adr/ADR-0001-event-sourced-foundation.md) |
| **Category** | Technical / data integrity |
| **Description** | A projection does not match the log state: an event was dropped, applied out of order, or applied with a different result than a replay would produce. The consequence is that the digital thread — the platform's product — is quietly wrong, and the error is not detectable by looking at the data, only by comparing it to the log |
| **Likelihood** | Medium (2) |
| **Impact** | High (3) |
| **Inherent exposure** | **6** |
| **Owner role** | Platform Lead |
| **Mitigation** | The log is the system of record, so divergence is recoverable rather than a data-loss event. A periodic reconciliation job compares the live projection against a replay of the log over a bounded window and reports any difference. Projection rebuild is a supported operation, not an emergency procedure. Replay determinism is a tested property (WP-0.3, acceptance criterion 3), verified across 100 runs |
| **Contingency** | Rebuild the affected projection from the log. During the rebuild, reads are served from the log directly at reduced performance, so the platform stays available while it is corrected. The affected window is disclosed and the divergence is traced to a cause before the rebuild is accepted |
| **Trigger** | The reconciliation job reports any difference; projection lag exceeds 60 s sustained; a rebuild produces a different state than the live projection; a consumer reports a missing or duplicated entity |
| **Residual exposure** | **2** (L=L 1, I=M 2). Recoverability is the mitigation, and it is a strong one |

### R-21 — Model drift undetected

| Field | Value |
|---|---|
| **Source** | Software delivery risk arising from [ADR-0008](adr/ADR-0008-model-card-and-fidelity-registry.md); PSDD §9 |
| **Category** | Technical / AI-ML |
| **Description** | A model's inputs change distribution and its predictions degrade, but nothing detects it, so a stale model produces confident wrong answers inside a safety-relevant decision. The platform's credibility depends on models being honest about their limits, and a single undetected drift episode destroys that trust more thoroughly than a model that never existed |
| **Likelihood** | Medium (2) |
| **Impact** | High (3) |
| **Inherent exposure** | **6** |
| **Owner role** | Data and MLOps Lead |
| **Mitigation** | Drift monitoring is part of the model card (section 9) and is a platform capability, not a per-model effort. The envelope narrows automatically on new evidence and use outside the envelope is refused, so the failure mode is a refusal rather than a wrong answer. A fidelity recomputation is triggered by every relevant test result. A score movement beyond the materiality threshold notifies the owner and the dependent pillars |
| **Contingency** | Automatic suspension of the model above the suspend threshold, with the dependent pillars notified and the outputs produced under the model identified and quarantined for review. The historical-output identification is possible because every model-derived output records the model version, the fidelity at the time of use and the operating point |
| **Trigger** | A model has had no fidelity recomputation in 90 days; the drift score crosses the investigate threshold for two consecutive periods; an envelope narrowing invalidates an existing downstream result; a model is used without a recorded operating point |
| **Residual exposure** | **3** (L=L 1, I=H 3). Drift detection is imperfect by nature; the residual impact is high because the domain is safety-relevant |

### R-22 — Ingestion throughput shortfall

| Field | Value |
|---|---|
| **Source** | PSDD §8 — "test data ingestion ≥ 10 GB/s burst (range support)" |
| **Category** | Technical / performance |
| **Description** | The ingest path does not sustain the required burst rate, so a large range campaign is delayed, buffered or partially rejected. The consequence is a test campaign whose data is incomplete, which undermines the campaign's value at exactly the moment it was most expensive to run |
| **Likelihood** | Medium (2) |
| **Impact** | Medium (2) |
| **Inherent exposure** | **4** |
| **Owner role** | Platform Lead |
| **Mitigation** | The ingest path is sharded by source and partition, so one tenant's burst does not starve another. Raw bytes go to the object store and the fabric carries only the envelope, which is orders of magnitude smaller than the payload — the 10 GB/s figure is a bytes target, not an append target. Back-pressure is explicit rather than silent: the source is throttled with a clear signal and data is never silently dropped. The throughput harness is a release gate (WP-0.7) |
| **Contingency** | A dedicated ingest partition for the affected range, with the shard count increased for the duration of the campaign. A partially ingested batch is quarantined rather than accepted with a partial record count, and the campaign is rescheduled rather than recorded incompletely |
| **Trigger** | Sustained throughput below 80% of target for 15 minutes; back-pressure events rising above 5% of batches; the per-partition ceiling being hit in a single range campaign; a rejected-record rate above 0.1% on a valid source |
| **Residual exposure** | **2** (L=L 1, I=M 2). The target is measured, sharded and gated |

### R-25 — Performance target unachievable at required fidelity

| Field | Value |
|---|---|
| **Source** | PSDD §8 — "Kill-chain Monte Carlo: 10k-run engagement batch < 4h on a dedicated partition" |
| **Category** | Technical / performance |
| **Description** | The Monte Carlo target is met only by reducing the model's fidelity, or the fidelity is met only by missing the target. The consequence is a compromise discovered late — a validated engagement analysis that cannot be run at the scale a programme question requires, or a fast analysis whose results do not survive scrutiny |
| **Likelihood** | Medium (2) |
| **Impact** | Medium (2) |
| **Inherent exposure** | **4** |
| **Owner role** | Platform Lead |
| **Mitigation** | The surrogate model is the designed answer, and the surrogate's fidelity envelope is published and enforced (WP-4.2). The dedicated partition is sized against the target, and the target is validated with a representative engagement from Increment 4 rather than first measured at delivery. The distinction between the high-fidelity model and the surrogate is explicit in the `EngagementScenario` and in the results summary |
| **Contingency** | Run the 10,000-run batch on the full model over a longer window, or run the surrogate with a widened sample. Whichever is used, the `resultsSummary` records which model and which fidelity produced it, so the compromise is visible in the artefact rather than in a footnote |
| **Trigger** | The measured batch time exceeds 3 hours at the target fidelity; the surrogate's envelope excludes the engagement region in question; a results summary cannot state the model version and fidelity that produced it |
| **Residual exposure** | **2** (L=L 1, I=M 2). The design anticipates the trade-off and records it |

### R-26 — Ontology type proliferation

| Field | Value |
|---|---|
| **Source** | Software delivery risk arising from [`architecture/02-ontology-model.md`](architecture/02-ontology-model.md) §7 |
| **Category** | Technical / ontology |
| **Description** | Pillar-specific types accumulate in the shared ontology — a `CmcLot`, an `EngineerRating`, a `ThreatTrack`. Each is individually reasonable. The cumulative effect is that the shared ontology stops being shared: the strike side and the shield side have separate vocabularies, the type count grows past what any consumer can reason about, and the type-floors and partition requirements multiply |
| **Likelihood** | Medium (2) |
| **Impact** | Medium (2) |
| **Inherent exposure** | **4** |
| **Owner role** | Chief Architect |
| **Mitigation** | The change-control path requires the raiser to state why an existing type plus an attribute cannot express the need, and the reviewer rejects the request if one can. An attribute that is meaningful across two or more pillars, or appears in three or more types, is promoted to a shared `$def` rather than duplicated. The registry version is bumped on every change, so growth is visible in the version history. The Ontology / Data pod owns the registry and arbitrates |
| **Contingency** | A consolidation pass at an increment gate: types with a single owning pillar and no cross-pillar use are folded back into their parent's `attributes`. The consolidation is a registry major-version change and is communicated with the compatibility rules of [ADR-0002](adr/ADR-0002-json-schema-contracts-over-shared-libraries.md) |
| **Trigger** | The entity type count exceeds 30; three or more change requests in an increment propose new types; a type is proposed with a single owning pillar and no cross-pillar consumer; a change request's stated justification is "it is different from the existing type" without a semantic argument |
| **Residual exposure** | **2** (L=L 1, I=M 2). The gate is procedural, and procedural gates are bypassed under pressure, but the version history makes the growth visible |

## 5. Security, compliance and accreditation risks

### R-10 — Classified-access latency

| Field | Value |
|---|---|
| **Source** | Software delivery risk arising from PSDD §2.1 **P7**; PSDD §13 (classification friction) |
| **Category** | Security / personnel |
| **Description** | Clearance processing and accreditation take longer than the hiring and onboarding plan assumes — 3–9 months for a clearance, longer for SCI, and longer still for a site accreditation. The consequence is that a pod forms with an insufficient cleared complement, cannot work on the content it was formed for, and the ramp is gated by the vetting system rather than by hiring |
| **Likelihood** | High (3) |
| **Impact** | High (3) |
| **Inherent exposure** | **9** |
| **Owner role** | Programme Director |
| **Mitigation** | Clearance processing starts on the day of the offer, not the day of the start date. Every pod's first 6–9 weeks of work is deliberately unclassified — CI pipeline, local profile, conformance harness, test tooling — which is most of the Increment 0 engineering work and is not a consolation prize. Unclassified work is not gated by vetting. A vetting capacity agreement is sought with the sponsoring organisation at programme formation. The cleared-workforce demand model (E-4) is run on the programme's own workforce from Increment 1, so the gap is measured rather than assumed |
| **Contingency** | Re-sequence the pods so that unclassified-capable work is done first and the classified work follows the vetting. Where a pod cannot obtain a cleared complement, its work is paired with a partner organisation that already holds one — the academic consortium and the prime partnerships. A pod that cannot be staffed is descoped, and the descope is disclosed rather than absorbed by the remaining engineers |
| **Trigger** | Any clearance outstanding for more than 120 days; a pod below 60% cleared at the midpoint of its first increment; a site accreditation not started 90 days before the planned site deployment; two or more vets failing in the same quarter |
| **Residual exposure** | **6** (L=M 2, I=H 3). Vetting throughput is outside the programme's control and the constraint is structural |

### R-16 — Multi-tenant isolation failure

| Field | Value |
|---|---|
| **Source** | Software delivery risk arising from [ADR-0007](adr/ADR-0007-classification-partitioning.md); PSDD §8 (multi-program tenancy) |
| **Category** | Security / confidentiality |
| **Description** | Content from one tenant or one programme becomes visible to another — through a query path that omits the tenant filter, a shared projection instance, a cache key that does not include the tenant, or an export that aggregates across tenants. The consequence is a confidentiality incident involving programme data, in a platform whose value proposition includes keeping programmes separate |
| **Likelihood** | Medium (2) |
| **Impact** | High (3) |
| **Inherent exposure** | **6** |
| **Owner role** | Security Lead |
| **Mitigation** | Tenant scoping is applied at the storage partition, not only in a query predicate — a credential does not span a partition, and the partition is determined by classification. The negative isolation suite attempts cross-partition and cross-tenant access across every service and every endpoint and asserts that all attempts fail; it is a release gate (WP-0.9, WP-0.3). Cache keys include the tenant. Every query result carries the tenant and the partition. A tenant-scoped API is the only supported surface |
| **Contingency** | Immediate tenant-scoped purge of any shared cache or derived index, which is a rebuildable artefact. A full tenant-scoped audit of the affected window using the audit ledger, which records every access with its tenant. Notification to the affected programmes follows the incident procedure, and the incident is not closed until the cause is identified and a test has been added to the isolation suite |
| **Trigger** | Any cross-tenant access appears in the audit ledger, regardless of whether it returned data; a cache key is changed without including the tenant; a service's projection instance is shared across tenants; the isolation suite is skipped in a release pipeline |
| **Residual exposure** | **3** (L=L 1, I=H 3). The impact remains catastrophic because the exposure is other programmes' classified content; the likelihood is low because the boundary is structural rather than conventional |

### R-17 — Supply-chain component compromise

| Field | Value |
|---|---|
| **Source** | PSDD §10 — "NGSH itself developed under CMMC L2+ with SBOM for all components" |
| **Category** | Security / supply chain |
| **Description** | A compromised dependency, a malicious build step or a substituted artefact enters the platform through the software supply chain. In an accredited product the consequence is not only a technical incident but a compromise of the accreditation itself |
| **Likelihood** | Low (1) |
| **Impact** | High (3) |
| **Inherent exposure** | **3** |
| **Owner role** | Platform Lead |
| **Mitigation** | An SBOM per build artefact, published with the artefact and retained for the version's life. Provenance attestations linking each artefact to its source commit, contract digests and codegen version. Reproducible builds, so a third party can rebuild and obtain the same digest — which is what makes the SBOM meaningful. Artefact signing with verification before deployment in any profile. Continuous dependency scanning plus a full SCA scan at each release. No cloud SDK in the domain layer, so the domain layer's SBOM contains no provider component whose behaviour is outside the accreditation boundary |
| **Contingency** | Roll back to the previous signed digest. The rollback is itself a promotion through the gates, so it is an exercised path rather than an untested one. Where a component is suspected compromised, the platform is rebuilt from source with the component removed or patched, and the artefact is re-signed and re-attested. Where the compromise is in the build pipeline rather than the component, the build environment is re-provisioned and every artefact since the last verified attestation is rebuilt |
| **Trigger** | A critical vulnerability with a known-exploited variant appearing in a transitive dependency; the reproducible-build check fails on an artefact; a signature verification fails in a deployment pipeline; an SBOM is missing from a published artefact; a licence or origin review flags a dependency |
| **Residual exposure** | **3** (L=L 1, I=H 3). Supply-chain compromise is a low-probability, high-impact event that no amount of process eliminates |

### R-19 — Edge node compromise or spoofed telemetry

| Field | Value |
|---|---|
| **Source** | Software delivery risk arising from [ADR-0006](adr/ADR-0006-edge-degraded-mode-and-reconciliation.md) |
| **Category** | Security / edge |
| **Description** | A compromised or malicious edge node submits fabricated measurements or observations into the digital thread. Because the edge is by design an untrusted component that only proposes, the failure mode is that fabricated proposals are accepted as facts, and a test result that never happened becomes part of the qualification evidence |
| **Likelihood** | Medium (2) |
| **Impact** | High (3) |
| **Inherent exposure** | **6** |
| **Owner role** | Edge and Field Lead |
| **Mitigation** | The edge holds no fabric write credential; it proposes and every proposal is validated as any other write's, including the constraint set and the classification rules. Node identity is per-site and revocable, so a compromised node can be excluded from the fabric. The reconciliation rules make a fabricated event detectable when it conflicts with a concurrent genuine one, and quarantine every undecidable conflict rather than accepting it. The audit ledger records the originating node on every edge-originated event, so the provenance of any edge claim is reconstructable. Site accreditation and physical security are part of the site model |
| **Contingency** | Revoke the node's identity, which excludes it from the fabric. Quarantine and review the events it proposed within a bounded window, using the `edge.nodeId` marker on each event. If an immutable `TestResult` was fabricated, the qualification evidence is re-validated by physical re-test — the platform cannot retract a fabrication, only identify it, which is exactly why the escalation path exists |
| **Trigger** | An edge node proposes a result for a test article and campaign that another node also proposed; the same edge node shows an anomalous event rate; a node's clock offset changes abruptly; an edge-originated event fails a constraint that fabric-originated events of the same shape pass |
| **Residual exposure** | **3** (L=L 1, I=H 3). Physical security at the site remains the primary control and it is outside the platform |

### R-23 — Key management and HSM unavailability

| Field | Value |
|---|---|
| **Source** | Software delivery risk arising from [`architecture/04-security-architecture.md`](architecture/04-security-architecture.md) §8 |
| **Category** | Security / cryptography |
| **Description** | The design assumes a locally operable HSM in each zone, because no cloud KMS is reachable from an IL6 annex or an edge appliance. If an HSM is not available in a zone, the zone cannot hold P-R or P-S keys, and the classification content it is meant to hold cannot be placed there. The consequence is that a required zone cannot be stood up |
| **Likelihood** | Medium (2) |
| **Impact** | High (3) |
| **Inherent exposure** | **6** |
| **Owner role** | Security Lead |
| **Mitigation** | The HSM requirement is a programme dependency identified in Increment 0 (WP-0.10, WP-0.11) rather than discovered at deployment. The key classes are separated so that a zone that cannot obtain an HSM can still operate with software key stores at P-U and P-C, which is the zone's expected content in the early increments. The key-recovery procedure is documented and exercised annually. The `ledgerFormatVersion` mechanism exists to carry a future hash migration without a re-architecture |
| **Contingency** | Operate the affected zone at a lower partition set until an HSM is available, with the restricted content held centrally under a different accreditation. Sequence the rollout so that the CUI zones come first and the IL6 annex follows its HSM, which is the natural order anyway because P-R content arrives with Increment 4 |
| **Trigger** | An HSM procurement is not initiated within 60 days of the programme start; a zone's key ceremony has no scheduled date; a key-recovery rehearsal is not performed within 12 months; a software key store is proposed for a SECRET-classified partition |
| **Residual exposure** | **3** (L=L 1, I=H 3). The mitigation reduces the coupling but does not remove the dependency on equipment outside the programme's control |

## 6. Workforce and organisational risks

### R-14 — Key-personnel concentration

| Field | Value |
|---|---|
| **Source** | Software delivery risk arising from the pod model |
| **Category** | Workforce / continuity |
| **Description** | A small number of individuals hold knowledge that exists nowhere else — the reconciliation merge rule, the canonicalisation function, the partition routing, the fidelity scoring methods, the policy bundle semantics. If one of them leaves, the corresponding capability stops being maintainable, and the recovery is slow because the knowledge was never written down |
| **Likelihood** | Medium (2) |
| **Impact** | High (3) |
| **Inherent exposure** | **6** |
| **Owner role** | Programme Director |
| **Mitigation** | Every pod has a designated deputy from the day it forms (composition rule CR-5 in [`staffing.md`](staffing.md)), and the deputy runs the pod's on-call and its reviews. The highest-risk knowledge — the canonicalisation function, the merge rule, the partition routing, the policy bundle — is written as a specification with a named owner, and the specification is in the repository rather than in an inbox. Each of these has a paired implementation review, so a second engineer has read it critically. The ADRs and the architecture documents exist precisely to externalise this class of decision |
| **Contingency** | The named deputy assumes ownership with the specification as the handover artefact, supported by a time-boxed pairing period with a departing engineer where the departure allows it. If the departure is abrupt, the specification is the recovery mechanism and the capability is frozen — no changes — until a second engineer is onboarded |
| **Trigger** | Any individual holding a sole-owner capability resigns or is reassigned; a pod has no deputy after a team change; a capability specification has not been reviewed by a second engineer in 12 months; the bus factor for the policy bundle, the canonicalisation function or the merge rule is one |
| **Residual exposure** | **3** (L=L 1, I=H 3). Some knowledge is irreducibly personal; the deputy rule and the written specifications bound the exposure |

### R-18 — Cleared-workforce pipeline shortfall

| Field | Value |
|---|---|
| **Source** | PSDD §2.1 **P7** — "Cleared, skilled workforce supply does not track classified production demand" (WISH; JHTO workforce studies) |
| **Category** | Workforce / market |
| **Description** | The cleared, skilled labour market does not grow with classified production demand, so the programme cannot hire the domain engineers it needs and the industrial base it serves cannot hire either. This is the problem Pillar E exists to address, and the programme is simultaneously a victim of it. The consequence is a slow ramp, a programme that is staffed by generalist engineers who lack domain depth, and a product whose credibility depends on domain authority the programme does not have |
| **Likelihood** | High (3) |
| **Impact** | High (3) |
| **Inherent exposure** | **9** |
| **Owner role** | Programme Director |
| **Mitigation** | The workforce demand model (E-4) quantifies the gap by region and trade, and is run on the programme's own workforce from Increment 1 — so the constraint is measured, not asserted. The academic consortium (PSDD §14) and the DASH-MOT and HAMTC ecosystems are engaged as staffing channels, not only as data sources. Domain experts are engaged fractionally as advisors and reviewers with a day-per-week allocation, which is obtainable where a full-time hire is not. The platform is designed so that domain experts are *users* rather than authors: the model card and the applicability envelope let a domain expert own a model without writing the pipeline. The WISH/SHY framings are the durable ones across budget cycles (PSDD §13) |
| **Contingency** | Reduce the domain depth the programme attempts and increase the reliance on partner organisations for the domain work, with the platform providing the integration and the evidence. Be explicit in the increment reports about which results rest on programme-authored domain content and which rest on partner content. The product is still valuable as the integration and evidence layer even where it is not the source of the domain knowledge |
| **Trigger** | Two or more unfilled cleared domain roles after 120 days; the consortium partner count falling below three; a competitor announcing a large cleared-hypersonics hiring programme; E-4 reporting a widening gap for the trades the programme depends on |
| **Residual exposure** | **6** (L=M 2, I=H 3). The market constraint is real, national, and not within the programme's power to change |

## 7. Data, rights and environment risks

### R-12 — Data rights and intellectual property

| Field | Value |
|---|---|
| **Source** | Software delivery risk arising from PSDD §10 (ITAR/EAR) and §13 (prime data-sharing) |
| **Category** | Data / rights |
| **Description** | The data the platform needs is subject to contractual, export-control or proprietary constraints that prevent its use for a purpose the programme wants. Specifically: prime process data used for characterisation may not be used to build a commercial product; academic partners may not receive content that a prime considers proprietary even after sanitisation; and a derived model trained on restricted data may not be distributed |
| **Likelihood** | Medium (2) |
| **Impact** | High (3) |
| **Inherent exposure** | **6** |
| **Owner role** | Business Development Lead |
| **Mitigation** | The one-way extract pipeline with a manifest, a named reviewer and an anchored record establishes the mechanism for using data without transferring ownership ([ADR-0007](adr/ADR-0007-classification-partitioning.md)). `Part.exportControlled` and `Supplier.exportControlled` carry the jurisdiction flag, so the export gate operates at the record level rather than on a judgement call. The citizenship rule in the PDP gates export-controlled content independently of clearance. Model artefacts inherit the classification of their evidence, so a model trained on restricted data cannot be distributed into a lower partition. Data-rights terms are negotiated into the teaming agreements before the data arrives, not after |
| **Contingency** | Use synthetic or government-owned data for the affected capability, marked as such in `Provenance.source`, and restrict the commercial claim accordingly. Where a specific partner's data is the only source for a specific result, the result is delivered under the partner's terms rather than being published as a platform capability. The sanitized-extract profile for that view is renegotiated rather than worked around |
| **Trigger** | A teaming agreement reaching the data-rights schedule and the counsel flagging a restriction; a partner withdrawing data after an extract; the guard's transformation rules being rejected for a specific view; a request to distribute a model whose evidence is export-controlled |
| **Residual exposure** | **4** (L=M 2, I=M 2). The mechanism is sound; the underlying commercial terms are outside the programme's control |

### R-15 — Test-environment scarcity

| Field | Value |
|---|---|
| **Source** | PSDD §2.1 **P5** — "National hypersonic test enterprise is fragmented; M&S is not test-coupled; designs iterate on scarce flight tests" (Atlantic Council; GAO) |
| **Category** | Data / environment |
| **Description** | Range slots, wind tunnel hours, sled campaigns and sled-track time are scarce, contested between programmes, and scheduled months or years ahead. The consequence is that campaigns are delayed, campaigns are accepted with less instrumentation than they need, and the programme cannot obtain the evidence required for a flight demonstration on the schedule it has committed to |
| **Likelihood** | High (3) |
| **Impact** | High (3) |
| **Inherent exposure** | **9** |
| **Owner role** | Pillar G Lead |
| **Mitigation** | The virtual test range (G-1) exists to substitute for physical tests, and the substitution is measured rather than asserted: the acceptance criterion is that ≥ 10 physical slots are allocated to a virtual campaign with a ≥ 7-in-10 convergence rate. The campaign digital twin (G-2) models capacity, telemetry coverage and instrumentation availability, so a slot is requested with a feasibility assessment rather than optimistically. B-3 makes test capability visible across organisations, which is the precondition for cross-DoD scheduling optimisation. The MPS planning for the 2027 event is made with the constraint already applied rather than discovered late |
| **Contingency** | Shift the evidence strategy toward coupon, material and ground testing that does not consume scarce slots, and use the virtual range for the design-space exploration that would otherwise have consumed them. Sequence the campaign plan so that the slots that are genuinely scarce — flight — are reserved for the questions that only flight can answer, with everything else displaced to the virtual or the coupon level. If a slot is lost, the affected requirement's verification status becomes explicitly `PARTIAL` rather than being quietly met by weaker evidence |
| **Trigger** | A requested slot being unavailable by more than one quarter; the virtual-to-physical convergence rate falling below 7 in 10; telemetry coverage proving inadequate after instrumentation is fixed; the programme competing with another programme for the same range window |
| **Residual exposure** | **6** (L=M 2, I=H 3). Scarcity is physical and shared. The virtual range reduces the dependence; it does not remove it for the evidence that only a range can produce |

## 8. Aggregate exposure profile

### 8.1 By category

| Category | Inherent | Residual | Retired | Critical risks |
|---|---|---|---|---|
| Programme and political | 50 | 32 | 18 | 2 |
| Technical and delivery | 52 | 27 | 25 | 2 |
| Security, compliance and accreditation | 30 | 18 | 12 | 1 |
| Workforce and organisational | 15 | 9 | 6 | 1 |
| Data, rights and environment | 15 | 10 | 5 | 1 |
| **Total** | **162** | **96** | **66** | **7** |

### 8.2 Observation

| Observation | Detail |
|---|---|
| The technical risks are the most mitigable | The technical category carries the largest inherent exposure and the largest reduction, because the mitigations are funded engineering work inside the programme's control — codegen, conformance gates, isolation suites, replay determinism |
| The residual is concentrated in things outside the programme's control | Access approvals (R-02, R-04, R-10), physical scarcity (R-15), the labour market (R-18), budget cycles (R-03, R-06) and national priorities (R-13). No amount of engineering retires these. The programme's response to them is sequencing and framing, not engineering |
| Every critical risk has a contingency that is an architectural property rather than an activity | The programme's design is deliberately shaped so that the worst cases are absorbed by the architecture: the log makes divergence recoverable, partitioning makes tenancy failure structural, the envelope makes model drift a refusal, the guard makes academic sharing safe. This is the intended reading of the architecture documents under stress |

### 8.3 Risks with no technical mitigation

| Risk | Why no technical mitigation exists | Programme response |
|---|---|---|
| R-02, R-04 | Data access is granted by authorities outside the programme | Sequencing (Pillar E first), framing (complement not replace), relationship-building from Increment 1 |
| R-03, R-06, R-13 | Budget and national priorities | Standalone revenue-capable products per increment (PSDD §11), industrial-base and workforce framings, early decision on the 2027 event scope |
| R-10, R-18 | Vetting throughput and the cleared labour market | Start clearance processing on the offer date; design the first 6–9 weeks of every pod to be unclassified; engage domain experts fractionally and via the consortium |
| R-15 | Range capacity is physical | Virtual substitution with measured convergence; sequence slots toward the questions only a range can answer |
| R-12 | Commercial and export-control terms | Negotiate before the data arrives; maintain the sanitized-extract mechanism as the alternative path |
| R-17, R-19, R-23 | Physical and supply-chain security | Reproducible builds, signed artefacts, node revocation, HSM procurement as an early programme dependency |

## 9. Review, ownership and escalation

### 9.1 Review cadence

| Review | Frequency | Attendees | Output |
|---|---|---|---|
| Risk review | Monthly | Programme Director, Chief Architect, Security Lead, pod leads | Updated exposures; trigger checks; mitigation status |
| Architecture review board | Per increment, plus on any proposed ADR | Platform, Security, Ontology and one domain authority | ADR decisions; supersessions |
| Programme board | Quarterly | Programme Director, sponsor, Chief Architect, Security Lead | Critical and high risks; escalations; funding decisions |
| Security review | Monthly | Security Lead, Service Lead, embedded security engineers in each pod | Policy bundle changes; partition changes; obligation coverage |
| Trigger sweep | Continuous, automated | — | Trigger conditions checked by pipeline and by the observability stack; breaches raise to the monthly review within one working day |

### 9.2 Escalation thresholds

| Condition | Action |
|---|---|
| A critical risk's trigger fires | The owner notifies the programme board within one working day. The contingency is exercised, not merely reviewed |
| A critical risk's residual exposure rises above 6 | Escalated to the sponsor with a funded remediation proposal or an explicit acceptance request |
| Three or more risks in the same category move a band in one quarter | A systemic review of that category is convened. Three movements in one category indicate a design or plan problem, not three independent problems |
| Any risk's mitigation is unfunded | The risk is escalated to the programme board for funding. An unfunded mitigation is an assumed mitigation and is scored as if the risk were unmitigated |
| A risk materialises | The contingency is executed, the incident is written up, and the register records the realised exposure against the forecast. The forecast error is itself reviewed |

### 9.3 Ownership rules

| Rule | Detail |
|---|---|
| Owner roles must exist | Every owner role in this register maps to a role in the staffing model ([`staffing.md`](staffing.md)). An owner role that does not exist is an orphan risk and is escalated at the quarterly board |
| No risk is owned by a project | A project ends; a risk does not. Ownership sits with a pod or a programme role that persists across increments |
| Residual exposures are re-scored | A residual score is only valid while the mitigation is in place and verified. A mitigation that is removed, deferred or found not to work reverts the score to the inherent exposure |
| New risks are added, not edited in | A risk's inherent exposure is a forecast at the time of raising. A materially new understanding is a new risk with a cross-reference, so the register shows how the programme's understanding changed |
| Retired is not the same as closed | A retired risk stays on the register with its mitigation and its re-scored residual, for at least one increment, so the register remains an audit trail |

## 10. References

**PSDD:** §1 (dual-mission platform; the platform's role), §2.1 **P5** (fragmented test enterprise, scarce flight tests), §2.1 **P7** (cleared workforce supply), §2.2 (mission need), §3.2 (out of scope — non-replacement), §4.1 (concept), §4.2 (design principles), §5 (pillars and capabilities), §5.5 (Pillar E workforce pipeline), §6.3 (data governance — ITAR/EAR partitioning, sanitized extracts), §7 (IF-1..IF-7), §8 (Availability, Performance, Scalability, Modularity, AI/ML, Auditability), §9 (AI/ML governance), §10 (Security and Compliance Architecture; SBOM), §11 (phasing; the 2027 validation event; the standalone-product rule), §12 (KPIs), §13 (the six programme risks carried into this register), §14 (teaming strategy).

**Contracts:** `contracts/ontology/registry.json` (the constraints whose enforcement underpins R-16, R-19 and R-21), `contracts/events/catalog.json` (the subscription groups whose enforcement underpins R-07), `contracts/events/event-envelope.schema.json` (the envelope whose `edge` block underpins R-19).

**Architecture:** [`architecture/01-system-context.md`](architecture/01-system-context.md) §8 (the ten architectural invariants, which are the mitigations for several of these risks), [`architecture/02-ontology-model.md`](architecture/02-ontology-model.md) §7 (the change-control path that mitigates R-26), [`architecture/04-security-architecture.md`](architecture/04-security-architecture.md) §13 (the known security gaps SG-1 to SG-8, each of which is a risk source), [`architecture/05-deployment-architecture.md`](architecture/05-deployment-architecture.md) §6 (the degraded-mode behaviour that mitigates R-19).

**ADRs:** all eight in [`../adr/`](adr/README.md).

**Planning:** [`roadmap/increments.md`](roadmap/increments.md) §10 (the 2027 validation event position behind R-13), [`roadmap/work-packages.md`](roadmap/work-packages.md) §12 (the critical path behind R-13 and R-07), [`staffing.md`](staffing.md) §8–§9 (the ramp-up and clearance constraints behind R-10, R-14 and R-18).
