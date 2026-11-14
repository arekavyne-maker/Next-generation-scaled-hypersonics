# NGSH Architecture Decision Records

## Purpose

This directory holds the Architecture Decision Records (ADRs) for the NGSH platform. Each ADR captures one architectural decision that has been settled, the context that forced it, the alternatives that were rejected and with what reason, the consequences — including the ones that are unpleasant — and how the decision supports the Preliminary Software Design Document (PSDD) and the CMMC 2.0 Level 2+ programme. ADRs are the durable record of *why*; the architecture documents in [`../architecture/`](../architecture/) record *what*.

## Contents

| # | Title | Subject |
|---|---|---|
| [ADR-0001](ADR-0001-event-sourced-foundation.md) | The Event Log Is the System of Record | Event sourcing as the foundation of the digital thread |
| [ADR-0002](ADR-0002-json-schema-contracts-over-shared-libraries.md) | JSON Schema Contracts Instead of Shared Source Libraries | The contract layer as the only cross-language coupling |
| [ADR-0003](ADR-0003-platform-agnostic-hybrid-deployment.md) | Platform-Agnostic, Hybrid-First Deployment | The deployment abstraction and the three-zone topology |
| [ADR-0004](ADR-0004-abac-with-pdp-pep-separation.md) | ABAC with Separated Policy Decision Point and Policy Enforcement Points | Authorization model and enforcement topology |
| [ADR-0005](ADR-0005-tamper-evident-audit-ledger.md) | A Separate Tamper-Evident Audit Ledger | Independent forensic record with hash chaining and anchoring |
| [ADR-0006](ADR-0006-edge-degraded-mode-and-reconciliation.md) | Edge Degraded Mode and Deterministic Reconciliation | Disconnected operation and the merge rule |
| [ADR-0007](ADR-0007-classification-partitioning.md) | Physical Classification Partitioning of Storage | Storage partitioning, downgrade prevention, sanitized extracts |
| [ADR-0008](ADR-0008-model-card-and-fidelity-registry.md) | Model Cards and a Fidelity Registry | Model provenance, fidelity scoring, approval gates |

## Decision index

| ADR | Title | Status | Date | Rationale |
|---|---|---|---|---|
| ADR-0001 | The Event Log Is the System of Record | Accepted | 2026-11-14 | The digital thread is a history; making the log authoritative gives replay, lineage, audit and constraint enforcement from one write path, and reduces every other store to a rebuildable projection. |
| ADR-0002 | JSON Schema Contracts Instead of Shared Source Libraries | Accepted | 2026-11-14 | Polyglot (Go/Python/TypeScript) needs a coupling mechanism that is not a language monoculture; JSON Schema gives a human-reviewable, versioned, machine-checkable contract with generated codecs. |
| ADR-0003 | Platform-Agnostic, Hybrid-First Deployment | Accepted | 2026-11-14 | The IL5 enclave, the IL6 annex and the disconnected edge annex all run the same code; the difference is a declared capability set, not a code branch, and no domain package may import a cloud SDK. |
| ADR-0004 | ABAC with Separated PDP and PEPs | Accepted | 2026-11-14 | Access depends on the conjunction of clearance, citizenship, program and resource classification, which RBAC cannot express; one PDP with many PEPs keeps the rule single and makes the denial path safe. |
| ADR-0005 | A Separate Tamper-Evident Audit Ledger | Accepted | 2026-11-14 | The business log cannot audit itself — same writers, same storage, same credentials; an independently written, hash-chained, externally anchored ledger is what makes the trail evidence rather than self-report. |
| ADR-0006 | Edge Degraded Mode and Deterministic Reconciliation | Accepted | 2026-11-14 | The data is created at factories and ranges, often disconnected; disconnected operation is a designed capability and the merge must be deterministic, with immutable evidence escalated rather than silently resolved. |
| ADR-0007 | Physical Classification Partitioning of Storage | Accepted | 2026-11-14 | Application-layer filtering makes confidentiality depend on every query path in the codebase; physical partitioning makes the boundary independent of application correctness and makes the one-way academic extract genuinely one-way. |
| ADR-0008 | Model Cards and a Fidelity Registry | Accepted | 2026-11-14 | A fidelity score that is not recomputed from new test evidence is a decaying claim; provenance, envelope, approval and automatic re-scoring are what make test-coupled M&S real rather than aspirational. |

## ADR process

### Template

Every ADR uses the same section structure, in the same order. A decision that does not fit the template is a sign that the decision is not yet settled.

```markdown
# ADR-NNNN: Title

## Status
## Date
## Context
## Decision
## Alternatives Considered
## Consequences
   ### Positive
   ### Negative
   ### What this makes harder
## Compliance Notes
## References
```

| Section | Requirement |
|---|---|
| Title | One line. States the decision, not the topic. "The Event Log Is the System of Record", not "Event Sourcing". |
| Status | `Proposed`, `Accepted` or `Superseded`. Nothing else. |
| Date | The date the decision was taken, ISO 8601. |
| Context | The forces that made a decision necessary. Reference PSDD sections and contract files. State the problem before proposing a solution. |
| Decision | The rule, stated normatively. Where the decision has numbered sub-rules, number them. Where it needs tables — version rules, compatibility rules, limits — use tables. |
| Alternatives Considered | At least two genuine alternatives, each with the specific reason it was rejected. "Not suitable for our scale" is not a reason. If an alternative was rejected for a reason that no longer holds, say so. |
| Consequences | Positive, negative, and "what this makes harder". The third subsection is mandatory and is the one that keeps the record honest; an ADR with no difficulties listed has not been thought through. |
| Compliance Notes | How the decision supports the PSDD §8 non-functional requirements, the PSDD §10 security architecture, and CMMC 2.0 L2+ obligations. A table mapping obligation to mechanism. |
| References | PSDD sections by number, and specific contract files by path. Relative links to sibling ADRs. |

### Status values

| Status | Meaning | What it implies for the architecture |
|---|---|---|
| `Proposed` | Raised, argued, not yet settled. May be implemented experimentally | The architecture documents may reference it as a decision under consideration. No implementation is committed |
| `Accepted` | Settled. Binding on all work in the programme | The architecture documents treat it as normative. Deviation requires a new ADR that supersedes this one |
| `Superseded` | Replaced by a later ADR | The ADR remains in the repository as the historical record. It is marked `Superseded by ADR-NNNN` in the Status section, and the superseding ADR links back to it |

There is no `Rejected` status. A rejected proposal is either not written up, or — if the argument is worth preserving — written as an ADR that is immediately superseded, with the reasoning preserved. A rejected decision that vanishes leaves the next reader to re-derive it.

### Lifecycle

| Stage | Who | Output |
|---|---|---|
| 1. Raised | Any engineer | A draft ADR with a `Proposed` status and at least one genuine alternative |
| 2. Reviewed | Architecture review board: Platform pod lead, Security & Compliance pod lead, one domain authority from the affected pillar | Comments recorded; the ADR is revised in place |
| 3. Decided | Architecture review board | Status set to `Accepted`; date fixed at the decision date |
| 4. Published | Architecture owner | Linked from this index, from the affected architecture documents, and from the change log |
| 5. Superseded | Architecture owner | A new ADR is written and the old one is marked `Superseded by ADR-NNNN` with a pointer |

### Rules

| # | Rule |
|---|---|
| R-1 | One decision per ADR. If an ADR needs the word "and" in its title, it is two ADRs |
| R-2 | ADRs are immutable once accepted. A change of mind is a new ADR that supersedes the old one. This preserves the history of the reasoning, which is often the most valuable part of the record |
| R-3 | An ADR that contradicts an accepted ADR cannot also be `Accepted`. The contradiction is resolved by superseding |
| R-4 | Every accepted ADR must be traceable to at least one PSDD section and, where applicable, to specific contract files. An architectural decision with no requirement behind it is either a preference or a mistake |
| R-5 | The "What this makes harder" subsection is mandatory. An ADR with an empty one will be sent back |
| R-6 | ADR numbering is monotonic and never reused. A withdrawn ADR keeps its number |
| R-7 | An ADR is closed by the architecture review board, not by its author |

### Current state

All eight ADRs are `Accepted` as of 2026-11-14. They record the four settled programme-level decisions:

1. **Increment 0 is the shared foundation.** The ontology, event log, policy, audit ledger, graph projection, ingestion and edge sync are built before any pillar. See [`../roadmap/increments.md`](../roadmap/increments.md).
2. **Platform-agnostic, hybrid-first deployment.** No cloud SDKs in domain code; three zones; degraded mode at the edge. See [ADR-0003](ADR-0003-platform-agnostic-hybrid-deployment.md).
3. **Scale-agnostic staffing.** Work is expressed as work packages and pod templates, scalable by adding pods. See [`../staffing.md`](../staffing.md).
4. **Polyglot by design.** Go for the data plane, Python for domain and ML services, TypeScript for the console, with JSON Schema contracts as the only coupling. See [ADR-0002](ADR-0002-json-schema-contracts-over-shared-libraries.md).

## Related documents

| Document | Relationship |
|---|---|
| [`../architecture/01-system-context.md`](../architecture/01-system-context.md) | Platform context and the two mission sides |
| [`../architecture/02-ontology-model.md`](../architecture/02-ontology-model.md) | The 23 entity types, the 10 relation types, constraints C-001..C-008 |
| [`../architecture/03-foundation-services.md`](../architecture/03-foundation-services.md) | The six foundation services and the ten event types |
| [`../architecture/04-security-architecture.md`](../architecture/04-security-architecture.md) | Zero trust, ABAC, partitioning, accreditation boundaries |
| [`../architecture/05-deployment-architecture.md`](../architecture/05-deployment-architecture.md) | Zones, profiles, reconciliation path, degraded-mode behaviour |
| [`../roadmap/increments.md`](../roadmap/increments.md) | Increment 0 through Increment 5 |
| [`../roadmap/work-packages.md`](../roadmap/work-packages.md) | Work-package breakdown and pod assignments |
| [`../staffing.md`](../staffing.md) | Pod model and reference organisations |
| [`../risk-register.md`](../risk-register.md) | Programme and delivery risks with numeric exposure |
