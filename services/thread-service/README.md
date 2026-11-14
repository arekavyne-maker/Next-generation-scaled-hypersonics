# ngsh-thread

The digital thread projection and the traversal queries on top of it: trace
paths, requirement verification coverage, graph statistics.

Part of the NGSH foundation. See the repository root `README.md` for the
architecture, `docs/adr/` for the reasoning behind the design decisions, and
`NGSH_Development_Plan.md` for the delivery plan.

## Run locally

```bash
make dev-thread     # from the repository root
```

Or directly:

```bash
uv run python -m ngsh_thread.app
```

Configuration comes from the environment; see `.env.example` in the repository
root. The service listens on `NGSH_PORT`, defaulting to `8085`.

## Endpoints

- `GET /healthz` — liveness
- `GET /readyz` — readiness
- `GET /v1/service/info` — service metadata
- `GET /v1/entities/{type}/{id}` — a projected entity and its relations
- `GET /v1/relations` — projected relations, filtered
- `GET /v1/trace` — walk the thread outward from a root entity
- `POST /v1/trace/requirements/{id}/coverage` — verification coverage
- `GET /v1/graph/stats` — counts by entity and relation type
- `POST /v1/project/apply` — apply events to the projection
- `POST /v1/project/replay` — rebuild the projection from the log
