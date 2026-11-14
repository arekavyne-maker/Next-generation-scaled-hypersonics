# ngsh-ontology

Serves the shared ontology: the 23 entity types, the 10 relation types, the
JSON Schemas that define them, and the cross-entity invariants every write
must satisfy.

Part of the NGSH foundation. See the repository root `README.md` for the
architecture, `docs/adr/` for the reasoning behind the design decisions, and
`NGSH_Development_Plan.md` for the delivery plan.

## Run locally

```bash
make dev-ontology     # from the repository root
```

Or directly:

```bash
uv run python -m ngsh_ontology.app
```

Configuration comes from the environment; see `.env.example` in the repository
root. The service listens on `NGSH_PORT`, defaulting to `8081`.

## Endpoints

- `GET /healthz` — liveness
- `GET /readyz` — readiness
- `GET /v1/service/info` — service metadata
- `GET /v1/ontology/registry` — the full registry
- `GET /v1/ontology/types` — entity types, optionally filtered by pillar
- `GET /v1/ontology/types/{type}` — schema and metadata for one type
- `GET /v1/ontology/relations` — relation types
- `GET /v1/ontology/constraints` — invariants C-001..C-008
- `POST /v1/ontology/validate` — validate an entity or a relation
- `GET /v1/events/catalog` — the event type catalog
- `POST /v1/ontology/reload` — re-read the contract layer after a change
