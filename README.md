# NGSH — Next-Generation Scaled Hypersonics

A dual-mission software platform for the American hypersonic enterprise: the
digital engineering, test, and industrial-readiness environment for hypersonics,
serving the strike side (MBSE, digital-thread manufacturing, CMC process
intelligence, surge readiness) and the shield side (counter-hypersonic
kill-chain engineering, threat digital twins, virtual test enterprise) on one
shared data fabric.

> This repository contains the programme's **software delivery plan** and the
> **Increment 0 foundation** — the shared substrate that every pillar stands
> on. It is deliberately not a pillar feature set.

| Document | Purpose |
|---|---|
| [`NGSH_Preliminary_Software_Design_Document.md`](NGSH_Preliminary_Software_Design_Document.md) | The authoritative design document (PSDD v0.1) |
| [`NGSH_Development_Plan.md`](NGSH_Development_Plan.md) | The delivery plan: increments, work packages, staffing, risk, measurement |
| [`docs/adr/`](docs/adr/) | Architecture decision records |
| [`docs/architecture/`](docs/architecture/) | System, ontology, service, security and deployment architecture |
| [`docs/roadmap/`](docs/roadmap/) | Increment detail and the full work breakdown |
| [`contracts/`](contracts/) | The contract layer — the source of truth for every shape in the platform |

---

## The central architectural claim

The digital thread that traces a U.S. CMC part from powder to flight also
traces an adversary threat from observation to engagement solution. One
ontology, two mission sides.

That claim is not a slogan here; it is enforced by the contract layer. The
same `TestResult` type holds a wind-tunnel coupon result and a flight
campaign result. The same `Requirement` type holds a manufacturing
performance requirement and a fire-control data-quality requirement. The same
`Model` type carries a fidelity score whether it is an aero solver or a
machine-learning drift detector.

---

## Architecture in one diagram

```
                       ┌──────────────────────────────────────┐
                       │        NGSH CONTROL CONSOLE          │
                       │  event stream · digital thread ·     │
                       │  ledger · policy · ontology          │
                       └──────────────────────────────────────┘
                                          │
┌─────────────────────────────────────────┼─────────────────────────────────────────┐
│                    ZERO-TRUST DATA FABRIC (CUI · ABAC · audit · partition)        │
│                                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   ontology   │  │    fabric    │  │    policy    │  │    audit     │         │
│  │  23 types    │  │  event log   │  │   PDP/PEP    │  │ hash chain   │         │
│  │  10 relations│  │  system of   │  │  explicit    │  │ tamper-      │         │
│  │  8 invariants│  │  record      │  │  deny wins  │  │ evident      │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         └─────────────────┴──────────────────┴──────────────────┘                 │
│                                    ┌──────────────┐                             │
│                                    │    thread    │  projection + traversal     │
│                                    │  digital     │                             │
│                                    │   thread     │                             │
│                                    └──────┬───────┘                             │
│                                           │        ┌──────────────┐               │
│                         ┌─────────────────┴────────┤    ingest    │               │
│                         │                          │  lineage +   │               │
│              ┌──────────┴──────────┐               │  digest +    │               │
│              │   EDGE ANNEX        │               │  class.      │               │
│              │ degraded mode,      │               └──────────────┘               │
│              │ store-and-forward   │                                             │
│              └─────────────────────┘                                             │
└──────────────────────────────────────────────────────────────────────────────────┘
```

The six foundation services are independently deployable, communicate over
plain HTTP, and store their state behind a small executor interface that runs
on SQLite locally and PostgreSQL in an accredited environment.

---

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+. No Docker needed.

```bash
make setup          # install dependencies
make verify         # lint + contract validation + full test suite
make dev            # run all six services locally
make demo           # in another terminal: walk the foundation end to end
make demo-edge      # in another terminal: walk the edge annex flow
```

The demo exercises the whole path: validate an entity against the contract
layer, ingest a batch of test data, watch the events land in the fabric,
project them into the digital thread, trace a requirement to its verification
evidence, take a policy decision, and verify the audit chain.

### The stack locally

| Service | Port | Responsibility |
|---|---|---|
| ontology | 8081 | The shared ontology: types, relations, invariants, validation |
| fabric | 8082 | The append-only event log — the system of record |
| policy | 8083 | The Policy Decision Point for attribute-based access control |
| audit | 8084 | The tamper-evident, hash-chained ledger |
| thread | 8085 | The digital thread projection and its traversal queries |
| ingest | 8086 | Bulk admission of test, telemetry and manufacturing data |

Every service exposes `/healthz`, `/readyz`, `/v1/service/info` and OpenAPI
at `/docs`.

The **edge annex agent** (`apps/edge-agent`, port 8087) runs at a factory
floor or test range. It captures events while the fabric is unreachable,
serves reads from a local cache, and reconciles deterministically when the
link returns. `make demo-edge` walks that flow.

---

## Repository layout

```
contracts/            The contract layer — JSON Schema, registry, policy, event catalogue
  ontology/           23 entity types, 10 relation types, 8 invariants
  events/             Event envelope and per-event payload schemas
  policy/             The ABAC rule set (data, not code)

libs/ngsh-core/       Shared domain primitives: envelope, ontology, policy,
                      audit, event log, projection, identity, storage
services/             The six foundation services, each independently deployable
apps/web/             The engineering console
apps/edge-agent/      The edge annex agent (degraded mode, reconciliation)
tests/                unit · integration · e2e · contract parity
tools/                Contract validator and code generation
deploy/               Platform-agnostic deployment: compose, Helm, OTel
docs/                 ADRs, architecture, roadmap, staffing, risk register
scripts/              run_stack · seed · demo
```

---

## The rules the code enforces

These are not conventions. Each is enforced in code, in a contract, or in a
test, and each of them will be argued about at least once.

1. **The event log is the system of record.** The graph, the search indexes,
   the lakehouse and the vector index are projections rebuilt by replaying it.
   A projection can be deleted and rebuilt without loss.
2. **Contracts, not code, define shapes.** An ontology change is a reviewed
   artefact before it is a code change. `make contracts` is a merge gate.
3. **Fail closed.** An unparseable classification is treated as *more*
   restricted. An unmatched policy is a denial. A resource type not named in
   an allow rule is unreachable. A model without a fidelity score is rejected.
4. **Evidence is immutable.** Test results are append-only; a correction is a
   new superseding record, never an edit.
5. **Everything derived names its source.** Provenance, method and confidence
   are required on derived values — CMMC evidence and model credibility are
   the same requirement.
6. **No domain module imports a cloud-provider SDK.** The platform must land
   in an accredited cloud, an on-prem enclave, or a disconnected range annex
   without change.

---

## Testing

```bash
make test                 # everything
make test-unit            # domain units
make test-integration     # service behaviour and contract parity
make contracts            # the contract layer validates itself
```

The e2e suite contains the vertical slice that matters most: it ingests data,
projects it, traces it, takes a policy decision, verifies the audit chain,
then **destroys the projection and rebuilds it from the event log alone**,
asserting the thread comes back identical.

---

## Deployment profiles

Platform-agnostic by construction. The same images run in four postures:

| Profile | Posture |
|---|---|
| `local` | Single process, SQLite, development actor |
| `il5` | Accredited cloud enclave, PostgreSQL, HA, PIV/ICAM |
| `il6` | On-prem classified node, dedicated storage, anti-affinity, no public ingress |
| `edge` | Factory floor or range annex, single replica, store-and-forward, later sync |

See [`docs/architecture/05-deployment-architecture.md`](docs/architecture/05-deployment-architecture.md)
and [`deploy/`](deploy/).

---

## Programme

The delivery plan — six increments, 7,130 engineer-weeks across 49 work
packages, a scale-agnostic pod model, and a 26-risk register with leading
indicators and named owners — is in
[`NGSH_Development_Plan.md`](NGSH_Development_Plan.md).

**Increment 0 is this repository.** It has no pillar capability in it, and
that is the point: the ontology, the fabric, the policy engine, the ledger
and the thread are the parts of NGSH that cannot be retrofitted once eight
pillars depend on them.

---

*Classification handling: CUI (document). The system it plans is designed for
IL5/IL6 operation. See [`docs/architecture/04-security-architecture.md`](docs/architecture/04-security-architecture.md).*
