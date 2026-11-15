# The Complete Build — Every Capability on a Runnable Path

## Purpose

This document describes the build that closes the PSDD scope in the reference
implementation: **34 capabilities across eight pillars and seven external
interfaces, each reachable through a tested path.** It is the companion to
[`07-pillar-coverage.md`](07-pillar-coverage.md), which explains each pillar's
rules in depth, and to the ADRs, which record why the platform is shaped this
way.

"Complete" here has a precise meaning. It does **not** mean that every external
institution has been connected or accredited. It means:

* every capability named in PSDD §5 has an owning service and an endpoint that
  returns a real result;
* every external interface IF-1 to IF-7 has a validated boundary, a declared
  direction and a deterministic receipt;
* the result is written to the event log and read back through the graph, not
  held in a service-private table;
* the path is covered by a unit or integration test, and the whole scope is
  walked end to end by `scripts/demo_full.py`;
* a real counterpart can replace a simulated adapter without changing the
  contract, the direction rule or the receipt shape.

The remaining external dependencies are listed in §7. They are certification
and counterpart-integration work, not unfinished platform code.

## 1. Topology

The reference stack has sixteen independently deployable services plus the
console and the edge annex:

| Layer | Services | Ports |
|---|---|---|
| Entry point | `gateway-service` | 8080 |
| Foundation | `ontology`, `fabric`, `policy`, `audit`, `thread`, `ingest` | 8081–8086 |
| Pillars | `architecture`, `workforce`, `manufacturing`, `testlab`, `supply`, `engagement`, `industrial` | 8088–8094 |
| Cross-cutting | `analytics`, `integration` | 8095–8096 |
| Edge annex (optional) | `edge-agent` | 8087 |
| Console | `apps/web` (nginx or Vite dev server) | 3000 / 5173 |

Every service has its own `pyproject.toml`, container image, Compose service and
Helm values block. A programme can deploy Pillar B without Pillar F. The
gateway is the only address the console needs; it resolves
`/api/<service>/...` to the owning service and forwards the remainder without
rewriting the domain.

The console routes all API traffic through the gateway in both development
(Vite proxy) and the container topology (nginx upstream). The gateway's own
platform endpoints are mounted at its root and are reached through the
`/api/gateway/` prefix, which the proxy strips.

## 2. Capability matrix

The canonical list lives in
`libs/ngsh-core/ngsh_core/capabilities.py`. The gateway reports it, the console
renders it and a unit test checks every declared endpoint against the owning
service's router.

### Pillar A — MBSE and the digital thread core

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| A-1 | Digital twin backbone | architecture | `POST /v1/baselines`, `POST /v1/baselines/{id}/verify` |
| A-2 | Modularity engine | architecture | `POST /v1/variants/generate`, `POST /v1/variants/{id}/core-error` |
| A-3 | Requirements-to-test traceability | architecture | `GET /v1/requirements/{id}/coverage`, `GET /v1/requirements/gaps` |
| A-4 | Technology insertion planner | architecture | `POST /v1/insertion/assess` |
| A-5 | Digital engineering SaaS | architecture | `POST /v1/icds/generate`, `GET /v1/sysml/export`, `POST /v1/sysml/import` |

### Pillar B — manufacturing and materials process intelligence

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| B-1 | Defense MES | manufacturing | `POST /v1/process-runs`, `POST /v1/travellers`, `GET /v1/genealogy/{id}` |
| B-2 | CMC process characterisation | manufacturing | `POST /v1/drift` |
| B-3 | Test capability management | testlab | `POST /v1/campaigns`, `GET /v1/campaigns/{id}/curation` |
| B-4 | Rate and cost simulation | manufacturing | `POST /v1/simulate-rate`, `POST /v1/production/simulate` |

### Pillar C — test, evaluation and flight-demonstration data

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| C-1 | Unified test data lake | ingest | `POST /v1/lakehouse/objects`, `GET /v1/lakehouse/objects/{digest}/verify` |
| C-2 | Automated reduction and anomaly detection | testlab | `POST /v1/anomalies/detect`, `POST /v1/test-results` |
| C-3 | Twin validation loop | testlab | `POST /v1/twin-validation`, `POST /v1/models/{id}/regenerate` |
| C-4 | Campaign management | testlab | `POST /v1/campaigns`, `POST /v1/schedule/optimise` |

### Pillar D — supply chain and production scaling

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| D-1 | Multi-tier visibility | supply | `GET /v1/supply-risks`, `POST /v1/suppliers` |
| D-2 | Foreign dependency mapping | supply | `POST /v1/reconstitutes`, `GET /v1/supply-risks` |
| D-3 | Surge readiness twin | supply | `POST /v1/surge` |

### Pillar E — cleared workforce pipeline of record

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| E-1 | Digital-twin training | workforce | `POST /v1/training/scenarios`, `GET /v1/training/coverage` |
| E-2 | Replicable curriculum engine | workforce | `POST /v1/curriculum/packages` |
| E-3 | Skills credentialing | workforce | `POST /v1/credentials`, `GET /v1/work-authorisation` |
| E-4 | Workforce demand model | workforce | `POST /v1/workforce/gap` |
| E-5 | Industry-academia sandbox | workforce | `POST /v1/extracts` |

### Pillar F — counter-hypersonic kill-chain engineering

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| F-1 | Threat digital twins | engagement | `POST /v1/threats`, `POST /v1/threat-models` |
| F-2 | Kill-chain simulator | engagement | `POST /v1/scenarios/{id}/batch`, `GET /v1/kill-chain` |
| F-3 | Fire-control data quality scoring | engagement | `POST /v1/fire-control/measure`, `POST /v1/fire-control/quality` |
| F-4 | Interim architecture workbench | engagement | `POST /v1/candidates/evaluate` |
| F-5 | Golden Dome readiness | engagement | `POST /v1/plugins`, `POST /v1/plugins/{id}/run` |
| F-6 | Red/blue co-simulation | engagement | `POST /v1/co-simulation` |

### Pillar G — test enterprise and M&S federation

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| G-1 | Virtual test range | thread | `GET /v1/datasets`, `GET /v1/datasets/{id}/lineage` |
| G-2 | Campaign digital twin | testlab | `POST /v1/range-capacity`, `POST /v1/schedule/optimise` |
| G-3 | Automated model validation | testlab | `POST /v1/twin-validation`, `POST /v1/models/{id}/regenerate` |
| G-4 | Fidelity registry | testlab | `GET /v1/fidelity/registry`, `POST /v1/fidelity/{id}/drift` |

### Pillar H — industrial surge and affordability

| Id | Capability | Service | Runnable path |
|---|---|---|---|
| H-1 | Surge readiness command | industrial | `POST /v1/surge-readiness` |
| H-2 | Reconstitution planning | industrial | `POST /v1/reconstitution/assess` |
| H-3 | Affordability engineering | industrial | `POST /v1/affordability/trace`, `POST /v1/affordability/rate-curve` |

## 3. External interfaces

The register is `ngsh_core.integration.INTERFACE_REGISTER`; the runtime boundary
is `ngsh_core.adapters`. Every interface validates its payload, enforces its
direction and returns a content-addressed transport key that makes a retry
recognisable.

| Id | Interface | Direction | Status | Boundary |
|---|---|---|---|---|
| IF-1 | Prime PLM/MES APIs | bi-directional | ADAPTER | REST + STEP AP242 / OPC-UA payloads at `/v1/interfaces/IF-1/{inbound,outbound}` |
| IF-2 | MDA/Aegis systems | bi-directional | ADAPTER | Engagement scenario exchange, validated and receipted |
| IF-3 | SDA PWSA / HBTSS feeds | inbound | INBOUND_ONLY | Inbound tracks accepted; outbound is refused with the programme-office note |
| IF-4 | Range instrumentation | bi-directional | ADAPTER | Test-article manifests and instrumentation lists |
| IF-5 | University LMS / AR-VR clients | outbound | ADAPTER | Curriculum package export |
| IF-6 | Government identity (PIV/ICAM) | inbound | ADAPTER | Signed assertion verified, then redacted before persistence |
| IF-7 | Analytics/BI | outbound | ADAPTER | Programme report export |

`ADAPTER` means the platform supplies a deterministic simulated counterpart and
a stable contract. The real counterpart is supplied and accredited by the
programme; the boundary code does not change when it is.

The local IF-6 path issues an HMAC-signed assertion through the `piv-sim`
identity provider. Issuance is refused outside the `local` and `edge`
deployment profiles, and the real `PivIdentityProvider` fails closed without
live metadata and verification URLs.

## 4. How a capability becomes an authoritative fact

Every pillar follows the same sequence:

```
caller -> gateway -> pillar service
                       |
                       |-- validate payload against the contract
                       |-- apply the pillar's own rules
                       |-- append an event to the fabric
                       |-- project the event into the digital thread
                       '-- return the entity and the decision
```

The pillar never writes authoritative state to a private table. Derived reports
(for example a surge readiness report or a reconstitution assessment) are stored
as annotations on the entity they concern and published as `entity.updated`, so
the report is reproducible from the log and its provenance is visible.

Content-addressed artefacts (lakehouse objects, baselines, curriculum packages)
are content, not a second source of truth: their digest is recorded on the
entity or in the event, and the bytes can be re-fetched and verified.

## 5. Cross-cutting guarantees

| Concern | Guarantee | Where it is enforced |
|---|---|---|
| Contracts | 23 entity types, 10 relation types and 11 event types are the only shapes accepted; a change is a contract change | `contracts/`, `tools/validate_contracts.py`, generated models |
| Event log | The log is the system of record; the graph is a rebuildable projection | `fabric-service`, `thread-service`, ADR-0001 |
| Access control | ABAC with PDP/PEP separation, explicit deny wins, fail-closed defaults | `policy-service`, `ngsh_core.policy`, ADR-0004 |
| Audit | Hash-chained, tamper-evident ledger | `audit-service`, ADR-0005 |
| Classification | Storage partitions and cross-classification refusal | ADR-0007, C-001 |
| Model governance | A model must be approved and carry fidelity evidence before use; regeneration never auto-approves | C-004, `testlab-service`, ADR-0008 |
| Determinism | Batch simulation, reconciliation, variant generation and threat derivation are hash-derived and reproducible | `engagement`, `edge`, `modularity`, `threatmodel` |

The ontology count is checked by tests and tooling. It stays at **23 entity
types, 10 relation types and 11 event types**. The new capabilities are
computed over existing types; no type was added merely to make a capability
look complete.

## 6. Verification

The complete build is verified by four gates:

```bash
make verify        # ruff + contract validation + codegen check + full test suite
make test          # the full suite
make demo-full     # walk 34 capabilities and 7 interfaces through the gateway
make demo-programme # the original programme traversal across all pillars
```

At the time of writing:

* **466 tests** pass (unit, integration, end-to-end);
* **279 contract checks** pass;
* codegen reports the generated models are current;
* `ruff check` and `ruff format --check` are clean;
* `scripts/demo_full.py` finishes with
  `34/34 capabilities, 7/7 interfaces, 15 services`;
* `scripts/demo_programme.py` still traverses all pillars in one thread.

The console has a **Platform** page that renders the live service health, the
capability matrix and the interface register from the gateway. If the stack is
not running it degrades to the deterministic mock dataset and says so.

## 7. What remains external

These items cannot be completed inside the reference build. Each has a working
adapter or a fail-closed path, so the platform does not pretend to have data or
authority it does not have.

| Item | Current state | What a programme supplies |
|---|---|---|
| PIV/ICAM | Local signed assertion in `local`/`edge`; real provider fails closed | Accredited IdP metadata and verification endpoints |
| Prime PLM/MES | Validated IF-1 adapter and deterministic receipts | The prime's endpoint, credentials and mapping |
| MDA/Aegis | Validated IF-2 exchange | Link-16/MTDS gateway and accreditation |
| SDA/PWSA | Inbound-only IF-3 boundary | Feed connection and programme-office approval for any outbound path |
| Range instrumentation | Validated IF-4 manifests | TDMS/HDF5 stream and range network access |
| LMS / AR-VR | Outbound IF-5 package export | Partner LTI 1.3 registration |
| BI connectors | Outbound IF-7 reports | Consumer endpoint and credential |
| PostgreSQL runtime | Store supports the DSN and dialect; tests run on SQLite | Accredited database service |
| Docker / Helm runtime | Compose and chart are validated as files; Docker and Helm are not installed here | Container registry and cluster |
| Classified data and accreditation | Classification partitions and denial paths are implemented | Authority to operate and accredited enclave |

The platform-agnostic rule holds: no cloud SDK appears in a domain package. A
deployment supplies placement, storage and identity through configuration and
opaque connection strings.

## 8. Reading path

| If you want to | Read |
|---|---|
| Understand the scope and the invariants | [`01-system-context.md`](01-system-context.md) |
| See the types, relations and constraints | [`02-ontology-model.md`](02-ontology-model.md) |
| Work on the foundation | [`03-foundation-services.md`](03-foundation-services.md) |
| Add a service or a data path safely | [`04-security-architecture.md`](04-security-architecture.md) |
| Deploy or operate the platform | [`05-deployment-architecture.md`](05-deployment-architecture.md) |
| See each pillar's rules in depth | [`07-pillar-coverage.md`](07-pillar-coverage.md) |
| Understand a specific decision | [`../adr/README.md`](../adr/README.md) |
