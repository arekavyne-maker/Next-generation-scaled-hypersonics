# ngsh-ingest

Bulk admission of test, telemetry and manufacturing data, with lineage,
digest and classification accounted for at the point of entry.

Part of the NGSH foundation. See the repository root `README.md` for the
architecture, `docs/adr/` for the reasoning behind the design decisions, and
`NGSH_Development_Plan.md` for the delivery plan.

## Run locally

```bash
make dev-ingest     # from the repository root
```

Or directly:

```bash
uv run python -m ngsh_ingest.app
```

Configuration comes from the environment; see `.env.example` in the repository
root. The service listens on `NGSH_PORT`, defaulting to `8086`.

## Endpoints

- `GET /healthz` — liveness
- `GET /readyz` — readiness
- `GET /v1/service/info` — service metadata
- `POST /v1/ingest` — admit a batch and publish the resulting events
- `GET /v1/ingest/batches` — batch accounting
- `GET /v1/ingest/batches/{batch_id}` — one batch
