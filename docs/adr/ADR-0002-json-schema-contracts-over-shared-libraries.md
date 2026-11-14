# ADR-0002: JSON Schema Contracts Instead of Shared Source Libraries

## Status

Accepted

## Date

2026-11-14

## Context

NGSH is intentionally polyglot. The data plane — ingestion, the event log, the edge agent — is Go, because it has to sustain a ≥ 10 GB/s burst ingestion path and an edge footprint measured in tens of megabytes (PSDD §8 Performance). Domain and ML services are Python, because the ML ecosystem (PSDD §9) lives there. The console is TypeScript, because the operator and program-office experience needs a rich client (IF-5, IF-7).

That choice immediately creates a coupling problem. A shared entity model, a shared validation rule set, a shared event envelope and a shared set of generated codecs all have to exist somewhere, and the naive answer is a shared library.

The naive answer has two failure modes. Either the library is written in one language and the other two call into it across a process boundary (which reintroduces a network dependency inside a single logical service and makes the "service" boundary artificial), or the library is duplicated per language and drifts. The second failure mode is the more common one and it is silent: a Python service accepts a `TestResult` that a Go service would reject, the discrepancy surfaces in production as an unexplainable projection divergence, and by then the schema has forked.

The alternative answer is an interface-definition language — Protobuf/gRPC, Thrift, Avro, GraphQL SDL, OpenAPI. Each is a legitimate choice and each was considered. What they share is that they are all *domain-specific* schema languages, with a schema that is meaningful only to a compiler that understands that language, and a set of generated types whose semantics are defined by code generation rather than by an inspectable artifact.

NGSH additionally needs something that the contracts layer already has and uses: a **classification-aware, constraint-aware ontology**, not just a shape. `contracts/ontology/registry.json` declares, per entity type, a `classificationFloor`, a `pii` flag and an owning pillar set; per relation type, the allowed source and target types, cardinality, `mayCrossClassification`, `requiresProvenance` and `supportsRollup`; and eight cross-cutting constraints C-001..C-008 that reference those attributes. That registry is JSON, inspectable by a human, diffable by a tool, and directly consumable by a policy engine. That is not an accident of implementation; it is the shape the problem wants.

## Decision

**The JSON Schema contract layer under `contracts/` is the single source of truth for every cross-service data structure. Generated codecs are produced from it into each language. No shared source library is published, and no service may hand-roll a model of a contract type.**

### Contract layout

| Path | Content | Authority |
|---|---|---|
| `contracts/ontology/common.schema.json` | `$defs` for `EntityId`, `Timestamp`, `Classification`, `Actor`, `Provenance`, `EntityHeader`, `Measurement`, `Attachment`, `Reference`, `FidelityScore`, `CostEstimate` | Common header and value objects used by every entity and every event |
| `contracts/ontology/entities.schema.json` | The 23 entity types, discriminated by `type` via `oneOf` | Entity bodies |
| `contracts/ontology/relations.schema.json` | The 10 relation types, with lifecycle fields `assertedAt` / `retractedAt` / `retractionReason` | Edge bodies |
| `contracts/ontology/registry.json` | Entity/relation registry plus constraints C-001..C-008 | Entity semantics, classification floors, constraint catalogue |
| `contracts/events/event-envelope.schema.json` | The envelope every record carries | Transport and versioning of every write |
| `contracts/events/<event-type>.schema.json` | Per-event payload schemas | Event payload bodies |
| `contracts/events/catalog.json` | The ten event types with `eventVersion`, `owner`, `schema` path, and `subscriptionGroups` | Event index and routing vocabulary |

### Versioning model

Four independent version numbers, each with a distinct blast radius.

| Version | Lives on | Bumped when | Semantics |
|---|---|---|---|
| `ontologyVersion` | `registry.json` | A new entity type, a new relation type, or a change to a registry attribute (floor, pii, pillars, cardinality, `mayCrossClassification`) | Major on removal or semantic change; minor on addition |
| `catalogVersion` | `catalog.json` | A new event type is added, or a `subscriptionGroup` changes | Minor on addition of a type; major on removal or regrouping |
| `eventVersion` | per event type, in `catalog.json` and the payload schema `$id` | The meaning or the required fields of that event type's payload change | Integer, monotonically increasing, per event type. This is the *payload* version |
| `version` | per entity, in `EntityHeader` | Any mutation of that entity | Optimistic-concurrency counter, not a schema version |

`catalog.json` states the rule explicitly: *"Adding a type is a minor version bump; changing the meaning or required fields of an existing payload is a major bump of that type's own eventVersion."*

### Compatibility rules

Within a single `eventVersion` (and within a single `ontologyVersion` for entity bodies):

| Change | Permitted within version? | Rationale |
|---|---|---|
| Adding a new **optional** property | Yes | An old consumer ignores it; a new consumer can use it |
| Adding a new property to a `payload` that has `additionalProperties: false` | Yes, provided it is optional | The payload schemas declare `additionalProperties: false`; adding an optional property is additive |
| Adding a new **enum value** | **No** | All enums in the contracts are closed. An old consumer's decoder will fail on an unseen value. A new enum value requires an `eventVersion` bump |
| Making an optional property required | **No** | Breaks every producer that omits it. Requires `eventVersion` bump |
| Removing or renaming a property | **No** | Requires `eventVersion` bump |
| Narrowing a type or adding a numeric/string constraint | **No** | Breaks existing producers. Requires `eventVersion` bump |
| Widening a constraint (relaxing a minimum, adding an accepted format) | Yes | Existing data remains valid |
| Changing the *meaning* of a field while keeping the shape | **No** | Shape compatibility is not semantic compatibility. Requires `eventVersion` bump even though the schema diff is empty. This case is the most common source of silent corruption and the reason `eventVersion` is tracked per event type and not inferred from the schema hash |
| Changing a `classificationFloor` in the registry | No — `ontologyVersion` major | Floor changes invalidate existing data classification |
| Changing `mayCrossClassification` on a relation type | No — `ontologyVersion` major | Alters what C-002 will permit at write time |
| Changing an entity's `idPrefix` | No — `ontologyVersion` major | Breaks every existing identifier |

Requirements:
1. **Backward compatibility within a major version is mandatory.** A consumer built against `eventVersion: 1` must correctly process every `eventVersion: 1` payload, including payloads produced later.
2. **Forward compatibility is not guaranteed and is not required.** A consumer must tolerate a payload whose `eventVersion` is greater than it knows by routing it to a quarantine path rather than failing hard — but it is permitted to refuse it. The fabric must never crash on an unknown `eventVersion`.
3. **Major version transitions are additive and time-boxed.** A `eventVersion: 2` is introduced alongside `eventVersion: 1`; consumers migrate; `eventVersion: 1` is retired only after all consumers have migrated and at least one full retention window has elapsed.
4. **Deprecation is explicit.** A retired version is recorded in `catalog.json` with a `deprecated` marker and a retirement date.

### What codegen must guarantee

The generator (`tools/codegen`) is the only permitted producer of contract-derived types. It must guarantee:

| # | Guarantee | Verification |
|---|---|---|
| GEN-1 | **Determinism.** Identical contract inputs produce byte-identical output. No timestamps, no environment, no map-iteration order in the output. | Regenerate twice in CI, diff the trees; fail on any difference |
| GEN-2 | **Staleness is a build failure.** Generated code is committed, and CI regenerates and fails if the committed tree differs from the regenerated tree. | CI job `contracts:codegen-check` |
| GEN-3 | **No hand edits.** Generated code lives in a dedicated package (`libs/ngsh-core` and per-language equivalents) that is excluded from manual-edit linting and carries a generated-code header. The package's public surface contains nothing but generated types and thin helpers | Lint rule + review checklist |
| GEN-4 | **Decode implies validate.** A decoded value has already passed schema validation. Validation is not a separate optional step in business logic. | Generated decoders call the validator; no raw deserialization path is exposed |
| GEN-5 | **Closed enums are total.** A generated enum type has an `Unknown` variant carrying the raw string. Decoding an unrecognized value never panics and never silently maps to a default | Property test: fuzz decode with arbitrary strings |
| GEN-6 | **Round-trip preservation.** Unknown fields encountered on read are preserved and re-emitted on write, so that a service acting as a relay does not strip fields it does not understand | Round-trip property test against the schema's `additionalProperties` policy |
| GEN-7 | **No reflection in the hot path.** Generated code must not require runtime schema evaluation per record. Schema evaluation is permitted at trust boundaries and in the contract-test harness only | Benchmark gate on the ingest path |
| GEN-8 | **Reference resolution.** `$ref` to `common.schema.json` and to the per-event schemas resolves offline, from a pinned local copy. No network fetch at build or run time | Build runs with network egress disabled |
| GEN-9 | **A published schema diff.** Every contract change emits a machine-readable diff (fields added, removed, tightened, enum values added) and attaches it to the change request. | CI artifact on every contract PR |
| GEN-10 | **Contract tests are generated too.** Each contract gets conformance fixtures: valid instances, invalid instances per constraint, and boundary cases. Services must pass the generated fixtures before release. | `contracts:conformance` job in every service pipeline |

### Change-control path for a contract change

1. Open a change request against `contracts/` naming the affected `eventVersion` or `ontologyVersion`.
2. Codegen produces the schema diff (GEN-9). A diff that touches a required field, an enum, a constraint, a floor or `mayCrossClassification` is classified **major**.
3. The registry-level constraints are re-checked: does the change alter the satisfiability of C-001..C-008 for existing data?
4. Backward-compatibility is checked by running the existing conformance fixtures against the new schema. Any fixture that now fails is a breaking change and forces a major bump.
5. Generated code is regenerated and committed; the CI staleness check (GEN-2) gates merge.
6. Consumer impact is assessed: every service declaring a subscription on the affected event type must confirm it handles the new version, or the event is routed to quarantine for that consumer.
7. The new version is added to `catalog.json` with its schema path and owner. Deprecated versions are retained with an explicit retirement date.

## Alternatives Considered

### ALT-1. Protobuf / gRPC as the contract layer

*Rejected.* Protobuf is the strongest candidate and was rejected on three specific grounds. First, it does not describe the *stored* form: the contracts are JSON Schema over JSON documents that live in a graph, a document store and a lakehouse, so JSON would remain in the stack and two schemas (`.proto` and JSON Schema) would have to be kept in step. Second, protobuf's generated types are not human-reviewable artifacts — a schema diff is a compiled diff, which is exactly the wrong property for an artifact that must be handed to a CMMC assessor, a prime partner and an academic partner with three different toolchains. Third, protobuf has no native way to express the classification and constraint semantics that the registry carries; those would live in a side file anyway, so the "single source of truth" claim would be false. What is retained from this option is the *generated codec* discipline and the discipline of a wire-version field per message.

### ALT-2. A shared library written in one language, called from the others via FFI or a sidecar

*Rejected.* Cross-language FFI (Go→cgo, Python→pybind11, TypeScript→napi) creates a native-code accreditation problem: every binary artifact in the product becomes an SBOM entry (PSDD §10 requires SBOM for all components), and native extension building in an IL5/IL6 build chain is a continuous operational burden. A sidecar process version is strictly worse — it is a network call inside what should be one service, it adds a serialization hop on the ingest path, and it makes the service boundary a lie.

### ALT-3. GraphQL SDL as the contract layer

*Rejected.* GraphQL is excellent at read/query shape and poor at the event semantics NGSH depends on: it has no per-message version field, no immutability concept, no notion of an aggregate with a monotonic sequence, and no natural representation of an append-only fact stream. It also does not express closed enums with the totality guarantee (GEN-5) that C-008-style read-time rules need. GraphQL is a reasonable *read API* on top of the projections; it is not a contract layer for the write path.

### ALT-4. Hand-written models per language, kept in step by convention

*Rejected.* This is the default and it is the failure mode this ADR exists to prevent. Three hand-written model sets for 23 entity types, 10 relation types, 10 event types and 11 common value objects is roughly 1,200 type definitions to keep in agreement. The divergence is not caught by review; it is caught in production, as an event that a Go service accepts and a Python service rejects, or — worse — as a projection that silently drops a field. The cost of generating instead is bounded and one-time; the cost of hand-writing is paid continuously.

### ALT-5. A single "core" model library published per language from one source with a hand-rolled generator

*Rejected as a variant of ALT-4.* If the generator is hand-rolled and the shared core is a bespoke DSL, then the contract layer is a *program* rather than a *document*, and every schema review requires reading generator output rather than a specification. JSON Schema draft 2020-12 is a published standard with published validation semantics; using it means the contract is reviewable by a human without running any NGSH tooling.

### ALT-6. Keep the contracts but remove codegen and validate at runtime with a JSON Schema validator

*Rejected for the hot path, retained for the trust boundary.* Runtime schema evaluation per record is far too slow for a ≥ 10 GB/s ingest path and adds a dependency with its own vulnerability profile. It is, however, exactly right at a trust boundary — an edge agent receiving NDJSON from a range instrument, a partner API accepting a payload. The decision is therefore: **generated decoders on the hot path, full schema validation at trust boundaries**, plus the generated conformance fixtures (GEN-10) that make the boundary behaviour testable.

## Consequences

### Positive

| # | Consequence |
|---|---|
| P-1 | Polyglot without a language monoculture. Go, Python and TypeScript all participate as first-class peers; none is the "owner" of the model. |
| P-2 | The contract is a human-reviewable artifact. A prime partner, an academic partner and a CMMC assessor can all read `contracts/ontology/entities.schema.json` without NGSH tooling. |
| P-3 | The registry's classification semantics (floors, `mayCrossClassification`, `pii`) are co-located with the shapes, so the enforcement rules and the shapes cannot drift apart. |
| P-4 | Compatibility is mechanical. GEN-2 (staleness), GEN-4 (decode implies validate), GEN-6 (round-trip) and GEN-10 (conformance fixtures) turn "did we break a partner?" from an opinion into a test result. |
| P-5 | Interoperability posture (PSDD §8: "Open APIs, OpenMBEE/SysML v2 alignment, OGC/NIEM-compatible data exchange where applicable") is credible because the platform can emit and consume plain JSON conforming to a published schema, not a proprietary binary. |
| P-6 | Adding a pillar cannot fork the model. A pillar that needs a new attribute extends an entity's `attributes` or proposes a new entity type through the change-control path, and every consumer gets the generated codec automatically. |
| P-7 | Contract reuse for free: the same schemas describe entities, event payloads and the envelope, so the audit ledger and the sanitized-extract manifest can reuse `Classification`, `Actor` and `Attachment` without a parallel schema family. |

### Negative

| # | Consequence |
|---|---|
| N-1 | JSON Schema is verbose. A 23-type `oneOf` entity schema is large, and the discriminated-union ergonomics of generated Go/Python/TypeScript types are not as pleasant as hand-written domain types. |
| N-2 | JSON Schema can express *shape*, not *semantics*. The `requiresSkill` relation may point at any `Skill`; nothing in the schema stops it pointing at one that does not exist. Existence and semantic validity live in the registry and the policy layer, not in the schema. See "What this makes harder" HW-1. |
| N-3 | Codegen is a build-time dependency that must itself be maintained, secured and included in the SBOM. A bug in the generator propagates to every consumer simultaneously. |
| N-4 | `additionalProperties: false` plus round-trip preservation (GEN-6) is a subtle pairing: a service that adds an unknown field locally and writes it back must not have that field rejected by a peer running an older schema. Implementations must therefore not strip or rewrite unknown fields without an explicit policy decision. |
| N-5 | Validation at trust boundaries plus generated decoders on the hot path means there are two validation regimes. A bug that appears only at the boundary (an edge agent's parser differing from the fabric's) is possible and must be tested for explicitly. |
| N-6 | Version compatibility across three languages and an unknown number of external consumers is a permanent operational tax. It is paid for by the CI budget in WP-0.1. |

### What this makes harder

| # | Harder thing | Why |
|---|---|---|
| HW-1 | Expressing cross-entity invariants | C-005 (a `Credential.personId` must resolve to a `Person` whose citizenship permits the activity and whose clearance is current at issue time) and C-006 (every `Person` referenced by a `Credential` or `ProcessRun.operatorId` must have a non-expired clearance at the time of reference) are *temporal, referential* constraints. JSON Schema cannot express them, so they live in the ontology/policy enforcement point at append time. The schema guarantees the *shape*; the registry plus the policy engine guarantees the *meaning*. Both are required, and only one of them is machine-checkable by a schema validator. |
| HW-2 | Closed enums | `System.systemType`, `TestResult.outcome`, `Model.modelType`, `ThreatSystem.threatClass`, `Person.citizenship`, `Actor.clearance` and the `Classification.level` enum are all closed. Adding a value is a major-version event for the affected event type, which is a heavier process than a normal schema edit. This is a deliberate trade: a closed enum in the contract layer is what makes GEN-5 (total decoding) and C-008 (read-time clearance comparison against `classification.level`) tractable. |
| HW-3 | Domain richness without domain sprawl | `attributes` is a free-form object on every entity, which could quietly become an untyped second model. The rule is: an attribute that has meaning across two or more pillars, or that appears in three or more entity types, must be promoted to a `$def` in `common.schema.json`. Enforcement is by review at the change-control step 3. |
| HW-4 | Referential integrity across projections | The contract layer guarantees that `Requirement.allocatedToIds` is a well-formed entity id. It does not guarantee the target exists. Referential integrity is a property of the log, enforced by the append path (which can see the aggregate set) and by projection reconciliation. This is an argument for the log being the system of record ([ADR-0001](ADR-0001-event-sourced-foundation.md)), not a weakness of the contract layer. |
| HW-5 | Generating for a language the organization does not use yet | The codegen must support Go, Python and TypeScript today and an academic partner's choice tomorrow (IF-5). Each additional target is a generator maintenance cost, and a target that is not maintained becomes a drift source — exactly the failure mode this ADR removes. |

## Compliance Notes

| PSDD / regulatory obligation | How this ADR supports it |
|---|---|
| PSDD §8 Interoperability — "Open APIs, OpenMBEE/SysML v2 alignment, OGC/NIEM-compatible data exchange where applicable" | A published JSON Schema contract is directly usable by a SysML v2 or NIEM partner without NGSH tooling; generated codecs are an optimization, not a prerequisite. |
| PSDD §8 Modularity — "All pillars independently deployable and licenseable (each must stand alone commercially)" | A pillar can be licensed, separated or re-implemented against the published contract alone. The contract layer is the boundary that makes standalone commercial viability plausible. |
| PSDD §10 — "NGSH itself developed under CMMC L2+ with SBOM for all components" | Generated code is a build artifact with a deterministic, auditable derivation from a reviewed source (GEN-1, GEN-9). It does not add a third-party dependency to the SBOM, and its provenance is stronger than a hand-written model's. |
| PSDD §6.3 — ITAR/EAR partitioning; sanitized extracts for academic partners | Because the contract is a document, a sanitized-extract profile can be defined as a *schema profile* (a projection of the same contract with a restricted field set) rather than as bespoke export code. This is a prerequisite for the ICAP-style guard described in [ADR-0007](ADR-0007-classification-partitioning.md). |
| PSDD §8 Auditability — "Every model version, test result, and access decision reconstructable" | `eventVersion` makes "which version of the record was this?" answerable without guessing; without it, reconstruction of a historical decision is ambiguous. |
| CMMC 2.0 L2 (SA family) | Change control over contracts with a machine-produced diff and a defined compatibility test is a system-development change-control artifact, not a documentation exercise. |
| CMMC 2.0 L2 (CA-2, CA-3) | A published, versioned contract set is the "system inventory and its documented boundaries" evidence at the interface level. |
| CMMC 2.0 L2 (MP family) | `EntityHeader.version` plus per-entity `Provenance` gives the media-protection evidence chain; every contract change is a protected configuration item. |

## References

**PSDD:** §4.2 (design principles 2, 5, 6), §6.1 (core ontology), §6.2 (data stores), §6.3 (data governance), §7 (interface design), §8 (Interoperability, Modularity, Auditability), §9 (AI/ML governance), §10 (Security & Compliance Architecture), §14 (teaming strategy — partners consume the contracts).

**Contracts:**
- `contracts/ontology/common.schema.json` — the shared `$defs` referenced by every other schema.
- `contracts/ontology/entities.schema.json` — 23 entity types via `oneOf`; `additionalProperties` semantics on `attributes`.
- `contracts/ontology/relations.schema.json` — 10 relation types with a closed `type` enum and retraction lifecycle.
- `contracts/ontology/registry.json` — `ontologyVersion`, per-type `classificationFloor` / `pii` / `pillars`, relation `cardinality` / `mayCrossClassification` / `requiresProvenance` / `supportsRollup`, constraints C-001..C-008.
- `contracts/ontology/registry.schema.json` — the schema that validates the registry itself.
- `contracts/events/event-envelope.schema.json` — `eventVersion`, `schemaRef`, `idempotencyKey`, the `edge` reconciliation block.
- `contracts/events/catalog.json` — `catalogVersion`, per-type `eventVersion`, `subscriptionGroups`, and the stated minor/major bump rule.
- `contracts/events/<event-type>.schema.json` — payload bodies; note `additionalProperties: false` on each.

**Tooling:** `tools/codegen` (generator), `libs/ngsh-core` (committed generated output for the reference language).

**Related ADRs:** [ADR-0001](ADR-0001-event-sourced-foundation.md) (the log is the write path the contracts govern), [ADR-0007](ADR-0007-classification-partitioning.md) (contract-level classification semantics and sanitized-extract profiles), [ADR-0008](ADR-0008-model-card-and-fidelity-registry.md) (model card and fidelity shapes are contract-governed).
