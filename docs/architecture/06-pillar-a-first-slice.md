# Pillar A First Slice — Architecture Service

## Purpose

This document states what the Pillar A first slice delivers, how its two
capabilities are computed, and what it deliberately does not do. It exists so
that an engineer extending Pillar A knows which parts of the behaviour are
load-bearing, and so that an assessor can check the increment's claims against
an implementation rather than against a promise.

The slice implements **WP-1.1** (configuration baseline and digital twin
backbone) and **WP-1.2** (requirements and traceability engine) from
[`../roadmap/work-packages.md`](../roadmap/work-packages.md). Increment 1
commits to these two work packages as the first slice of capabilities **A-1**
and **A-3**, because Pillar E's curriculum and credentials are drawn from the
digital thread and would otherwise be built on illustrative data
([`../roadmap/increments.md`](../roadmap/increments.md) §4).

## Contents

1. [What is delivered](#1-what-is-delivered)
2. [Configuration baselines](#2-configuration-baselines)
3. [The interface registry](#3-the-interface-registry)
4. [Requirement traceability](#4-requirement-traceability)
5. [API surface](#5-api-surface)
6. [Storage and deployment](#6-storage-and-deployment)
7. [What is not delivered](#7-what-is-not-delivered)
8. [Verification](#8-verification)

## 1. What is delivered

| Capability | Delivered | Not delivered |
|---|---|---|
| **A-1** Configuration baseline | Content-addressed baselines pinning part revisions, variants, interfaces and software builds; reproducible identity; resolution from a `TestArticle` | The full SysML environment, baseline branching and merging, and the design-change workflow |
| **A-1** Interface registry | Characteristic validation (rate, latency, timing model, envelope) and content digests for ICD revisions | Interface negotiation and the automated ICD conformance test harness |
| **A-3** Traceability | Verification status computed from `verifies` evidence; review items for `MARGINAL`, `INCONCLUSIVE`, unreviewed `PASS` and `NOT_RUN`; hierarchy rollup; gap report | The requirement authoring UI, cost-driver linkage and the full Pillar A scope, which completes in Increment 5 |

The service is `services/architecture-service` (port 8088). It holds the
domain rules in `libs/ngsh-core/ngsh_core/architecture.py` so that the thread
projection and the architecture service cannot disagree about whether a
requirement is verified.

## 2. Configuration baselines

A baseline is a set of pinned members:

```json
{
  "systemId": "SYS:01J8Z...",
  "name": "Preliminary design review",
  "members": [
    {"entityType": "Part", "entityId": "PART:01J8Z...", "revision": "C"},
    {"entityType": "Variant", "entityId": "VAR:01J8Z...", "revision": "2"},
    {"entityType": "Interface", "entityId": "IFC:01J8Z..."}
  ],
  "softwareBuilds": ["fw-1.4.2"]
}
```

### 2.1 The identifier is the content

The baseline identifier is derived from the canonical JSON of the system id
and the sorted members:

```
digest = sha256(canonical_json({idVersion, systemId, members}))
id     = "BL:" + digest[:26].upper()
```

Three consequences follow, and each is a test:

| Consequence | Why it matters | Where it is tested |
|---|---|---|
| The same inputs produce the same id on any machine | Two partners can compare baselines without exchanging an allocator | `tests/unit/test_architecture.py::test_baseline_id_is_deterministic_across_member_order` |
| Renaming a baseline does not change its identity | A label is not a configuration | `test_baseline_id_ignores_the_label` |
| A stored baseline can be re-proved from its own record | A baseline that cannot be recomputed is a claim | `verify_baseline`, exercised by `POST /v1/baselines/{id}/verify` |

`idVersion` is part of the digest. Changing the derivation is a
contract-breaking change and must bump the version, which is why the version
travels with every stored baseline.

### 2.2 Ambiguity is rejected

A baseline that pins two revisions of the same part is not a baseline. The
service rejects duplicate members, unknown entity types, member ids that do not
carry their type's prefix, and a revisioned type (`Part`, `Variant`,
`Interface`, `Material`, `ProcessPlan`) without a revision. Rejection is
preferable to guessing, because a test article resolved against an ambiguous
baseline is not evidence.

### 2.3 Resolution from a test article

A `TestArticle` names its configuration through `buildConfigurationId`.
`GET /v1/baselines/resolve/{testArticleId}` reports one of three outcomes:

* the article resolves to a registered baseline (`resolved: true`);
* the article names no build configuration (`resolved: false`);
* the article names a baseline the service does not hold (`resolved: false`).

The third case is not treated as success. A test article whose configuration
cannot be produced is a finding, not a default.

## 3. The interface registry

An interface declares four characteristics, and each answers a different
question:

| Characteristic | Question it answers | Validation |
|---|---|---|
| `rate` | How much data crosses per unit time | Positive number |
| `latency` | How long it may take | Number ≥ 0 |
| `timing` | What synchronisation model applies | `SYNCHRONOUS`, `ASYNCHRONOUS`, `PERIODIC`, `EVENT` |
| `envelope` | Within what operating range the budgets hold | Non-empty object |

An interface that declares a rate but not a timing model is not an interface;
the registry refuses it. `interface_digest` hashes the endpoints and the
normalised characteristics, so a baseline can pin an ICD revision rather than
an ICD label. The `Interface` entity itself is still written through the normal
ontology path; this registry adds the completeness gate.

## 4. Requirement traceability

### 4.1 The evidence rule

Verification status is computed, never read from the stored
`verificationStatus` attribute. The stored attribute is an assertion; the
computed status is the finding.

| Evidence | Status | May satisfy? |
|---|---|---|
| No `verifies` evidence | `NOT_STARTED` | No, and a gap item is raised |
| `PASS` with `reviewedBy` present, and nothing outstanding | `COMPLETE` | Yes |
| `PASS` without `reviewedBy` | `PARTIAL` | No: an unreviewed pass is a claim |
| `MARGINAL` | `PARTIAL` | No: raises a `marginal_outcome` review item |
| `INCONCLUSIVE` | `PARTIAL` | No: raises an `inconclusive_outcome` review item |
| `NOT_RUN` | `PARTIAL` | No: raises a `not_run` review item |
| `FAIL` present | `PARTIAL` / `IN_PROGRESS` | No, and a gap item is raised |
| Outcome outside the contract enum | `PARTIAL` | No, and a gap item is raised |

`MARGINAL` and `INCONCLUSIVE` do not satisfy a requirement: they raise a
review item for a human, which is WP-1.2 acceptance criterion 2. Coverage is
the ratio of *satisfying* results to total results, so an unreviewed pass
contributes to the denominator and not the numerator.

### 4.2 The rollup

`aggregate_status` combines a requirement's own status with its children's:

* `COMPLETE` only when the parent and every child are complete;
* `NOT_STARTED` only when nothing in the subtree has started;
* `PARTIAL` when the subtree is mixed or anything is complete but not all;
* `IN_PROGRESS` otherwise.

`rollup_tree` evaluates post-order over `parentId`, in sorted id order, so the
same tree always produces the same report. It reports orphans (a child whose
coverage is missing) and cycles rather than absorbing them into a parent's
status.

## 5. API surface

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/baselines` | Create or fetch a baseline (idempotent) |
| `GET` | `/v1/baselines` | List baselines, optionally by `systemId` |
| `GET` | `/v1/baselines/{id}` | Fetch one baseline |
| `GET` | `/v1/baselines/resolve/{testArticleId}` | Resolve an article to its baseline |
| `POST` | `/v1/baselines/{id}/verify` | Recompute the baseline identity |
| `POST` | `/v1/interfaces` | Register an interface definition |
| `GET` | `/v1/interfaces` | List registered interfaces |
| `GET` | `/v1/requirements/{id}/coverage` | Coverage report for one requirement |
| `POST` | `/v1/requirements/rollup` | Rollup for a set or a subtree |
| `GET` | `/v1/requirements/gaps` | Requirements with a gap or review item |

Every response is the same shape the console and the other pillars consume;
there is no second, richer internal representation. The service also exposes
the standard `/healthz`, `/readyz` and `/v1/service/info` endpoints.

## 6. Storage and deployment

Only two tables are owned by the service, in the platform database:

| Table | Content |
|---|---|
| `architecture_baselines` | Baseline identity, digest, pinned members, software builds, authorship |
| `architecture_interfaces` | Interface definition keyed by content digest |

Everything else — requirements, test results, test articles, systems — is read
from the thread projection, which is rebuilt from the event log (ADR-0001).
The service therefore has no second copy of the digital thread, and a
projection rebuild cannot leave it stale.

The service is a normal platform container: the same image runs in DP-L,
DP-5, DP-6 and DP-E, and the storage layer is the shared executor over SQLite
or PostgreSQL. It appears in `deploy/compose/docker-compose.yml` and in the
Helm chart as `services.architecture`; no deployment profile treats it
differently from the foundation services.

## 7. What is not delivered

Stated plainly, because the increment's exit criteria are not yet met:

| Item | Status | Blocker |
|---|---|---|
| I1-1, real-thread training scenarios | Not started | Pillar E training environment (WP-1.3) is not built |
| I1-2, partner curriculum replication | Not started | Requires an academic partner and the AW-1 handoff |
| I1-3, ≥ 100 issued credentials | Not started | Credentialing service (WP-1.5) is not built |
| I1-4, monthly workforce gap report | Not started | Requires classified production demand data |
| I1-5, sandbox extract pipeline | Not started | Requires the security review workflow and a partner environment |
| I1-6, ≥ 50 traced requirements | **Mechanism delivered, corpus pending** | The trace and rollup exist; a real 50-requirement corpus requires the programme's requirement set |
| I1-7, ≥ 10 operators over 4 weeks | Not started | Requires the console workflow and a pilot cohort |
| I1-8, standalone licensable | Partial | The service deploys independently; licence gating is not implemented |
| I1-9, audit completeness across the pilot | Partial | The foundation records access decisions; the pilot period does not exist yet |

The requirement authoring workflow, the cost-driver linkage and the full SysML
environment remain in the Increment 5 scope for Pillar A-1/A-3.

## 8. Verification

| Gate | Command | What it proves |
|---|---|---|
| Unit | `uv run pytest tests/unit/test_architecture.py` | Determinism, validation, the evidence rule, the rollup |
| Service | `uv run pytest tests/integration/test_architecture_service.py` | The HTTP surface behaves as specified |
| Full suite | `uv run pytest tests/` | No regression in the foundation |
| Lint and format | `uv run ruff check libs services apps tests tools scripts` | Style is not a matter of taste |

The unit tests deliberately include the negative cases: a duplicate member, a
missing characteristic, an unreviewed pass, a `MARGINAL` outcome, a failure
alongside a pass, and a rollup cycle. A capability that only works on the happy
path is not a capability.
