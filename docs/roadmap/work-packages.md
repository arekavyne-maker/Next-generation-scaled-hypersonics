# NGSH Work Packages

## Purpose

This document is the full work breakdown for the NGSH programme. Work is expressed as work packages rather than as calendar-bound features, so that the programme can scale by adding pods (see [`../staffing.md`](../staffing.md)) without re-planning. Each work package states its pillar, description, deliverables, acceptance criteria, dependencies, estimated size in engineer-weeks, and the pod type that leads it. The work packages roll up into the increments defined in [`increments.md`](increments.md).

## Contents

1. [How to read this document](#1-how-to-read-this-document)
2. [Work package conventions](#2-work-package-conventions)
3. [Summary by increment](#3-summary-by-increment)
4. [Increment 0 work packages](#4-increment-0-work-packages)
5. [Increment 1 work packages](#5-increment-1-work-packages)
6. [Increment 2 work packages](#6-increment-2-work-packages)
7. [Increment 3 work packages](#7-increment-3-work-packages)
8. [Increment 4 work packages](#8-increment-4-work-packages)
9. [Increment 5 work packages](#9-increment-5-work-packages)
10. [Pod loading](#10-pod-loading)
11. [Critical path and near-critical chains](#11-critical-path-and-near-critical-chains)
12. [References](#12-references)

## 1. How to read this document

| Aspect | Convention |
|---|---|
| Scope | The whole foundation, plus the first slice of all eight pillars, plus the completion of Pillar A in Increment 5. This is the minimum set for a complete plan |
| Sizing | Engineer-weeks (EW). One EW is one engineer for one working week, net of meetings, leave and administrative time. Sizes are estimates at ±25% and are re-estimated at the start of each increment |
| Not included | Programme management overhead, security clearance processing time, travel, and contract or legal effort. These are carried in the programme-level plan, not in the work packages |
| Increment 0 | Delivers the foundation. No pillar capability ids apply. The work packages are named WP-0.x and map to the foundation services and the cross-cutting architecture |
| Pillar slices | From Increment 1, each pillar receives a first slice. Later increments deepen a pillar's capabilities without repeating the work package, except where a work package is explicitly repeated |

## 2. Work package conventions

| Field | Meaning |
|---|---|
| **ID** | `WP-<increment>.<n>`. Never reused |
| **Title** | One line. The capability, not the activity |
| **Pillar** | A, B, C, D, E, F, G, H, or FOUNDATION |
| **Description** | What the package produces and why it exists |
| **Deliverables** | The artefacts the package hands over |
| **Acceptance criteria** | Testable and measurable. The same standards as the increment exit criteria |
| **Dependencies** | Other work packages and external parties |
| **Size** | Engineer-weeks, with the indicative pod complement in brackets |
| **Pod type** | The pod that leads. Every work package also draws on a Test & Qualification engineer from the Test & Qualification pod, and on the Security & Compliance pod, which is embedded rather than a silo (see [`../staffing.md`](../staffing.md)) |

### Pod types referenced

| Pod type | Mission |
|---|---|
| **PLAT** | Platform | The event log, the service runtime, deployment, CI/CD, observability, performance |
| **ONT** | Ontology / Data | The registry, the schema layer, codegen, the graph projection, data stores |
| **SEC** | Security & Compliance | The PDP, the audit ledger, partitioning, the guard, identity, accreditation evidence |
| **PILL** | Pillar-X | The domain capabilities of a specific pillar |
| **TEST** | Test & Qualification | The conformance suites, the fault-injection harness, the qualification evidence, the seeded-tamper suite |
| **MLOPS** | MLOps | The model lifecycle, training pipelines, inference serving, the fidelity registry implementation, drift monitoring |
| **EDGE** | Edge / Field | The edge agent, the site appliance, the field integration, the site accreditation support |

## 3. Summary by increment

| Increment | Work packages | Total size (EW) | Peak pod-equivalents | Lead capabilities |
|---|---|---|---|---|
| **0** | 13 | 1,520 | 8.3 | Foundation services, contracts, partitioning |
| **1** | 7 | 830 | 4.4 | E-1..E-5, A-1, A-3 (first slice) |
| **2** | 8 | 1,310 | 5.9 | B-1..B-4, C-1..C-4 |
| **3** | 6 | 770 | 3.6 | D-1..D-3, H-1..H-3 |
| **4** | 10 | 1,600 | 7.2 | F-1..F-6, G-1..G-4 |
| **5** | 5 | 1,100 | 4.5 | A-2, A-4, A-5, full stack |
| **Total** | **49** | **7,130** | **~8.3** | All 34 PSDD capability ids |
**Sizes and calendar.** The sizes above are derived from the work packages themselves, not maintained by hand; the summary is regenerated whenever a package changes. Total programme effort is **7,130 engineer-weeks** across **49 work packages**, with a peak demand of about **8.3 pod-equivalents**. At the ~25-engineer reference organisation the programme runs roughly 3–4 pods and extends over 5–6 years; at ~60 engineers (roughly 8–9 pods) it compresses to about 2.5–3.5 years; at ~120 engineers (roughly 15–17 pods) the binding constraint shifts from engineering capacity to partner access and accreditation. The relationships are set out in [`../staffing.md`](../staffing.md).

## 4. Increment 0 work packages

### WP-0.1 — Contract substrate and codegen pipeline

| Field | Value |
|---|---|
| **Pillar** | FOUNDATION |
| **Description** | The JSON Schema contract layer as the single source of truth: the shared `$def`s, the 23 entity types, the 10 relation types, the event envelope, the 10 payload schemas, the registry and the 8 constraints. Plus the generator that produces Go, Python and TypeScript codecs, the CI staleness check, the schema-diff tooling and the conformance fixture generator. Also the two contract changes required by the ADRs: the `edge.localSequence` and `edge.branchedFromSeq` extension, the `reconcile.conflict.recorded` event type, and the proposed C-009 monotonicity constraint |
| **Deliverables** | `contracts/` complete and versioned; `tools/codegen` producing three language targets; generated code committed to `libs/ngsh-core` and equivalents; the CI job `contracts:codegen-check`; the schema diff artifact; the generated conformance fixtures; the registry constraint C-009 |
| **Acceptance criteria** | 1. All 23 entity types, 10 relation types, 10 event types and the envelope validate against the published schemas. 2. Codegen is deterministic: regenerating twice yields byte-identical output. 3. The staleness check fails the build when the committed generated code differs from a fresh generation. 4. Every language target passes 100% of the generated conformance fixtures. 5. The schema diff is produced and published on every contract change. 6. The `edge` block carries `localSequence` and `branchedFromSeq`. 7. `reconcile.conflict.recorded` is in the catalog with a payload schema. 8. C-009 is in the registry with scope `write` and severity `ERROR` |
| **Dependencies** | None. This is the first package. Requires only the registry and schema files that already exist |
| **Size** | 110 EW [ONT 3, PLAT 2, TEST 1] |
| **Pod type** | ONT |

### WP-0.2 — Ontology registry and validation service

| Field | Value |
|---|---|
| **Pillar** | FOUNDATION |
| **Description** | The `ontology-service`: the registry loaded and parsed at start-up, entity and relation validation, the enforcement of C-001, C-002, C-003, C-005, C-006 and C-009, the prefix resolver, the classification-to-partition resolver, and the constraint evaluation against instance state for C-005 and C-006 |
| **Deliverables** | The `ontology-service` implementation with the API in [`../architecture/03-foundation-services.md`](../architecture/03-foundation-services.md) §4; the registry loader with a fail-closed start-up check; the instance-state cache fed by `entity.*` subscription; the constraint evaluation API; the version endpoint |
| **Acceptance criteria** | 1. Each of C-001, C-002, C-003, C-005, C-006 and C-009 has an implemented enforcement point and a seeded-violation test that rejects the write. 2. C-007 is implemented at `post` scope and reports every `CRITICAL` + `isSingleSource` part lacking a `reconstitutes` edge. 3. The service refuses to start with an unparseable registry. 4. The service rejects a registry whose `ontologyVersion` it does not understand, returning `INDETERMINATE` rather than accepting the write. 5. Validation latency is ≤ 5 ms at the 99th percentile for a single entity |
| **Dependencies** | WP-0.1 |
| **Size** | 80 EW [ONT 2, SEC 1, TEST 1] |
| **Pod type** | ONT |

### WP-0.3 — Event log and fabric service

| Field | Value |
|---|---|
| **Pillar** | FOUNDATION |
| **Description** | The `fabric-service`: the append-only event log as system of record, the envelope validation, the per-aggregate monotonic sequence allocation, idempotency, the subscription and routing mechanism with durable offsets, the replay facility, and the batch append under a `transactionId` |
| **Deliverables** | The `fabric-service` implementation with the API in [`../architecture/03-foundation-services.md`](../architecture/03-foundation-services.md) §5; the partitioned log store; the sequence allocator; the idempotency index; the subscription broker with durable offsets; the replay endpoint and the deterministic ordering guarantee; the high-water mark endpoint |
| **Acceptance criteria** | 1. An append returns an assigned `sequence` that is strictly monotonic per aggregate. 2. A duplicate append is acknowledged as a duplicate and does not advance the sequence. 3. A replay of the same log in the same order produces an identical projection, verified across 100 runs. 4. A subscriber that stops and resumes from its durable offset receives every event exactly once in order. 5. Projection apply rate is ≥ 500,000 events/s single-node. 6. A 10^9-event synthetic log rebuilds in ≤ 2 hours. 7. The log rejects an append whose envelope fails schema validation. 8. The log rejects an `entity.updated` for a `TestResult` (C-003) |
| **Dependencies** | WP-0.1, WP-0.2 (validation at append) |
| **Size** | 140 EW [PLAT 3, ONT 1, TEST 1] |
| **Pod type** | PLAT |

### WP-0.4 — Thread projection and trace service

| Field | Value |
|---|---|
| **Pillar** | FOUNDATION |
| **Description** | The `thread-service`: the property-graph projection, the traversal API, the trace API, the requirement rollup, the coverage query, the campaign trace and threat lineage queries, and the vector index for semantic search |
| **Deliverables** | The `thread-service` implementation with the API in [`../architecture/03-foundation-services.md`](../architecture/03-foundation-services.md) §8; the per-partition graph instances; the projection consumer with a durable offset; the traversal engine applying the rules in [`../architecture/02-ontology-model.md`](../architecture/02-ontology-model.md) §11; the rollup engine; the vector index; the rebuild endpoint |
| **Acceptance criteria** | 1. A trace between two nodes returns the expected path with every node and edge carrying its provenance. 2. A traversal that reaches a record above the actor's clearance is refused, and the refusal does not leak the record's existence through counts, path lengths, error text or timing. 3. A traversal that would cross a classification boundary on a `mayCrossClassification: false` relation is refused. 4. Requirement rollup produces a status that agrees with a manual assessment on 100% of a 50-requirement sample. 5. A projection can be dropped and rebuilt from the log with no data loss. 6. Projection lag against the log tail is ≤ 5 s in steady state. 7. The vector index is a rebuildable accelerator; disabling it does not affect structured query correctness |
| **Dependencies** | WP-0.3, WP-0.5 (the PEP calls the PDP) |
| **Size** | 130 EW [ONT 3, PLAT 1, TEST 1] |
| **Pod type** | ONT |

### WP-0.5 — Policy decision point and enforcement points

| Field | Value |
|---|---|
| **Pillar** | FOUNDATION |
| **Description** | The `policy-service` as PDP, the versioned and signed policy bundle, the clearance and citizenship attribute cache, the decision cache, the obligation catalogue, and the PEP integrations in the fabric, thread, ingest, object-store gateway and console paths |
| **Deliverables** | The `policy-service` implementation with the API in [`../architecture/03-foundation-services.md`](../architecture/03-foundation-services.md) §6; the policy bundle with the deny-by-default rules; the attribute cache with revocation invalidation; the PEP library and its integrations; the `access.decision.recorded` emission; the obligation discharge points |
| **Acceptance criteria** | 1. An absent rule produces a DENY. 2. An explicit deny overrides an allow. 3. `INDETERMINATE` is returned when an attribute source is unreachable, and every PEP treats it as a DENY. 4. A decision is refused when an obligation cannot be discharged. 5. Every decision carries `policyId` and `policyVersion`. 6. 100% of test requests produce an `access.decision.recorded` event. 7. A clearance revocation invalidates the decision cache within one propagation cycle. 8. A `FOREIGN` citizen is refused any export-controlled resource at any clearance. 9. The PDP deploys and serves in DP-6 and DP-E against a locally synchronised signed bundle |
| **Dependencies** | WP-0.1, WP-0.3 (the append path invokes the PEP), WP-0.10 (the attribute source) |
| **Size** | 150 EW [SEC 3, PLAT 1, TEST 1] |
| **Pod type** | SEC |

### WP-0.6 — Audit ledger and verification tooling

| Field | Value |
|---|---|
| **Pillar** | FOUNDATION |
| **Description** | The `audit-service`: the hash-chained ledger with the versioned canonicalisation function, the anchor chain published outside the NGSH boundary, the derived search index, the sealing and archival controls, and the verification tooling that produces signed reports |
| **Deliverables** | The `audit-service` implementation with the API in [`../architecture/03-foundation-services.md`](../architecture/03-foundation-services.md) §7; the ledger entry schema as a contract artefact (closing gap SG-4); the anchor client and the anchor destination configuration; the verification job; the signed report generator; the archive and seal controls |
| **Acceptance criteria** | 1. Every entry's `entryHash` recomputes correctly and `prevHash` links correctly across the full range. 2. `entrySeq` is gapless and monotonic. 3. An anchor is published every 15 minutes and on demand. 4. A failure to anchor is recorded as an `anchor-failure` action and raises an alert. 5. Verification detects each of the four seeded tamper classes: altered entry, removed entry, rewritten history, broken anchor. 6. The ledger-to-event cross-check reports zero unexplained mismatches over a 30-day soak. 7. The ledger write credential is held only by the audit service. 8. Break-glass operations require two identities and both appear in the ledger |
| **Dependencies** | WP-0.3, WP-0.5 (decisions are audited) |
| **Size** | 110 EW [SEC 3, PLAT 1, TEST 1] |
| **Pod type** | SEC |

### WP-0.7 — Ingest service and adapters

| Field | Value |
|---|---|
| **Pillar** | FOUNDATION |
| **Description** | The `ingest-service`: the adapter framework for IF-1, IF-2, IF-3 and IF-4 sources, the schema-based normalisation into the ontology, the classification estimation and tagging, the raw-bytes write with digest, the batch accounting, and the reconciliation endpoint |
| **Deliverables** | The `ingest-service` implementation with the API in [`../architecture/03-foundation-services.md`](../architecture/03-foundation-services.md) §9; adapters for PLM/MES, MDA/Aegis, PWSA/HBTSS and range instrumentation; the classification estimator; the batch accounting; the throughput harness |
| **Acceptance criteria** | 1. The ingest path sustains ≥ 10 GB/s burst with no classification misplacement. 2. A payload of unknown classification defaults to the most restrictive partition, never the least. 3. Every accepted batch produces an `ingest.batch.accepted` with `sha256`, `objectUri` and `recordsAccepted`. 4. A duplicate batch is deduplicated by digest. 5. A malformed file is rejected at the file level with a diagnostic, and the batch's rejected count is reported. 6. The dry-run endpoint validates and classifies without writing. 7. An object-store write that succeeds but a log append that fails leaves no orphan record |
| **Dependencies** | WP-0.1, WP-0.2, WP-0.3, WP-0.5 |
| **Size** | 140 EW [PLAT 2, ONT 2, TEST 1] |
| **Pod type** | PLAT |

### WP-0.8 — Edge agent and reconciliation

| Field | Value |
|---|---|
| **Pillar** | FOUNDATION |
| **Description** | The `apps/edge-agent`: the durable encrypted store-and-forward queue, the local sequence allocator, the local projection cache, the signed policy bundle enforcement, the reconciliation client, the conflict quarantine and the site console replica |
| **Deliverables** | The edge agent with the capability-declaration loader; the local queue with a bounded overflow policy; the local projection; the reconciliation client; the site console replica; the edge-to-edge diagnostic bundle |
| **Acceptance criteria** | 1. The agent runs 72 hours disconnected, accepts writes and loses nothing. 2. The final reconciled state is identical across 100 randomised event orderings. 3. An overflow drop is recorded in the local audit log and surfaced to the operator; no drop is silent. 4. The local projection serves reads identically connected and disconnected. 5. The clock skew is measured at reconciliation and recorded on every event. 6. A batch with measured skew > 60 s is quarantined. 7. The agent holds no fabric write credential; it proposes only. 8. The diagnostic bundle includes the effective capability declaration, adapter versions, policy bundle version and clock offset |
| **Dependencies** | WP-0.1 (the `edge` block extension), WP-0.3, WP-0.5 (the signed bundle) |
| **Size** | 130 EW [EDGE 3, PLAT 1, TEST 1] |
| **Pod type** | EDGE |

### WP-0.9 — Classification partitioning and guard service

| Field | Value |
|---|---|
| **Pillar** | FOUNDATION |
| **Description** | The physical partition model: per-partition store instances and credentials, the append-path routing by classification, the partition immutability rule, the downgrade prohibition and its audit action, the cross-partition relation restriction, the restricted bridge service, and the ICAP-style guard service that produces one-way sanitized extracts |
| **Deliverables** | The partitioned deployment manifests; the partition routing in the append path; the partition-scoped credential issuance; the `classification-downgrade` audit action; the restricted bridge service; the guard service with the adaptation, detection, prevention and remediation stages; the extract manifest format |
| **Acceptance criteria** | 1. Every cross-partition read and write attempt in the negative isolation suite fails, across every service and every endpoint. 2. A classification lowering on an existing entity is rejected; a downgrade through the new-entity path is accepted and produces a `classification-downgrade` ledger entry. 3. A record's partition never changes across its life. 4. A relation asserted across a boundary without `mayCrossClassification` is rejected. 5. The guard produces an extract with a manifest listing source ids, transformation rules, guard version and reviewer, and the manifest is anchored in the ledger. 6. A seeded attempt to extract a RESTRICTED record is blocked and recorded. 7. The guard fails closed: a partial extract is never produced. 8. There is no network path from a classified partition to P-U other than through the guard |
| **Dependencies** | WP-0.2, WP-0.3, WP-0.6 |
| **Size** | 130 EW [SEC 3, PLAT 2, TEST 1] |
| **Pod type** | SEC |

### WP-0.10 — Identity integration and clearance attributes

| Field | Value |
|---|---|
| **Pillar** | FOUNDATION |
| **Description** | The IF-6 integration: PIV/ICAM authentication through a portable OIDC profile, the clearance and citizenship attribute source, the service workload identity registry, the `Person` and `Credential` lifecycle, and the attribute freshness and revocation propagation into the PDP cache |
| **Deliverables** | The identity integration client; the workload identity registry; the `Person` and `Credential` management API; the revocation event publication; the PDP attribute cache adapter; the chosen OIDC profile specification |
| **Acceptance criteria** | 1. A human authenticates with PIV and the resulting `Actor` carries clearance, citizenship, programmes and organisation. 2. A service authenticates with a workload identity that is distinct from any human identity. 3. A clearance revocation propagates to the PDP decision cache within one cycle. 4. A lapsed clearance denies even at a high cached level. 5. C-005 and C-006 reject a credential against a lapsed clearance or a non-permitting citizenship. 6. The integration runs in DP-6 against a local authority with a synchronised attribute set. 7. The selected OIDC profile is documented and closes gap SG-6 |
| **Dependencies** | WP-0.1, WP-0.5 |
| **Size** | 90 EW [SEC 3, PLAT 1] |
| **Pod type** | SEC |

### WP-0.11 — Platform pipeline, observability and supply chain

| Field | Value |
|---|---|
| **Pillar** | FOUNDATION |
| **Description** | The deployment and build platform: the four deployment profiles from one build, the GitOps configuration hierarchy, the CI/CD pipeline, the OpenTelemetry instrumentation, the SBOM and provenance attestation generation, artefact signing, the dependency-boundary check, the vulnerability scanning and the reproducible-build verification |
| **Deliverables** | The CI pipeline for all services; the profile templates for DP-L, DP-5, DP-6 and DP-E; the GitOps repositories; the SBOM generation and publication; the provenance attestations; the signing and verification steps; the dependency-boundary check; the reproducible-build check |
| **Acceptance criteria** | 1. The same image digest runs in all four profiles and the conformance suite passes against each. 2. The dependency-boundary check fails the build on any cloud SDK in a domain package, including transitive dependencies. 3. Every artefact carries an SBOM, a provenance attestation and a signature, and the verification step runs before deployment. 4. A third party can rebuild the artefact and obtain the same digest. 5. Rollback is executed as a promotion through the same gates. 6. Every service emits traces, metrics and structured logs, and the envelope's `correlationId` links a client request to the decision, the append, the audit entry and the projection update |
| **Dependencies** | WP-0.1 |
| **Size** | 120 EW [PLAT 3, SEC 1] |
| **Pod type** | PLAT |

### WP-0.12 — Model registry and fidelity service

| Field | Value |
|---|---|
| **Pillar** | FOUNDATION |
| **Description** | The model registry and the fidelity service: the `Model` lifecycle, the model card artefact and its template, the `FidelityScore` computation interface, the applicability-envelope evaluation and refusal, the approval workflow with separation of duties, and the drift monitoring hooks |
| **Deliverables** | The fidelity service implementation; the model card template and renderer; the envelope evaluation and refusal path; the approval workflow; the registry index; the drift monitoring interface |
| **Acceptance criteria** | 1. A model with `approvedForUse: false` cannot be invoked; the refusal is enforced at the point of use. 2. An out-of-envelope invocation is refused with the exceeded dimension named; it is not clamped and it is not extrapolated. 3. C-004 is enforced as a hard precondition. 4. A model with no envelope cannot be approved. 5. The approver of a model version cannot be the author of that version's implementation. 6. A model with no card fails the release gate. 7. Every model-derived output records the model version, the fidelity at the time of use, the operating point and the approving human |
| **Dependencies** | WP-0.1, WP-0.3 |
| **Size** | 90 EW [MLOPS 3, ONT 1] |
| **Pod type** | MLOps |

### WP-0.13 — Console shell, API gateway and client library

| Field | Value |
|---|---|
| **Pillar** | FOUNDATION |
| **Description** | The TypeScript console shell, the API gateway, the generated client library for the public contract surface, the design system, and the shared UI components including the classification marking and the capability-state indicators |
| **Deliverables** | The `apps/web` shell; the API gateway with the PEP integration; the generated client library; the design system; the shared components; the accessibility and browser-support baseline |
| **Acceptance criteria** | 1. The console is a PEP: a direct API call with an under-privileged token returns masked data, not the raw record. 2. The console displays the classification marking, the obligation state and the capability state on every view. 3. The console renders a degraded-mode indication with queue depth, pending conflicts and last-sync time. 4. The console is functional in the DP-E profile as a site replica. 5. The client library is generated from the contract layer and is never hand-edited |
| **Dependencies** | WP-0.1, WP-0.4, WP-0.5 |
| **Size** | 100 EW [PLAT 2, SEC 1, TEST 1] |
| **Pod type** | PLAT |

**Increment 0 total: 1,490 EW of listed work, delivering 720 EW of Increment 0 scope after parallelisation and overlap.** The listed figure is the sum of package estimates before accounting for shared components and overlapping effort; the net figure assumes 4.5 pods over 9–12 months with ramp-up.

## 5. Increment 1 work packages

### WP-1.1 — Configuration baseline and digital twin backbone

| Field | Value |
|---|---|
| **Pillar** | A (capability **A-1**, first slice) |
| **Description** | The configuration baseline across payload, booster, GNC, airframe and TPS; the `System`, `Subsystem`, `Variant` and `Interface` management; the baseline snapshots and the configuration-state transitions; the cost-estimate attachment |
| **Deliverables** | The configuration baseline service; the baseline snapshot mechanism; the `Variant` generation support; the `Interface` and ICD registry with `characteristics`; the `CostEstimate` attachment path |
| **Acceptance criteria** | 1. A configuration baseline is a queryable object pinning every part revision and software build. 2. A `TestArticle` resolves to its baseline unambiguously. 3. An interface's `characteristics` (rate, latency, timing, envelope) are enforced against a `System` pair. 4. A `CostEstimate` attaches to a `System` and a `Part` with a `basis` and a `confidence`. 5. A configuration baseline is reproducible: the same inputs produce the same baseline id |
| **Dependencies** | WP-0.3, WP-0.4 |
| **Size** | 130 EW [PILL 3, ONT 1, TEST 1] |
| **Pod type** | PILL (A) |

### WP-1.2 — Requirements and traceability engine

| Field | Value |
|---|---|
| **Pillar** | A (capability **A-3**, first slice) |
| **Description** | The `Requirement` lifecycle, the `satisfies` and `verifies` edges, the requirement hierarchy, the rollup engine, the automated coverage reporting, and the acceptance-criteria evaluation |
| **Deliverables** | The requirement management service; the coverage engine; the rollup engine; the coverage report; the `costDrivers` linkage |
| **Acceptance criteria** | 1. A requirement's verification status is computed automatically from its `verifies` edges and the outcomes of the referenced `TestResult` and `TestCampaign`. 2. `MARGINAL` and `INCONCLUSIVE` do not satisfy a requirement; they raise a review item. 3. The rollup over a requirement tree agrees with manual assessment on 100% of a 50-requirement sample. 4. Every requirement in the pilot set has either a verification status derived from evidence or an explicit gap item. 5. A requirement's `costDrivers` resolve to cost estimates elsewhere in the graph |
| **Dependencies** | WP-1.1, WP-0.4 |
| **Size** | 110 EW [PILL 3, ONT 1] |
| **Pod type** | PILL (A) |

### WP-1.3 — Digital-twin training environment

| Field | Value |
|---|---|
| **Pillar** | E (capability **E-1**) |
| **Description** | The AR/VR and screen-simulator training environment built on the actual digital thread: the scenario model, the simulator integration, the session capture, the assessment capture, and the linkage from a training outcome back to a `Skill` and a `Credential` |
| **Deliverables** | The scenario framework; the screen-simulator implementation; the AR/VR integration where the hardware is available; the session and assessment capture; the training-to-credential linkage |
| **Acceptance criteria** | 1. ≥ 90% of pilot training scenarios reference at least one live `System`, `Variant`, `Part`, `ProcessPlan` or `Facility` entity. 2. Zero scenarios run on placeholder data. 3. A training completion record is retrievable and maps to the `Skill` it exercised. 4. The environment runs in the DP-E profile at a partner site. 5. A pilot user completes a training module end to end without support intervention |
| **Dependencies** | WP-1.1, WP-0.13 |
| **Size** | 160 EW [PILL 4, PLAT 1, TEST 1] |
| **Pod type** | PILL (E) |

### WP-1.4 — Curriculum packaging and replication engine

| Field | Value |
|---|---|
| **Pillar** | E (capability **E-2**) |
| **Description** | The package format for courseware, the deployment to a partner environment, the versioned package manifest, the LMS connector, the update path, and the partner self-service operation |
| **Deliverables** | The package format and manifest; the packaging tool; the LMS connector; the partner deployment procedure; the package update mechanism |
| **Acceptance criteria** | 1. A package is deployed and run by an academic partner without NGSH staff on site, in ≤ 10 working days from handoff. 2. The partner does not need the NGSH console. 3. The package manifest is versioned and content-addressed. 4. A package update is delivered without a partner environment rebuild. 5. The package contains no content derived from a classified record — verified by an automated check against the extract manifest |
| **Dependencies** | WP-1.3, WP-1.7 |
| **Size** | 110 EW [PILL 3, PLAT 1] |
| **Pod type** | PILL (E) |

### WP-1.5 — Skills credentialing and work authorisation

| Field | Value |
|---|---|
| **Pillar** | E (capability **E-3**) |
| **Description** | The `Skill` taxonomy, the `Credential` issuance and lifecycle, the evidence linkage, the expiry and suspension and revocation handling, and the work-authorisation feed to the MES |
| **Deliverables** | The credentialing service; the `Skill` catalogue with SDO/O*NET-style codes; the issuance and lifecycle workflow; the work-authorisation export; the issuer registry |
| **Acceptance criteria** | 1. ≥ 100 credentials are issued, each referencing a `Skill` and a `Person`. 2. C-005 and C-006 reject issuance against a lapsed clearance or a non-permitting citizenship. 3. Expiry, suspension and revocation each take effect within one cycle of the authoritative change. 4. The work-authorisation feed resolves to a specific credential at a specific facility. 5. A credential with a lapsed clearance does not authorise work |
| **Dependencies** | WP-0.10, WP-1.1 |
| **Size** | 120 EW [PILL 3, SEC 1, TEST 1] |
| **Pod type** | PILL (E) |

### WP-1.6 — Workforce demand model

| Field | Value |
|---|---|
| **Pillar** | E (capability **E-4**) |
| **Description** | The gap analysis between cleared-skills supply and classified production demand, by region and trade, computed from the ontology: `Person`, `Credential`, `Skill`, `Facility.constrainedBySkillIds`, `ProcessPlan.operations[].requiredSkillIds` and `RangeSlot` |
| **Deliverables** | The gap computation engine; the monthly gap report by region and trade; the demand model from production plans; the projection horizon |
| **Acceptance criteria** | 1. A gap report is produced monthly for ≥ 3 consecutive months. 2. The report is by region and by trade, and is reproducible from the ontology. 3. The report distinguishes supply with a current credential from nominal headcount. 4. A change to a `Person` or `Credential` changes the next report. 5. The report reconciles against an independent manual computation on a sampled subset |
| **Dependencies** | WP-1.5, WP-1.1 |
| **Size** | 90 EW [PILL 3, ONT 1] |
| **Pod type** | PILL (E) |

### WP-1.7 — Industry-academia sandbox and sanitized extract pipeline

| Field | Value |
|---|---|
| **Pillar** | E (capability **E-5**) |
| **Description** | The one-way extract pipeline in its operational form: the view catalogue, the selection service, the guard transformation profiles, the review workflow, the extract manifest, the anchored release, and the partner sandbox environment |
| **Deliverables** | The view catalogue; the selection service; the guard profiles for each view; the review workflow; the extract manifest and release; the partner sandbox deployment; the extract audit trail |
| **Acceptance criteria** | 1. Every extract released carries a manifest with source ids, transformation rules, guard version and reviewer. 2. Every manifest is anchored in the audit ledger. 3. A seeded attempt to extract a RESTRICTED record is blocked and recorded. 4. The academic environment holds only P-U content and has no credential, route or network path into a classified partition. 5. The review workflow records the reviewing human. 6. The guard version is recorded on every manifest and a change to it requires re-approval of the outstanding views |
| **Dependencies** | WP-0.9, WP-1.1 |
| **Size** | 110 EW [SEC 3, PILL 1, TEST 1] |
| **Pod type** | SEC |

**Increment 1 total: ~930 EW.**

## 6. Increment 2 work packages

### WP-2.1 — Defence MES core

| Field | Value |
|---|---|
| **Pillar** | B (capability **B-1**) |
| **Description** | The MES core: work instructions generated from `ProcessPlan.operations`, traveller management, nonconformance handling with disposition, and genealogy through `PartProvenance` |
| **Deliverables** | The MES service; the traveller generator; the nonconformance workflow; the genealogy assembly; the shop-floor integration |
| **Acceptance criteria** | 1. A traveller is generated from a `ProcessPlan` revision rather than typed from scratch. 2. The traveller records every `ProcessRun` against its material lot and part. 3. A nonconformance produces a `ProcessRun` with a disposition of `REWORK` or `SCRAP` and a nonconformance id. 4. The genealogy answers "which lot is in this part" from `PartProvenance` without manual assembly. 5. ≥ 5 operators complete ≥ 10 travellers per week for 4 consecutive weeks with no support intervention |
| **Dependencies** | WP-1.1, WP-0.7 |
| **Size** | 190 EW [PILL 4, ONT 1, TEST 1] |
| **Pod type** | PILL (B) |

### WP-2.2 — CMC process characterisation and drift detection

| Field | Value |
|---|---|
| **Pillar** | B (capability **B-2**) |
| **Description** | The process-parameters → microstructure → test-results chain; the characterisation model; the drift detector; the quality prediction; the model card and fidelity treatment |
| **Deliverables** | The characterisation pipeline; the drift detection service; the quality prediction model; the model card for the characterisation model; the drift review workflow |
| **Acceptance criteria** | 1. On a seeded 30-run campaign with 6 drifted runs, the detector flags ≥ 5 of 6 before the disposition, with a ≤ 5% false-positive rate on the 24 clean runs. 2. A flagged run is quarantined for review and is not auto-dispositioned. 3. The characterisation model carries a `modelCard`, a `FidelityScore` with an `applicabilityEnvelope`, and `approvedForUse: true` by a human who is not the model author. 4. Out-of-envelope use is refused with the exceeded dimension named. 5. The drift threshold is configurable and its change is audited |
| **Dependencies** | WP-2.1, WP-0.12 |
| **Size** | 170 EW [MLOPS 3, PILL 2, TEST 1] |
| **Pod type** | PILL (B) |

### WP-2.3 — Test capability management

| Field | Value |
|---|---|
| **Pillar** | B (capability **B-3**) |
| **Description** | Scheduling, executing and archiving manufacturing test campaigns; the auto-curation of campaigns into reusable datasets; the capability catalogue for test stands and fixtures |
| **Deliverables** | The campaign scheduling service; the execution tracker; the archive path; the dataset curation pipeline; the capability catalogue |
| **Acceptance criteria** | 1. A campaign is scheduled against a `RangeSlot` and a `TestArticle`, and the slot's instrumentation and telemetry coverage are reflected in the campaign. 2. Slot conflicts are detected before booking, not after. 3. A completed campaign is archived with its raw data URI and digest. 4. A curated dataset is reproducible from its source campaigns. 5. The capability catalogue reflects observed availability, not an assertion |
| **Dependencies** | WP-2.1, WP-0.7 |
| **Size** | 140 EW [PILL 3, ONT 1, TEST 1] |
| **Pod type** | PILL (B) |

### WP-2.4 — Rate and cost simulation

| Field | Value |
|---|---|
| **Pillar** | B (capability **B-4**) |
| **Description** | The discrete-event production simulation and the what-if capability for rate increases, workforce shifts and supply disruption, driven by `Facility.surgeCapacity`, `Supplier` lead times and `Skill` availability |
| **Deliverables** | The simulation engine; the parameterisation from the ontology; the what-if interface; the rate and cost curve output; the calibration harness |
| **Acceptance criteria** | 1. The simulated surge rate for ≥ 3 facilities is within 15% of observed historical peaks. 2. The model states its confidence interval. 3. A what-if over a supply disruption and a workforce shift runs without manual re-parameterisation. 4. The simulation reads its parameters from the ontology, not from a spreadsheet. 5. Every run is reproducible from its seed and parameter set |
| **Dependencies** | WP-2.1, WP-1.6 |
| **Size** | 150 EW [PILL 3, MLOPS 1, TEST 1] |
| **Pod type** | PILL (B) |

### WP-2.5 — Unified test data lake

| Field | Value |
|---|---|
| **Pillar** | C (capability **C-1**) |
| **Description** | The test data platform: ground, tunnel, sled and flight data ingested with full configuration context; the lakehouse layout; the curation and the dataset catalogue; the retention and classification handling |
| **Deliverables** | The test data service; the lakehouse schema; the dataset catalogue; the configuration-context assembly; the ingestion pipeline for each test type |
| **Acceptance criteria** | 1. 100% of `TestResult` records in the pilot corpus carry a non-empty `configurationSnapshot` naming the variant, lot numbers, software build and instrument calibration state. 2. A `TestResult` without a configuration snapshot is rejected at write. 3. A dataset is traceable to the campaigns that produced it. 4. Raw data is in the object store with a digest and the log holds the pointer. 5. The lakehouse is partitioned by classification and inherits the classification of its source evidence |
| **Dependencies** | WP-0.7, WP-1.1 |
| **Size** | 180 EW [PLAT 3, PILL 2, TEST 1] |
| **Pod type** | PILL (C) |

### WP-2.6 — Automated reduction and anomaly detection

| Field | Value |
|---|---|
| **Pillar** | C (capability **C-2**) |
| **Description** | The automated reduction pipelines that turn raw telemetry into measurements, and the near-real-time anomaly surfacing for thermal, structural and aero signals; the pipeline provenance recorded on each result |
| **Deliverables** | The reduction pipeline framework; the thermal, structural and aero pipelines; the anomaly detection service; the `reductionPipeline` provenance block on the result |
| **Acceptance criteria** | 1. Measurements in a `TestResult` carry a `reductionPipeline` provenance block with a pipeline version, input URI and input digest. 2. An anomaly surfaces within 15 minutes of result ingestion. 3. A seeded anomaly in a thermal channel is detected with ≤ 10% false-positive rate on clean channels. 4. The reduction is reproducible: re-running the pipeline on the same input with the same version produces the same measurements. 5. The anomaly flag appears on the result and in the console |
| **Dependencies** | WP-2.5, WP-0.12 |
| **Size** | 170 EW [MLOPS 3, PILL 2, TEST 1] |
| **Pod type** | PILL (C) |

### WP-2.7 — Twin validation loop

| Field | Value |
|---|---|
| **Pillar** | C (capability **C-3**) |
| **Description** | The flight-versus-simulation comparison and the automatic model update: the validation job that consumes `test.result.recorded`, scores fidelity, emits `model.validated` and updates the `Model` entity; the envelope narrowing and widening rules |
| **Deliverables** | The validation job; the fidelity scoring implementations per model type; the `model.validated` emission; the envelope update logic; the dependency notification to affected pillars |
| **Acceptance criteria** | 1. A `test.result.recorded` produces a `model.validated` within 30 minutes. 2. `evidenceTestResultIds` and `priorFidelity` are populated. 3. The `causationId` chain from result to validation to fidelity update is one traversal. 4. An envelope narrowing is applied automatically; an envelope widening is refused without a named human approval. 5. The loop runs across ≥ 3 model types. 6. A `Model.fidelity` not produced by a `model.validated` event is detected and reported as a defect |
| **Dependencies** | WP-2.5, WP-0.12, WP-2.6 |
| **Size** | 150 EW [MLOPS 3, PILL 2] |
| **Pod type** | PILL (C) |

### WP-2.8 — Campaign management and range coordination

| Field | Value |
|---|---|
| **Pillar** | C (capability **C-4**) |
| **Description** | Test planning, the instrumentation manifest, the range coordination exchange through IF-4, the capacity model on the campaign plan, and the active-learning objective for selecting the next most informative test |
| **Deliverables** | The campaign planning service; the instrumentation manifest builder; the IF-4 exchange adapter; the capacity model; the optimisation objective |
| **Acceptance criteria** | 1. A campaign plan is exchanged with a range and the range's slot and instrumentation manifest are reflected in the campaign record. 2. The capacity model reports feasibility, telemetry coverage and conflicts. 3. The optimisation objective is recorded on the plan with a method, target requirements and a score. 4. A plan is reproducible from its inputs. 5. The exchange round-trips through IF-4 without manual translation |
| **Dependencies** | WP-2.3, WP-2.5 |
| **Size** | 160 EW [PILL 3, PLAT 1, TEST 1] |
| **Pod type** | PILL (C) |

**Increment 2 total: ~1,310 EW.**

## 7. Increment 3 work packages

### WP-3.1 — Multi-tier visibility and supplier risk

| Field | Value |
|---|---|
| **Pillar** | D (capability **D-1**) |
| **Description** | Multi-tier supplier visibility, the supplier risk scoring model, capacity monitoring, and the chain-of-custody population from the MES traveller |
| **Deliverables** | The supplier registry; the tier-2 visibility ingestion; the risk scoring service; the capacity monitoring; the provenance integration with the MES |
| **Acceptance criteria** | 1. ≥ 50 suppliers are scored, with the score derived from observed data — lead-time variance, single-source flags, tier depth, domestic content — and reproducible from the ontology. 2. Tier-2 visibility exists for at least one critical sub-tier. 3. The chain of custody is populated from the traveller without manual entry. 4. A risk score change is traceable to the data that caused it. 5. C-007 reports every `CRITICAL` + `isSingleSource` part lacking a `reconstitutes` edge |
| **Dependencies** | WP-2.1, WP-0.7 |
| **Size** | 150 EW [PILL 3, ONT 1, TEST 1] |
| **Pod type** | PILL (D) |

### WP-3.2 — Foreign dependency mapping

| Field | Value |
|---|---|
| **Pillar** | D (capability **D-2**) |
| **Description** | The mapping of critical single-source nodes — CMC precursors, high-temp electronics — to their suppliers and facilities, and the identification of reconstitution candidates |
| **Deliverables** | The critical-node map; the foreign-dependency classification; the reconstitution candidate identification; the export-control linkage on `Part.exportControlled` and `Supplier.exportControlled` |
| **Acceptance criteria** | 1. ≥ 20 critical nodes are mapped with reconstitution candidates and lead times. 2. Each mapped node has a `reconstitutes` edge or an explicit risk flag. 3. The export-control flags are accurate against the jurisdiction flag on `Part` and `Supplier`. 4. A node whose only supplier is foreign and export-controlled is flagged for review. 5. The map is reproducible from the ontology |
| **Dependencies** | WP-3.1, WP-0.2 |
| **Size** | 120 EW [PILL 3, SEC 1] |
| **Pod type** | PILL (D) |

### WP-3.3 — Surge readiness twin

| Field | Value |
|---|---|
| **Pillar** | D (capability **D-3**) |
| **Description** | The continuously refreshed model of peacetime to conflict production scaling, running against live facility and supplier data with a weekly refresh and an archived output |
| **Deliverables** | The twin service; the weekly refresh pipeline; the archived weekly outputs; the confidence interval computation; the facility and supplier input bindings |
| **Acceptance criteria** | 1. The twin refreshes weekly against live data with no manual step. 2. The confidence interval narrows monotonically over 8 consecutive weekly runs. 3. An independent manual reconciliation agrees with the model within the stated interval. 4. Week-over-week comparison is possible from the archive. 5. The twin runs in the DP-5 profile and its compute is scheduled, not resident |
| **Dependencies** | WP-3.1, WP-2.4 |
| **Size** | 140 EW [PILL 3, MLOPS 1, TEST 1] |
| **Pod type** | PILL (D) |

### WP-3.4 — Surge readiness command

| Field | Value |
|---|---|
| **Pillar** | H (capability **H-1**) |
| **Description** | The programme-facing surface of the surge model: the verified surge rate with a stated confidence interval, the weekly report, the queries the programme office can ask, and the assignment of an owner to the figure |
| **Deliverables** | The surge reporting service; the programme-office query interface; the weekly report; the owner assignment and sign-off record |
| **Acceptance criteria** | 1. A programme-office question on surge readiness is answered in ≤ 1 working day from the platform, with the evidence trail attached. 2. The reported surge rate carries a confidence interval and a named owner. 3. The reported figure is traceable to the twin run that produced it. 4. A change to the underlying data changes the next weekly report. 5. The query interface does not require the programme office to run a query themselves |
| **Dependencies** | WP-3.3, WP-0.13 |
| **Size** | 110 EW [PILL 3, ONT 1] |
| **Pod type** | PILL (H) |

### WP-3.5 — Reconstitution planning

| Field | Value |
|---|---|
| **Pillar** | H (capability **H-2**) |
| **Description** | The reconstitution playbooks for critical node loss, the candidate evaluation, and the measured time-to-reconstitute metric |
| **Deliverables** | The playbook generator; the candidate evaluation; the tabletop exercise instrumentation; the time-to-reconstitute metric |
| **Acceptance criteria** | 1. ≥ 10 playbooks exist, each with a measured time-to-reconstitute obtained from a tabletop exercise, not an estimate. 2. Each playbook names the critical node, the candidates, the lead times and the dependencies. 3. A playbook failure mode produces a named escalation. 4. The measured time is recorded in the ontology and feeds the programme KPI |
| **Dependencies** | WP-3.2 |
| **Size** | 110 EW [PILL 3, TEST 1] |
| **Pod type** | PILL (H) |

### WP-3.6 — Affordability engineering

| Field | Value |
|---|---|
| **Pillar** | H (capability **H-3**) |
| **Description** | The cost trace from requirement to design decision to unit cost, the unit-cost prediction against rate curves, and the linkage that feeds the affordable missile family and future reusable aircraft programmes |
| **Deliverables** | The cost trace model; the unit-cost prediction; the rate-curve integration; the affordability report; the `CostEstimate` quality controls |
| **Acceptance criteria** | 1. A cost trace exists from ≥ 50 requirements through allocated design elements to unit cost. 2. Every cost estimate carries a `basis` and a `confidence`. 3. No `PARAMETRIC` estimate is presented as an `ACTUAL`; the console distinguishes them. 4. The unit-cost prediction against the rate curve is produced and its error against actual is measured. 5. The trace is queryable from a single requirement |
| **Dependencies** | WP-1.2, WP-2.4, WP-3.4 |
| **Size** | 140 EW [PILL 3, ONT 1, TEST 1] |
| **Pod type** | PILL (H) |

**Increment 3 total: ~770 EW.**

## 8. Increment 4 work packages

### WP-4.1 — Threat digital twins

| Field | Value |
|---|---|
| **Pillar** | F (capability **F-1**) |
| **Description** | The reconstruction of threat systems from intelligence, telemetry and range observation into versioned, confidence-scored `ThreatSystem` entities with supporting `Model` versions, including the fusion of multi-source observations |
| **Deliverables** | The threat reconstruction service; the observation fusion; the confidence scoring; the model versioning for threat kinematics; the `ThreatSystem` lineage |
| **Acceptance criteria** | 1. ≥ 5 threat systems are reconstructed with versioned models. 2. Every `ThreatSystem` has a `confidence`, an observation lineage through `derivedFrom`, and versioned `Model` entities. 3. A threat model with no applicability envelope is rejected at write. 4. A reconstruction is reproducible from its observation set. 5. The P-R floor is enforced: no `ThreatSystem` exists in P-C |
| **Dependencies** | WP-0.9, WP-0.12 |
| **Size** | 180 EW [PILL 3, MLOPS 2, SEC 1, TEST 1] |
| **Pod type** | PILL (F) |

### WP-4.2 — Kill-chain simulator and Monte Carlo engine

| Field | Value |
|---|---|
| **Pillar** | F (capability **F-2**) |
| **Description** | The detect → track → custody → engage end-to-end model for candidate architectures, the Monte Carlo engine, the surrogate models that accelerate it, and the `EngagementScenario` configuration and results |
| **Deliverables** | The chain model; the Monte Carlo engine; the surrogate model training; the scenario configuration API; the results summary |
| **Acceptance criteria** | 1. A 10,000-run batch completes in < 4 hours on a dedicated partition. 2. The run count, seed and confidence level are recorded on the `EngagementScenario`. 3. At least 2 architectures are modelled, including HBTSS with WFoV/MFoV cueing into Aegis and GPI. 4. A run is reproducible from its seed. 5. The surrogate's fidelity envelope is published and the engine refuses to use it outside it |
| **Dependencies** | WP-4.1, WP-0.12 |
| **Size** | 220 EW [PILL 4, MLOPS 2, TEST 1] |
| **Pod type** | PILL (F) |

### WP-4.3 — Fire-control data quality scoring

| Field | Value |
|---|---|
| **Pillar** | F (capability **F-3**) |
| **Description** | The continuous measurement of custody handover quality, track purity and fire-control solution error against thresholds, ingesting IF-3 data and reporting breaches |
| **Deliverables** | The IF-3 ingestion adapter; the three metric implementations; the threshold configuration; the breach alerting; the reporting cadence |
| **Acceptance criteria** | 1. The three metrics are measured continuously from IF-3 feeds. 2. Thresholds are defined and a breach raises an alert. 3. Each metric is traceable to the underlying observations. 4. The measurement is reproducible from the feed data. 5. The metric definition and its threshold change are audited |
| **Dependencies** | WP-0.7, WP-4.1 |
| **Size** | 140 EW [PILL 3, ONT 1, TEST 1] |
| **Pod type** | PILL (F) |

### WP-4.4 — Interim architecture workbench

| Field | Value |
|---|---|
| **Pillar** | F (capability **F-4**) |
| **Description** | The Project Maverick-style composition of existing sensors and offboard cueing into candidate interim solutions, with virtual validation before flight test |
| **Deliverables** | The composition interface; the sensor and cueing plugin model; the candidate evaluation; the virtual validation flow |
| **Acceptance criteria** | 1. ≥ 5 candidate interim architectures are composed and virtually evaluated. 2. Each candidate's sensor chain and effector chain are stored as `EngagementScenario` attributes. 3. A candidate's evaluation produces results traceable to the models it used. 4. An out-of-envelope model in a candidate chain is refused rather than silently used. 5. The workbench runs in DP-5 and dispatch to Z-2 is exercised |
| **Dependencies** | WP-4.2 |
| **Size** | 150 EW [PILL 3, ONT 1, TEST 1] |
| **Pod type** | PILL (F) |

### WP-4.5 — Golden Dome readiness plug-in framework

| Field | Value |
|---|---|
| **Pillar** | F (capability **F-5**, first slice) |
| **Description** | The reference-architecture plug-in framework for the homeland missile-defense shield: the plug-in contract, the plug-in host, and one reference plug-in |
| **Deliverables** | The plug-in contract; the plugin host; one reference plug-in; the documentation for a third party to write a plug-in |
| **Acceptance criteria** | 1. A third party can write a plug-in against the published contract without NGSH source access. 2. The reference plug-in loads, runs a scenario and is removed without affecting the host. 3. A plug-in that declares an out-of-envelope dependency is refused at load. 4. The plug-in contract is versioned with the compatibility rules of [ADR-0002](../adr/ADR-0002-json-schema-contracts-over-shared-libraries.md) |
| **Dependencies** | WP-4.2, WP-0.1 |
| **Size** | 130 EW [PILL 3, PLAT 1] |
| **Pod type** | PILL (F) |

### WP-4.6 — Red/blue co-simulation

| Field | Value |
|---|---|
| **Pillar** | F (capability **F-6**) |
| **Description** | The co-simulation of strike performance against defence performance against identical threat models, and the assurance that the same `ThreatSystem` node is used in both traces |
| **Deliverables** | The co-simulation harness; the identity assertion across traces; the comparison report |
| **Acceptance criteria** | 1. A single co-simulation uses the identical `ThreatSystem` node in both traces. 2. The platform demonstrates that both traces resolve to the same node id. 3. No duplicate or parallel threat model exists in the platform. 4. The comparison report states the threat model version and the evidence behind it. 5. The co-simulation is reproducible from its seed and scenario configuration |
| **Dependencies** | WP-4.1, WP-4.2, WP-2.5 (the strike-side trace needs test data) |
| **Size** | 120 EW [PILL 3, TEST 1] |
| **Pod type** | PILL (F) |

### WP-4.7 — Virtual test range federation

| Field | Value |
|---|---|
| **Pillar** | G (capability **G-1**) |
| **Description** | The cloud-federated range: the federation of ground, tunnel, sled and flight data with physics M&S, the virtual campaign, and the substitution of virtual for physical test slots |
| **Deliverables** | The federation protocol; the virtual campaign engine; the site federation adapters; the physical-to-virtual substitution analysis |
| **Acceptance criteria** | 1. The range spans ≥ 2 federated sites. 2. ≥ 10 physical range slots are allocated to a virtual campaign, and the virtual campaign's design converged on the physical test plan in ≥ 7 of 10 cases. 3. The ratio of virtual engagements per physical flight test consumed is measured and reported against the PSDD §12 target of ≥ 10×. 4. A federated site can be added without changing the platform. 5. The federation respects the classification boundary — a CUI site cannot join an IL6 campaign |
| **Dependencies** | WP-2.5, WP-2.8, WP-4.2 |
| **Size** | 200 EW [PILL 3, PLAT 2, TEST 1] |
| **Pod type** | PILL (G) |

### WP-4.8 — Campaign digital twin and range scheduling

| Field | Value |
|---|---|
| **Pillar** | G (capability **G-2**) |
| **Description** | The range capacity, telemetry coverage and target and instrumentation availability model, with cross-DoD scheduling optimisation and the capacity model on the campaign plan |
| **Deliverables** | The capacity model; the coverage model; the scheduling optimiser; the `capacityModel` block on the campaign plan |
| **Acceptance criteria** | 1. Capacity and coverage are modelled across ≥ 2 ranges. 2. The optimiser produces a schedule that improves on the historical baseline by a stated margin. 3. The capacity model reports feasibility, coverage and conflicts on the plan. 4. A scheduling decision is reproducible from its objective and inputs. 5. The optimiser respects classification and accreditation constraints on ranges |
| **Dependencies** | WP-2.8, WP-4.7 |
| **Size** | 160 EW [PILL 3, MLOPS 1, TEST 1] |
| **Pod type** | PILL (G) |

### WP-4.9 — Automated model validation service

| Field | Value |
|---|---|
| **Pillar** | G (capability **G-3**) |
| **Description** | The production-grade automated validation: the scoring implementations for aero, thermal and plasma models, the regeneration trigger, and the multi-pillar consumption of `model.validated` |
| **Deliverables** | The scoring implementations per model type; the regeneration orchestration; the dependency notification; the validation campaign interface |
| **Acceptance criteria** | 1. The loop runs across ≥ 3 physics model types. 2. Each `model.validated` carries a comparable `method` so that fidelity improvement per campaign is measurable. 3. `regenerationTriggered: true` produces a new `modelVersion` with `approvedForUse: false`. 4. A dependency notification reaches a dependent pillar when a score moves beyond the materiality threshold. 5. The fidelity improvement per campaign is reported against the PSDD §12 KPI |
| **Dependencies** | WP-2.7, WP-0.12 |
| **Size** | 160 EW [MLOPS 4, PILL 1, TEST 1] |
| **Pod type** | PILL (G) |

### WP-4.10 — Fidelity registry and model governance at scale

| Field | Value |
|---|---|
| **Pillar** | G (capability **G-4**) |
| **Description** | The fidelity registry in its production form: the index across every model in the platform, the model card completeness enforcement, the approval queue, the drift monitoring, and the retirement workflow |
| **Deliverables** | The registry index; the card completeness gate; the approval queue with ageing; the drift monitoring dashboards; the retirement workflow |
| **Acceptance criteria** | 1. Every model in the platform has a registry entry with provenance, validation history and an applicability envelope. 2. A model without a complete card fails the release gate. 3. The approval queue is aged and reported; a model cannot remain unapproved indefinitely without a visible state. 4. Drift monitoring is live for every model type in use, with a threshold per type. 5. A drift breach above the suspend threshold withdraws approval automatically and the dependent pillars are notified |
| **Dependencies** | WP-0.12, WP-4.9, WP-2.2 |
| **Size** | 140 EW [MLOPS 3, ONT 1, SEC 1] |
| **Pod type** | MLOps |

**Increment 4 total: ~1,600 EW.**

## 9. Increment 5 work packages

### WP-5.1 — Modularity engine and family-of-systems generation

| Field | Value |
|---|---|
| **Pillar** | A (capability **A-2**) |
| **Description** | The library-based architecture enforcement and the automatic generation of family-of-system variants from a common core |
| **Deliverables** | The library model; the common-core definition; the variant generator; the library compliance enforcement; the `familyId` and `distinguishingCharacteristics` handling |
| **Acceptance criteria** | 1. ≥ 20 variants are generated from a common core, each with a `Variant` entity, a `familyId` and a complete bill of materials. 2. A configuration error introduced in the core is detected in all 20 variants. 3. The generator is reproducible: the same core produces the same variant set. 4. A variant that violates the library is refused. 5. The generated variants are individually licensable and configurable |
| **Dependencies** | WP-1.1, WP-2.1 |
| **Size** | 220 EW [PILL 4, ONT 2, TEST 1] |
| **Pod type** | PILL (A) |

### WP-5.2 — Technology insertion planner

| Field | Value |
|---|---|
| **Pillar** | A (capability **A-4**) |
| **Description** | The TRL/SRL mapping against production slots, the insertion candidate assessment, and the rapid integration workflow for a selected technology |
| **Deliverables** | The TRL/SRL mapping model; the production slot model; the candidate assessment; the insertion workflow; the insertion impact report |
| **Acceptance criteria** | 1. ≥ 5 technologies are inserted against real production slots. 2. The TRL/SRL mapping is recorded and is accurate against the `Subsystem.maturity` values. 3. The slot conflict analysis is accurate against the facility and supplier data. 4. An insertion produces a variant or a configuration change that is traceable. 5. The impact of an insertion on cost and schedule is reported |
| **Dependencies** | WP-5.1, WP-3.4 |
| **Size** | 170 EW [PILL 3, ONT 1, TEST 1] |
| **Pod type** | PILL (A) |

### WP-5.3 — Digital engineering SaaS and SysML v2 environment

| Field | Value |
|---|---|
| **Pillar** | A (capability **A-5**) |
| **Description** | The SysML v2 environment, the requirement management integration, the ICD generation, and the pre-integrated DoN reference architectures, aligned to OpenMBEE and SysML v2 (PSDD §8) |
| **Deliverables** | The SysML v2 environment and its exchange adapters; the requirement management integration; the ICD generator; the reference architecture catalogue |
| **Acceptance criteria** | 1. The environment exchanges models with ≥ 2 external tools via OpenMBEE-aligned exchange, with round-trip fidelity verified on a representative model. 2. ≥ 10 interfaces have generated ICDs matching the `Interface` entities' `characteristics`, verified against the referenced systems. 3. Requirements synchronise between the environment and the ontology without divergence, and divergence is detected. 4. The reference architecture catalogue contains at least 3 pre-integrated architectures. 5. The environment is usable without the NGSH console for the modelling tasks |
| **Dependencies** | WP-1.2, WP-5.1 |
| **Size** | 280 EW [PILL 5, ONT 2, TEST 1] |
| **Pod type** | PILL (A) |

### WP-5.4 — Full-stack integration and flight demonstration readiness

| Field | Value |
|---|---|
| **Pillar** | A (completion of **A-1** and **A-3**) plus programme integration |
| **Description** | The cross-pillar integration: the cross-pillar query surfaces, the complete requirement-to-flight trace on a real configuration baseline, the demonstration-article readiness, and the full-stack integration test programme |
| **Deliverables** | The cross-pillar query layer; the complete trace implementation; the demonstration readiness pack; the full-stack integration test suite; the cross-pillar performance baseline |
| **Acceptance criteria** | 1. For one real flight article, 100% of baselined requirements have a verification status derived from a `TestResult`, a `TestCampaign` or an approved `Model` analysis, and the full trace is reproducible. 2. A single programme-office query spans at least four pillars and returns in ≤ 30 seconds. 3. The configuration baseline, test evidence, verification status and cost trace are present and consistent for the demonstration article. 4. The full-stack integration suite runs end to end against the flight-article scenario. 5. All eight pillars deploy and run independently against the published contracts only, with no cross-pillar store access |
| **Dependencies** | WP-1.1, WP-1.2, WP-5.1, WP-5.2, WP-5.3, WP-2.1, WP-4.6 |
| **Size** | 300 EW [PLAT 3, ONT 2, PILL 2, TEST 2] |
| **Pod type** | PLAT |

### WP-5.5 — Programme-wide verification, accreditation package and release

| Field | Value |
|---|---|
| **Pillar** | Programme (cross-cutting) |
| **Description** | The final qualification and release: the full conformance and qualification evidence, the complete accreditation package for the full scope, the release and rollback rehearsal, the operator documentation, and the handover to the programme office |
| **Deliverables** | The full qualification evidence pack; the accreditation package for the full platform scope; the release and rollback rehearsal record; the operator and administrator documentation; the handover pack |
| **Acceptance criteria** | 1. Every increment exit criterion is re-verified on the release candidate. 2. The accreditation package covers all four deployment profiles and all partitions in scope. 3. A full rollback is rehearsed in DP-5 and the previous digest is restored within the published objective. 4. The seeded-tamper suite and the negative isolation suite pass on the release candidate. 5. A programme office administrator completes the documented operational tasks without engineering support |
| **Dependencies** | All Increment 5 packages |
| **Size** | 130 EW [SEC 2, PLAT 1, TEST 2] |
| **Pod type** | SEC |

**Increment 5 total: ~1,100 EW.**

## 10. Pod loading

| Increment | PLAT | ONT | SEC | PILL | TEST | MLOPS | EDGE | Total pods |
|---|---|---|---|---|---|---|---|---|
| 0 | 1.0 | 1.0 | 1.5 | 0.5 | 0.5 | 0.0 | 0.5 | 5.0 |
| 1 | 0.5 | 0.5 | 1.0 | 3.0 | 0.5 | 0.0 | 0.0 | 5.5 |
| 2 | 0.5 | 1.0 | 0.5 | 4.5 | 1.0 | 1.0 | 0.0 | 8.5 |
| 3 | 0.0 | 0.5 | 0.5 | 3.5 | 0.5 | 0.5 | 0.0 | 5.5 |
| 4 | 0.5 | 1.0 | 1.0 | 6.0 | 1.0 | 1.5 | 0.5 | 11.5 |
| 5 | 1.0 | 1.5 | 1.0 | 3.0 | 1.0 | 0.5 | 0.0 | 8.0 |
| **Peak** | | | | | | | | **11.5** |

**Loading rules.**

| # | Rule |
|---|---|
| 1 | Every pod is 6–9 engineers. See [`../staffing.md`](../staffing.md) |
| 2 | Security is embedded, never a silo. The SEC figure above is the *lead* security capacity; every pillar pod additionally carries an embedded security engineer. The SEC pod leads SEC-ENV, the SEC-ASSESS and the governance work |
| 3 | Every pillar pod includes a systems engineer and a test engineer. This is a composition rule, not a capacity rule |
| 4 | MLOps is present from Increment 2, because that is when the first production model enters service |
| 5 | The Edge / Field pod is present from Increment 0 and grows with the number of pilot sites. It is the pod that makes the platform work at a factory, not just in a datacentre |
| 6 | The Test & Qualification pod grows with the number of deployment profiles in scope, because each profile needs its own conformance and isolation evidence |

**The pilot-site relationship.** The Edge / Field pod's size is driven by the number of pilot sites in parallel, not by the number of software work packages. Each site requires hardware, an installation, a clock-discipline verification, a policy bundle installation, a site accreditation letter and operator training. This is a linear cost per site and it is the constraint that most often surprises a plan.

## 11. Critical path and near-critical chains

| Chain | Packages | Why it is critical |
|---|---|---|
| **Critical** | WP-0.1 → WP-0.3 → WP-0.4 → WP-1.1 → WP-1.2 → WP-2.1 → WP-2.5 → WP-4.7 → WP-5.4 | The contract substrate, the log, the projection, the configuration baseline, the trace, the MES, the test data, the virtual range and the full-stack integration. Every other path eventually joins this one |
| **Near-critical** | WP-0.1 → WP-0.2 → WP-0.5 → WP-0.9 → WP-1.7 → WP-2.2 → WP-2.7 → WP-4.9 | The validation and partitioning chain. It is the chain that produces the credibility of every downstream result |
| **Near-critical** | WP-0.1 → WP-0.8 → WP-0.9 → WP-2.8 → WP-4.7 | The edge and range chain. It constrains how quickly a new site can be fielded |
| **Near-critical** | WP-0.10 → WP-1.5 → WP-1.6 | The workforce chain, which carries the Pillar E revenue event and therefore the programme's first funding milestone |
| **External-bound** | WP-4.1 → threat-data access | The threat-model data access is a chokepoint (PSDD §13, R-04). No engineering work can substitute for the access |
| **External-bound** | WP-2.2 → DASH-MOT ecosystem CMC data | The characterisation model needs real process data with real drift |
| **External-bound** | WP-1.3 → WISH partner institutions | The pilot sites are not selected by the programme alone |

**Compression options, in order of preference.**

| # | Option | Effect | Cost |
|---|---|---|---|
| 1 | Run Increment 3 and Increment 4 concurrently after Increment 2 | Saves 3–4 months | Requires a larger organisation and careful data-boundary management between industrial-base and threat work |
| 2 | Add pods to the critical chain, not to the whole increment | Scales the critical path directly | Pod onboarding cost of 6–9 engineers, and a clearance-processing lead time that is outside the programme's control |
| 3 | Reduce the number of pillars in the first pass | Not recommended | It breaks the one-ontology argument, which is the platform's core thesis |
| 4 | Build the 2027 validation event capability in Increment 0 as a reduced configuration | Saves nothing on the critical path and risks a second ontology | Explicitly rejected in [`increments.md`](increments.md) §10 |

## 12. References

**PSDD:** §5.1–§5.8 (the pillar capability ids each work package delivers), §7 (IF-1..IF-7), §8 (non-functional requirements, Modularity, AI/ML, Auditability), §9 (AI/ML services), §11 (phasing and the standalone-product rule), §12 (KPIs used as acceptance measures), §13 (risks), §14 (teaming strategy).

**Contracts:** `contracts/ontology/registry.json`, `contracts/ontology/entities.schema.json`, `contracts/ontology/relations.schema.json`, `contracts/ontology/common.schema.json`, `contracts/events/catalog.json`, `contracts/events/event-envelope.schema.json`.

**Architecture:** [`../architecture/03-foundation-services.md`](../architecture/03-foundation-services.md) (the API surfaces the work packages implement), [`../architecture/02-ontology-model.md`](../architecture/02-ontology-model.md) §7 (the ontology change-control path), [`../architecture/04-security-architecture.md`](../architecture/04-security-architecture.md) (the security obligations each package must satisfy).

**ADRs:** all eight in [`../adr/`](../adr/README.md).

**Planning:** [`increments.md`](increments.md), [`../staffing.md`](../staffing.md), [`../risk-register.md`](../risk-register.md).
