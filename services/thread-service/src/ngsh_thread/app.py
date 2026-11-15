"""NGSH thread service: the digital thread projection.

The graph is a materialisation of the event log, not an independent source of
truth. That distinction is what makes the thread trustworthy: the projection
can be deleted and rebuilt from the log without loss, so it is never the place
where an authoritative fact lives (ADR-0001).

This service owns the traversal queries that the platform is built around:

* trace paths outward from any entity, in either direction;
* requirement verification coverage, the end-to-end trace required by
  Pillar A-3;
* graph statistics per entity and relation type.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from ngsh_core.app import create_service
from ngsh_core.config import Settings, load_settings
from ngsh_core.envelope import EventEnvelope
from ngsh_core.errors import ValidationError
from ngsh_core.graph import GraphProjector
from ngsh_core.lakehouse import dataset_catalog, dataset_lineage
from ngsh_core.search import search as search_projection
from ngsh_core.store import open_database

SERVICE_NAME = "thread"
DESCRIPTION = (
    "The digital thread: a projection of the event log, and the traversal "
    "queries that connect requirements, parts, processes, tests and threats."
)

router = APIRouter(prefix="/v1", tags=["thread"])


def _projector(request: Request) -> GraphProjector:
    return request.app.state.projector


@router.get("/entities", summary="List projected entities")
async def list_entities(
    request: Request,
    type: str | None = Query(None, description="Filter by entity type."),
    tenant: str | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List the entities in the projection.

    A convenience over the projection, used by the console to populate
    entity pickers. The projection is rebuildable from the log, so this is
    never an authoritative read.
    """
    entities = _projector(request).entities(entity_type=type, tenant=tenant, limit=limit, offset=offset)
    return {"entities": entities, "count": len(entities), "limit": limit, "offset": offset}


@router.get("/entities/{entity_type}/{entity_id}", summary="Fetch a projected entity")
async def get_entity(request: Request, entity_type: str, entity_id: str) -> dict[str, Any]:
    projector = _projector(request)
    entity = projector.entity(entity_type, entity_id)
    if entity is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": f"no {entity_type} with id {entity_id!r}"}},
        )
    return {"entity": entity, "relations": projector.relations_for(entity_type, entity_id)}


@router.get("/relations", summary="List projected relations")
async def list_relations(
    request: Request,
    fromId: str | None = Query(None),
    toId: str | None = Query(None),
    type: str | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
) -> dict[str, Any]:
    projector = _projector(request)
    relations = projector.relations(
        from_id=fromId,
        to_id=toId,
        relation_type=type,
        limit=limit,
    )
    return {"relations": relations}


@router.get("/trace", summary="Trace the digital thread from a root entity")
async def trace(
    request: Request,
    root: str = Query(..., description="Root entity as 'Type:id', e.g. 'TestResult:TR:01J8Z...'."),
    depth: int = Query(3, ge=1, le=8),
    relationTypes: str | None = Query(None, description="Comma-separated relation types to include."),
    direction: str = Query("both", pattern="^(out|in|both)$"),
) -> dict[str, Any]:
    """Walk outward from a root entity.

    The walk is breadth-first with a visited set, so cycles in the ontology
    terminate rather than loop.
    """
    entity_type, _, entity_id = root.partition(":")
    if not entity_type or not entity_id:
        raise ValidationError("root must be formatted as 'Type:id'")

    types = [t.strip() for t in relationTypes.split(",") if t.strip()] if relationTypes else None
    result = _projector(request).trace(
        entity_type,
        entity_id,
        depth=depth,
        relation_types=types,
        direction=direction,
    )
    return result.to_dict()


@router.post("/trace/requirements/{requirement_id}/coverage", summary="Requirement verification coverage")
async def requirement_coverage(request: Request, requirement_id: str) -> dict[str, Any]:
    """Verification status of a requirement.

    A requirement is verified when at least one test result that verifies it
    passed and none failed. Partial coverage is the normal state of a
    programme in flight, so the response reports the ratio alongside the
    flag.
    """
    return _projector(request).requirement_coverage(requirement_id)


@router.get("/search", summary="Search the digital thread")
async def search(
    request: Request,
    q: str = Query(..., min_length=1, description="Free-text query, e.g. 'TPS ablative' or 'PART:NSN-4472'."),
    type: str | None = Query(None, description="Restrict to one entity type."),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    """Rank thread entities against a query, with the matched fields.

    The index is a projection over the graph, rebuilt from the log like every
    other read. Results explain themselves: every hit carries the fields that
    matched and the score it earned.
    """
    entities = _projector(request).entities(limit=10_000)
    return search_projection(entities, q, entity_type=type, limit=limit)


@router.get("/datasets", summary="Catalogue the test data lake")
async def datasets(request: Request) -> dict[str, Any]:
    """Build the dataset catalogue from admitted test results.

    A dataset is *configured* only when every result referencing it carries a
    configuration snapshot. The catalogue is derived from the thread, so it can
    be rebuilt and never becomes a second source of truth.
    """
    results = _projector(request).entities(entity_type="TestResult", limit=10_000)
    return dataset_catalog(results)


@router.get("/datasets/{dataset_id}/lineage", summary="Lineage for one dataset")
async def dataset_lineage_route(request: Request, dataset_id: str) -> dict[str, Any]:
    """Resolve a dataset id to the results, configurations and models behind it."""
    results = _projector(request).entities(entity_type="TestResult", limit=10_000)
    catalogue = dataset_catalog(results)["datasets"]
    entry = next((item for item in catalogue if item["datasetId"] == dataset_id), None)
    if entry is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "not_found",
                    "message": f"no dataset with id {dataset_id!r}",
                }
            },
        )
    return dataset_lineage(entry["uri"], results)


@router.get("/graph/stats", summary="Graph statistics")
async def stats(request: Request) -> dict[str, Any]:
    return _projector(request).stats()


@router.post("/project/apply", summary="Apply events to the projection")
async def apply_events(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Apply a batch of events to the projection.

    Called by the fabric after an append. The operation is idempotent, so a
    retried delivery does not corrupt the projection.
    """
    raw_events = body.get("events") if isinstance(body, dict) else None
    if not isinstance(raw_events, list):
        raise ValidationError("body must contain an 'events' array")

    projector = _projector(request)
    applied = 0
    for raw in raw_events:
        try:
            envelope = EventEnvelope.model_validate(raw)
        except Exception:
            continue
        projector.apply(envelope)
        applied += 1

    return {"applied": applied, "cursor": projector.cursor()}


@router.post("/project/replay", summary="Rebuild the projection from the log")
async def replay(request: Request) -> dict[str, Any]:
    """Rebuild the whole projection by replaying the event log.

    This is the operation that demonstrates that the graph holds nothing the
    log does not: delete the projection, replay the log, and the thread comes
    back identical.
    """
    projector = _projector(request)
    settings: Settings = request.app.state.settings

    events = _read_events(request, settings)
    for envelope in events:
        projector.apply(envelope)

    return {"replayed": len(events), "cursor": projector.cursor(), "stats": projector.stats()}


def _read_events(request: Request, settings: Settings) -> list[EventEnvelope]:
    """Read the log from the fabric service, or from the shared store."""
    if settings.fabric_url:
        import httpx

        collected: list[EventEnvelope] = []
        cursor = 0
        with httpx.Client(timeout=10.0) as client:
            while True:
                response = client.get(
                    f"{settings.fabric_url}/v1/events", params={"after": cursor, "limit": 500}
                )
                response.raise_for_status()
                page = response.json()
                for raw in page.get("events", []):
                    collected.append(EventEnvelope.model_validate(raw))
                if not page.get("hasMore"):
                    break
                cursor = page.get("cursor", cursor)
        return collected

    from ngsh_core.eventlog import EventLog

    log = EventLog(request.app.state.executor)
    return list(log.replay())


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()
    executor = open_database(resolved.dsn)

    app = create_service(
        SERVICE_NAME,
        settings=resolved,
        description=DESCRIPTION,
        routers=[router],
        tags=[
            {"name": "thread", "description": "Digital thread traversal and projection."},
            {"name": "operations", "description": "Health and metadata."},
        ],
    )
    app.state.executor = executor
    app.state.projector = GraphProjector(executor)
    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
