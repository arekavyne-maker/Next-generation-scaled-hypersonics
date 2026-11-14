# ADR-0001: The Event Log Is the System of Record

## Status

Accepted

## Date

2026-11-14

## Context

NGSH is a dual-mission platform whose central claim is a single shared ontology carrying a digital thread across parts, processes, tests, threats and people (PSDD §4.1, §4.2 principle 1). The same `Part` node must trace a U.S. CMC article from powder lot to flight article, and the same `TestResult` node must hold a wind-tunnel run, a sled shot and a flight campaign outcome (PSDD §6.1).

PSDD §6.2 names six storage technologies: a property graph, a time-series database, an S3-compatible object store, a NoSQL document store, an open-format lakehouse, and a vector index. PSDD §6.3 requires an immutable, append-only test-result ledger and end-to-end automated data lineage. PSDD §8 requires that "every model version, test result, and access decision" be reconstructable.

Those requirements pull in opposite directions. A digital thread is a history. A graph store optimized for traversal is a mutable present-tense state. If the graph is authoritative, then history lives only in a mutable structure, lineage is reconstructed by comparing snapshots, an in-place mutation is indistinguishable from a legitimate correction, and the append-only ledger required by PSDD §6.3 becomes a parallel bookkeeping exercise that can drift from the truth.

The contract layer already commits to one answer. `contracts/events/event-envelope.schema.json` states in its own description: *"The event log is the system of record; the graph, search indexes, lakehouse and vector index are projections rebuilt by replay."* The envelope defines `occurredAt` versus `recordedAt` as a deliberate split between physical-world fact time and fabric acceptance time, plus `causationId`, `correlationId` and `transactionId`. The entity contract `contracts/events/entity.created.schema.json` embeds the full entity body in the payload so that "the event log alone can rebuild every projection." Constraint C-003 in `contracts/ontology/registry.json` states that a `TestResult` is immutable once written and corrections are new events carrying `supersedesRef`.

This ADR ratifies that commitment, specifies the operational consequences, and states explicitly where the rule is permitted to be broken.

## Decision

**The append-only event log is the authoritative system of record for NGSH. Every other store — graph, time-series, object store, document store, lakehouse, vector index — is a derived projection that can be dropped and rebuilt from the log without loss of authoritative state.**

Concretely:

| Rule | Statement |
|---|---|
| DR-1.1 | All state mutation enters NGSH through exactly one path: append of a schema-valid event envelope to the log. No service writes directly to a projection store. |
| DR-1.2 | The write path is command-oriented. Callers submit intent; the fabric appends the fact. A caller's `POST /parts` does not create a part in the graph — it causes an `entity.created` event, whose projection creates the graph node. |
| DR-1.3 | All ten event types in `contracts/events/catalog.json` are the only vocabulary of state change: `entity.created`, `entity.updated`, `entity.relation.asserted`, `entity.relation.retracted`, `test.campaign.planned`, `test.result.recorded`, `process.run.completed`, `model.validated`, `ingest.batch.accepted`, `access.decision.recorded`. |
| DR-1.4 | The envelope is mandatory and universal: `eventId`, `eventType`, `eventVersion`, `aggregateType`, `aggregateId`, `sequence`, `occurredAt`, `recordedAt`, `tenant`, `actor`, `payload` (per `contracts/events/event-envelope.schema.json`, `required`). |
| DR-1.5 | `eventId` is a ULID and doubles as the idempotency key for at-least-once delivery. `idempotencyKey`, scoped to `(tenant, eventType)`, is the caller-supplied variant. |
| DR-1.6 | `sequence` is monotonic per aggregate and is the sole concurrency-control mechanism. There is no database-level row lock and no last-write-wins on a shared mutable row. Two writers to the same aggregate contend on sequence, not on a table. |
| DR-1.7 | `occurredAt` is the physical-world fact time; `recordedAt` is the fabric acceptance time and is authoritative for ordering. `recordedAt` is never earlier than `occurredAt`. |
| DR-1.8 | Causality is explicit: `causationId` names the command or event that directly caused this one; `correlationId` spans one logical request or campaign; `transactionId` groups events that a projection must apply atomically. |
| DR-1.9 | Replay is deterministic. Ordering key is `(aggregateType, aggregateId, sequence)`, then `eventId` lexicographic as the final tiebreak. A projection built by replaying the log in this order is byte-identical to one built in real time, given the same log. |
| DR-1.10 | `TestResult` never emits `entity.updated`. A correction is a new `test.result.recorded` carrying `supersedesRef` (C-003). The superseded result remains in the log and in the graph, marked superseded. |
| DR-1.11 | Every event carries `classification` and `actor`. Classification is a property of the *fact*, not of the storage cell that happens to hold it. |
| DR-1.12 | The log is retained in full. Compaction may archive superseded payload bodies to a cold store, but it must preserve the superseding chain, the envelope metadata, and the ordering keys. Archiving is not deletion. |

### Snapshot policy

Snapshots exist, but they are caches, never authority.

| Aspect | Rule |
|---|---|
| Purpose | Avoid full replay on every restart. Nothing else. |
| Cadence | A projection checkpoints every 10 million applied events or every 15 minutes of applied-event time, whichever comes first. |
| Content | Projection-side state plus the `(aggregateType, aggregateId, sequence)` high-water mark and the `eventId` of the last applied event. |
| Trust | A snapshot is admissible only if its high-water mark matches the log. A snapshot whose high-water mark cannot be confirmed against the log is discarded and the projection is rebuilt. |
| Format | Versioned independently of the projection implementation. A snapshot written by build N is readable by build N+1 for at least 4 releases. |
| Deletion | Snapshots are disposable at any time. There is no operational procedure that requires keeping one. |
| Authority rule | If a snapshot and the log disagree, the log wins and the snapshot is regenerated. There is no merge, no reconciliation heuristic, no manual fix path. |

### Replay cost and the budget it implies

Full replay is O(total events). The architecture accepts this and constrains the platform so that replay stays affordable:

| Quantity | Target | Notes |
|---|---|---|
| Projection apply rate, single-node | ≥ 500,000 events/s | Go data plane, batched graph upserts |
| Full projection rebuild, 10^9 events | ≤ 2 hours | Single-node reference implementation; scales horizontally by partition |
| Full projection rebuild, 10^10 events | ≤ 24 hours | Requires snapshot-assisted replay; measured, not assumed |
| Projection lag behind log tail (steady state) | ≤ 5 s | Enforced as an SLO with alerting |
| Projection lag behind log tail (degraded) | ≤ 60 s before alerts escalate | |

The budget is kept affordable by never putting bulk bytes in the log. Raw telemetry samples, imagery and large artifacts live in the object store and the time-series store; the log carries a reference and a SHA-256 digest (the `Attachment` type in `contracts/ontology/common.schema.json` carries `uri` + `sha256` + `sizeBytes` + `classification`). One `test.result.recorded` event may point at 40 GB of reduced telemetry and cost 4 KB of log.

### When it is permitted to break the rule

Breaking the rule means writing to a projection outside the event path. It is permitted only in the four enumerated cases below, each with a named compensating control.

| # | Case | Permitted operation | Compensating control |
|---|---|---|---|
| X-1 | Bulk sensor telemetry | Samples are written directly to the time-series store and object store | The log carries a `process.run.completed` or `ingest.batch.accepted` event with `sensorChannels[].uri` + `sha256` + `sampleRateHz`, so the bytes remain discoverable, digest-verified and lineage-linked |
| X-2 | Large binary artifacts | Bytes go to the object store | Log carries the `Attachment` reference with digest; the graph carries the pointer plus integrity digest, never the payload |
| X-3 | Historical backfill (legacy data, one-time migration) | A controlled loader may write projection rows directly | The loader must synthesize `entity.created` / `entity.updated` events with `provenance.source` set to the backfill identifier and `provenance.method` set to the loader version, then append them to the log. **The backfill is not complete until the synthetic events are appended.** |
| X-4 | Query cannot be served by the log at the required latency | — | **Not permitted.** This case is resolved by appending a *derived summary event* that makes the log answerable, or by adding a projection. Direct projection writes are never the remedy. |

No other exception exists. In particular, there is no "fast path" for high-volume writes and no "bulk update" API for operators.

### When the rule should be revisited

This ADR should be re-opened if any of the following becomes true:

1. A proven requirement demands cross-aggregate ACID transactions spanning more than one aggregate, which the `transactionId` mechanism can only approximate.
2. Regulatory or contractual obligation requires that a specific artifact be provable *without* replaying the log (the answer is then the audit ledger in [ADR-0005](ADR-0005-tamper-evident-audit-ledger.md), not abandoning the log).
3. Measured replay cost exceeds the budget above by an order of magnitude for a projection that cannot be snapshot-assisted.
4. A pillar's read latency requirement cannot be met by any projection of the log, and the gap cannot be closed by adding a projection.

## Alternatives Considered

### ALT-1. Graph-first: the property graph is the system of record

*Rejected.* The property graph is the best possible answer to "show me the trace from this CMC lot to this flight article", and it is the worst possible answer to "who changed this, when, and what did it say before". In-place mutation destroys provenance, which PSDD §6.3 requires for lineage and PSDD §10 requires for Program Protection Plan artifacts. It also puts the audit trail (PSDD §8 Auditability) on the same storage path as the data it audits — a single compromised service with graph write access would silently rewrite history. The graph is retained, but as a projection.

### ALT-2. Relational OLTP as the source of truth, change-data-capture into a log

*Rejected.* This is the classical transactional-outbox pattern and it is genuinely good at mutable operational state. It was rejected for NGSH because it creates two authoritative-looking copies that must be reconciled, because CDC of *graph edges* into a property graph is a well-known source of subtle divergence (ordering, tombstones, multi-hop retractions), and because the classification-partitioning posture required by PSDD §10 is far simpler when there is exactly one write path to partition. It also puts an OLTP schema in the critical path of a platform whose stated interoperability posture is "open APIs, OpenMBEE/SysML v2 alignment" (PSDD §8) — a relational core schema is a strong anchor against future schema churn.

### ALT-3. Document store (MongoDB/CouchDB-style) as the system of record

*Rejected.* Excellent for heterogeneous entity bodies, weak for the relation semantics that the digital thread is actually about. The 10 canonical relation types in `contracts/ontology/relations.schema.json` with explicit `fromTypes`, `toTypes` and `cardinality` would be enforced in application code rather than by the store, and the projection into the property graph would become a second, lossy transformation rather than a faithful replay. Classification partitioning is also markedly harder: key-prefix partitioning by document does not align with the graph-level edges that carry classification.

### ALT-4. Lakehouse (open table format) as the system of record

*Rejected.* A lakehouse is the right *destination* for curated ML training corpora (PSDD §6.2), and `ingest.batch.accepted` with `format: "PARQUET"` shows it is a first-class projection. It is the wrong system of record: point reads are slow, write semantics are batch-oriented with latency measured in minutes, and it cannot express a per-aggregate monotonic `sequence` as a concurrency primitive. The specific thing that would break is C-003: making a `TestResult` immutable is trivial when the unit of write is a log record and awkward when the unit of write is a partition overwrite.

### ALT-5. Keep the event log but treat it as an audit trail only, with the graph authoritative

*Rejected.* This is the most tempting alternative, because it preserves the graph's query performance and the log's immutability. It fails on one concrete requirement: constraint C-002 requires that a relation may not cross a classification boundary unless its type is declared `mayCrossClassification=true`. Enforcing that rule at write time requires knowing the classification of both endpoints — which means the write path must see the graph. If the graph is authoritative and separate from the write path, C-002 is unenforceable and becomes a nightly consistency check. The decision is to make the log the place where C-001 through C-008 are enforced, once, at the point of append.

## Consequences

### Positive

| # | Consequence |
|---|---|
| P-1 | The full audit trail required by PSDD §8 (Auditability) is a by-product of the write path, not a parallel instrumentation effort. Every fact carries `actor`, `occurredAt`, `recordedAt`, `classification` and `provenance`. |
| P-2 | Lineage for CMMC assessment and Program Protection Planning (PSDD §6.3, §10) is computable by graph traversal over `derivedFrom` and `Provenance.parentRefs`, because lineage was never a derived property — it was in the record. |
| P-3 | Constraint enforcement (C-001..C-008) has a single, well-defined enforcement point: the append path, with the registry in `contracts/ontology/registry.json` as the rule source. |
| P-4 | Replay is the disaster-recovery mechanism. A lost or corrupted projection store is a ticket, not an incident. |
| P-5 | Multi-pillar integration is cheap. A pillar that needs a CMC process history consumes `process.run.completed` and replays it into its own store; it never has to ask Pillar B for a query API. |
| P-6 | Test-coupled M&S (PSDD §4.2 principle 4) is implementable as a projection: `test.result.recorded` → fidelity scoring → `model.validated`. The causality is explicit via `causationId`. |
| P-7 | The `idempotencyKey` mechanism gives clean at-least-once ingestion semantics for range instrumentation feeds (IF-4), where duplicate delivery is the normal case. |

### Negative

| # | Consequence |
|---|---|
| N-1 | Every read path is a read of a projection, so projections are on the critical path for query latency even though the log is on the critical path for writes. Two latencies to manage instead of one. |
| N-2 | Storage amplification: the same fact exists in the log and in up to five projections. A `Part` with 40 attributes costs a few KB in the log and perhaps 50 KB across projections. |
| N-3 | Deletion is hard. The `deleted` flag in `EntityHeader` is a soft delete; GDPR-style or "destroy this contractor's data" requirements require either a tombstone-plus-suppression policy or an explicit exemption with a documented justification. This is a real cost and must be handled in the data-retention work package, not ignored. |
| N-4 | Read-your-writes is not free. After an append, a caller querying the graph sees stale data until the projection catches up (target ≤ 5 s). Callers needing read-your-writes must use the `sequence` high-water mark or a synchronous projection path. |
| N-5 | The log becomes the most valuable asset in the system and therefore the primary target. Compromise of the log compromises everything. This is why the log is append-only at the storage layer, partitioned by classification ([ADR-0007](ADR-0007-classification-partitioning.md)), and separately attested by the audit ledger ([ADR-0005](ADR-0005-tamper-evident-audit-ledger.md)). |
| N-6 | The event schema is a long-term public commitment. Every one of the ten event types and 23 entity types becomes a compatibility surface for every pillar, partner and academic consumer. |
| N-7 | Schema evolution becomes an engineering discipline with a CI cost, rather than a database migration. |

### What this makes harder

| # | Harder thing | Why |
|---|---|---|
| HW-1 | Bulk editing and data cleanup | There is no `UPDATE` and no `DELETE`. A correction to a `Part` is an `entity.updated` with a new `version`; a correction to a `TestResult` is a new `test.result.recorded` with `supersedesRef`. Operator tooling must be built to express intent as events. |
| HW-2 | Exploratory query during development | Developers lose "just look at the table". Mitigations: a read-only projection with a lag indicator, and a `fabricctl replay --to <sequence>` scratch environment. |
| HW-3 | Schema evolution of entities | Entity attribute changes are `entity.updated` events with `changedFields`. A *structural* change to an entity type requires a new `eventVersion` for the events that carry it — see [ADR-0002](ADR-0002-json-schema-contracts-over-shared-libraries.md). |
| HW-4 | Cross-aggregate transactional integrity | `transactionId` lets a projection apply a set atomically, but the log itself does not offer two-phase commit across aggregates. A projection that needs strict atomicity across aggregates must implement a compensating pattern. |
| HW-5 | Very high write rates from a single aggregate | `sequence` is per aggregate; a hot aggregate (one test article receiving 10^8 telemetry-derived updates) would create a hot partition. Mitigated by aggregating telemetry into summaries before appending (rule X-1), never by appending raw samples. |

## Compliance Notes

| PSDD / regulatory obligation | How this ADR supports it |
|---|---|
| PSDD §8 Auditability — "Every model version, test result, and access decision reconstructable" | The three named artifacts map to three event types: `model.validated`, `test.result.recorded`, `access.decision.recorded`. Reconstruction is replay, not forensics. |
| PSDD §6.3 — "Full audit trail; immutable test-result ledger (append-only)" | Implemented as C-003 plus rule DR-1.10. The business ledger is the log; a *separate* tamper-evident attestation of it is specified in [ADR-0005](ADR-0005-tamper-evident-audit-ledger.md). |
| PSDD §6.3 — "Data lineage automated end-to-end (supports CMMC assessment and program protection planning)" | `Provenance.parentRefs`, the `derivedFrom` relation and `causationId` give three independent lineage traversals. |
| PSDD §8 Modularity — "All pillars independently deployable and licenseable" | A pillar subscribes to the log and owns only its projections; it never reaches into another pillar's store. This is the mechanism that makes independent deployment true rather than aspirational. |
| PSDD §8 Availability — 99.9% core fabric | The log's append path is the only stateful critical path; projection stores can be rebuilt. Availability of the fabric is availability of the append path. |
| CMMC 2.0 L2 (AU family) | Audit records are produced by the write path itself (AU-2, AU-3, AU-10). Event immutability supports AU-9 (protection of audit tools). |
| CMMC 2.0 L2 (CA family) | Append-only storage with per-record digests supports CA-3 (control of information transferred) and the integrity argument used at CA-2 assessments. |
| CMMC 2.0 L2 (SI family) | Integrity verification of the log supports SI-7. |
| ITAR/EAR (PSDD §10) | Classification is carried on the event, and C-001 is enforceable at append time, so an export-control determination can be made on the write path rather than during a later query. |

## References

**PSDD:** §4.1 (concept: two layers, one ontology), §4.2 (design principles 1 and 4), §6.1 (core ontology), §6.2 (data stores), §6.3 (data governance), §8 (Non-Functional Requirements — Auditability, Availability, Modularity), §9 (AI/ML governance), §10 (Security & Compliance Architecture).

**Contracts:**
- `contracts/events/event-envelope.schema.json` — the envelope; explicitly designates the event log as system of record.
- `contracts/events/catalog.json` — the ten event types; `catalogVersion` and per-type `eventVersion` semantics.
- `contracts/events/entity.created.schema.json` — full entity body embedded so the log alone can rebuild projections.
- `contracts/events/entity.updated.schema.json` — `changedFields`, `previousVersion`; states that immutable types must not emit it.
- `contracts/events/test.result.recorded.schema.json` — `supersedesRef` and the immutability note.
- `contracts/events/model.validated.schema.json` — `causationId`-linked fidelity update path.
- `contracts/ontology/registry.json` — C-003 (immutability), C-007 (post-scope criticality check), relation `requiresProvenance`.
- `contracts/ontology/common.schema.json` — `EntityHeader.deleted` (soft delete), `Provenance.parentRefs`, `Attachment.uri`/`sha256`.

**Related ADRs:** [ADR-0002](ADR-0002-json-schema-contracts-over-shared-libraries.md) (schema versioning discipline for the log's payload types), [ADR-0005](ADR-0005-tamper-evident-audit-ledger.md) (separate attestation of the log), [ADR-0006](ADR-0006-edge-degraded-mode-and-reconciliation.md) (how the log survives disconnection), [ADR-0007](ADR-0007-classification-partitioning.md) (physical partitioning of the log and its projections).
