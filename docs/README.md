# NGSH Documentation

## Purpose

This directory holds the architecture and programme documentation for NGSH (Next-Generation Scaled Hypersonics), the dual-mission hypersonic defence software platform. It is the documentation set for the platform described in [`../NGSH_Preliminary_Software_Design_Document.md`](../NGSH_Preliminary_Software_Design_Document.md) (PSDD v0.1) and implemented against the contract layer in [`../contracts/`](../contracts/). Where this documentation and a contract file disagree, the contract file wins: the contracts are generated into every language and enforced at runtime, whereas these documents are prose.

## Contents

| Directory or file | Subject |
|---|---|
| [`adr/`](adr/README.md) | Eight Architecture Decision Records — what was decided, why, and what it costs — plus the ADR index and process |
| [`architecture/`](architecture/README.md) | Five architecture documents — the platform context, the shared ontology, the foundation services, the security architecture and the deployment topology |
| [`roadmap/increments.md`](roadmap/increments.md) | Increment 0 (the shared foundation) through Increment 5, with exit criteria, dependencies and the risk each increment retires |
| [`roadmap/work-packages.md`](roadmap/work-packages.md) | The full work breakdown: 49 work packages with acceptance criteria, dependencies, size in engineer-weeks and pod assignment |
| [`staffing.md`](staffing.md) | The pod model, the pod composition rules, three reference organisations (≈25, ≈60, ≈120 engineers) and the cleared-workforce constraints |
| [`risk-register.md`](risk-register.md) | 26 programme and delivery risks, each with a numeric exposure, owner role, mitigation, contingency, trigger and residual exposure |

## Where to start

| If you are | Start with |
|---|---|
| New to the programme | [`architecture/01-system-context.md`](architecture/01-system-context.md), then [`roadmap/increments.md`](roadmap/increments.md) |
| Building a pillar | [`architecture/03-foundation-services.md`](architecture/03-foundation-services.md), then [`architecture/02-ontology-model.md`](architecture/02-ontology-model.md) |
| Extending the ontology | [`architecture/02-ontology-model.md`](architecture/02-ontology-model.md) §7, then [ADR-0002](adr/ADR-0002-json-schema-contracts-over-shared-libraries.md) |
| Adding an API or a data path | [`architecture/04-security-architecture.md`](architecture/04-security-architecture.md) §4 and §12, then [ADR-0004](adr/ADR-0004-abac-with-pdp-pep-separation.md) |
| Deploying or operating | [`architecture/05-deployment-architecture.md`](architecture/05-deployment-architecture.md), then [ADR-0003](adr/ADR-0003-platform-agnostic-hybrid-deployment.md) |
| Planning the programme | [`roadmap/increments.md`](roadmap/increments.md), [`roadmap/work-packages.md`](roadmap/work-packages.md), [`staffing.md`](staffing.md), [`risk-register.md`](risk-register.md) |
| Preparing for assessment | [`architecture/04-security-architecture.md`](architecture/04-security-architecture.md) §10 and §11, then [ADR-0005](adr/ADR-0005-tamper-evident-audit-ledger.md) and [ADR-0007](adr/ADR-0007-classification-partitioning.md) |

## The four settled programme decisions

1. **Increment 0 is the shared foundation.** The ontology, event log, policy, audit ledger, graph projection, ingestion and edge sync are built before any pillar. See [`roadmap/increments.md`](roadmap/increments.md) §3.
2. **Platform-agnostic, hybrid-first deployment.** No cloud SDKs in domain code; three zones; degraded mode at the edge. See [ADR-0003](adr/ADR-0003-platform-agnostic-hybrid-deployment.md).
3. **Scale-agnostic staffing.** Work is expressed as work packages and pod templates, scaled by adding pods. See [`staffing.md`](staffing.md).
4. **Polyglot by design.** Go for the data plane, Python for domain and ML services, TypeScript for the console, with JSON Schema contracts as the only cross-language coupling. See [ADR-0002](adr/ADR-0002-json-schema-contracts-over-shared-libraries.md).

## Notation

| Convention | Meaning |
|---|---|
| `PSDD §6.1` | A section of the Preliminary Software Design Document |
| `A-1` … `H-3` | A PSDD pillar capability id. **A single-letter prefix is always a PSDD capability id** |
| `ALT-n`, `DR-n`, `DS-n`, `GEN-n`, `EN-n`, `FD-n`, `CC-n`, `CS-n`, `FE-n`, `TB-n`, `CR-n`, `RP-n`, `X-n` | Document-local rule identifiers. Two-letter prefixes are used so that they can never be confused with a PSDD capability id. See [`architecture/README.md`](architecture/README.md) |
| `C-001` … `C-009` | An ontology constraint id from `contracts/ontology/registry.json`. `C-009` is a proposed extension not yet in the registry |
| `WP-x.y` | A work package from [`roadmap/work-packages.md`](roadmap/work-packages.md) |
| `R-nn` | A risk id from [`risk-register.md`](risk-register.md) |
| `P-U`, `P-C`, `P-R`, `P-S` | Classification storage partitions |
| `Z-0` … `Z-3` | Deployment zones |
| `DP-L`, `DP-5`, `DP-6`, `DP-E` | Deployment profiles |
