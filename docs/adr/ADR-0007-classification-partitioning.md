# ADR-0007: Physical Classification Partitioning of Storage

## Status

Accepted

## Date

2026-11-14

## Context

PSDD §10 fixes the deployment pattern: a GovCloud IL5 enclave, an on-prem IL6 annex for classified threat data and fire-control data, and edge nodes at factories and ranges. PSDD §6.3 requires ITAR/EAR partitions, sanitized extracts for academic partners, and CUI tagging at ingestion. PSDD §4.2 principle 6 requires "ITAR/EAR data partitioning from day one". The ontology registry assigns a `classificationFloor` to every one of the 23 entity types and a `mayCrossClassification` flag to every one of the 10 relation types, and constraints C-001, C-002 and C-008 exist specifically to enforce classification behaviour at write, write and read scope respectively.

The architectural question is where classification enforcement lives. The natural answer is "in the application": every query filters by classification, every write checks the floor, every export strips restricted fields. This is what most systems do, and it is what the phrase "attribute-based access control" suggests.

The problem with that answer is that it makes the *entire* confidentiality property of the system depend on the correctness of application code in every one of six foundation services and eight pillars, with no independent enforcement. A single missed filter in one query builder is a disclosure. In a platform whose purpose includes holding classified threat reconstructions and clearance-verified workforce records, that is not an acceptable single point of failure — and it is not an acceptable posture at assessment, either, because the demonstration of "no cross-boundary access" becomes a sampling exercise across every query path in the codebase.

The counter-argument to physical partitioning is real: partitioning is expensive, it makes cross-partition questions hard, and it means duplicating infrastructure per classification level. The question is not whether partitioning is free — it is not — but whether the properties it buys are properties the program requires.

PSDD §10 also names a specific mechanism for the crossing case: "ICAP-class guard services for sanitized extract generation (academic sandbox)". That is an acknowledgement that the crossing from classified to unclassified is a special, controlled, auditable operation, not a general capability.

## Decision

**NGSH physically partitions every storage tier by classification level. A record's partition is determined by its classification and is immutable for the life of the record. The only path from a classified partition to a lower partition is a one-way, guarded, audited extraction pipeline. Application-layer filtering is retained as a defence layer but is never the primary control.**

### Partition model

Classification levels are the ones declared in `Classification.level`: `UNCLASSIFIED`, `CUI`, `CUI//REL`, `CUI//FOUO`, `RESTRICTED`, `SECRET`, `TOP SECRET`.

| Partition | Holds | Physical realisation |
|---|---|---|
| **P-U** | UNCLASSIFIED — including all sanitized extracts | Dedicated object-store prefix, dedicated graph instance, dedicated document collection, dedicated lakehouse schema, dedicated vector index |
| **P-C** | CUI, CUI//REL, CUI//FOUO | Separate object-store bucket and key namespace, separate graph instance, separate document store, separate lakehouse schema, separate vector index |
| **P-R** | RESTRICTED — threat systems, threat observations, engagement scenarios | Separate instances again. The `classificationFloor` of `ThreatSystem`, `ThreatObservation` and `EngagementScenario` in the registry is `RESTRICTED`, so these types cannot exist in P-C at all |
| **P-S** | SECRET and TOP SECRET | IL6 annex only. No partition exists outside the IL6 enclave |
| **P-L** | Local / edge, scoped to the site's accreditation | Per-site instances, never shared with another site or zone |

`CUI//REL` and `CUI//FOUO` share partition P-C because they are CUI derivatives; the caveat travels with the record in `Classification.caveats` and is enforced by policy, not by partition. Partitioning by caveat would multiply partitions without adding a confidentiality boundary, since a caveat restricts *disclosure*, not *access by a cleared actor*.

### Partition assignment and immutability

| # | Rule |
|---|---|
| P-1 | A record's partition is derived from its `classification.level` at write time. The write is routed to that partition's stores by the ingest or fabric path. A record never sits in a store that is not its partition's store |
| P-2 | **Partition immutability.** A record's partition never changes. A record's classification may be *raised* in place (the record moves to a higher partition and the lower copy is tombstoned with `deleted: true` and a `supersededBy` annotation). A record's classification is never *lowered* in place |
| P-3 | **Downgrade prohibition.** Lowering a classification requires creating a *new* entity with a new id, in the lower partition, whose `Provenance.parentRefs` names the original, whose `Provenance.derivedFromClassified` chain is recorded, and whose `Classification.derivedFromClassified` is `true`. The original stays in its partition. This is enforced as a write-time check in the fabric append path and is an extension of C-001 |
| P-4 | A relation may only be asserted within a partition, or across partitions if the relation type has `mayCrossClassification: true` in the registry (C-002). Only `derivedFrom` and `requiresSkill` are cross-capable. A cross-partition relation is stored in the *lower* partition with a pointer into the higher one, and the pointer is not dereferenced by readers without a PEP decision |
| P-5 | The query path is bound to a partition. A service instance holds credentials for exactly the partitions it is accredited for. There is no query interface that spans partitions, because there is no credential that spans partitions |
| P-6 | Each partition is an independent instance of every store: its own graph database, its own object-store namespace, its own document collection, its own time-series database, its own lakehouse schema, its own vector index. Sharing an instance with a row-level filter is explicitly rejected (see Alternatives) |
| P-7 | Backups, snapshots, exports and logs are partition-scoped. An operator cannot take a backup of P-C without separately taking one of P-S, and the two backups are administered under different authorisations |
| P-8 | The `classificationFloor` in the registry is enforced as a *floor*, not a ceiling. An entity may be classified above its floor. A `Part` with a `CUI` floor may be recorded as `RESTRICTED` |

### Downgrade prevention

Three layers, and the storage layer is the one that does not depend on application correctness:

| Layer | Control | Mechanism |
|---|---|---|
| 1. Type floor | An entity's classification may never be lower than the `classificationFloor` of its type (C-001) | Registry lookup at append time. Rejects the write. Enforced in the fabric append path, not in a caller |
| 2. Partition placement | A record is physically written only into the partition matching its classification | The routing decision is made in the append path; the storage credential for a partition cannot write to another partition's store |
| 3. Monotonicity | Classification never decreases in place; lowering requires a new entity in a lower partition with an explicit provenance link (P-3) | Append-path check: an `entity.updated` that lowers `classification.level` is rejected. The new-entity path is a different operation and is audited as `classification-downgrade` |

C-001 is the registry-level rule; layers 2 and 3 are the operational realisation of it plus the monotonicity extension that the registry does not currently state. **The monotonicity extension is a required contract change**, listed under Required Contract Changes below.

### One-way sanitized extracts for academic partners

The academic sandbox (Pillar E-5, IF-5) is fed by a one-way pipeline. There is no path back.

| Stage | Component | Rule |
|---|---|---|
| 1. Request | A request for an extract is raised against a *view* — a named, versioned subset of the ontology — not against raw data | The request names a view id and a time range |
| 2. Selection | A selection service inside the classified zone selects records matching the view | Only records whose `classification.level` is at or below the extract's ceiling are eligible |
| 3. Transformation | A **guard service** performs the sanitisation: field-level removal, value generalisation, unit conversion, date shifting, identifier re-mapping, and removal of `Provenance.parentRefs` chains that would lead to restricted content | The guard is the only component with read access to both the classified source and the unclassified destination |
| 4. Review | A human reviewer (or a validated automated classifier plus a human spot-check) approves the transformed content | The approval is recorded in the audit ledger before the extract is released |
| 5. Release | The guard writes the sanitized artifact to partition P-U, content-addressed, with a manifest | The manifest lists the source record ids, the transformation rules applied, the guard version, the reviewer, and the classification ceiling |
| 6. Anchoring | The manifest is anchored to the audit ledger | The manifest is the evidence that the extract was produced, from what, under which rules |
| 7. No return path | The academic environment receives only the sanitized artifact and the manifest | There is no interface from P-U to any classified partition. The academic environment is in P-U |

Two properties of this design are load-bearing:

- **The guard is a chokepoint.** Because the classified partition has no other egress route to P-U, the guard is not a service that *should* be applied but the only one that *can* be. There is no path around it.
- **The extract is a new fact, not a copy.** The sanitized artifact gets its own id, its own provenance and its own classification. It is not a read of the original; it is a derived, separately classified record. Its `Provenance.derivedFromClassified` is true and its `parentRefs` are replaced by the manifest reference. This is what makes the downgrade prohibition (P-3) hold even for sanctioned extractions.

### ICAP-style guard

The guard is modelled on an ICAP service because that pattern already encodes the required properties: an explicit policy, an explicit transformation, and a chokepoint position in the path.

| ICAP concept | NGSH guard equivalent |
|---|---|
| Service definition | The guard service, with a versioned transformation profile per view |
| Adaptation | The selection stage — which records are in scope for this extract |
| Detection | The classification screen — reject any record above the extract ceiling |
| Prevention | The transformation — removal, generalisation, re-mapping |
| Remediation | The review-and-approve gate, with the reviewer recorded |
| Caching | None. The guard holds no classified content beyond the working set of one extract, and the working set is destroyed after release |
| Fail mode | Fail closed. If the guard cannot complete a transformation, the extract is not released. Partial extracts are not a supported output |

### Why application-layer filtering alone is insufficient

| # | Gap | Consequence of relying on the app layer |
|---|---|---|
| 1 | A missed filter in one of many query paths | A disclosure with no independent barrier. The blast radius of a single query-builder bug is the entire partition |
| 2 | Time-of-check to time-of-use | The PEP checks classification at the start of a request; a join, a traversal, or a cached plan can reach a node the check did not cover |
| 3 | No separation of duties for storage administrators | A storage administrator with query access to a shared store can read classified content without ever passing through a PEP, and no access decision is recorded |
| 4 | Bulk extraction becomes trivial | An authorised user with a legitimate query capability can pull a complete classified corpus through an ordinary API, one page at a time, and the volume is not bounded by any control |
| 5 | It cannot demonstrate "no downgrade" | An assessor asking "how do you know content was never moved to a lower partition?" cannot be answered by "the application filters correctly". Physical placement answers it |
| 6 | It does not scale with data volume | At the PSDD §8 target of ≥ 10 GB/s burst ingestion, re-evaluating a classification filter over every record of a batch, and redaction at query time, is the bottleneck. Classification must be resolved once, at write, into a physical location |
| 7 | It cannot contain a compromised service | If a service is compromised, the partitioning is what limits the blast radius to one classification level. Filtering does not help at all |
| 8 | It does not survive a shared store | A multi-tenant shared store makes the storage administrator the weakest link and creates a resource-exhaustion path where one tenant's query affects another's data |

Application-layer filtering is **retained** as a layer: it produces better user experience, it enforces need-to-know and program scoping within a partition, and it is the layer that implements the obligations from [ADR-0004](ADR-0004-abac-with-pdp-pep-separation.md). It is simply not the only thing standing between a CUI record and a SECRET record.

### Required contract changes

| # | Change | File | Rationale |
|---|---|---|---|
| 1 | Add an explicit monotonicity rule to the registry constraint catalogue — "C-009: an entity's classification may not be lowered in place; a downgrade creates a new entity in a lower partition with `derivedFromClassified=true` and a `parentRefs` link to the original" | `contracts/ontology/registry.json` | Rule P-3. C-001 constrains the *floor*; it does not prevent a downgrade from `SECRET` to `CUI` for a type whose floor is `CUI`. The prohibition is currently only a design intention |
| 2 | Add `partitionId` to the `Attachment` type, and to the `Classification` header as the resolved partition | `contracts/ontology/common.schema.json` | Lets a reader and an auditor determine where a record physically resides without consulting deployment configuration, and lets the guard's manifest reference the partition explicitly |
| 3 | Add a `classification-downgrade` action to the audited verb list, with the source id, the target id and the approving reviewer | audit ledger entry schema (to be created under WP-0.6) | The downgrade path is the most sensitive operation in the platform and must be distinguishable in the ledger from an ordinary write |

## Alternatives Considered

### ALT-1. Single store with a classification column, enforced by row-level security / partitioned views

*Rejected.* This is the standard application-layer answer and it fails on gaps 1, 2, 3, 5, 6 and 7 above. Its decisive defect is the compromised-service case: a single store means a single service credential can reach every row, so the confidentiality boundary exists only in the code path that was compromised. The storage administrator is also a single point of disclosure, and row-level security on a shared engine is typically implemented in the same database process that serves the application query — so a query that escapes the policy is a query that escapes the storage layer too. For a platform that must hold threat reconstructions and clearance-verified workforce records, this does not meet the posture PSDD §10 describes.

### ALT-2. Enclave-per-classification with no intra-zone partitioning

*Rejected.* A simpler variant: the IL5 enclave holds everything CUI and below; the IL6 annex holds everything above CUI. This is cheaper and it is a real boundary. It was rejected because it does not match the data. The academic sandbox (Pillar E-5) needs sanitized content in a world-unconnected environment that has no relationship to the IL5 enclave at all; if UNCLASSIFIED content lives in the IL5 enclave, the academic environment must reach into the enclave, which breaks the one-way property and forces the enclave to hold content that is not sensitive — a larger attack surface and a larger accreditation scope for no benefit. Separating P-U from P-C costs one more set of instances and makes the academic sandbox a genuinely separate environment, which is what the one-way extract pipeline was designed to produce.

### ALT-3. Label-based access control with tag inheritance, applied at the storage engine

*Rejected.* Tag inheritance is an attractive model for expressing "this record inherits the classification of its parent" without storing the label explicitly, and it was seriously considered for the graph traversal problem, where a node's effective classification is the maximum over its neighbours' partitions. It was rejected because: the tagging engine becomes a second, implicit policy system whose correctness is as hard to demonstrate as the application filters it replaces; tag propagation bugs silently mislabel records, and a mislabel is a silent disclosure in the *label* store itself; and the effective classification of a traversal is already computed by the thread service's PEP, which has the graph context the tagging engine lacks. Where tag inheritance is used, it is used only as an *assist* for the read-side PEP, never as the enforcement mechanism.

### ALT-4. Encrypt-by-level with a per-level key, over a shared store

*Rejected as insufficient.** Per-level keys with envelope encryption do not solve the problem. A query path that must read content across levels must hold or derive multiple keys, so the key-holding component reaches every level; and it does not stop a legitimate read of a lower-level record from being *used* to infer classified content. Encryption-at-rest is necessary and is specified in `04-security-architecture.md`; it is not a substitute for placement. Per-level keys are retained as an additional layer, so that a compromised P-U store cannot expose P-C ciphertext in a form that is trivially decryptable with a widely-scoped key.

### ALT-5. Logical partitioning through separate schemas / namespaces in one shared instance

*Rejected.* This is a common cost-saving move and it fails gap 3 and gap 7 for the same reason as ALT-1: one instance, one administrative domain, one set of credentials. It also fails gap 6 (the engine's query planner must still evaluate the classification predicate over every row). The cost saving is real but it is spent from the confidentiality budget.

### ALT-6. Two-way replication of content into lower partitions for performance, with periodic re-classification

*Rejected.* Replicating a SECRET record into a CUI partition, even temporarily, creates a window in which a partition boundary is violated, and that window is invisible in an audit unless the replication is itself logged. It also destroys the property that the *location* of a record states its classification, which is the property that makes an assessment tractable. If performance requires denormalised lower-level data, the correct construction is a **sanitized extract** through the guard, which is a classified-to-unclassified operation with an approval and a manifest, not a replication job.

## Consequences

### Positive

| # | Consequence |
|---|---|
| P-1 | The confidentiality boundary is physical and independent of application correctness. A bug in a query builder cannot move a SECRET record into a CUI partition. |
| P-2 | The blast radius of a compromised service is bounded by its partition credential. A compromised P-C service cannot read P-R. |
| P-3 | The storage administrator is no longer a single point of disclosure for the whole corpus, and their actions are separable from application actions. |
| P-4 | Downgrade is structurally prevented rather than policed. P-3 makes a downgrade an explicit, auditable, new-entity operation rather than a state change that happens to be checked. |
| P-5 | The one-way extract pipeline is genuinely one-way. The academic sandbox (E-5, IF-5) has no path into a classified partition, so the "least privilege" claim for academic partners is structural. |
| P-6 | Assessment is tractable. "Show that a CUI record never appears in a higher partition" is a physical inspection. "Show that no query returns a SECRET row" is a sampling exercise across the entire codebase. |
| P-7 | Multi-tenancy and classification compose. The tenant filter and the partition filter are enforced by different mechanisms at different layers. |
| P-8 | The classification ceiling of a deployment profile falls out of the partition model: DP-L is P-U only, DP-5 is P-U + P-C, DP-6 is P-U + P-C + P-R + P-S. |

### Negative

| # | Consequence |
|---|---|
| N-1 | Infrastructure cost multiplies by the number of partitions. Four store instances per zone, times three zones. This is the single largest cost driver of the platform build. |
| N-2 | Cross-partition questions are hard. A trace that crosses a partition boundary cannot be answered in one query. This is the principal analytical pain of the platform and it is real — see HW-1. |
| N-3 | Operational burden: four sets of backups, four sets of capacity plans, four sets of upgrade procedures, four sets of dashboards. |
| N-4 | The guard service is on the critical path for every academic deliverable and every sanitized report to a partner. It becomes a queue that must be staffed. |
| N-5 | Content that legitimately spans partitions — for example a `TestResult` that references a RESTRICTED `ThreatObservation` — must be represented as a cross-partition pointer rather than a copy, which changes the ergonomics of the thread service. |
| N-6 | Partition count grows with classification diversity. If the program introduces a new caveat that must be a partition, the infrastructure bill grows. The decision to keep CUI//REL and CUI//FOUO inside P-C is a specific mitigation of this. |
| N-7 | Developers must think about partitioning in every query path, which slows feature work and is a permanent tax on the engineering organisation. |

### What this makes harder

| # | Harder thing | Why |
|---|---|---|
| HW-1 | Cross-partition trace analysis | The digital thread's most valuable queries often span levels — for example, a flight test result (CUI) referencing a threat observation (RESTRICTED) in an engagement scenario (RESTRICTED). The resolution is a *bridge*: a dedicated service instance holding credentials for both partitions, whose queries are themselves audited and whose results are themselves re-classified to the higher level. The bridge is a high-value asset and a high-value target, and it must be deliberately small and heavily monitored |
| HW-2 | One aggregate spanning partitions | `Requirement` (CUI floor) and `EngagementScenario` (RESTRICTED floor) are different aggregates, so this is manageable — but `TestResult` (CUI floor) referencing `ThreatObservation` (RESTRICTED) means a `verifies` relation whose endpoints are in different partitions. C-002 permits only `derivedFrom` and `requiresSkill` to cross, so the `verifies` edge must live in P-C with a non-dereferenceable pointer into P-R. The model has to represent that, and the UI has to explain it |
| HW-3 | One ontology, many partitions | The 23 entity types and 10 relation types are defined once but instantiated across partitions. A single type's instances live in different places, so a query for "all TestResults" is a fan-out across partitions. The tenant-scoped API hides this from most callers, but the thread service must implement the fan-out, and it must apply the PEP per partition |
| HW-4 | Extract latency | A sanitized extract is a reviewed, approved, anchored artifact. It is not instant. Academic partners and program offices must plan for the lead time. This has to be communicated early, because "give me the data now" is the most common expectation |
| HW-5 | Classification on ingest from an untrusted source | A range instrument sends a file with no classification header. The ingest PEP must classify it before it enters a partition. Misclassification at ingest puts content in the wrong partition — a physical error, not a logical one. The ingest path therefore requires a default-deny rule: unclassified content enters P-C at worst, never P-U, until a human or a validated classifier says otherwise |
| HW-6 | Testing partition isolation | The CI suite must attempt to read across partitions and assert that it fails. A test that only asserts successful reads within a partition will pass on a broken implementation. Negative isolation tests are mandatory |
| HW-7 | Keeping the registry's floors and the deployed partitions in step | A new entity type with a `classificationFloor` of `RESTRICTED` requires that the P-R partition exist and be accredited before the type is usable. The type and the partition are coupled, and the change-control path for a new type must therefore include a partition-readiness check |

## Compliance Notes

| PSDD / regulatory obligation | How this ADR supports it |
|---|---|
| PSDD §4.2 principle 6 — "ITAR/EAR data partitioning from day one" | Partitioning is a physical property of the storage tier from the first increment, not a later hardening phase. |
| PSDD §6.3 — "ITAR/EAR partitions; sanitized extracts for academic partners" | Directly implemented; the one-way extract pipeline is the mechanism for Pillar E-5 and IF-5. |
| PSDD §6.3 — "CUI tagging at ingestion" | Classification is resolved at ingest and determines physical placement, so the tag is not advisory metadata. |
| PSDD §8 Security — "Zero trust; IL5 baseline with IL6 annex architecture" | Zero trust requires that no implicit trust zone exists. Partitioning removes the implicit zone in the storage tier. |
| PSDD §8 Auditability | Every partition placement and every extraction is auditable; the manifest and the anchor make the extract reconstructable. |
| PSDD §10 — "Deployment pattern: GovCloud IL5 enclave + on-prem IL6 annex (classified threat data, fire-control data) + edge nodes" | The partition map maps one-to-one onto the accreditation boundaries: P-U/P-C in the IL5 enclave, P-R and P-S in the IL6 annex, P-L per edge site. |
| PSDD §10 — "Cross-domain: ICAP-class guard services for sanitized extract generation (academic sandbox)" | The guard is specified as an ICAP-style service with adaptation, detection, prevention, remediation and a fail-closed mode. |
| PSDD §10 — "Program protection: PPP artifacts generated automatically from data lineage" | Physical placement gives the PPP artifact a verifiable claim: "this content was never in a lower-partition store", which is checkable rather than asserted. |
| CMMC 2.0 L2 (SC family) | SC-7 (boundary protection) is materially stronger with physical partitions; SC-28 (protection of information at rest) is layered with per-level encryption. |
| CMMC 2.0 L2 (CA family) | CA-3 (control of information transferred) is the guard pipeline; the extract manifest is the transfer record. |
| CMMC 2.0 L2 (AC family) | AC-4 (information flow enforcement) between partitions is structural: no credential spans a partition boundary. |
| CMMC 2.0 L2 (AU family) | Partition-crossing attempts, extract approvals and downgrade attempts are all in the audit ledger. |
| ITAR / EAR (22 CFR 120-130, 15 CFR 730-774) | Export-controlled content is gated by citizenship at the PEP ([ADR-0004](ADR-0004-abac-with-pdp-pep-separation.md)) and by physical placement, so a foreign-citizen request cannot even reach the store containing ITAR content. `Part.exportControlled` and `Supplier.exportControlled` carry the jurisdiction flag. |
| CNSSI 5016.1 / 32 CFR 2002 | Caveat handling travels with the record in `Classification.caveats`, and the original classification authorities travel in `Classification.origins`. |

## References

**PSDD:** §4.1 (zone sketch), §4.2 principles 3 and 6, §5.5 (Pillar E-5 industry–academia sandbox; Pillar E credentialing and PII), §6.1 (ontology types and their classification floors), §6.2 (the six data stores that are partitioned), §6.3 (data governance — CUI tagging, ITAR/EAR partitions, sanitized extracts, lineage), §7 IF-5 and IF-6 (academic consumers and identity), §8 (Security, Availability, Auditability), §9 (AI/ML — models inherit the classification of their evidence), §10 (Security & Compliance Architecture), §13 (risks — classification friction, threat-data access chokepoint).

**Contracts:**
- `contracts/ontology/common.schema.json` — `Classification` with `level` enum, `caveats`, `origins`, `derivedFromClassified`; `EntityHeader.classification`; `Attachment.classification`; `Actor.clearance` and `Actor.citizenship`.
- `contracts/ontology/registry.json` — `classificationFloor` per entity type (`UNCLASSIFIED` for `Skill`, `CUI` for most types, `RESTRICTED` for `ThreatSystem`, `ThreatObservation` and `EngagementScenario`); `pii: true` for `Credential` and `Person`; `mayCrossClassification: true` only for `derivedFrom` and `requiresSkill`; C-001 (floor), C-002 (boundary), C-005/C-006 (clearance validity), C-007 (single-source critical parts), C-008 (scenario read clearance).
- `contracts/ontology/entities.schema.json` — `Part.exportControlled`, `Supplier.exportControlled`, `Person.citizenship`, `Person.clearanceLevel`, `Person.clearanceExpiry`, `Facility.securityLevel`.
- `contracts/events/event-envelope.schema.json` — `classification` on every envelope, so a record's partition is derivable from the log.
- `contracts/events/access.decision.recorded.schema.json` — the decision record for any cross-partition or extract-related request.

**Related ADRs:** [ADR-0001](ADR-0001-event-sourced-foundation.md) (the log is partitioned with everything else; the append path is where the partition routing decision happens), [ADR-0003](ADR-0003-platform-agnostic-hybrid-deployment.md) (zone topology and deployment profiles), [ADR-0004](ADR-0004-abac-with-pdp-pep-separation.md) (the layered enforcement model and the citizenship gate), [ADR-0005](ADR-0005-tamper-evident-audit-ledger.md) (the ledger records partition-crossing attempts and extract approvals), [ADR-0006](ADR-0006-edge-degraded-mode-and-reconciliation.md) (Step 5's classification gate in reconciliation), [ADR-0008](ADR-0008-model-card-and-fidelity-registry.md) (a model's applicability envelope and evidence set inherit classification).
