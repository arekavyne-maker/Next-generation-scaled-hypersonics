# ngsh-fabric

The append-only event log. The system of record for the entire platform:
every other store is a projection rebuilt by replaying this log.

Part of the NGSH foundation. See the repository root `README.md` for the
architecture, `docs/adr/` for the reasoning behind the design decisions, and
`NGSH_Development_Plan.md` for the delivery plan.

## Run locally

```bash
make dev-fabric     # from the repository root
```

Or directly:

```bash
uv run python -m ngsh_fabric.app
```

Configuration comes from the environment; see `.env.example` in the repository
root. The service listens on `NGSH_PORT`, defaulting to `8082`.

## Endpoints

- `GET /healthz` — liveness
- `GET /readyz` — readiness
- `GET /v1/service/info` — service metadata
- `POST /v1/events` — append one event or a batch
- `GET /v1/events` — read the stream, filtered by type and tenant
- `GET /v1/events/{event_id}` — fetch a single event
- `GET /v1/stats` — event counts by type
- `GET /v1/catalog` — the event type catalog
- `GET /v1/topics` — subscription groups
