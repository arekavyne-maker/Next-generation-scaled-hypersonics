"""NGSH engagement service (Pillars F and G).

Increment 4's kill-chain and virtual-range capabilities: threat systems and
observations, engagement scenarios that name their sensor and effector chains,
a deterministic Monte Carlo batch with a measured throughput, a kill-chain
report that names missing stages, and range bookings that refuse to overlap.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from ngsh_core.app import create_service
from ngsh_core.config import Settings, load_settings
from ngsh_core.engagement import kill_chain, run_batch, slot_conflicts
from ngsh_core.errors import NotFoundError, ValidationError
from ngsh_core.graph import GraphProjector
from ngsh_core.ids import new_ulid
from ngsh_core.ontology import OntologyLoader
from ngsh_core.publish import (
    actor_for,
    entity_document,
    entity_event,
    publish,
    relation_document,
    relation_event,
)
from ngsh_core.store import open_database

SERVICE_NAME = "engagement"
DESCRIPTION = (
    "Pillars F and G: threat engagement scenarios, deterministic Monte Carlo "
    "batches, the kill-chain view and virtual range bookings."
)

router = APIRouter(prefix="/v1", tags=["engagement"])


def _projector(request: Request) -> GraphProjector:
    return request.app.state.projector


def _attrs(entity: dict[str, Any] | None) -> dict[str, Any]:
    return (entity or {}).get("attributes") or {}


def _require(request: Request, entity_type: str, entity_id: str) -> dict[str, Any]:
    entity = _projector(request).entity(entity_type, entity_id)
    if entity is None:
        raise NotFoundError(f"no {entity_type} with id {entity_id!r}")
    return entity


@router.post("/threats", summary="Register a threat system", status_code=201)
async def create_threat(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    for key in ("designation", "threatClass"):
        if not isinstance(body.get(key), str) or not body[key]:
            raise ValidationError(f"'{key}' is required")
    threat_id = body.get("threatId") or f"THR:{new_ulid()}"
    settings: Settings = request.app.state.settings
    actor = actor_for(settings, request)
    document = entity_document(
        "ThreatSystem",
        threat_id,
        {
            "designation": body["designation"],
            "threatClass": body["threatClass"],
            "kinematicProfile": body.get("kinematicProfile") or {},
            "characteristics": body.get("characteristics") or [],
            "confidence": body.get("confidence"),
            "observationIds": body.get("observationIds") or [],
            "modelVersionIds": body.get("modelVersionIds") or [],
        },
        tenant=settings.tenant,
        program=settings.program,
        created_by=actor.subjectId,
    )
    await publish(request, entity_event(document, actor, registry=request.app.state.registry))
    return {"threat": document}


@router.post("/scenarios", summary="Create an engagement scenario", status_code=201)
async def create_scenario(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    name = body.get("name")
    if not isinstance(name, str) or not name:
        raise ValidationError("'name' is required")
    threat_ids = body.get("threatSystemIds") or []
    if not isinstance(threat_ids, list):
        raise ValidationError("'threatSystemIds' must be a list")

    scenario_id = f"ESC:{new_ulid()}"
    settings: Settings = request.app.state.settings
    actor = actor_for(settings, request)
    document = entity_document(
        "EngagementScenario",
        scenario_id,
        {
            "name": name,
            "threatSystemIds": threat_ids,
            "defensiveArchitecture": body.get("defensiveArchitecture"),
            "sensorChain": body.get("sensorChain") or [],
            "effectorChain": body.get("effectorChain") or [],
            "timeline": body.get("timeline") or {},
            "monteCarloConfig": body.get("monteCarloConfig") or {},
            "resultsSummary": body.get("resultsSummary") or {},
        },
        tenant=settings.tenant,
        program=settings.program,
        created_by=actor.subjectId,
    )

    events = [entity_event(document, actor, registry=request.app.state.registry)]
    for threat_id in threat_ids:
        _require(request, "ThreatSystem", str(threat_id))
        relation = relation_document(
            "engages",
            ("EngagementScenario", scenario_id),
            ("ThreatSystem", str(threat_id)),
            tenant=settings.tenant,
            asserted_by=actor.subjectId,
        )
        events.append(relation_event(relation, actor, registry=request.app.state.registry))

    await publish(request, *events)
    return JSONResponse(status_code=201, content={"scenario": document})


@router.post("/scenarios/{scenario_id}/batch", summary="Run a deterministic engagement batch")
async def batch(request: Request, scenario_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    scenario = _attrs(_require(request, "EngagementScenario", scenario_id))
    runs = body.get("runs", 10_000)
    if not isinstance(runs, int) or runs <= 0:
        raise ValidationError("'runs' must be a positive integer")
    return run_batch(
        {"id": scenario_id, **scenario},
        runs=runs,
        seed=int(body.get("seed", 1234)),
        pk_threshold=float(body.get("pkThreshold", 0.7)),
    )


@router.get("/kill-chain", summary="Kill chain for a scenario, stage by stage")
async def kill_chain_view(
    request: Request,
    scenarioId: str = Query(...),
) -> dict[str, Any]:
    projector = _projector(request)
    scenario = _attrs(_require(request, "EngagementScenario", scenarioId))

    threats = [
        _attrs(entity)
        for entity in projector.entities(entity_type="ThreatSystem", limit=5000)
        if entity["id"] in set(scenario.get("threatSystemIds") or [])
    ]
    observation_ids = {str(item) for threat in threats for item in threat.get("observationIds") or []}
    observations = [
        _attrs(entity)
        for entity in projector.entities(entity_type="ThreatObservation", limit=5000)
        if entity["id"] in observation_ids
    ]
    # Any approved model can assess an engagement; the stage reports which.
    models = [
        _attrs(entity) for entity in projector.entities(entity_type="Model", limit=5000)
    ]

    return kill_chain(
        observation=observations[0] if observations else None,
        threat=threats[0] if threats else None,
        scenario={"id": scenarioId, **scenario},
        models=models,
    )


@router.post("/range-slots", summary="Book a virtual range slot", status_code=201)
async def book_slot(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    projector = _projector(request)
    existing = [
        {**_attrs(entity), "id": entity["id"]}
        for entity in projector.entities(entity_type="RangeSlot", limit=5000)
    ]
    conflicts = slot_conflicts(body, existing)
    if conflicts:
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "range_slot_conflict",
                    "message": "the requested range slot overlaps an existing booking",
                    "context": {"conflicts": conflicts},
                }
            },
        )

    slot_id = f"RS:{new_ulid()}"
    settings: Settings = request.app.state.settings
    actor = actor_for(settings, request)
    document = entity_document(
        "RangeSlot",
        slot_id,
        {
            "facilityId": body.get("facilityId"),
            "start": body.get("start"),
            "end": body.get("end"),
            "campaignId": body.get("campaignId"),
            "instrumentation": body.get("instrumentation") or [],
            "telemetryCoverage": body.get("telemetryCoverage") or {},
            "status": "CONFIRMED",
        },
        tenant=settings.tenant,
        program=settings.program,
        created_by=actor.subjectId,
    )
    await publish(request, entity_event(document, actor, registry=request.app.state.registry))
    return JSONResponse(status_code=201, content={"slot": document})


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()
    executor = open_database(resolved.dsn)
    registry = OntologyLoader(resolved.contracts_dir).load()

    app = create_service(
        SERVICE_NAME,
        settings=resolved,
        description=DESCRIPTION,
        routers=[router],
        tags=[
            {"name": "engagement", "description": "Pillars F and G: threats, scenarios, batches, range."},
            {"name": "operations", "description": "Health and metadata."},
        ],
    )
    app.state.executor = executor
    app.state.registry = registry
    app.state.projector = GraphProjector(executor)
    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
