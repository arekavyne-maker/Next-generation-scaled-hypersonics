# ngsh-audit

The tamper-evident ledger. Append-only and hash-chained, so that a rewritten
history breaks every subsequent hash and can be detected on demand.

Part of the NGSH foundation. See the repository root `README.md` for the
architecture, `docs/adr/` for the reasoning behind the design decisions, and
`NGSH_Development_Plan.md` for the delivery plan.

## Run locally

```bash
make dev-audit     # from the repository root
```

Or directly:

```bash
uv run python -m ngsh_audit.app
```

Configuration comes from the environment; see `.env.example` in the repository
root. The service listens on `NGSH_PORT`, defaulting to `8084`.

## Endpoints

- `GET /healthz` — liveness
- `GET /readyz` — readiness
- `GET /v1/service/info` — service metadata
- `POST /v1/ledger` — append an entry
- `GET /v1/ledger` — read entries
- `GET /v1/ledger/verify` — recompute the chain and report any break
- `GET /v1/ledger/head` — current chain head
- `GET /v1/ledger/{digest}` — one entry by hash
