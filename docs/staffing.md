# NGSH Staffing Model

## Purpose

This document specifies how the NGSH programme is staffed. It defines the pod model, the pod types, the rules for composing a programme from pods, three reference organisations at approximately 25, 60 and 120 engineers, the ramp-up sequencing, and the cleared-workforce constraints from PSDD §2.2 P7 and §5.5 that constrain who can be hired and how quickly. It exists because the programme must scale without re-planning, and because the programme's own workforce constraint — cleared, skilled people — is one of the problems it is built to solve.

## Contents

1. [Why pods](#1-why-pods)
2. [Pod types](#2-pod-types)
3. [Pod composition rules](#3-pod-composition-rules)
4. [Composing a programme](#4-composing-a-programme)
5. [Reference organisation — ~25 engineers](#5-reference-organisation--25-engineers)
6. [Reference organisation — ~60 engineers](#6-reference-organisation--60-engineers)
7. [Reference organisation — ~120 engineers](#7-reference-organisation--120-engineers)
8. [Ramp-up sequencing](#8-ramp-up-sequencing)
9. [Cleared-workforce constraints](#9-cleared-workforce-constraints)
10. [Recruiting and retention](#10-recruiting-and-retention)
11. [Cost and availability](#11-cost-and-availability)
12. [References](#12-references)

## 1. Why pods

| Aspect | Model |
|---|---|
| Unit of composition | A pod of 6–9 engineers with a single accountable lead |
| Unit of scaling | Adding pods, not stretching pods. A pod at 9 engineers is at capacity; a 10th engineer makes it worse, not better |
| Unit of planning | Work packages with acceptance criteria, assigned to a pod |
| Unit of accountability | A pod owns a coherent slice of capability end to end — design, implementation, test, documentation and operational handover |
| Why not individuals | The platform's work is highly interdependent: the contract layer, the log, the partitioning and the reconciliation rules cross every service. Individual assignment produces integration debt (R-07) |
| Why not larger teams | Above about 12 engineers, the coordination overhead of a single team exceeds the delivery capacity gain. The coordination cost scales worse than linearly, and the failure mode of a large team is a subgroup that stops talking to another subgroup |
| Why not smaller teams | Below about 5 engineers, there is no one to cover the on-call, the review and the cross-cutting responsibilities that a classified, on-call platform requires |

**The scaling property.** The whole point of the pod model is that the programme can be scaled by adding pods. Each pod has a defined composition, a defined set of skills and a defined integration contract with the other pods — the contract layer and the event catalogue. Adding a pod does not require re-planning, and removing one does not strand work.

## 2. Pod types

Seven pod types. Each has a distinct mission and a distinct skill mix.

| Pod type | Mission | Primary disciplines | Typical size |
|---|---|---|---|
| **Platform** | The event log, the service runtime, deployment, CI/CD, observability, performance, the console shell | Distributed systems, Go, SRE, some frontend | 7–9 |
| **Ontology / Data** | The registry, the schema layer, codegen, the graph projection, the data stores, the query engines | Data modelling, Go, Python, graph and query internals | 7–8 |
| **Security & Compliance** | The PDP, the audit ledger, partitioning, the guard, identity, and the accreditation evidence package | Security engineering, identity, compliance, some SRE | 6–8 |
| **Pillar-X** | The domain capabilities of one pillar: E, B, C, D, F, G, H or A | Domain engineers, systems engineers, software engineers, test engineers | 7–9 |
| **Test & Qualification** | The conformance suites, the fault-injection harness, the seeded-tamper suite, the isolation tests, the qualification evidence | Test engineering, quality engineering, some systems engineering | 6–8 |
| **MLOps** | The model lifecycle, training pipelines, inference serving, the fidelity registry implementation, drift monitoring | ML engineering, data engineering, some platform | 6–8 |
| **Edge / Field** | The edge agent, the site appliance, field integration, site deployment, site accreditation support | Systems, embedded, SRE, field engineering | 6–9 |

### Pod mission statements

| Pod | Owns | Does not own |
|---|---|---|
| Platform | The append path, the log, the broker, the build pipeline, the deployment profiles, the observability stack | Domain semantics |
| Ontology / Data | The registry, the contract layer, the codegen, the graph projection, the store topology, the query engines | Authorization policy |
| Security & Compliance | The PDP and PEP library, the audit ledger, the partitioning model, the guard, the identity integration, the evidence package | The services it protects; it defines and verifies their controls but does not implement their domain logic |
| Pillar-X | The domain capability, its domain models, its workflows and its user experience | The foundation it consumes |
| Test & Qualification | The verification strategy, the test assets, the qualification evidence, the release gates | The code under test |
| MLOps | The model lifecycle, the training and serving pipelines, the fidelity registry, the drift monitoring | The domain use of a model's output |
| Edge / Field | The edge agent, the site appliance, the site integration, the site rollout | The site network, the site accreditation decision |

## 3. Pod composition rules

These rules are what make a pod a pod. They are composition rules, not capacity rules, and they are not negotiable under schedule pressure.

| # | Rule | Rationale |
|---|---|---|
| CR-1 | **Security is embedded, not a silo.** Every pod has at least one engineer with the security responsibility for its own work — threat modelling, classification handling, secure defaults, and the review of its own changes. The Security & Compliance pod leads the cross-cutting controls; it does not perform per-change review for the other pods | A central security team cannot review the volume of change a twelve-pod programme produces. Review that is a queue is not review. The embedded engineer has the context; the central pod has the standard |
| CR-2 | **Every pillar pod includes a systems engineer.** Not a software engineer who plays at systems engineering. A pillar pod owns the requirement decomposition, the interface definition and the integration | The failure mode of an MBSE and digital-thread programme is a digital thread that does not match the engineering. The systems engineer is the check on that |
| CR-3 | **Every pillar pod includes a test engineer.** The test engineer is a member of the pod, not a downstream customer of it. They write the pod's tests, own the pod's verification evidence, and have a veto on the pod's exit | Verification produced by a separate downstream team arrives after the design decision it should have informed |
| CR-4 | **Every pod has a named lead who is accountable for delivery, not for review.** The lead is a working engineer with a smaller individual load | A lead who reviews everything is a bottleneck. The lead is accountable for the pod's acceptance criteria |
| CR-5 | **Every pod has a designated deputy.** The deputy can run the pod's on-call and its reviews. This is the mitigation for key-personnel concentration (R-14) | A platform with no deputies has single points of failure at the level of the individual |
| CR-6 | **Pods do not share engineers across increments.** An engineer is in one pod for the duration of an increment. Context transfer is a real cost and it is paid at the increment boundary, not hidden | Shared engineers are how institutional knowledge becomes a bottleneck |
| CR-7 | **The pod reviews its own work before it is presented.** The pod holds an internal review against the acceptance criteria before the increment gate | Quality at the pod level is cheaper than quality at the gate level |
| CR-8 | **Every pod has a cleared engineer who can hold the highest classification the pod touches.** For pods touching P-R or P-S content, this is a hard requirement on the pod's composition, not a nice-to-have | Clearance processing is a long lead time. Discovering at pod formation that three of seven engineers cannot hold the required clearance reshapes the plan at exactly the wrong moment |

### Standard pod composition

A typical 7-engineer pillar pod:

| Role | Count | Notes |
|---|---|---|
| Pod lead | 1 | Senior engineer; 60% individual capacity |
| Systems engineer | 1 | Requirement decomposition and interface definition |
| Software engineers | 2–3 | The delivery capacity |
| Test engineer | 1 | In-pod verification and evidence |
| Security engineer (embedded) | 1 | Classification handling, threat modelling, secure defaults |
| Platform / data engineer | 0–1 | Shared with the Platform or Ontology pod where the work is specialised |

A typical 7-engineer platform pod swaps the systems engineer for a second software engineer and adds an SRE.

## 4. Composing a programme

### 4.1 The rules

| # | Rule |
|---|---|
| 1 | The programme is a set of pods. Every pod is fully staffed from the start of its increment. A half-staffed pod is worse than no pod, because it produces work that cannot be completed |
| 2 | The reference compositions below are the starting point. They scale by adding whole pods of the same type, or by adding a pillar pod for a new pillar |
| 3 | A pod's size within a range is set by the increment's workload, not by a preference for large or small teams |
| 4 | The order of pod formation follows the increment's critical path. Pods on the critical path are formed first, because their onboarding and clearance lead time is longest |
| 5 | Every increment's pod set has at least one Test & Qualification pod and at least one Security & Compliance pod. These are not optional at any scale |
| 6 | The Edge / Field pod's size is driven by the number of pilot sites in parallel, and the Security & Compliance pod's size is driven by the number of accreditation packages in flight |

### 4.2 The composition worked

| Increment | Platform | Ontology/Data | Security | Pillar | Test | MLOps | Edge | Total |
|---|---|---|---|---|---|---|---|---|
| 0 | 1 | 1 | 1.5 | 0.5 | 0.5 | — | 0.5 | 5.0 |
| 1 | 0.5 | 0.5 | 1 | 3 | 0.5 | — | — | 5.5 |
| 2 | 0.5 | 1 | 0.5 | 4.5 | 1 | 1 | — | 8.5 |
| 3 | — | 0.5 | 0.5 | 3.5 | 0.5 | 0.5 | — | 5.5 |
| 4 | 0.5 | 1 | 1 | 6 | 1 | 1.5 | 0.5 | 11.5 |
| 5 | 1 | 1.5 | 1 | 3 | 1 | 0.5 | — | 8.0 |

Half pods are fractional allocations of a pod that is shared between two increments or two work streams. A 0.5 pod means a pod with fewer than six engineers, which is outside the composition rule; in practice, a 0.5 allocation means one pod split across two work packages with a lead covering both, and that arrangement is used only where the two work packages share a lead.

## 5. Reference organisation — ~25 engineers

**Shape.** 4 to 5 pods. Optimised for the foundation and the Pillar E revenue event, not for breadth.

| Pod | Type | Size | Primary assignment |
|---|---|---|---|
| Platform Core | Platform | 7 | Event log, broker, CI/CD, deployment, observability |
| Ontology and Data | Ontology / Data | 7 | Registry, contract layer, codegen, graph projection |
| Security and Compliance | Security & Compliance | 6 | PDP, audit ledger, partitioning, guard, identity |
| Pillar E and A | Pillar-X | 7 | E-1..E-5 plus the A-1 and A-3 first slice |
| — | — | **27** | |

**Coverage.** Increment 0 in full, then Increment 1. The programme's first revenue event (Pillar E under a WISH-type OTA) is delivered. Pillars B through H are represented by the shared foundation rather than by dedicated pods.

**What this organisation cannot do.**

| Constraint | Consequence |
|---|---|
| No MLOps pod | The first production model cannot be brought into service under the rules in [ADR-0008](adr/ADR-0008-model-card-and-fidelity-registry.md). The characterisations in Increment 2 must be delivered with a fractional MLOps allocation from the Ontology pod, which is a genuine quality risk on the fidelity score |
| One pillar pod | Only one pillar is in flight. The 2027 validation event capability cannot be delivered in parallel with Pillar E |
| No dedicated Test & Qualification pod | Verification is embedded in each pod, which satisfies rule CR-3, but the cross-cutting suites — the fault-injection harness, the seeded-tamper suite, the isolation matrix — have no home and will be built late and badly |
| One embedded security engineer per pod | The accreditation evidence package competes with feature work for the Security pod's capacity, because the SEC pod is also the one writing the evidence |

**What this organisation is good at.** It is good at proving the foundation and the first revenue event. The programme's thesis — one ontology, two mission sides — is demonstrated at the Pillar E scale, and the physical partitioning, the audit ledger and the edge agent are all real rather than aspirational.

**Critical scaling advice.** From 25 engineers, the highest-value addition is not another pillar pod. It is a **Test & Qualification pod and an MLOps pod**. The programme's largest quality risks (R-07 integration debt, R-08 contract drift, R-11 fidelity shortfall) are all verification risks, and they are cheap to retire with verification capacity and expensive to retire without.

## 6. Reference organisation — ~60 engineers

**Shape.** 8 to 9 pods. Two pillars in flight at once, with the foundation and the verification function properly staffed.

| Pod | Type | Size | Primary assignment |
|---|---|---|---|
| Platform Core | Platform | 8 | Log, broker, pipeline, deployment, observability |
| Platform Services | Platform | 7 | Ingest service, adapters, console, client library |
| Ontology and Data | Ontology / Data | 7 | Registry, codegen, graph projection, stores |
| Security and Compliance | Security & Compliance | 7 | PDP, audit ledger, partitioning, guard, identity, evidence |
| Pillar E and A | Pillar-X | 7 | E-1..E-5, A-1, A-3 |
| Pillar B and C | Pillar-X | 8 | B-1..B-4, CR-1..CR-4 |
| Test and Qualification | Test & Qualification | 7 | Conformance, fault injection, seeded tamper, isolation matrix, evidence |
| MLOps | MLOps | 6 | Model lifecycle, fidelity registry, drift monitoring |
| Edge and Field | Edge / Field | 6 | Edge agent, site rollout, site accreditation support |
| — | — | **63** | |

**Coverage.** Increment 0 and Increment 1 in full, Increment 2 with B and C running together, and the foundation's verification function properly resourced. Increment 3 (D and H) and Increment 4 (F and G) follow, with the pillar pods converted in sequence.

**What this organisation can do.**

| Capability | Enablement |
|---|---|
| Two pillars in parallel | Pillar pods are converted rather than created |
| The fault-injection harness is a first-class asset | The Test and Qualification pod owns it, with the Edge and Field pod as the consumer |
| The 2027 validation event capability is developed in parallel with the Pillar E revenue event | The second pillar pod and the MLOps pod make the reduced configuration credible |
| The accreditation evidence package is produced continuously, not at the end | The Security pod is staffed for the evidence, not only for the controls |
| Field rollout runs in parallel with feature development | The Edge and Field pod is dedicated to it |

**What this organisation still cannot do.**

| Constraint | Consequence |
|---|---|
| No second Security & Compliance pod | The P-R partition accreditation and the P-S work compete with the CUI evidence package |
| No dedicated infrastructure / site reliability function | Site reliability for the pilot sites falls on the Edge and Field pod, which is also doing the software |
| Clearance processing throughput | At 60 engineers, roughly 40 will need a clearance to work on CUI content. If the processing throughput is below that, the ramp is gated by the vetting system, not by hiring |

## 7. Reference organisation — ~120 engineers

**Shape.** 15 to 17 pods. Four pillars in flight, a dedicated platform organisation, and separated security and verification functions.

| Pod | Type | Size | Primary assignment |
|---|---|---|---|
| Platform Core | Platform | 9 | Log, broker, sequencing, replay, performance |
| Platform Services | Platform | 8 | Ingest, adapters, reconciliation, console |
| Platform Infrastructure | Platform | 8 | Deployment profiles, SRE, observability, capacity, cost |
| Ontology and Data | Ontology / Data | 8 | Registry, codegen, graph projection, stores, query |
| Security Engineering | Security & Compliance | 8 | PDP, PEPs, partitioning, guard, identity |
| Security Compliance and Evidence | Security & Compliance | 7 | Accreditation packages, audit operations, verification reports, policy |
| Pillar E and A | Pillar-X | 8 | E-1..E-5, A-1, A-3 |
| Pillar B | Pillar-X | 8 | B-1..B-4 |
| Pillar C | Pillar-X | 8 | CR-1..CR-4 |
| Pillar D and H | Pillar-X | 8 | D-1..D-3, H-1..H-3 |
| Pillar F | Pillar-X | 9 | F-1..F-6 |
| Pillar G | Pillar-X | 8 | G-1..G-4 |
| Test and Qualification | Test & Qualification | 8 | Conformance, fault injection, isolation matrix, qualification |
| MLOps | MLOps | 8 | Model lifecycle, fidelity registry, drift, training pipelines |
| Edge and Field | Edge / Field | 8 | Edge agent, site rollout, site accreditation support |
| — | — | **121** | |

**Coverage.** The full plan. Increments 0 through 5 run with a real critical path, all eight pillars are in flight at some point, and the 2027 validation event capability proceeds in parallel with the Pillar E revenue event.

**What this organisation can do.**

| Capability | Enablement |
|---|---|
| Four pillars in flight | The pillar pods are created and converted without a staffing decision per increment |
| Security engineering and security compliance are separated | The controls and the evidence are produced by different teams, which is what an assessor expects to see |
| Platform infrastructure is a function, not a task | Site reliability and capacity are owned, not absorbed |
| Field rollout is concurrent with feature development at scale | The Edge and Field pod runs multiple site rollouts in parallel |
| Dual-path critical work | The 2027 event path and the main revenue path both have dedicated capacity |

**What changes at 120 engineers.** The constraint shifts from engineering capacity to **partner access, accreditation throughput and range availability**. The technical work scales; the external dependencies do not. Adding a sixteenth pod does not accelerate a prime's data-sharing decision or a range's accreditation.

| Shifted constraint | Detail |
|---|---|
| Clearance and accreditation throughput | At 120 engineers, roughly 80 will need a clearance. The vetting system becomes the ramp constraint |
| Partner data access | IF-1, IF-2 and IF-3 each have one counterparty on the other side. More engineers on our side does not change their calendar |
| Range and facility availability | Scarcity of range slots is a physical constraint (R-15), and the virtual range substitutes for some of it, but not for the qualified range capacity that a flight demonstration needs |
| Coordination overhead | At this size the programme's own governance becomes a cost. The architecture review board and the increment gates need to be designed for this scale, not retrofitted |

## 8. Ramp-up sequencing

### 8.1 Sequence

| Phase | Duration | Actions | Staffing |
|---|---|---|---|
| **RP-1 Formation** | Weeks 0–6 | Form the first 2 pods (Platform Core, Security). Begin clearance processing immediately — it is the longest lead item and it starts first | ~14 |
| **RP-2 Foundation build** | Weeks 6–26 | Add the Ontology and Data pod and the first Pillar pod. Build WP-0.1, WP-0.2, WP-0.3, WP-0.5 | ~28 |
| **RP-3 Foundation complete** | Weeks 26–46 | Add the Test & Qualification pod and the Edge and Field pod. Complete WP-0.4 through WP-0.13. Run the Increment 0 gate | ~42 |
| **RP-4 First pillar** | Weeks 46–70 | Convert the pillar pod to Pillar E and A. Add the MLOps pod if the organisation is above 30 engineers. Deliver Increment 1 | ~48–60 |
| **RP-5 Scale** | Weeks 70 onward | Add pods per increment. Each increment adds 1–3 pods, with the critical-chain pod added first | Per target |

### 8.2 The clearance lead time problem

This is the single most disruptive fact in the staffing plan, and it is why the ramp cannot be compressed by hiring faster.

| Aspect | Reality |
|---|---|
| Lead time | Clearance processing for a new hire typically runs 3–9 months, and is longer for SCI. It is outside the programme's control and outside the programme's ability to expedite |
| What it gates | Every pod that touches CUI content needs a majority-cleared complement. A pod that forms at 40% cleared cannot work on classified work, and it cannot be moved to a pod that can |
| What it does *not* gate | Unclassified work — the contract layer, the codegen, the build pipeline, the local profile, the test harnesses, the console shell, the documentation |
| The ramp strategy | **Form pods with an unclassified core and a cleared complement.** The first 6–9 weeks of every pod's work is unclassified work — the CI pipeline, the local profile, the conformance harness, the test tooling. This is not a consolation prize; it is the majority of the engineering work in Increment 0 |
| The dependency | The programme needs a vetting capacity agreement with the sponsoring organisation, and it needs it at formation, not at the first clearance-gated deliverable |
| The tracking | R-10 in [`risk-register.md`](risk-register.md) |

### 8.3 Ramp-up is not linear

| Phase | Capability | Why |
|---|---|---|
| Month 0–2 | 20% | Pod formation, tooling, unclassified foundation work |
| Month 3–6 | 50% | Foundation build, first contracts, first pipelines |
| Month 7–12 | 80% | Full Increment 0 scope, first pillar slice |
| Month 13+ | 100% | Steady state, subject to clearance and partner access |

The plan must be built against the *steady-state* capacity, not the ramp. A plan that assumes the full headcount from month 1 will be wrong by 40–60% in the first year.

## 9. Cleared-workforce constraints

### 9.1 From the PSDD

| Source | Constraint | Effect on staffing |
|---|---|---|
| PSDD §2.1 **P7** | "Cleared, skilled workforce supply does not track classified production demand" (WISH; JHTO workforce studies) | The programme cannot hire its way out of the problem it exists to solve. Its own hiring faces the same market. This is a documented risk (R-18) |
| PSDD §2.2 | "guarantees a cleared workforce pipeline" | Pillar E is the staffing solution, and it is also the staffing constraint |
| PSDD §5.5 | Pillar E — Cleared Workforce Pipeline of Record | E-1 through E-5 are the mechanism. The programme dogfoods it: its own credentialing is built in Increment 1 and used from Increment 2 |
| PSDD §5.5 **E-3** | Badging tied to real process qualifications; feeds B-1 work authorisation | The platform's own work authorisation for its own sites is driven by its own credentialing. This is a deliberate dogfood: it forces the credentialing model to be correct before it is sold |
| PSDD §5.5 **E-4** | Gap analysis: cleared-skills supply vs. classified production demand, by region and trade | The E-4 model is the instrument for the programme's own hiring decisions. Run it on itself first |
| PSDD §14 | Teaming: academia consortium members, industry partners | A deliberate part of the staffing strategy: university consortium partners supply domain expertise and training capacity that the programme cannot hire |
| PSDD §13 | "Budget cyclicality — Workforce + industrial-base framings (WISH/SHY) are durable across budget cycles" | The hiring profile is skewed toward workforce-and-industrial-base skills, which are more durable across budget cycles than platform engineering skills |

### 9.2 What this means for the hiring profile

| Skill | Scarcity | Programme response |
|---|---|---|
| Cleared engineers with hypersonic domain depth | Very scarce. This is the binding constraint | Do not compete head-on. Use the academic consortium, the DASH-MOT and HAMTC ecosystems, and the prime partnerships to reach the domain |
| Composites and CMC process engineers | Very scarce | Partner with the DASH-MOT ecosystem. Build the platform so that these engineers are users, not authors |
| Test and range operations engineers | Scarce, and geographically distributed | The Edge / Field pod works with existing range organisations rather than hiring away from them |
| Security engineers with a clearance and an accreditation mindset | Scarce; a combination that is rare | The Security and Compliance pod is deliberately small and senior. Its two pods at 120 engineers reflect the scarcity |
| Distributed systems and Go, at a clearance | Scarce | This is the clearest case for the platform-agnostic architecture: it reduces the number of distinct technology stacks a cleared engineer must hold |
| MLOps with a clearance and a safety-relevant background | Very scarce | The MLOps pod works with Pillar domain engineers rather than replacing them. The model card is what lets a domain expert own the model without writing the pipeline |
| SysML and MBSE practitioners | Moderately scarce | WP-5.3 is the only work package that needs them at depth, and it is in Increment 5. It can be contracted or partnered rather than hired |

### 9.3 The programme's own credentialing

| Rule | Detail |
|---|---|
| The programme dogfoods Pillar E | From Increment 1, the programme's own site work authorisation is driven by `Credential` entities issued by the same service it is building |
| Clearance currency is enforced, not remembered | C-005 and C-006 apply to the programme's own personnel records. A lapsed clearance removes work authorisation automatically |
| Skills are recorded against real process qualifications | A credential requires `evidenceRefs` — a `TestResult`, a `ProcessRun` or a qualification artefact. A credential with no evidence cannot be issued |
| The gap model runs on the programme | E-4 is computed on the programme's own workforce from Increment 1, and the result informs the ramp plan for the following increment |
| Regional diversity is a constraint, not an aspiration | E-4 produces the gap by region and trade. A concentration of cleared skills in one geography is a programme risk (R-10, R-18), not only a workforce statistic |

## 10. Recruiting and retention

| # | Rule | Rationale |
|---|---|---|
| 1 | Hire into pods, not into roles. A candidate is assessed against a pod's composition and its acceptance criteria | Pod-level hiring preserves the composition rules. Role-level hiring tends to produce a surplus of software engineers and a deficit of test engineers |
| 2 | The systems engineer and the test engineer are the hardest roles to fill and the first to be sacrificed. They are the first to be protected | CR-2 and CR-3 are the rules that distinguish a pod from a group of developers |
| 3 | Clearance processing starts on the day of the offer, not on the day of the start date | The 3–9 month lead time is the ramp constraint |
| 4 | Retention is managed at the pod level. A pod losing two engineers in a quarter is a scheduling event, not a staffing event | Pod-level continuity preserves the tacit knowledge that lives in the pod |
| 5 | Every pod has a deputy from the day it forms (CR-5) | The mitigation for R-14. A deputy is not a promotion; it is a named, trained, practised second |
| 6 | The programme employs for the academic-partner relationship explicitly | PSDD §14. The consortium is a staffing channel, not only a distribution channel |
| 7 | Domain experts are engaged as advisors and reviewers with a day-per-week allocation, not as employees | The scarcity is real. A fractional allocation from an existing CMC or range expert is obtainable; a full-time hire is not |
| 8 | Pod leads are selected for delivery accountability and for technical credibility in the domain | A lead who is only a manager produces a pod that needs a manager, and the pod's work is the foundation of everything |
| 9 | The security and compliance roles are explicitly career-tracked | They are the hardest to recruit and the easiest to under-rate. An untracked security engineer is a security engineer who leaves |
| 10 | Programme office and sponsor-facing roles are separate from delivery pods | The scale-up path for a senior engineer is technical leadership, not programme management. If the only path up is programme management, the best engineers leave the code |

## 11. Cost and availability

### 11.1 Headcount to deliver the plan

| Target organisation | Pods | Engineers | Plan duration | Binding constraint |
|---|---|---|---|---|
| ~25 | 4–5 | 27 | 5–6 years | Partner access and the absence of a verification pod |
| ~60 | 8–9 | 63 | 3–3.5 years | Clearance throughput; a single Security pod for two accreditation paths |
| ~120 | 15–17 | 121 | 18–24 months per increment, full plan in 2.5–3 years | Partner access, accreditation throughput, range availability. **Not engineering capacity** |

### 11.2 The scaling observation

Adding engineers has diminishing returns that become visible between 60 and 120. The programme's own risk register documents the two constraints that do not scale with headcount:

| Constraint | Scales with engineering? | Scales with what |
|---|---|---|
| Prime data sharing (R-02) | No | Teaming agreements, programme time, the delivery of a working integration |
| Threat-model data access (R-04) | No | Access approvals and accreditation, not engineering |
| Range availability (R-15) | No | Virtual range substitution (G-1) and physical range scheduling |
| Clearance throughput (R-10) | No | Vetting capacity |
| Integration debt (R-07) | Inversely — more engineers can increase it | Contract discipline and the verification function |
| Contract drift (R-08) | Inversely | Codegen and CI enforcement |
| Fidelity shortfall (R-11) | Partly | The fidelity registry and the approval discipline |

**The practical implication.** Between 60 and 120 engineers, the highest-value investment is in the **Test and Qualification pod**, the **Security and Compliance pod** and the **Edge and Field pod** — the three functions that retire the risks that do not scale with headcount — and in the **partner and accreditation work**, which is a programme management investment rather than an engineering one.

## 12. References

**PSDD:** §1 (dual-mission platform), §2.1 **P7** (cleared workforce supply), §2.2 (mission need — the cleared workforce pipeline guarantee), §3.1 (in scope — cleared-workforce training, credentialing and demand modelling), §4.2 (design principles), §5.1–§5.8 (Pillar A–H capability ids), §5.5 **E-1..E-5** (cleared workforce pipeline of record), §6.3 (data governance), §8 (Availability, Scalability, Modularity), §11 (phasing; each phase yields a standalone product), §12 (workforce guarantee KPI: cleared-skills supply against classified demand, by region and trade), §13 (risks — budget cyclicality), §14 (teaming strategy — academia consortium, CMC ecosystem).

**Architecture:** [`architecture/01-system-context.md`](architecture/01-system-context.md) §5 (external actors), [`architecture/03-foundation-services.md`](architecture/03-foundation-services.md) §3 (subscription groups, which define the integration contract between pods).

**ADRs:** [ADR-0002](adr/ADR-0002-json-schema-contracts-over-shared-libraries.md) (the coupling mechanism that makes pod integration cheap), [ADR-0003](adr/ADR-0003-platform-agnostic-hybrid-deployment.md) (the deployment profiles that the Edge / Field pod supports), [ADR-0004](adr/ADR-0004-abac-with-pdp-pep-separation.md) (the security work that is embedded in every pod), [ADR-0008](adr/ADR-0008-model-card-and-fidelity-registry.md) (the model card as the mechanism that lets a domain expert own a model without writing the pipeline).

**Planning:** [`roadmap/increments.md`](roadmap/increments.md), [`roadmap/work-packages.md`](roadmap/work-packages.md), [`risk-register.md`](risk-register.md).
