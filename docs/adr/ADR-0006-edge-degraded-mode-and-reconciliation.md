# ADR-0006: Edge Degraded Mode and Deterministic Reconciliation

## Status

Accepted

## Date

2026-11-14

## Context

PSDD §4.2 principle 3 requires the platform to be deployable at the edge, with factory-floor and range annexes synchronised to the central fabric. PSDD §8 requires "edge annexes degraded-mode capable with later sync". PSDD §7 IF-4 defines bi-directional range instrumentation exchange (test article manifests, telemetry, schedules) — the interface most likely to be exercised in poor connectivity. PSDD §3.3 (scope) includes federated M&S and virtual test range capability, which implies multiple geographically separated sites producing facts about the same aggregates.

Degraded mode is not an error condition. A range annex on a bad link, a factory floor during a network maintenance window, and an air-gapped IL6 annex doing offline analysis are all *normal operating states* of the platform. The architecture must therefore treat disconnected operation as a designed capability with specified behaviour, specified merge semantics and specified limits.

The hard part is not buffering. It is the merge. Once two sites have independently modified the same aggregate, the platform must produce a *deterministic* result — the same inputs must always yield the same state — and the result must be *explainable* to the engineers who will use it to make decisions about flight hardware.

What makes this difficult in NGSH specifically:

1. **Some facts are immutable and some are not.** Constraint C-003 makes a `TestResult` immutable once written: a correction is a new event carrying `supersedesRef`. Two sites that both record a result for the same article and campaign are not in a conflict that can be resolved by a rule; they are in a situation that must be *detected and escalated*, because the physical test happened once or twice, and the platform cannot adjudicate physics.
2. **The ordering guarantee in the log is per-aggregate.** The envelope's `sequence` is "per-aggregate monotonic sequence" that "enforces optimistic concurrency and enables deterministic replay ordering". The aggregate's sequence space is therefore single-writer by construction — which is exactly the invariant a disconnected multi-writer site breaks.
3. **Clock skew is a physical fact, not a bug.** A range annex without a reference clock will drift. The envelope already carries `edge.clockSkewMs` to record the delta at reconciliation, which means the design has already accepted that skew exists and must be *recorded*, not hidden.
4. **Classification travels with the fact.** A conflicting pair of edits may not have the same classification, and the merge rule must not be the thing that downgrades content ([ADR-0007](ADR-0007-classification-partitioning.md)).

## Decision

**Edge nodes operate a durable store-and-forward queue, run in a defined degraded mode, and reconcile with the fabric using a deterministic, rule-based merge. Where the rules cannot decide, the platform escalates to a human rather than guessing.**

### Degraded mode

| Aspect | Behaviour |
|---|---|
| Write path | Edge writes are appended to a durable, encrypted local queue (WAL-backed) with a per-aggregate local sequence allocator. The edge does not attempt to write to the fabric |
| Read path | Reads are served from the local projection cache. The read result is identical whether or not the fabric is reachable — this is a hard requirement, not a best effort |
| Identity | The edge validates the actor against a signed policy bundle and a locally cached clearance attribute set. It does not require the PDP to be reachable to decide; it requires the bundle to be unexpired |
| Classification | The edge holds only the classification level it is accredited for. Its stores are separate instances, never shared volumes |
| Capacity | The queue is bounded. On overflow the oldest items are dropped by a declared priority order, and every drop is recorded as a local audit entry and surfaced to the operator. Silent loss is prohibited |
| Replay at the edge | The edge can rebuild its local projection from its own queue plus its last synchronised snapshot |
| Console | A local console replica serves the site operator with the same UI and the same data semantics |

### Sequence allocation at the edge

| # | Rule |
|---|---|
| S-1 | Each edge node holds a **local sequence space** per aggregate, independent of the fabric's global sequence space for that aggregate. The edge's local sequence starts at 1 for an aggregate it has never seen |
| S-2 | The edge records the fabric sequence it last knew for that aggregate (`lastKnownFabricSeq`). On reconnection the edge presents its queue with both its local sequence and the `lastKnownFabricSeq` it branched from |
| S-3 | The fabric allocates the **global** sequence on acceptance. The mapping from edge-local sequence to global sequence is recorded in the event's `edge` block so the two can always be related |
| S-4 | The `edge` block is extended with `localSequence` and `branchedFromSeq` so that the branching point is explicit. **This is a required contract change; see the contract-gap note below** |
| S-5 | An edge that has never synchronised (a cold-started annex) presents every aggregate as a full local creation. The fabric treats these as *proposed* creations and admits them only if the aggregate id does not already exist, in which case the edge's creation is accepted and the global sequence is assigned normally |

### Reconciliation procedure

On reconnection the edge performs, in order:

1. **Handshake.** Exchange protocol version, the edge node id, the policy bundle version, the clock offset estimate, and the set of aggregates the edge has touched with their local high-water marks.
2. **Clock measurement.** Both sides compute the offset; the edge records `edge.clockSkewMs` on every batch it submits. The fabric computes its own view of the offset and stores the agreed value.
3. **Pull.** The edge requests the fabric's state for the aggregates it cares about that changed since its `lastKnownFabricSeq`. The fabric returns the authoritative versions. The edge applies them to its local projection.
4. **Push.** The edge submits its queued events in batches, each batch carrying `batchId`, the `edge` block, and the events ordered by `(aggregateId, localSequence)`.
5. **Per-aggregate application.** For each aggregate, the fabric applies the conflict rule below.
6. **Quarantine.** Events that the rule cannot decide are written to a quarantine store, indexed by aggregate, and surfaced to the operator with a full explanation. The batch is acknowledged — the edge's queue is not blocked by one undecidable event.
7. **Acknowledgement.** The fabric returns, per batch, the list of accepted `eventId`s, the list of quarantined `eventId`s with reasons, and the resulting global high-water mark per aggregate. The edge retains quarantined items locally until an operator resolves them.
8. **Verification.** The edge re-reads the affected aggregates from the fabric and confirms its local projection matches. A mismatch is raised as an edge incident and the local projection is rebuilt from the fabric.

### The conflict rule

The rule is applied **per aggregate**, after the edge's queue has been ordered by local sequence. Three inputs determine the outcome: the *immutability class* of the aggregate, the *sequence relationship*, and the *classification relationship*.

#### Step 1 — Idempotency

If an incoming `eventId` has already been accepted, the event is a duplicate. It is dropped, counted as `duplicate`, and acknowledged. No state change.

#### Step 2 — Sequence relationship

Let `L` be the edge-local sequence, `B` the edge's `branchedFromSeq` (the fabric sequence the edge last knew), and `G` the fabric's current global sequence for the aggregate.

| Condition | Classification-independent outcome |
|---|---|
| `L` sequence already present at the fabric with the same `eventId` | Duplicate (Step 1) |
| The edge's events form a contiguous run from `B+1` upward and the fabric has not advanced past `B` for this aggregate | **Fast-forward.** The whole run is applied in order. This is the normal case: the edge was the only writer |
| The fabric's global sequence is still `B` and the edge's run is contiguous, but the fabric received other events for this aggregate from another source | Apply the run in order after the fabric's events; the edge's events are appended, not merged. No conflict |
| The fabric's global sequence has advanced past `B` **and** the edge's run overlaps the advanced region | **Conflict.** Go to Step 3 |
| The edge's run has an internal gap (a dropped queue entry, or an overflow drop) | The gap is recorded as a **sequence gap**. The contiguous prefix is applied; the remainder is quarantined as `gap` |
| The edge's run contains two events with the same local sequence | Both are quarantined as `divergent-sequence`. The edge's local allocator is at fault; this is an edge incident |

#### Step 3 — Immutability class

| Aggregate class | Resolution |
|---|---|
| **Immutable** (`TestResult` — C-003) | **Never auto-resolved.** If the fabric already holds a result for the same `(testArticleId, campaignId)` that is not superseded by this event, the incoming event is quarantined as `immutable-conflict`. Two sites claiming a result for the same physical test is a physical-world question, and it goes to a human. If the incoming event carries `supersedesRef`, it is accepted as a new version of the result and the prior result is marked superseded — the C-003-correct behaviour, and no conflict |
| **Append-only** (`PartProvenance` chain-of-custody entries, `ThreatObservation`, `ProcessRun`) | Both sides are kept. Append-only facts are additive; two records of two observations are both true. No conflict, no loss |
| **Mutable** (`Part` attributes, `Requirement` status, `ProcessPlan` revision, `Facility` attributes) | **Deterministic last-writer-wins by a fixed composite key**, defined below |
| **Relation** (the 10 relation types) | Retraction wins over assertion for the same relation id. Two *different* relations between the same pair of endpoints are both retained. A retraction received before its assertion (out of order) is buffered until the assertion arrives or the batch completes, then applied in causal order |

#### Step 4 — Mutable resolution key

For a mutable aggregate, when both the fabric and the edge have modified the aggregate since the branch point, the winner is selected by the **fixed composite key**:

```
winner = max by ( effectiveAt, recordedAtAuthority, eventId )
```

| Component | Definition | Why |
|---|---|---|
| `effectiveAt` | For a mutable attribute write, the `occurredAt` of the event | Business time. The edge's occurrence of a fact is the fact's time, not its transmission time |
| `recordedAtAuthority` | The fabric's acceptance time of the *received* event, i.e. `recordedAt` assigned on acceptance | Where two events have the same `effectiveAt`, the one the fabric accepted first is the incumbent. This is a tiebreak, not a policy |
| `eventId` | ULID lexicographic order | Total, deterministic, and independent of arrival order. Guarantees that every replica computes the same winner |

The loser is **not discarded**. It is applied to the audit ledger as a `reconcile-conflict` entry, and the winning aggregate carries an annotation recording the losing `eventId`, so a human can discover that a concurrent edit happened and what it said.

#### Step 5 — Classification gate

Before any merge is applied, both candidate states are checked against the classification rules:

| Check | Rule | Action on violation |
|---|---|---|
| Floor | The merged entity's classification must be ≥ the entity type's `classificationFloor` (C-001) | Reject the write. No merge |
| Non-downgrade | A merge must never lower an entity's classification | Reject the write. No merge |
| Boundary | A relation must not cross a classification boundary unless its type permits it (C-002) | Reject the relation assertion. The entities remain |
| Read-side | An engagement scenario must not be readable below its classification (C-008) | Enforced at the PEP, not here |

Because both candidates are checked, a merge can never be the mechanism by which content is downgraded. If a merge would produce a downgrade, both candidates are rejected and the aggregate is escalated.

#### Step 6 — Escalation

Any of the following produces a `reconcile-conflict` audit entry and an operator-visible conflict record in the fabric:

| Trigger | Escalation |
|---|---|
| `immutable-conflict` | A safety/quality review task is raised against the aggregate, assigned to the program quality authority |
| `gap` | A data-completeness task is raised. The affected aggregates are marked incomplete for reporting until resolved |
| `divergent-sequence` | An edge-node incident is raised against the node |
| Classification-gate violation | A security task is raised |
| Mutable conflict where the winner is the edge write and the difference is material | A review task is raised, but the deterministic winner is applied first — determinism is not suspended pending review |

### Clock skew handling

| # | Rule |
|---|---|
| CS-1 | `occurredAt` is the physical-world fact time and is **trusted within a declared uncertainty**. It is never adjusted by the receiver |
| CS-2 | `recordedAt` is the fabric's acceptance time and is the authoritative ordering key for anything the fabric controls. It is never earlier than `occurredAt` |
| CS-3 | The edge node maintains a disciplined clock. NTP with a site-local reference is the minimum; PTP where the site supports it is preferred |
| CS-4 | `edge.clockSkewMs` records the measured delta between the edge clock and the fabric clock at reconciliation. It is recorded on the event, on the batch, and in the audit ledger |
| CS-5 | Skew ≤ 5 s: recorded, no action. |
| CS-6 | 5 s < skew ≤ 60 s: recorded, and the affected events are flagged. `effectiveAt`-based tiebreaks may be unreliable, so the `eventId` component of the composite key dominates |
| CS-7 | skew > 60 s: the batch is quarantined as `clock-skew` and escalated. The edge's clock must be corrected before the batch is retried |
| CS-8 | A fact that occurred at the edge *before* the edge was disconnected but is only captured after reconnection still carries its original `occurredAt`. Late arrival is normal and is not an error. The envelope already separates the two times for exactly this reason |
| CS-9 | Where the site has no trustworthy clock at all, the edge records `occurredAt` from the process-local best estimate and marks the batch `clock-untrusted`; the fabric assigns `recordedAt` and the events are ordered by `recordedAt` only. The `effectiveAt` component of the composite key is disabled for that batch |

### What this design does NOT solve

| # | Not solved | Why it cannot be solved here | Mitigation / position |
|---|---|---|---|
| N-1 | Distributed consensus across sites | There is no consensus protocol and none is planned. The merge rule is a *deterministic function*, not a consensus algorithm | Single-writer discipline for critical aggregates; conflicts are made visible rather than prevented. Documented as an accepted limitation in the program risk register (R-20) |
| N-2 | Exactly-once side effects for external systems at the edge | An edge agent that calls a machine tool cannot atomically "call the tool" and "append to the log" | At-least-once with idempotency keys; physical actions at the edge are recorded by the operator's workflow, not by the agent |
| N-3 | Real-time global visibility | A disconnected site cannot see changes made elsewhere | The local projection is explicitly a cache; the UI shows connection state and last-sync time |
| N-4 | Multi-aggregate atomicity across the disconnection boundary | `transactionId` groups events for atomic application by a projection, but a transaction that spans a disconnection cannot be guaranteed | Transactions are scoped to one site at one time; a cross-site transaction is decomposed into per-site transactions with an explicit compensating step |
| N-5 | Loss of events when the edge node itself fails | The local queue is durable against process failure, not against media loss until it is replicated | Where the site requires it, the edge node's queue is replicated to a second local appliance; this is a site configuration option, not a platform default |
| N-6 | Physical truth of a captured test result | Two conflicting `TestResult` records cannot be adjudicated by software | Escalation to the program quality authority; the platform never silently picks one |
| N-7 | GPS denial effects on time | A site under GNSS denial may have no reference clock | The `clock-untrusted` path (CS-9) exists precisely for this, with the cost that `effectiveAt` ordering is unavailable for the affected batch |
| N-8 | Conflict on relation *assertions* between the same pair of endpoints with different attributes | Two assertions of "Part X is manufactured by Facility Y" with different `weight` values are genuinely ambiguous | Both are retained; the graph keeps the later-asserted one as current and the other as historical, with both recorded in the ledger. This is documented as a known lossy case |

### Required contract changes

This ADR requires two extensions to the contract layer that do not exist yet. They are listed here so that they are scheduled in WP-0.1 rather than discovered later:

| # | Change | File | Rationale |
|---|---|---|---|
| 1 | Add `edge.localSequence` (integer) and `edge.branchedFromSeq` (integer) to the `edge` block of the envelope and of `ingest.batch.accepted` | `contracts/events/event-envelope.schema.json`, `contracts/events/ingest.batch.accepted.schema.json` | Rule S-4. Without the branching point, the fabric cannot tell an edge's "first write after sync" from a "duplicate of an old write", and the fast-forward case cannot be distinguished from a conflict |
| 2 | Add a `reconcile.conflict.recorded` event type to the catalog | `contracts/events/catalog.json` and a new payload schema | Step 6. Conflicts must be first-class, queryable records, not only audit-ledger entries. The event carries `aggregateId`, `conflictClass` (one of `immutable-conflict`, `gap`, `divergent-sequence`, `clock-skew`, `classification-violation`), `winningEventId`, `losingEventId`, `edge.nodeId`, and the resolution action taken |

Both are additive and optional within the existing envelope version, so they do not require an `eventVersion` bump under the compatibility rules of [ADR-0002](ADR-0002-json-schema-contracts-over-shared-libraries.md).

## Alternatives Considered

### ALT-1. Edge nodes are read-only; all writes go through the central fabric

*Rejected.* It eliminates the reconciliation problem entirely, and it eliminates the platform. The primary writes in this domain happen at the factory floor and at the range: process run parameters, part measurements, test results. A write path that requires the central fabric to be reachable means the platform is unusable at exactly the places where the data is created. It also means that a range with a poor link loses the ability to record a test result at all, which is unacceptable.

### ALT-2. Last-writer-wins on wall-clock time, with the edge clock trusted

*Rejected.* This is the common implementation and it is unsafe in this domain. It requires trusting the edge clock to be correct and comparable across sites, which fails under GNSS denial (N-7), under manual clock correction, and when the clock is simply wrong at one site. It also produces non-deterministic outcomes: two replicas that receive the same two events in different orders can compute different winners, which breaks the replay determinism required by [ADR-0001](ADR-0001-event-sourced-foundation.md). The composite key of Step 4 adds only the amount of clock dependence that is unavoidable, and disables it entirely in the `clock-untrusted` case.

### ALT-3. Operational transformation / conflict-free replicated data types at the edge

*Rejected for the platform baseline, not permanently excluded.* CRDTs give conflict-free convergence without a central authority, which is genuinely attractive for the mutable entities. They were rejected because they require every mutable entity type to declare a merge semantics up front, which conflicts with the ontology's requirement that a domain expert define the merge for a `ProcessPlan` revision or a `Requirement` status transition. Silent automatic merging of engineering records is worse than surfacing a conflict. The design is compatible with CRDT semantics being adopted for a *specific* entity type later, if the domain authority for that type specifies it; the `reconcile.conflict.recorded` event and the deterministic composite key are the extension points.

### ALT-4. Distributed consensus (Raft/Paxos-style) replicated across sites

*Rejected.* A site-to-site consensus protocol between an IL6 annex and a factory floor introduces a network dependency that the whole design is trying to avoid, requires the sites to trust each other's quorum membership (a cross-accreditation problem: a factory floor is not a peer of a classified annex), and buys a guarantee — global total order — that the program does not need. The program needs determinism and visibility, not consensus. The cost is that conflicts are resolved by a rule and escalated to humans rather than prevented.

### ALT-5. Vector clocks or happens-before metadata carried on every event

*Rejected.* Vector clocks are the standard answer to "was this edit concurrent or causally after the other", and they would give a more precise conflict classification. They were rejected for the cost/benefit at this scale: a vector clock per aggregate per site is metadata growth on the hot path, a merge algorithm for vector clocks (which is itself non-trivial and error-prone), and a per-aggregate site registry that must be maintained. The `branchedFromSeq`/`lastKnownFabricSeq` pair captures the same information for the specific topology NGSH actually has — a single central fabric with peer edge sites — at a fraction of the complexity. If NGSH ever adopts peer-to-peer edge sites with no central fabric, this decision must be revisited.

### ALT-6. Reconcile by re-reading the authoritative state and replaying the edge's actions as commands

*Rejected.* This is the "replay the intent" model: the edge's queued items are re-submitted as commands to the fabric, which applies them against current state and either accepts or rejects. It is attractive because it reuses the normal command path. It was rejected because a command replayed against advanced state can take a *different* action than the edge intended — for example, incrementing a counter twice — and because "the edge's action" is often not expressible as a command without the edge's original state context. The rule-based merge of Steps 1–6 is more faithful.

## Consequences

### Positive

| # | Consequence |
|---|---|
| P-1 | Disconnected operation is a first-class capability with a specified behaviour table, testable in CI against the DP-E profile ([ADR-0003](ADR-0003-platform-agnostic-hybrid-deployment.md)). |
| P-2 | Reconciliation is deterministic: the same set of events yields the same final state regardless of arrival order or which replica computes it. This preserves the replay determinism that the whole log architecture depends on. |
| P-3 | Immutable evidence is never silently overwritten. The C-003 conflict path escalates to a human, which is the only correct behaviour when two sites disagree about a physical test. |
| P-4 | Conflicts are visible and recoverable. The losing write is retained in the ledger and annotated on the aggregate, so a concurrent edit is discoverable and reviewable. |
| P-5 | Clock skew is measured and recorded rather than assumed away, and the platform degrades safely when the clock is not trustworthy. |
| P-6 | The edge read path is identical connected or disconnected, which is what makes operators trust the tool enough to use it in the field. |
| P-7 | The design is portable to a site with no network at all, with the only degradation being that reconciliation is deferred. |

### Negative

| # | Consequence |
|---|---|
| N-1 | The merge rules are domain policy expressed in code and must be reviewed by engineers who understand the domain, not only by platform engineers. Each mutable entity type needs a merge decision. |
| N-2 | The `edge` block must be extended, and the extension must be adopted by every edge agent implementation, including the partner-supplied ones. |
| N-3 | Escalation is a workflow obligation on the program, not a software feature. If nobody triages reconcile conflicts, the system accumulates them and the queue of unresolved conflicts becomes the real state of the digital thread. |
| N-4 | The `clock-untrusted` path disables `effectiveAt` ordering, which materially changes merge behaviour for those batches and must be understood by the domain authority. |
| N-5 | The edge queue's overflow policy is a data-loss policy, and it must be agreed with the program, not chosen by the platform team. |
| N-6 | Two sites writing the same mutable aggregate produce a deterministic but *semantically arbitrary* winner. The platform's job is to make that arbitrary choice visible, not to make it correct. |
| N-7 | Reconciliation is a real piece of distributed-systems engineering with real failure modes, and it will need its own test harness with fault injection. |

### What this makes harder

| # | Harder thing | Why |
|---|---|---|
| HW-1 | Getting the merge rule right for `Requirement.status` | A `Requirement` transitioning `IMPLEMENTED` → `VERIFIED` at one site and `IMPLEMENTED` → `INVALID` at another is not a mechanical tiebreak; the domain authority must define whether the states are ordered, exclusive, or both. Until it does, the platform applies the deterministic key and escalates |
| HW-2 | Explaining the outcome to an engineer | "The platform chose your write because your `occurredAt` was later" is a weak explanation for a records decision. The conflict record must carry the full composite key breakdown so the reasoning is inspectable |
| HW-3 | Testing | Determinism must be tested by construction: the same event set applied in many permutations must produce one result. The fault-injection harness (disconnect at every point, duplicate every batch, reorder every event) is a mandatory test asset, not an optional one |
| HW-4 | Quarantine lifecycle | A quarantined event is neither applied nor discarded, and its resolution may require domain input that arrives weeks later. The quarantine store needs its own retention, its own UI, and a rule for expiry that does not silently drop evidence |
| HW-5 | Edge operator competence | The edge console must show connection state, queue depth, pending conflicts and the last successful sync at a glance, because the operator at a factory floor has no access to the central fabric's view |
| HW-6 | Multi-tenant edge sites | A factory that serves two programs shares one edge node and therefore one queue. The queue is partitioned by tenant, and a tenant's overflow must not evict another tenant's events. This is a fairness constraint on the overflow policy, which is a policy question as much as a technical one |

## Compliance Notes

| PSDD / regulatory obligation | How this ADR supports it |
|---|---|
| PSDD §4.2 principle 3 — "Deployable at the edge — factory-floor and range annexes with sync to the central fabric" | Directly implemented; the sync path is the reconciliation procedure. |
| PSDD §8 Availability — "edge annexes degraded-mode capable with later sync" | Degraded mode is specified as a capability set with a behaviour table, and is exercised in CI against the DP-E profile. |
| PSDD §8 Auditability — "Every model version, test result, and access decision reconstructable" | Reconciliation outcomes are recorded: accepted events in the business log, conflicts and drops in the audit ledger, and — with the proposed contract change — as first-class `reconcile.conflict.recorded` events. |
| PSDD §6.3 — "Data lineage automated end-to-end" | `edge.nodeId`, `edge.capturedAt`, `edge.reconciledAt` and the proposed `edge.localSequence` make the edge-to-fabric path fully traceable. |
| PSDD §10 — classification partitioning | Step 5 ensures that reconciliation can never be the mechanism of a downgrade, which is the specific abuse the partitioning design is meant to prevent. |
| CMMC 2.0 L2 (AU family) | Edge actions are audited locally and reconciled; the ledger records every drop, conflict and quarantine resolution. |
| CMMC 2.0 L2 (CA family) | CA-3 (information transferred) covers the edge-to-fabric transfer, including the reconciliation protocol and its integrity checks. |
| CMMC 2.0 L2 (SI family) | SI-7 (integrity) covers the digest checks on reconciled batches; `ingest.batch.accepted.sha256` is the batch-level integrity anchor. |
| DoD directives on supply-chain and untrusted edge devices | The edge agent is an untrusted-by-default component: it holds no fabric write credential, it proposes events rather than asserting them, and every proposal is subject to the same validation as any other writer's. |

## References

**PSDD:** §4.1 (zone sketch — edge nodes at factories/ranges), §4.2 principle 3, §5.3 (Pillar C — test data platform and campaign management), §5.7 (Pillar G — virtual test range federation, G-2 campaign digital twin), §6.3 (data governance — CUI tagging at ingestion, lineage), §7 IF-4 (range instrumentation, bi-directional), §8 (Availability, Auditability, Interoperability), §10 (deployment pattern, cross-domain guards), §13 (risks — classification friction, threat-data access chokepoint).

**Contracts:**
- `contracts/events/event-envelope.schema.json` — `sequence` ("per-aggregate monotonic sequence... enforces optimistic concurrency and enables deterministic replay ordering"), `occurredAt` / `recordedAt` split, `idempotencyKey`, `eventId` ULID (used as the final deterministic tiebreak), and the `edge` block with `nodeId`, `capturedAt`, `reconciledAt`, `clockSkewMs` (extended by this ADR).
- `contracts/events/ingest.batch.accepted.schema.json` — the batch-level edge reconciliation record, with `batchId`, `sha256`, `recordsAccepted` / `recordsRejected`, and its own `edge` block.
- `contracts/events/test.result.recorded.schema.json` — `supersedesRef`, the mechanism that makes an immutable-result correction non-conflicting.
- `contracts/ontology/registry.json` — C-001, C-002, C-003 (immutability, which drives the Step 3 immutable branch), C-008.
- `contracts/ontology/common.schema.json` — `EntityHeader.version` (optimistic concurrency), `EntityHeader.deleted` (soft delete), `Actor`, `Classification`.

**Related ADRs:** [ADR-0001](ADR-0001-event-sourced-foundation.md) (the replay determinism this preserves), [ADR-0002](ADR-0002-json-schema-contracts-over-shared-libraries.md) (the compatibility rules under which the two proposed contract changes are additive), [ADR-0003](ADR-0003-platform-agnostic-hybrid-deployment.md) (the DP-E profile and the capability declarations), [ADR-0005](ADR-0005-tamper-evident-audit-ledger.md) (where conflicts, drops and quarantines are recorded), [ADR-0007](ADR-0007-classification-partitioning.md) (Step 5's classification gate).
