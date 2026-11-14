"""NGSH fabric service.

The system of record. Every mutation in the platform is an event appended
here; every other store is a projection rebuilt by replaying this log
(ADR-0001).

Responsibilities:

* accept events, enforcing per-aggregate sequencing and idempotency;
* serve the event stream to projections and to the console;
* expose the event catalog so that consumers know what they may subscribe to;
* notify interested projections when new events land.

The service holds no business logic beyond the invariants of the log itself.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from ngsh_core.app import create_service
from ngsh_core.config import Settings, load_settings
from ngsh_core.envelope import EventEnvelope
from ngsh_core.errors import ValidationError
from ngsh_core.eventlog import EventLog
from ngsh_core.ontology import OntologyLoader
from ngsh_core.store import open_database

SERVICE_NAME = "fabric"
DESCRIPTION = (
    "The NGSH data fabric. Append-only event log; the system of record for every other store in the platform."
)

router = APIRouter(prefix="/v1", tags=["fabric"])


def _catalog(settings: Settings) -> dict[str, Any]:
    path = settings.contracts_dir / "events" / "catalog.json"
    if not path.exists():
        return {"catalogVersion": "0.0.0", "events": [], "subscriptionGroups": {}}
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/events", summary="Append one or more events")
async def publish(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Append events to the log.

    Accepts either a single envelope or ``{"events": [...]}``. The response
    reports each event separately so that a partially-rejected batch is
    visible to the caller rather than collapsing into an opaque error.
    """
    log: EventLog = request.app.state.eventlog

    raw_events = body.get("events") if isinstance(body, dict) and "events" in body else [body]
    if not isinstance(raw_events, list) or not raw_events:
        raise ValidationError("request body must be an event envelope or a non-empty 'events' array")

    envelopes: list[EventEnvelope] = []
    for index, raw in enumerate(raw_events):
        try:
            envelopes.append(EventEnvelope.model_validate(raw))
        except Exception as exc:
            raise ValidationError(f"event at index {index} is not a valid envelope", detail=str(exc)) from exc

    outcomes = log.append_batch(envelopes)

    accepted = [o for o in outcomes if o.accepted]
    rejected = [{"eventId": o.eventId, "reason": o.reason} for o in outcomes if not o.accepted]

    # Fan out to projections. A projection failure must not fail the append:
    # the log is authoritative and projections are rebuildable, so the
    # projection is simply re-driven later.
    notifications = await _notify_projections(request, accepted)

    status = 201 if accepted and not rejected else 200
    return JSONResponse(
        status_code=status,
        content={
            "accepted": [{"eventId": o.eventId, "duplicate": o.duplicate} for o in accepted],
            "rejected": rejected,
            "notifications": notifications,
        },
    )


async def _notify_projections(request: Request, accepted: list[Any]) -> dict[str, Any]:
    """Push newly accepted events to the thread projection.

    Delivery is best-effort and fire-and-forget. If the projection is down,
    the log still holds the events and the projection is rebuilt by replay.
    """
    if not accepted:
        return {"status": "skipped"}
    thread_url = request.app.state.settings.thread_url
    if not thread_url:
        return {"status": "disabled", "reason": "no thread service configured"}
    try:
        import httpx

        envelopes = []
        for outcome in accepted:
            envelope = request.app.state.eventlog.get(outcome.eventId)
            if envelope is not None:
                envelopes.append(envelope.to_logical_json())
        if not envelopes:
            return {"status": "no-op"}
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(f"{thread_url}/v1/project/apply", json={"events": envelopes})
            return {
                "status": "delivered" if response.status_code < 300 else "failed",
                "code": response.status_code,
            }
    except Exception as exc:  # network failure must not fail the append
        return {"status": "failed", "reason": type(exc).__name__}


@router.get("/events", summary="Read the event stream")
async def read_events(
    request: Request,
    after: int = Query(0, ge=0, description="Log sequence cursor to read after."),
    limit: int = Query(100, ge=1, le=1000),
    types: str | None = Query(None, description="Comma-separated event type patterns, e.g. 'test.*,model.*'"),
    tenant: str | None = Query(None),
    aggregateId: str | None = Query(None),
) -> dict[str, Any]:
    log: EventLog = request.app.state.eventlog
    patterns = [t.strip() for t in types.split(",") if t.strip()] if types else None
    events, cursor = log.read(
        after=after, limit=limit, types=patterns, tenant=tenant, aggregate_id=aggregateId
    )
    return {
        "events": [e.to_logical_json() for e in events],
        "cursor": cursor,
        "hasMore": len(events) == limit,
    }


@router.get("/events/{event_id}", summary="Fetch a single event")
async def get_event(request: Request, event_id: str) -> dict[str, Any]:
    log: EventLog = request.app.state.eventlog
    envelope = log.get(event_id)
    if envelope is None:
        return JSONResponse(
            status_code=404, content={"error": {"code": "not_found", "message": "no such event"}}
        )
    return envelope.to_logical_json()


@router.get("/stats", summary="Event log statistics")
async def stats(request: Request) -> dict[str, Any]:
    log: EventLog = request.app.state.eventlog
    return log.stats()


@router.get("/catalog", summary="Event type catalog")
async def catalog(request: Request) -> dict[str, Any]:
    return _catalog(request.app.state.settings)


@router.get("/topics", summary="Subscription groups")
async def topics(request: Request) -> dict[str, Any]:
    return _catalog(request.app.state.settings).get("subscriptionGroups", {})


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()

    app = create_service(
        SERVICE_NAME,
        settings=resolved,
        description=DESCRIPTION,
        routers=[router],
        tags=[
            {"name": "fabric", "description": "Event log operations."},
            {"name": "operations", "description": "Health and metadata."},
        ],
    )
    executor = open_database(resolved.dsn)
    app.state.executor = executor
    app.state.eventlog = EventLog(executor)
    app.state.registry = OntologyLoader(resolved.contracts_dir).load()

    from ngsh_fabric.edge import register as register_edge_routes

    register_edge_routes(app)

    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
