# NGSH Control Console

Operator-facing console for the **Next-Generation Scaled Hypersonics** platform: a
React + TypeScript single-page app over the NGSH event-sourced data fabric and
shared ontology.

It is an internal engineering tool, not a marketing site — dense, dark, technical,
with monospace identifiers and hashes everywhere. The six views are:

| Route | View | What it answers |
|---|---|---|
| `/` | Overview | Are the services up, what does the ontology look like, how fast is the log moving? |
| `/events` | Event Stream | What was written to the fabric, by whom, under which classification? |
| `/thread` | Digital Thread | How does this entity connect to the rest of the graph? |
| `/requirements` | Requirements | Is this requirement verified, and what are the coverage gaps? |
| `/audit` | Audit Ledger | Is the decision chain intact? |
| `/access` | Access Decisions | Would this subject be allowed to do this, and under which policy? |

---

## Running it

```bash
cd apps/web
npm install
npm run dev            # http://localhost:5173
```

The console **works with no backend at all**. Every panel degrades to a
deterministic mock dataset when a service cannot be reached, and the top bar
shows a `mock fallback` badge so the operator always knows which data is live.

Other scripts:

```bash
npm run build          # tsc --noEmit (app + config) then vite build
npm run lint           # tsc --noEmit only
npm run smoke          # headless render of all six routes (dev dependency: jsdom)
npm run preview        # serve the production build
```

Node 26 / npm 11 are expected.

---

## Pointing at the real backend

### Development (recommended): the dev proxy

`vite.config.ts` proxies one origin to the six services and strips the prefix:

```
/api/ontology -> http://localhost:8081
/api/fabric   -> http://localhost:8082
/api/policy   -> http://localhost:8083
/api/audit    -> http://localhost:8084
/api/thread   -> http://localhost:8085
/api/ingest   -> http://localhost:8086
```

In proxy mode the client calls `/api/<service>/v1/...`, e.g.
`/api/fabric/v1/events?limit=100`. No CORS configuration is needed on the
services for this path.

### Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `VITE_USE_MOCK` | unset | `true` forces the deterministic mock dataset; **no network calls are made**. |
| `VITE_API_MODE` | `proxy` in dev, `direct` in a build | `proxy` uses the dev proxy; `direct` talks to absolute URLs. |
| `VITE_API_BASE` | `http://localhost:8082` | API root. In proxy mode a path value (e.g. `/api`) is used as-is; in direct mode an absolute value is treated as a gateway origin and the service name is appended (`<base>/<service>`). |
| `VITE_API_ONTOLOGY` … `VITE_API_INGEST` | service defaults below | Per-service base URL override; highest precedence. |

Direct-mode service defaults: ontology `:8081`, fabric `:8082`, policy `:8083`,
audit `:8084`, thread `:8085`, ingest `:8086`.

```bash
# force mock mode
VITE_USE_MOCK=true npm run dev

# talk to a gateway
VITE_API_MODE=direct VITE_API_BASE=https://ngsh.internal npm run build

# pin one service to another host
VITE_API_MODE=direct VITE_API_ONTOLOGY=https://ontology.ngsh.internal npm run dev
```

Copy `.env.example` to `.env.local` to keep these out of your shell history.

### How the fallback works

`src/api/client.ts` wraps every call:

1. `VITE_USE_MOCK=true` → answer from the mock dataset immediately.
2. Otherwise call the live service.
   * `2xx` → the live response is used.
   * `5xx`, connection refused, DNS failure or an 8 s timeout → the request is
     served from the mock dataset and the console switches to `mock fallback`.
   * Other `4xx` → the error is surfaced to the operator (a rejected request is
     not silently replaced by fake data).

The sidebar always shows the current data source, and the reason for the last
fallback is available as the badge tooltip.

---

## What the console calls

| Service | Call | Used by |
|---|---|---|
| all | `GET /healthz` | Overview status tiles, top bar health strip |
| fabric | `GET /v1/events?after&limit&types&tenant` | Event Stream, Overview rate |
| fabric | `GET /v1/events/{eventId}` | Event Stream (single event drill-down) |
| ontology | `GET /v1/ontology/registry` | Overview coverage panel, Thread relation filters |
| ontology | `GET /v1/ontology/types/{type}` | available for type drill-down |
| thread | `GET /v1/entities/{type}/{id}` | Thread side panel |
| thread | `GET /v1/trace?root&depth&relationTypes` | Digital Thread graph |
| thread | `GET /v1/graph/stats` | Overview entity/relation counts |
| thread | `POST /v1/trace/requirements/{id}/coverage` | Requirements coverage |
| thread | `GET /v1/entities?type&limit` | **Assumed** — requirement list and root suggestions |
| audit | `GET /v1/ledger?after&limit` | Audit Ledger |
| audit | `GET /v1/ledger/verify` | chain-integrity banner |
| policy | `POST /v1/decisions` | Access Decisions form |
| policy | `GET /v1/policies` | policy list panel |
| ingest | `POST /v1/ingest` | available from the client (`submitIngest`) |

### API assumptions the backend must honour

1. **Service routing.** Paths are prefixed per service (`/api/fabric/v1/events`),
   because `v1` alone is ambiguous between services. `GET /v1/entities` on the
   thread service must not collide with the ontology or fabric routes.
2. **`GET /v1/entities?type=&limit=` (thread).** The published contract has no
   collection endpoint. The console assumes one for the requirement picker and
   the root-entity suggestions; a `404` is treated as "not implemented" and the
   mock list is used instead, so a missing endpoint degrades rather than breaks.
3. **Event pagination cursor.** The console treats the `cursor` in the response
   as the opaque continuation token and passes it back as `after`. It merges and
   re-sorts by `recordedAt`, so the view is correct whether the backend pages
   forwards (newer events) or backwards (older events). The mock pages
   backwards, i.e. the first response is the tail of the log.
4. **`types` filter grammar.** A comma-separated list of globs. The mock
   accepts `*` wildcards (`entity.*`) and bare prefixes (`test` matches
   `test.result.recorded`). A backend that only supports exact event types
   will return fewer rows for wildcard filters — no error, just a narrower view.
5. **Trace root format.** `{type}:{id}`, e.g. `TestResult:TR:01J8ZW4C7T2`. The
   console parses the first colon as the type separator, so entity ids may
   themselves contain colons.
6. **Trace edge direction.** `edges[].from` / `edges[].to` are entity ids, and
   `paths` are arrays of entity ids starting at the root.
7. **Coverage response.** `coverage` is a number in `0..1` (rendered as a
   percentage) and `gaps` are human-readable strings.
8. **Ledger cursor.** The audit service's `cursor` is opaque; the console
   passes it back as `after` and renders entries in `seq` order.
9. **Ledger hashes.** `hash` / `prevHash` are 64 hex characters. The mock
   computes a real SHA-256 chain over `prevHash|seq|timestamp|eventType|subject|action|resource|decision|reason`,
   so the integrity banner is a genuine verification rather than a decoration.
   The backend may use any digest as long as the chain verifies.
10. **`/healthz`.** Expected to answer `{"status":"ok"}`. The console also
    understands `degraded` and treats anything else as `down`.

---

## The mock dataset

`src/api/mock-data.ts` holds a deterministic NGSH-SHY program slice:

* **89 entities** across all 23 ontology types — an HGV-A1 glide vehicle, its
  CMC supply chain (nose cone `PART:NSN-4472`, prepreg lots, autoclave and
  pyrolysis plans), the wind-tunnel campaign `TC:WT-26-04`, the live flight
  campaign `TC:FLT-26-02`, 14 test results, 11 requirements, 5 models, the
  threat side (`THR:HGV-X9`), suppliers, facilities, cleared workforce records.
* **83 relations** over the 10 canonical relation types.
* **242 events** using the 10 contract event types, with ULIDs that sort like
  time, realistic actors, classification levels and attachment digests.
* **49 audit ledger entries** forming a real SHA-256 hash chain.
* 6 policy rules and a deterministic policy evaluator.

Everything is generated from a fixed seed and a fixed reference epoch
(`2026-11-14T18:42:00Z`), so the dataset — including every hash — is identical
on every run. Relative timestamps ("28m ago") are measured against that epoch
rather than the wall clock, so the console reads correctly regardless of when
it is opened.

Domain rules from the ontology constraints are respected: a `TestResult` never
emits `entity.updated` (C-003), entity classification never sits below its
type's `classificationFloor` (C-001), and only `mayCrossClassification`
relations bridge classification boundaries (C-002).

---

## Architecture

```
src/
  api/
    types.ts      contract types mirroring the NGSH schemas
    client.ts     live client + mock fallback + data-source tracking
    mock.ts       mock service implementations
    mock-data.ts  the deterministic dataset
  components/
    Layout.tsx        shell, sidebar, top bar, health strip
    DataTable.tsx     dense table with loading/error/empty/expandable states
    JsonViewer.tsx    collapsible JSON tree
    TraceGraph.tsx    hand-rolled SVG radial graph (no graph library)
    ClassificationBadge.tsx / StatusTile.tsx / Panel.tsx / Meter.tsx
    CopyableText.tsx / EventRow.tsx / Icon.tsx / States.tsx
  pages/          the six views
  lib/
    format.ts     timestamp / number / id formatting
    palette.ts    entity and relation colours
    clock.ts      reference clock for relative times
    sha256.ts     dependency-free SHA-256 (mock ledger chain)
    useAsync.ts   loading / error / data hook with abort handling
  styles/
    theme.css     design tokens
    global.css    component styles
```

### The graph

`TraceGraph.tsx` implements the visualisation from scratch:

* Breadth-first traversal assigns a depth to every node; the root sits at the
  centre and each depth level is a ring.
* Children inherit a slice of their parent's angular span, so sibling subtrees
  stay visually grouped instead of scattering around the circle.
* Edges are quadratic Béziers with a perpendicular bow; lateral (same-ring)
  edges arc outwards. Arrowheads are computed per edge, so they follow the
  relation colour.
* Nodes are coloured by entity type, edges by relation type; edges with
  `confidence < 0.60` are dashed.
* Nodes are keyboard reachable (`Tab`, then `Enter`/`Space` selects) and expose
  an `aria-label`.

No graph library is used — the layout, routing and hit testing are all in that
one file.

---

## Accessibility and state handling

* Real `<button>`, `<label>`, `<table>` and `<form>` elements throughout.
* Icon-only controls carry `aria-label`; expandable rows expose `aria-expanded`;
  the graph nodes are focusable buttons; the coverage bar is a `role="meter"`.
* Every fetch has an explicit loading, error and empty state — there are no
  silent failures, and errors name the failing service.
* Monospace for ids, hashes and payloads; `prefers-reduced-motion` is honoured.

---

## Notes and limitations

* The console is read-mostly. The two write paths are the policy decision
  endpoint and `POST /v1/ingest` (exposed in the client, not yet wired to a
  page).
* Classification badges show the level; caveats appear in the tooltip.
* The `ingest-service` health tile reports `degraded` in mock mode so the
  degraded visual state is exercised.
