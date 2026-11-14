# ADR-0004: ABAC with Separated Policy Decision Point and Policy Enforcement Points

## Status

Accepted

## Date

2026-11-14

## Context

PSDD §6.3 requires, at ingestion and thereafter: *"CUI tagging at ingestion; attribute-based access control (ABAC) with classification, program, citizenship, and need-to-know attributes"*, plus ITAR/EAR partitions and sanitized extracts for academic partners. PSDD §8 requires zero trust, an IL5 baseline with an IL6 annex architecture, and continuous monitoring. PSDD §10 requires a Program Protection Plan whose artifacts are generated automatically from data lineage, and describes ICAP-class guard services for sanitized extract generation. PSDD §7 defines IF-6 (Government identity PIV/ICAM) as the authentication and clearance-verification channel.

The authorization problem NGSH faces is not a role problem. It is a conjunction of at least five independent dimensions:

1. **Classification** — the level of the content (`Classification.level` ∈ UNCLASSIFIED / CUI / CUI//REL / CUI//FOUO / RESTRICTED / SECRET / TOP SECRET), plus caveats and original classification authorities.
2. **Program** — need-to-know scoping. A `Person` cleared to SECRET and assigned to NGSH-SHY has no need to know NGSH-MAVERICK threat data. This is a *per-resource* attribute, not a per-role attribute.
3. **Citizenship** — `Actor.citizenship` ∈ US / ALLIED / FOREIGN / UNKNOWN. Export-controlled content (ITAR/EAR) is gated on citizenship, not on clearance.
4. **Clearance** — `Actor.clearance` ∈ NONE / SECRET / TOP SECRET / SCI-CLEARED, matched against the resource level, with an expiry date (C-005, C-006).
5. **Environment** — device posture, network zone, time of access, tenant, whether the access is local to a physically controlled annex.

Any authorization model must express the conjunction, must evaluate it in **every** zone (including an IL6 annex with no reachability to a shared policy service), and must leave a reconstructable record of every decision (PSDD §8 Auditability).

The architectural question beyond the model itself is *where* the decision is made. If each service embeds its own authorization logic, the enforcement semantics fork with the number of services, and an assessor must sample every service to establish that the rule is the same everywhere. If a single monolithic service makes every decision, that service becomes both the availability bottleneck for the 10 GB/s ingest path and the highest-value target in the system.

## Decision

**NGSH uses attribute-based access control, evaluated by a dedicated Policy Decision Point (PDP) that is deployable in every zone, and enforced at multiple Policy Enforcement Points (PEPs) that are each co-located with the resource they protect. Authorization is deny-by-default. Every ALLOW carries obligations that the PEP must discharge.**

### The attribute model

| Subject attribute | Source | Notes |
|---|---|---|
| `actor.subjectId` | PIV/ICAM identity (IF-6) | Entity id in the `Person` namespace (`PER:` prefix) |
| `actor.kind` | Service identity registry | `user`, `service`, `device`, `edge-agent`, `anonymous` (per `contracts/ontology/common.schema.json`, `Actor.kind`) |
| `actor.clearance` | ICAM attribute store, cached | `NONE` / `SECRET` / `TOP SECRET` / `SCI-CLEARED`; verified, never self-asserted |
| `actor.citizenship` | ICAM attribute store, cached | `US` / `ALLIED` / `FOREIGN` / `UNKNOWN`; `UNKNOWN` is treated as the most restrictive |
| `actor.programs[]` | Program membership register | Need-to-know scoping, one entry per program of record |
| `actor.needToKnow[]` | Derived program membership + explicit grants | Fine-grained scoping tags beyond program |
| `actor.org` | Directory | Organization and, where relevant, facility |
| `actor.clearanceExpiry` | ICAM | Used by C-005 / C-006; a lapsed clearance denies even a high level |

| Resource attribute | Source | Notes |
|---|---|---|
| `resource.type` | Ontology registry | The 23 entity types |
| `resource.id` | Ontology | Typed entity id |
| `resource.classification.level` | Entity header | Authoritative |
| `resource.classification.caveats[]` | Entity header | e.g. `NOFORN`, `PROPIN` |
| `resource.classification.origins[]` | Entity header | Required for 508/5320-style marking |
| `resource.derivedFromClassified` | Entity header | Marks content derived from classified sources; forces sanitization on export |
| `resource.program` | Entity header | Program of record |
| `resource.tenant` | Entity header | Multi-program tenancy key |
| `resource.pii` | Ontology registry (`pii` flag) | True only for `Credential` and `Person` |
| `resource.floor` | Ontology registry (`classificationFloor`) | Minimum classification the type may hold (C-001) |

| Environment attribute | Source | Notes |
|---|---|---|
| `env.zone` | Deployment configuration | Z-1 / Z-2 / Z-3 / Z-0 |
| `env.network` | Deployment configuration | Which zones the calling node can reach |
| `env.devicePosture` | Device management / attestation | Managed, compliant, encrypted at rest |
| `env.time` | Fabric clock | Used by time-bounded grants and by C-005/C-006 validity checks |
| `env.locality` | Edge node identity | Whether the request originates inside a physically controlled annex |

### PDP / PEP topology

| Role | Component | Responsibility |
|---|---|---|
| **PDP** | `policy-service` | Evaluates the policy bundle against subject, resource and environment attributes. Returns `ALLOW` / `DENY` / `INDETERMINATE`, a `policyId`, a `policyVersion`, a human-readable `reason`, and a list of `obligations`. Emits `access.decision.recorded` for every decision |
| **PEP — fabric** | `fabric-service` (append and subscribe paths) | Guards the append API and the subscription/read path. Every append and every read of an event requires a decision |
| **PEP — graph** | `thread-service` | Guards every graph query. Applies the decision to the *result set*, not only to the query, because a traversal can reach a node the caller could not have fetched directly |
| **PEP — ingest** | `ingest-service` | Guards bulk ingestion. Decides at the *batch* level (classification of the batch) and at the record level where a batch mixes classifications |
| **PEP — bytes** | Object-store gateway | The only path to raw artifacts. The decision is on the URI, not on the bytes, and the gateway performs the classification check independently of the referring record — the referrer cannot downgrade what it points at |
| **PEP — console** | TypeScript web client | Field-level masking and export control. The console is a PEP but is never trusted to be the only PEP |
| **PEP — edge** | Edge agent | Evaluates locally against a synchronised policy bundle when the PDP is unreachable. A policy bundle is signed; the edge verifies the signature and applies only the most restrictive rules if the bundle is stale |

The PDP is stateless between decisions other than a bounded decision cache. Policy bundles are versioned documents; the `policyVersion` on every decision makes the rule that was applied reconstructable.

### Decision semantics

| Rule | Statement |
|---|---|
| DS-1 | Deny by default. An absent rule is a DENY, never an ALLOW. |
| DS-2 | Explicit deny overrides any allow. |
| DS-3 | `INDETERMINATE` is returned only when the PDP cannot reach a required attribute source (for example, a stale clearance cache on an IL6 annex with no directory path). `INDETERMINATE` is treated as DENY by every PEP, but it is distinguished in the audit record because it indicates a *system* condition, not a user condition |
| DS-4 | Classification comparison uses the ordering `UNCLASSIFIED < CUI < CUI//REL < CUI//FOUO < RESTRICTED < SECRET < TOP SECRET` as declared in `Classification.level`, with the caveat that `CUI//REL`, `CUI//FOUO` are CUI derivatives and are treated as CUI for clearance purposes and as CUI for partitioning, while caveats travel with the record |
| DS-5 | Clearance must be current at the moment of access, not merely present in the cache. A clearance whose `clearanceExpiry` has passed denies |
| DS-6 | Citizenship gates export-controlled resources: `FOREIGN` and `UNKNOWN` citizens never receive resources marked `exportControlled` (ITAR/EAR) regardless of clearance |
| DS-7 | Program need-to-know is conjunctive with classification. A correctly cleared actor with the wrong program membership still receives DENY |
| DS-8 | The floor constraint is applied as a *write* rule (C-001): a write whose classification is below the entity type's `classificationFloor` is rejected at the PEP before it reaches the log. The PDP also returns it as a resource attribute so that read-side rules can be written against it |
| DS-9 | Boundary-crossing relations are applied as a *read* rule (C-002, C-008): the PEP compares the classification of both endpoints of a traversed relation and denies a traversal that would cross a boundary that the relation type does not permit (`mayCrossClassification=false` in the registry) |
| DS-10 | Every ALLOW carries obligations. Obligations are mandatory; a PEP that cannot discharge an obligation must not return ALLOW |

### Obligations on ALLOW

| Obligation | Meaning | Enforced by |
|---|---|---|
| `log-externally` | The access must additionally be written to the audit ledger, not only to the event log | Audit PEP |
| `audit-every-read` | The read must produce an `access.decision.recorded` event even though reads are normally not events | Fabric PEP |
| `watermark` | The rendered output must carry a visible, user-attributable marking | Console PEP, export gateway |
| `no-export` | The content may be read but not exported, downloaded, copied or printed | Console PEP, export gateway, DLP at the object-store gateway |
| `redact-attributes` | Specific attributes must be masked before the content reaches the caller | Thread PEP, console PEP |
| `notify` | A second party must be notified of the access | Policy service post-decision hook |
| `require-recent-mfa` | The access is only permitted with an MFA assertion inside a specified time window | Identity integration, PDP context |
| `log-attribute-access` | Attribute-level read events must be recorded, not only entity-level | Thread PEP |

### Why not RBAC alone

Role-based access control remains in use as a **coarse overlay** — there are roles such as `program-admin`, `range-operator`, `safety-reviewer` and `auditor` that grant administrative capabilities. It is not the primary model. The reasons:

| # | Problem with RBAC alone | How ABAC resolves it |
|---|---|---|
| 1 | RBAC cannot express the conjunction of clearance, citizenship, program membership and resource classification without exploding into role permutations | ABAC evaluates the conjunction directly over attributes |
| 2 | Need-to-know is a *relationship* between an actor and a resource set, and it changes as programs re-scope. Roles encode the grant at the time of assignment; ABAC evaluates the grant at the time of access | Attributes are read live from the program register |
| 3 | Classification is a property of the *data*, and data is created continuously by ingestion. Every new classified artifact would need a role assignment for every legitimate reader — unmanageable at ingestion rates | ABAC compares the record's own `classification` header to the actor's clearance on every access |
| 4 | Temporal validity (C-005, C-006) needs "clearance current at the time of reference", which a static role cannot express | `actor.clearanceExpiry` and `env.time` are policy inputs |
| 5 | Role explosion: a coarser and coarser role set is the standard failure mode, producing roles named for situations rather than for duties | ABAC keeps the attribute set stable as content grows |
| 6 | RBAC does not carry obligations. "May read, may not export" cannot be expressed | Obligations are a first-class output of the decision |

### Defence in depth at the storage layer

Application-layer filtering is necessary and not sufficient. The enforcement is layered:

| Layer | Control |
|---|---|
| 1. PDP | The decision itself, with `policyId` and `policyVersion` |
| 2. PEP (service) | Applied per request, and per result-set element for traversals |
| 3. Storage | Physically partitioned by classification level ([ADR-0007](ADR-0007-classification-partitioning.md)). A query path is bound to a partition; a caller cannot reach a partition it is not cleared for because there is no network path to it |
| 4. Object-store gateway | Independent classification check on the raw bytes; the referring record cannot downgrade what it points at |
| 5. Guard service (ICAP-style) | The only egress path from classified to unclassified; produces sanitized extracts and records the extract manifest |
| 6. Audit ledger | Independent, tamper-evident record of every decision ([ADR-0005](ADR-0005-tamper-evident-audit-ledger.md)) |

## Alternatives Considered

### ALT-1. Pure RBAC with role-per-classification-per-program

*Rejected.* Fails immediately on the ingestion path. A newly created CUI record in program NGSH-SHY would require a role that every legitimate reader of NGSH-SHY CUI data holds, and granting that role also grants read on every other CUI record in that program — including records the reader has no need to know. This is exactly the "need-to-know" requirement PSDD §6.3 states. It also cannot express export-control gating on citizenship, which PSDD §10's ITAR/EAR posture depends on.

### ALT-2. Discretionary access control with per-object ACLs

*Rejected.* ACLs put the authorization decision on the object, which means every write must be accompanied by an ACL decision and every read must resolve an ACL list. With an inherited, graph-shaped structure (a `Part` inherits from a `Material`, a `TestResult` inherits from a `TestArticle`, all within a program), ACL inheritance becomes a second access-control language with its own administration burden. It also gives no basis for deny-by-default on *new* content: the default for a new object with no ACL is a decision the system must make implicitly, and ACL systems consistently make it permissive.

### ALT-3. Embedded authorization in each service, no separate PDP

*Rejected.* This is the most common failure mode in systems of this size. The semantics of the rule fork across six foundation services and eight pillars; a rule change requires N coordinated releases; an assessor must sample every service to conclude that "access control is implemented consistently"; and the enforcement evidence required by CMMC CA-3 (control of information transferred) is multiplied by the service count. It also produces exactly the wrong availability profile: authorization becomes embedded in the ingest hot path with no independent scaling or caching story.

### ALT-4. External policy engine as the PDP (e.g. an OPA/Rego-class engine), NGSH supplying the PEPs

*Rejected as the primary path, retained as an option for the rule language.* A declarative policy language is genuinely better for expressing the rules, and the platform should evaluate whether an external engine can be accredited and operated inside an IL6 annex with no outbound path. The reasons for not making it the primary decision are concrete: the policy engine's evaluation becomes an in-process dependency on the 10 GB/s ingest path; the interpreter and its transitive dependencies become part of the accredited product and the SBOM; and an external engine does not by itself solve the harder problem, which is **where the decision is enforced** — the PEP topology and the storage-layer partitioning — which is independent of the PDP implementation. The decision to separate the PDP as a *deployable component in every zone* is the durable part of this ADR; the rule evaluation engine behind it is an implementation detail subject to change.

### ALT-5. MAC / lattice-based access control (Bell-LaPadula / Biba) as the primary model

*Rejected.* Lattice models give a clean confidentiality argument and are attractive for a platform with a strong classification hierarchy. They were rejected as the primary model because NGSH's access decisions are not purely hierarchical: program need-to-know, citizenship-based export control, device posture and time-bounded grants are not lattice-comparable, so the lattice would have to be extended with non-lattice dimensions — at which point ABAC is the honest description of what is being built. Biba-style integrity (no write-down) is retained as a *specific derived rule* for the downgrade-prevention requirement, implemented physically per [ADR-0007](ADR-0007-classification-partitioning.md) rather than as the general model.

## Consequences

### Positive

| # | Consequence |
|---|---|
| P-1 | One rule, one place. The policy bundle is versioned; the decision carries `policyId` and `policyVersion`, so "which rule applied at 14:32 on the 3rd" is answerable exactly. |
| P-2 | Enforcement survives service churn. New services and new pillars inherit the PDP/PEP pattern; the rule does not need re-implementing. |
| P-3 | Deny-by-default plus explicit floor constraints means a bug in a new rule can only produce DENY, not disclosure — the failure mode of an authorization system should be a denial, and here it is. |
| P-4 | The decision record is an event (`access.decision.recorded`), so it participates in the same lineage, replay and audit machinery as everything else. No parallel audit mechanism is needed for access. |
| P-5 | Obligations are expressible, which RBAC cannot do, and are the mechanism by which "readable but not exportable" and "log externally" are enforced in practice. |
| P-6 | The PDP is deployable in every zone, including the IL6 annex and the edge appliance, so enforcement does not depend on cross-zone reachability. |
| P-7 | CMMC assessment evidence for AC-3, AC-5, AC-6, AU-2 and CA-3 is generated from the decision stream rather than assembled by hand. |

### Negative

| # | Consequence |
|---|---|
| N-1 | A PDP is an extra hop on the request path, including on the ingest hot path. Mitigated by a bounded, decision-keyed cache with a conservative TTL; the cache must be invalidated by policy-bundle version change and by clearance revocation events. |
| N-2 | The policy bundle is a critical configuration artifact. It needs change control, review, testing and a rollback path, and a bad bundle can deny the entire program or, worse, allow too much. |
| N-3 | Attribute quality becomes a security property. A stale clearance cache is a security defect, not a performance defect. This creates a hard dependency on the identity integration and on ICAM attribute freshness. |
| N-4 | Deny-by-default with `INDETERMINATE`-as-deny means any attribute-source outage becomes an availability event. The PDP must degrade safely (deny) while making the condition loudly visible. |
| N-5 | Policy authorship is a specialised skill. The team needs someone who can express a rule in a way that is both correct and legible to a non-programmer reviewer who will sign the assessment. |
| N-6 | Obligation enforcement is distributed: the decision says "watermark", but the console and the export gateway must actually do it. Every obligation requires a per-PEP implementation and a per-PEP test. |

### What this makes harder

| # | Harder thing | Why |
|---|---|---|
| HW-1 | Expressing "the same rule" across a CUI partition and a SECRET partition | The policy bundle is one document with per-level sections. A rule that must differ by level is a sign the rule is really two rules; the policy service must be able to evaluate per-zone variants without the caller having to know. |
| HW-2 | Offline edge enforcement | The edge agent needs a signed policy bundle and a way to decide "is my bundle too stale to trust?" — a staleness bound. Beyond the bound, the edge must fall back to its most restrictive local ruleset, which is a degraded but safe behaviour that must be specified per capability. |
| HW-3 | Result-set filtering in graph traversal | A PEP that guards the *query* rather than the *result* is not an access control. The thread service must filter nodes and edges during traversal, and must not leak the *existence* of a node the caller may not read — including through counts, path lengths and timing. |
| HW-4 | Policy change across eight pillars | A bundle change is a coordinated release because the decision stream must remain comparable across the change boundary. The `policyVersion` field makes the analysis possible, but the operational discipline is required. |
| HW-5 | Sanitized extract authorisation | The extract is a *product* of a decision, not a record. The guard service needs a policy that authorises the *transformation*, and the result needs its own classification, which may be lower than its inputs. This is the hardest single rule in the system and it is specified in [ADR-0007](ADR-0007-classification-partitioning.md). |
| HW-6 | Explainability | A DENY must be explainable to a user and to an assessor in terms of attributes and policy, not as "the policy service said no". The `reason` field on the decision is therefore a contract requirement, not a convenience. |

## Compliance Notes

| PSDD / regulatory obligation | How this ADR supports it |
|---|---|
| PSDD §6.3 — "attribute-based access control (ABAC) with classification, program, citizenship, and need-to-know attributes" | Direct implementation; the four named attributes are the first four rows of the subject attribute table. |
| PSDD §6.3 — "ITAR/EAR partitions; sanitized extracts for academic partners" | `exportControlled` on `Part` and `Supplier` plus the citizenship rule (DS-6) implement the export gate; the sanitized-extract path is the guard service specified in [ADR-0007](ADR-0007-classification-partitioning.md). |
| PSDD §6.3 — "CUI tagging at ingestion" | The ingest PEP decides at batch and record level, so the classification header is stamped and checked at the point of ingestion rather than inferred later. |
| PSDD §8 Security — "Zero trust; IL5 baseline with IL6 annex architecture; ABAC; continuous monitoring (CONMON)" | Never-trust/always-verify is the PDP/PEP model; continuous monitoring is the `access.decision.recorded` stream plus the audit ledger. |
| PSDD §8 Auditability — "every ... access decision reconstructable" | `access.decision.recorded` carries `decision`, `action`, `resource`, `policyId`, `policyVersion`, `obligations`, `reason` and `context`. |
| PSDD §10 — "Program protection: PPP artifacts generated automatically from data lineage" | The decision stream combined with lineage traversal is the input to PPP artifact generation. |
| PSDD §10 — "Cross-domain: ICAP-class guard services for sanitized extract generation" | The guard service is specified as a PEP plus an egress chokepoint in the layered defence table. |
| CMMC 2.0 L2 (AC family) | AC-3 (access enforcement) is the PDP/PEP pair; AC-6 (least privilege) is the attribute conjunction; AC-2 (account management) and AC-12 (session management) are the PIV/ICAM integration. |
| CMMC 2.0 L2 (AU family) | AU-2 (event logging), AU-3 (content of records), AU-6 (audit review) and AU-10 (non-repudiation) are the `access.decision.recorded` stream plus the ledger. |
| CMMC 2.0 L2 (CA family) | CA-3 (information transferred) is the ingestion PEP and the object-store gateway; CA-5 (information system components) is the SBOM posture. |
| CMMC 2.0 L2 (SC family) | SC-7 (boundary protection) is the zone topology and the storage-layer partitioning. |
| DoD Instruction 5000.01 / DCSA assessment | Supply-chain security for the NGSH product itself is covered in `04-security-architecture.md`; rule P-1 keeps third-party platform SDKs out of the accredited product. |

## References

**PSDD:** §6.1 (ontology types that carry classification), §6.3 (data governance — ABAC, classification, ITAR/EAR, audit, lineage), §7 (IF-6 government identity; IF-5 academic consumers), §8 (Security, Auditability), §9 (AI/ML — human-on-the-loop for safety-relevant predictions is an obligation on model use), §10 (Security & Compliance Architecture — deployment pattern, cross-domain guards, program protection), §13 (risks — classification friction, threat-data access chokepoint).

**Contracts:**
- `contracts/ontology/common.schema.json` — `Classification` (level enum, caveats, origins, `derivedFromClassified`), `Actor` (clearance, citizenship, programs, needToKnow), `EntityHeader.classification`, `Provenance.reviewedBy`.
- `contracts/ontology/registry.json` — `classificationFloor` per entity type (feeds DS-8 / C-001); `pii: true` on `Credential` and `Person`; `mayCrossClassification` per relation type (feeds DS-9 / C-002); C-001, C-002, C-005, C-006, C-008.
- `contracts/events/access.decision.recorded.schema.json` — the decision record: `decision` ∈ ALLOW/DENY/INDETERMINATE, `policyId`, `policyVersion`, `obligations[]`, `reason`, `context`.
- `contracts/events/event-envelope.schema.json` — `actor` and `classification` on every envelope, so every write carries the subject attributes that were in force.

**Related ADRs:** [ADR-0003](ADR-0003-platform-agnostic-hybrid-deployment.md) (the PDP must be deployable in every zone), [ADR-0005](ADR-0005-tamper-evident-audit-ledger.md) (independent attestation of decisions), [ADR-0007](ADR-0007-classification-partitioning.md) (storage-layer defence in depth), [ADR-0008](ADR-0008-model-card-and-fidelity-registry.md) (human approval is an obligation attached to model use).
