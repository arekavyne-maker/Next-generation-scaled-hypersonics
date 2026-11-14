# ngsh-core

Shared domain primitives for the NGSH platform.

This package holds everything that the six foundation services and all eight
pillars have in common:

| Module | Responsibility |
|---|---|
| `envelope` | Event envelope and entity models; the Python binding of the contract layer |
| `ontology` | Registry loading, JSON Schema validation, cross-entity invariants |
| `policy` | ABAC engine — the Policy Decision Point |
| `audit` | Hash-chained tamper-evident ledger |
| `eventlog` | Append-only event log with sequencing and idempotency |
| `graph` | Digital thread projection and traversal |
| `identity` | PIV/ICAM federation adapter and development stub |
| `classification` | Handling levels, floors and storage partitioning |
| `store` | Storage executor over SQLite and PostgreSQL |
| `app` | Shared FastAPI service kit |

The package deliberately contains no cloud-provider SDK calls and no
framework coupling in the domain modules, so that it can be vendored into an
accredited enclave or an edge annex unchanged.

## Design rules

1. The event log is the system of record. Everything else is a projection.
2. The contract files under `contracts/` are the source of truth for shapes.
   This package is a binding of them, validated against them in CI.
3. Fail closed. An unparseable classification is treated as more restricted,
   not less. An unmatched policy is a denial. An unknown operator is an error.
4. No domain logic depends on the deployment profile. The profile changes
   where a service runs, never what it means.

See `docs/adr/` for the reasoning behind each of these.
