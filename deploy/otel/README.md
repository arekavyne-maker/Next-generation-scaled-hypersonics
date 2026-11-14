# NGSH — Observability Conventions

How NGSH emits traces, metrics and logs, and the rules every service must
follow. The collector configuration lives in `otel-collector.yaml`; this
document is the contract the application teams code against.

The goal: a single trace that spans the console, the fabric, the policy
engine, the thread service and an edge annex, with enough metadata to answer
"which zone, which clearance, which tenant" — and nothing that leaks.

---

## 1. Transport and endpoint configuration

| Signal | Protocol | Default endpoint |
|---|---|---|
| Traces | OTLP gRPC (preferred) | `http://otel-collector:4317` |
| Traces | OTLP HTTP (fallback) | `http://otel-collector:4318` |
| Logs | OTLP HTTP | `http://otel-collector:4318` |
| Metrics | OTLP gRPC | `http://otel-collector:4317` |

Every service configures its SDK from environment variables only. No endpoint
is hard-coded in application code, and no vendor SDK is used — the platform
speaks OTLP to a generic endpoint and the deployment decides where it lands.

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector.observability.svc.cluster.local:4317"
export OTEL_EXPORTER_OTLP_PROTOCOL="grpc"
export OTEL_EXPORTER_OTLP_TLS_INSECURE="false"   # "true" only for local dev
```

### Collector environment variables

| Variable | Default | Purpose |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://127.0.0.1:4317` | The single generic OTLP destination |
| `OTEL_EXPORTER_OTLP_TLS_INSECURE` | `false` | Disable TLS (local dev only) |
| `OTEL_RECEIVER_GRPC_ENDPOINT` | `0.0.0.0:4317` | OTLP gRPC listener |
| `OTEL_RECEIVER_HTTP_ENDPOINT` | `0.0.0.0:4318` | OTLP HTTP listener |
| `OTEL_HEALTH_ENDPOINT` | `0.0.0.0:13133` | Collector health extension |
| `NGSH_CLASSIFICATION_LEVEL` | `UNCLASSIFIED` | Stamped onto every signal |
| `NGSH_DEPLOYMENT_PROFILE` | `local` | `local` \| `il5` \| `il6` \| `edge` |
| `NGSH_DEPLOYMENT_ZONE` | `local-dev` | Zone label |
| `NGSH_TENANT` | `ngsh-local` | Tenant key |
| `OTEL_DEBUG_VERBOSITY` | `normal` | Debug exporter verbosity |

> The `debug` exporter is **local development only**. Remove it from the
> `service.pipelines` section before a configuration is promoted into an
> accredited zone: it writes payload-level detail to stdout, which in an IL5
> or IL6 zone is a logging violation, not a convenience.

---

## 2. Resource attributes (mandatory)

Every signal carries these resource attributes. They are attached by the
collector (`resource` processor), so a service that forgets to set them still
produces correctly-attributed telemetry.

| Attribute | Example | Meaning |
|---|---|---|
| `service.name` | `fabric-service` | The emitting service |
| `service.namespace` | `ngsh` | Constant |
| `service.version` | `0.1.0` | Build identity |
| `deployment.profile` | `il5` | Which deployment profile the process runs under |
| `deployment.zone.name` | `govcloud-enclave-a` | Which of the three zones |
| `ngsh.classification.level` | `CUI` | Highest handling caveat carried by the zone |
| `ngsh.tenant` | `ngsh-shy` | Tenant key; every query is tenant-scoped |

### Classification attributes

`ngsh.classification.level` is a **zone-level** attribute: it names the
highest handling caveat the zone is accredited for, not the caveat of one
record. It must be one of:

```
UNCLASSIFIED | CUI | CUI//REL | CUI//FOUO | RESTRICTED | SECRET | TOP SECRET
```

The values match `contracts/ontology/common.schema.json#/$defs/Classification`.

### Tenant attributes

`ngsh.tenant` is mandatory on every signal. A signal that cannot be attributed
to a tenant is a defect: either the request was unscoped (fix the caller) or
the service is operating outside a tenant context (fix the service).

The record-level classification and tenant live in the *event envelope*
(`contracts/events/event-envelope.schema.json`) and are carried on the
**span**, not the resource — see below.

---

## 3. Trace propagation

### Format

W3C Trace Context only: `traceparent` and `tracestate`, with `baggage`
enabled. `traceparent` is mandatory on every outbound request.

```
traceparent: 00-<32 hex trace-id>-<16 hex span-id>-<01 flags>
```

### Rules

1. **Every inbound request creates a server span.** If the inbound request
   carries a valid `traceparent`, the new span's parent is the inbound
   `traceparent` span id. If it does not, the service starts a new trace.
2. **Every outbound request injects `traceparent`** into the outgoing headers.
   The service never forwards a stale `traceparent` unchanged — the outgoing
   span becomes the parent of the remote span.
3. **The platform's own correlation id rides in baggage**, not in a custom
   header, so it survives hops that do not know about NGSH:

   ```
   baggage: ngsh.correlation_id=<uuid>,ngsh.tenant=<tenant>
   ```

   `ngsh.correlation_id` is the envelope's `correlationId`. It groups all
   events produced while handling one logical request or campaign, which is
   not the same thing as a trace id — a single campaign spans many traces.

4. **The console is a tracing participant.** nginx forwards `traceparent`,
   `tracestate` and `baggage` unchanged (see
   `deploy/compose/web/proxy_params_ngsh.conf`), so the browser → nginx →
   service hop is one continuous trace.

5. **Edge annexes break the trace, not the data.** An edge node that has been
   disconnected for hours cannot extend a live trace. It opens a **new** trace
   per reconciled batch and links it to the original with the envelope's
   `causationId`/`correlationId`, plus the `edge.nodeId` and
   `edge.clockSkewMs` fields. Do not fabricate a parent span that never
   existed.

### Span naming

`{service}.{operation}` — lowercase, dot-separated, no entity identifiers, no
variable segments.

```
fabric.publish_event        good
ontology.get_entity         good
audit.record_access         good
audit.get_entity_A1B2C3     bad — unbounded cardinality in the span name
```

### Mandatory span attributes

| Attribute | On | Notes |
|---|---|---|
| `ngsh.event_type` | any span handling an event | e.g. `entity.created` |
| `ngsh.event_version` | any span handling an event | Integer |
| `ngsh.aggregate_type` | any span handling an event | Ontology type, e.g. `System` |
| `ngsh.tenant` | every span | Required even if the resource already carries it |
| `ngsh.classification.level` | every span | Level of the *record* being handled, which may be lower than the zone level |
| `ngsh.correlation_id` | any span inside a logical request | UUID, matches the envelope |
| `ngsh.causation_id` | any span caused by another event | Matches the envelope |
| `http.route` | every server span | The **templated** route (`/entities/{id}`), never the raw path |
| `ngsh.edge.node_id` | edge spans | The annex node id |

`ngsh.classification.level` on the span is the level of the specific record.
The resource attribute `ngsh.classification.level` is the level of the zone.
Both are named the same on purpose so a naive query still returns the more
specific of the two — but query the span attribute explicitly when the
distinction matters.

### Mandatory span status

* `STATUS_OK` on success.
* `STATUS_ERROR` on failure, with `exception.type` and `exception.message`
  set.
* An event that was **rejected** is `ERROR` — a rejected envelope is not a
  silent no-op.

---

## 4. Metric conventions

### Naming

`{namespace}_{unit}_{type}` — Prometheus-style, lowercase, underscore-separated.

```
ngsh_events_published_total
ngsh_event_publish_duration_seconds
ngsh_event_log_lag_seconds
ngsh_http_request_duration_seconds
```

* `_total` for counters, `_seconds` for durations, `_bytes` for sizes.
* The `ngsh_` prefix is mandatory. The collector's `filter/cardinality`
  processor looks for other patterns; the prefix keeps the rules simple.
* Every metric carries the `ngsh_` prefix so the backend can drop anything
  that is not NGSH's.

### Units

| Quantity | Unit | Notes |
|---|---|---|
| Durations | seconds | Histograms use `_duration_seconds` with `le` buckets |
| Sizes | bytes | `_bytes` |
| Counts | unitless | `_total` for counters |
| Rates | per second | `_per_second` |

### Cardinality rules — these are hard rules

1. **Never put an entity id in a metric label.** `PART:NSN-4472`, `SYS:01J8Z…`,
   `eventId`, `aggregateId`, `batchId`, `correlationId` — none of them may
   ever appear as a metric label. The number of entities is unbounded; a
   label set that includes one is a cardinality bomb.
2. **Never put a user id, person id, session id, or token in a metric label.**
   Those are PII-bearing and unbounded.
3. **Bounded dimensions only.** A metric label must come from a closed set:
   service name, event type (bounded by `contracts/events/catalog.json`),
   aggregate type (bounded by `contracts/ontology/registry.json`), tenant
   (bounded by the number of programs), classification level, outcome
   (`success` \| `rejected` \| `error`), deployment profile, zone.
4. **Entity-level detail goes in the trace or the log, not the metric.** If you
   need to count events for one part, that is a query over the event log —
   which is exactly what the fabric is for.
5. **Bounded histograms.** Custom bucket boundaries are allowed, but the
   bucket set must be fixed in code, not derived from observed values.
6. The collector enforces rules 1 and 3 defensively: metrics whose names match
   `.*\.(entity|aggregate|event|record)_id\..*` or `.*_by_(entity|aggregate|event|record)_id$`
   are dropped at the collector, before they can reach the backend.

### Mandatory metric attributes

Every NGSH metric carries, at minimum: `service.name`, `ngsh.tenant`,
`ngsh.classification.level`, `ngsh.deployment.profile`.

### Golden signals, per service

| Signal | Metric | Type |
|---|---|---|
| Latency | `ngsh_http_request_duration_seconds` | Histogram |
| Traffic | `ngsh_http_requests_total` | Counter |
| Errors | `ngsh_http_requests_total{outcome="error"}` | Counter (via `outcome`) |
| Saturation | `ngsh_event_log_lag_seconds` | Gauge (fabric, ingest) |

Fabric-specific:

* `ngsh_events_published_total{event_type, aggregate_type}` — counter
* `ngsh_event_log_lag_seconds` — gauge: now minus the newest `recordedAt`
  in the log. This is the single most important number in the platform.
* `ngsh_projection_lag_seconds{projection}` — gauge per projection
  (ontology, graph, audit).

---

## 5. Log conventions

### Format

Structured JSON, one object per line, on stdout. The container runtime
collects it; nothing writes to a file inside the container.

```json
{
  "timestamp": "2026-01-01T00:00:00.000Z",
  "level": "INFO",
  "logger": "ngsh.fabric.publisher",
  "message": "event accepted",
  "service": "fabric-service",
  "ngsh.tenant": "ngsh-shy",
  "ngsh.classification.level": "CUI",
  "ngsh.event_type": "entity.created",
  "ngsh.aggregate_type": "System",
  "ngsh.correlation_id": "3f2a...",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "ngsh.deployment.profile": "il5",
  "ngsh.deployment.zone": "govcloud-enclave-a"
}
```

### Rules

1. **Log records are a trace participant.** Every log line carries
   `trace_id` and `span_id`. A log line that cannot be tied to a trace is a
   defect; use a span for the surrounding operation.
2. **No secrets, ever.** No tokens, no connection strings, no clearance
   records, no key material. The collector's `attributes/redact` processor is
   a backstop, not the control.
3. **Classification markings travel with the record.** A log line about a
   classified record carries `ngsh.classification.level` for that record.
4. **No entity ids in the *message*.** Entity ids are fine as structured
   fields — they are not indexed as a metric dimension and do not create
   cardinality problems in a log store. They are not fine inside a metric
   label (see §4).
5. **Levels**: `DEBUG` (development only), `INFO` (default), `WARNING`
   (degraded but working), `ERROR` (failed operation), `CRITICAL` (the service
   cannot serve).
6. **Audit decisions are logged at `INFO` with `outcome`** and are also
   recorded as `access.decision.recorded` events. The log is for operators;
   the event is for the audit ledger.

---

## 6. Cross-zone behaviour

| Zone | Traces | Metrics | Logs |
|---|---|---|---|
| Central fabric | Full | Full | Full |
| Accredited cloud enclave | Full | Full | Full |
| On-prem IL6 enclave | Full, retained locally | Full, retained locally | Full, retained locally |
| Segregated edge annex | Local only while disconnected; flushed on reconciliation | Local buffer only; flushed on reconciliation | Local buffer only; flushed on reconciliation |

An edge annex is **disconnected**. Its collector buffers to disk, and the
buffer is flushed with the next store-and-forward reconciliation. Nothing
flows continuously between zones. See `deploy/README.md`, "Data flows between
zones".

---

## 7. Quick reference for a service author

```python
# 1. Resource attributes: set once, from the environment.
resource = Resource.create({
    "service.name": os.environ["NGSH_SERVICE_NAME"],
    "service.namespace": "ngsh",
    "deployment.profile": os.environ.get("NGSH_DEPLOYMENT_PROFILE", "local"),
    "deployment.zone.name": os.environ.get("NGSH_DEPLOYMENT_ZONE", "local-dev"),
    "ngsh.classification.level": os.environ.get("NGSH_CLASSIFICATION_LEVEL", "UNCLASSIFIED"),
    "ngsh.tenant": os.environ.get("NGSH_TENANT", "ngsh-local"),
})

# 2. A server span: parent comes from the inbound traceparent.
with tracer.start_as_current_span("fabric.publish_event") as span:
    span.set_attribute("ngsh.event_type", envelope.event_type)
    span.set_attribute("ngsh.aggregate_type", envelope.aggregate_type)
    span.set_attribute("ngsh.tenant", envelope.tenant)
    span.set_attribute("ngsh.classification.level", envelope.classification.level)
    span.set_attribute("ngsh.correlation_id", envelope.correlation_id)

    # 3. An outbound call: inject, do not copy.
    propagate.inject(headers=headers)   # headers["traceparent"] = ...

# 4. A metric: bounded labels only.
counter.add(1, {"event_type": "entity.created", "aggregate_type": "System"})
# NOT: counter.add(1, {"aggregate_id": "SYS:01J8Z..."})
```
