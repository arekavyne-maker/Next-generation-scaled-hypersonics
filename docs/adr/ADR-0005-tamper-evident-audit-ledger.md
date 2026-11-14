# ADR-0005: A Separate Tamper-Evident Audit Ledger

## Status

Accepted

## Date

2026-11-14

## Context

PSDD §6.3 requires a "full audit trail" and an "immutable test-result ledger (append-only)". PSDD §8 requires that "every model version, test result, and access decision" be reconstructable. PSDD §10 requires that Program Protection Plan artifacts be generated automatically from data lineage, and that NGSH itself be developed under CMMC L2+.

The event log described in [ADR-0001](ADR-0001-event-sourced-foundation.md) already satisfies most of this literally. It is append-only, it carries `actor`, `occurredAt`, `recordedAt` and `classification` on every envelope, and it records access decisions as `access.decision.recorded` events.

The question this ADR answers is whether the event log is *sufficient* as the audit record, or whether a second, differently-purposed ledger is required.

Four structural properties of the event log argue that it is not sufficient on its own:

1. **It is written by the same components that do the work.** The fabric appends on behalf of services. A component with append rights to the business log has append rights to the audit record. The audit record is therefore not independent of the thing it audits.
2. **It is partitioned and queryable.** The event log is stored in the same classification-partitioned stores, served by the same query paths, and read by the same services. A tamper that is possible against a stored artifact is possible against the log. The log's own integrity is asserted by the storage layer and by the projection rebuild — but the projection rebuild reconstructs from the same bytes.
3. **Its granularity is semantic, not forensic.** The log's unit is a business fact. "Who read this record, from which workstation, under which decision, at which microsecond" is not the same question as "what happened to this order", and squeezing the forensic question out of the business log means either over-recording (writing an event for every field read) or under-recording.
4. **Its retention and compaction rules are business-driven.** Superseded payload bodies may be archived to cold storage ([ADR-0001](ADR-0001-event-sourced-foundation.md), rule DR-1.12). A forensic record needs a retention regime that is not at the mercy of a business decision.

At the same time, a naïve second ledger fails in the opposite direction: a ledger that is merely another append-only table, written by the same services with the same credentials, adds cost and no assurance.

The design therefore requires a ledger with **independent write authority, cryptographic chaining, and externally published anchors**.

## Decision

**NGSH maintains a separate tamper-evident audit ledger, distinct from the business event log, written by the audit service, hash-chained entry by entry, and periodically anchored outside the NGSH trust boundary.**

### Separation from the business log

| Aspect | Business event log | Audit ledger |
|---|---|---|
| Purpose | Record *what is true* | Record *what was done to the system* |
| Unit | A domain fact (`entity.created`, `test.result.recorded`, …) | An action (a decision, a mutation, a read, an export, a config change, an administrative act) |
| Write authority | Services append through the fabric | The audit service appends; only the audit service holds the ledger write credential |
| Write path | Normal service path, high throughput | Separate path, deliberately low throughput and highly available |
| Ordering | Per-aggregate monotonic `sequence` | Single global monotonic `entrySeq` across the whole ledger |
| Retention | Business-driven; superseded bodies may be archived | Retention set by policy; bodies are never rewritten, only superseded by new entries |
| Storage | Classification-partitioned alongside business data | Classification-partitioned, but in a store that the business services have **no** write credential for |
| Consumer | Projections, pillar services, analysts | Auditors, investigators, CMMC assessors, the verification job |

The two are linked, not duplicated: every audit entry carries the `eventId` (or a list of `eventId`s) of the log record it describes, and the ledger is the place where *an audit of the audit trail* is anchored.

### Entry structure

Each ledger entry contains:

| Field | Purpose |
|---|---|
| `entrySeq` | Global monotonic sequence, gapless, assigned by the audit service |
| `prevHash` | The `entryHash` of the previous entry; `null` only for the genesis entry |
| `entryHash` | `SHA-256(canonical(entryBody) ‖ prevHash)` over a canonical serialisation (RFC 8785 JCS) of the entry body |
| `action` | The audited verb: `read`, `write`, `export`, `delete`, `approve`, `deploy`, `authenticate`, `policy-change`, `anchor`, `quarantine`, `reconcile` |
| `actor` | `Actor` from `contracts/ontology/common.schema.json` — subject, kind, clearance, citizenship, org |
| `resource` | `type` + `id` + `classification` of the object acted upon |
| `decision` | `ALLOW` / `DENY` / `INDETERMINATE` where an access decision was made |
| `policyId` / `policyVersion` | The rule that produced the decision |
| `eventRefs[]` | `eventId`s of the business log records related to this action |
| `context` | Environmental detail: node id, session id, source address (where policy permits), device posture, correlation id |
| `recordedAt` | The audit service's acceptance time, authoritative |
| `anchorRef` | The anchor that later covers this entry |

The `canonical(entryBody)` function is fixed and versioned. Changing it is a ledger format change requiring a new `ledgerVersion` and a re-anchoring procedure.

### Anchoring

| Aspect | Rule |
|---|---|
| Anchor content | The `entryHash` of the head entry at the anchor point, plus the `entrySeq`, plus the anchor time, plus the previous anchor's hash — forming a second, slower chain over the fast chain |
| Anchor period | Every 15 minutes, and on demand (a manual anchor is available to an operator and to the verification job) |
| Anchor destination | Outside the NGSH trust boundary: a separate system of record under different administrative control — a classification-appropriate standalone store, a third-party timestamping/countersignature service where accreditation permits, and an offline written record held by the security office |
| Anchor independence | The anchor destination must not be writable by the same credential or the same administrative domain as the ledger |
| Anchor failure | A failure to anchor is an alertable security event and is written to the audit ledger itself as a `anchor-failure` action. Anchoring failure does not stop the ledger from accepting entries, but it starts a measurable window of unattested entries that is reported |

### Verification procedure

The `auditctl verify` tool (produced by the audit service, run by the security office and by CI) performs, in order:

1. **Chain integrity.** Recompute `entryHash` for every entry in range and compare to the stored value. Verify `prevHash` linkage. Any mismatch is a *tamper* finding.
2. **Gap detection.** Verify `entrySeq` is gapless and monotonic. A gap is a *deletion* finding.
3. **Anchor check.** For each anchor covering the range, confirm the anchor's head hash matches the chain state at that point. A mismatch is a *rewritten history* finding.
4. **Anchor completeness.** Confirm that every entry in the range is covered by an anchor. Entries after the last anchor are *unattested*, which is a state to be reported, not a failure.
5. **Cross-check against the business log.** For the range, confirm that the count of `access.decision.recorded` events in the log matches the count of `read`/`write`/`export` audit entries with `decision` set, within the documented tolerance for known gaps (for example, decisions taken while the PDP was unreachable and served from a stale cache are recorded locally and arrive in batches). A material mismatch is a *coverage* finding and is itself escalated.
6. **Quarantine and reconciliation findings.** Confirm that every `quarantine` entry has a matching `resolve` entry or is still open. An open quarantine older than its review SLA is a finding.

Verification output is a signed report: the verification run identifier, the range verified, the findings by class, and the signature of the verifying identity. The report is itself anchored.

### What the ledger can prove

| # | Proposition | Conditions |
|---|---|---|
| 1 | No entry in the verified range has been altered since it was written | Chain integrity holds and the range is covered by at least one anchor |
| 2 | No entry has been removed from the middle of the verified range | Gapless `entrySeq` holds |
| 3 | The *order* of entries in the range is as recorded | Chain ordering holds |
| 4 | The head of the ledger at the anchor time is as it was at the anchor time | The anchor is verified and the anchor destination is trusted |
| 5 | The audited actions correspond one-to-one with the business-log records they claim to describe | The cross-check passes |
| 6 | An action was performed by a party holding a credential that produced the recorded `actor` attributes | Subject to the identity provider's own assurance |
| 7 | A specific decision was produced by a specific policy version | `policyId` / `policyVersion` are recorded at decision time and the policy bundle history is retained |

### What the ledger cannot prove

| # | Proposition the ledger does **not** support | Why |
|---|---|---|
| 1 | That an action never occurred, before the ledger existed or during a period with no writer | The ledger is a positive record only. It can be silent about events it never saw |
| 2 | That the recorded actor was a human, or that the credential was not stolen or shared | The ledger records what the identity provider asserted at the time |
| 3 | That the underlying facts are true | It attests to the record of an action, not to the physical reality it describes. A fraudulent test measurement that was faithfully recorded is faithfully recorded |
| 4 | That the pre-action system state was correct | It attests to actions, not to the state that was acted upon |
| 5 | That no one with access to the whole system wrote a *consistent but false* ledger from the beginning | An adversary who controls the ledger writer and the first anchors can produce a perfectly chained false history. The mitigation is the anchor's independence — the anchor destination is under different administrative control — not the hash chain itself |
| 6 | That an anchor was not itself compromised | The anchor's assurance is the assurance of the anchor destination. Chain-of-custody for the anchor must be maintained separately |
| 7 | The content of a read that the PDP never saw | Decisions taken in a disconnected edge mode and reconciled later are recorded at reconcile time with their original `occurredAt`; the temporal gap must be visible to an investigator |

### Separation of duties

| Role | May do | May not do |
|---|---|---|
| Service / pillar developer | Read and write domain data via the fabric | Append to the audit ledger; read the ledger's write credential; modify the anchor destination |
| Platform / fabric operator | Operate the fabric, scale it, deploy it | Append to the ledger; alter existing entries; change the canonicalisation function without a `ledgerVersion` change under review |
| Security office | Read the ledger; request and verify anchors; run `auditctl verify`; publish verification reports | Append business data; suppress an entry |
| Policy owner | Author policy bundles | Append to the ledger; bypass the PDP |
| Auditor (external) | Read the ledger and anchors; re-run verification independently | Append anything |
| Break-glass administrator | Perform a privileged action, which is itself logged and requires dual authorisation | Delete or alter any prior entry |

## Alternatives Considered

### ALT-1. Use the business event log as the sole audit record

*Rejected.* This is the tempting option because the log is already append-only and already carries `actor` and `classification`. It was rejected for the four structural reasons given in Context, most decisively on write authority: the components that perform the actions also write the record of the actions, so the audit trail is not independent evidence of anything. It is also the *only* option that requires no new infrastructure, which is exactly why it is dangerous — it looks sufficient and produces an audit posture that fails at assessment because "the system audited by the same component that performed the action" is not accepted evidence.

### ALT-2. Rely on immutable/WORM object storage (object-lock semantics) for audit records

*Rejected as the primary mechanism, retained as a substrate.** Write-once-read-many storage gives excellent guarantees against modification and deletion *by the storage layer*, and it is a strong component of the implementation. It was rejected as the *primary* mechanism for three reasons. First, availability: the accreditation posture in PSDD §10 does not guarantee a WORM-capable object store inside an IL6 annex, and the ledger must be writable there. Second, granularity: object-level immutability cannot detect an *omission* — an entry that was never written leaves no trace in a WORM bucket, whereas a hash chain breaks at the omission. Third, verifiability: proving to an assessor that a specific set of entries is complete and ordered requires a chain, which is exactly what WORM does not provide.

### ALT-3. RFC 3161 timestamp authority / trusted timestamping service

*Rejected as the primary mechanism, retained as an anchor destination.** Trusted timestamping proves that a given digest existed at a given time at a trusted third party. It does not establish *order* between entries, does not detect an omission in the middle of a range, and produces one artifact per timestamp rather than a verifiable structure. It is an excellent *anchor destination* and is listed as one of the permitted options.

### ALT-4. Blockchain / distributed ledger

*Rejected.* A permissioned chain provides an ordering and non-repudiation story, but nothing here needs consensus across mutually distrusting parties — NGSH has a single audit authority inside its own accreditation boundary. The chain adds nondeterminism, throughput limits on the write path, a materially larger dependency footprint in an accredited product, and a far harder CMMC assessment story, in exchange for properties that a hash chain plus an independent anchor already provides at a fraction of the cost.

### ALT-5. Database-native audit triggers (database audit log / change-data-capture)

*Rejected.* Useful as a supplementary signal, and it is retained for the storage-tier "who touched the bytes" question, which the application-level ledger cannot answer. But a database audit log records storage-level operations, not the semantic action. It cannot answer "which policy version authorised this export" and it cannot distinguish a read performed by the application from a read performed by an administrator's ad-hoc query against the same table — a distinction that matters when the application-layer decision and the storage-layer access disagree.

### ALT-6. A single ledger for both business facts and actions

*Rejected.* This is the "one log to rule them all" position. It couples the retention regime of forensic evidence to the retention regime of business data, forces the business write path to carry forensic-grade per-access entries at the ingest hot path, and makes a rule such as "the audit trail must survive a business-data purge" impossible to satisfy without a purge rule for the audit trail, which then destroys the business data. The two ledgers have different lifetimes and different purposes; keeping them separate is what makes each of them correct.

## Consequences

### Positive

| # | Consequence |
|---|---|
| P-1 | The audit trail has independent write authority, which is the property that makes it evidence rather than self-report. |
| P-2 | Tampering is detectable, including omission, which a WORM bucket alone cannot do. |
| P-3 | The ledger is the artefact that carries obligations such as `log-externally` and `audit-every-read` to their conclusion, because it is written independently of the PEP that imposed them. |
| P-4 | The `ledgerFormatVersion` and the `policyVersion` fields make the reconstruction required by PSDD §8 exact rather than approximate. |
| P-5 | Verification is automatable and can run continuously, not only before an assessment. A continuous verification job that publishes a signed daily report is a materially stronger posture than an annual sample. |
| P-6 | The anchoring design degrades gracefully: an unreachable anchor destination does not stop the ledger, it creates a measurable, reported window of unattested entries. |
| P-7 | Separation of duties is enforceable in the credential store, so the "operators cannot rewrite the record" property is a configuration fact rather than an organisational commitment. |

### Negative

| # | Consequence |
|---|---|
| N-1 | A second write path to operate, monitor, scale and accredit. |
| N-2 | A second classification-partitioned store, and the same partitioning decisions repeated. |
| N-3 | Ledger growth. At a read-audit rate of one entry per access decision, the ledger grows faster than the business log in entry count, though not in bytes. Retention and archival planning is required (see the `audit.archive` control below). |
| N-4 | The verification job must be correct. A verification tool that has never been shown to *fail* on a seeded tampering case is not evidence. Seeded-tamper tests are therefore a release gate, not a nice-to-have. |
| N-5 | Anchor independence is an organisational commitment as much as a technical one. If the anchor destination is administered by the same team, the independence claim is weak and must not be asserted in the assessment. |
| N-6 | Dual authorisation on break-glass operations adds latency to the path that most needs to be fast, and the break-glass procedure must be rehearsed or it will be bypassed under pressure. |

### What this makes harder

| # | Harder thing | Why |
|---|---|---|
| HW-1 | Reconciling the two ledgers | They answer different questions and will not have the same counts. The cross-check (verification step 5) needs a documented tolerance and a documented explanation for every class of mismatch, otherwise the check will be tuned until it never fires. |
| HW-2 | Canonicalisation | The hash chain requires one byte-exact serialisation. Every field that varies — map ordering, timestamp formatting, floating point representation, absent-versus-null — becomes a chain-breaking bug. The canonicalisation function is versioned and frozen within a `ledgerFormatVersion`. |
| HW-3 | Time | The ledger's `recordedAt` is the audit service's clock. If that clock drifts from the fabric clock, the two ledgers diverge in time. The skew is measurable and the verification report must state the observed skew rather than hide it. |
| HW-4 | Bulk operations | An operation that touches 10,000 records produces one logical action. Does it produce 10,000 entries or one? The rule is one entry per *decision*, with the resource set summarised by a manifest that is itself content-addressed and stored alongside — but the manifest must be reconstructable, which means it too must be anchored. |
| HW-5 | Reading the ledger at scale | Investigators need to query it. Querying an append-only hash chain by arbitrary predicates is expensive. The mitigation is a derived index that is explicitly *not* authoritative and is marked as such in the verification report. |
| HW-6 | "Nothing happened" claims | The ledger can prove that a recorded action occurred and that the record is intact. It cannot prove a negative. Any control that requires a negative claim ("no export occurred") must be paired with a positive control — for example, an export allow-list whose every use is expected to leave a matching entry. |

### Controls

| Control | Description |
|---|---|
| `audit.write` | Append an entry to the ledger. Held only by the audit service identity. |
| `audit.read` | Read ledger entries. Held by the security office and the audit read role; every read is itself audited. |
| `audit.verify` | Run verification and produce a signed report. |
| `audit.anchor` | Request an anchor. Requires the security-office role and is itself audited. |
| `audit.archive` | Move a sealed range to cold storage. The archive manifest records the head hash and the range boundary; it does not permit individual entry removal without breaking the chain. |
| `audit.seal` | Freeze a range, e.g. at the end of a program phase or before an assessment. A sealed range cannot be archived or modified; only the verification job can read it. |

## Compliance Notes

| PSDD / regulatory obligation | How this ADR supports it |
|---|---|
| PSDD §6.3 — "Full audit trail" | The ledger is the authoritative full audit trail; the business log is the record of domain facts. The distinction removes the ambiguity in "the audit trail" as a phrase. |
| PSDD §6.3 — "immutable test-result ledger (append-only)" | Satisfied at two levels: `TestResult` immutability in the business log (C-003) and the append-only, hash-chained forensic ledger. The two are complementary, not redundant. |
| PSDD §8 Auditability — "Every model version, test result, and access decision reconstructable" | Model versions are `model.validated` events plus ledger entries recording each approval action; test results are immutable log records; access decisions are `access.decision.recorded` events *and* ledger entries. |
| PSDD §10 — "Program protection: PPP artifacts generated automatically from data lineage" | Lineage comes from the business log; the evidence that the lineage was not altered comes from the ledger and its anchors. Both are needed for a credible PPP artifact. |
| CMMC 2.0 L2 (AU family) | AU-2/AU-3 (event logging and content), AU-6 (audit review, via the continuous verification report), AU-9 (protection of audit tools — the ledger write credential is separate), AU-10 (non-repudiation — the hash chain plus an independent anchor). |
| CMMC 2.0 L2 (CA family) | CA-3 (control of information transferred) is evidenced by the export and read entries in the ledger. |
| CMMC 2.0 L2 (SI family) | SI-4 (system monitoring) and SI-7 (software, firmware and information integrity) are directly supported by chain verification. |
| NIST SP 800-53 AU-9 / AU-10 alignment | The separation of duties table is written against these control intent statements. |
| Program Protection Plan (PPP) and security assessment evidence | The signed verification report, the anchor records and the separation-of-duties configuration are the artefacts an assessor asks for. |

## References

**PSDD:** §6.3 (data governance — full audit trail, immutable test-result ledger, lineage), §8 (Auditability), §10 (Security & Compliance Architecture — program protection, supply chain), §13 (risks — classification friction, threat-data access chokepoint).

**Contracts:**
- `contracts/events/access.decision.recorded.schema.json` — the decision event whose content the ledger entry mirrors, and whose `policyId` / `policyVersion` / `obligations` the ledger preserves.
- `contracts/events/event-envelope.schema.json` — `eventId` (the cross-reference from a ledger entry to the log), `actor`, `classification`, `recordedAt`, `correlationId`.
- `contracts/ontology/common.schema.json` — `Actor` (the ledger's subject record), `Classification` (the ledger's resource record), `Attachment` (content-addressed manifests for bulk operations).
- `contracts/ontology/registry.json` — C-003 (business-log immutability that the ledger attests to), C-005 and C-006 (clearance validity, which the ledger records as of `recordedAt`).

**Related ADRs:** [ADR-0001](ADR-0001-event-sourced-foundation.md) (the business log this ledger is deliberately separate from), [ADR-0004](ADR-0004-abac-with-pdp-pep-separation.md) (the decisions this ledger records), [ADR-0007](ADR-0007-classification-partitioning.md) (partitioning applies to the ledger store as well).
