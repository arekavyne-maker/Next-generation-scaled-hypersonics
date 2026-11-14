# ngsh-policy

The Policy Decision Point. Evaluates attribute-based access requests and
returns ALLOW, DENY or INDETERMINATE with the matched rule and any
obligations the enforcement point must discharge.

Part of the NGSH foundation. See the repository root `README.md` for the
architecture, `docs/adr/` for the reasoning behind the design decisions, and
`NGSH_Development_Plan.md` for the delivery plan.

## Run locally

```bash
make dev-policy     # from the repository root
```

Or directly:

```bash
uv run python -m ngsh_policy.app
```

Configuration comes from the environment; see `.env.example` in the repository
root. The service listens on `NGSH_PORT`, defaulting to `8083`.

## Endpoints

- `GET /healthz` — liveness
- `GET /readyz` — readiness
- `GET /v1/service/info` — service metadata
- `POST /v1/decisions` — evaluate an access request
- `GET /v1/policies` — the rule set
- `GET /v1/policies/{policy_id}` — one rule
- `POST /v1/policies/reload` — re-read the policy document after a change
