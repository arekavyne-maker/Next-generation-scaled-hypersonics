"""NGSH manufacturing service (Pillar B).

Increment 2's manufacturing capabilities, in the form the programme can use
today: a traveller built from a released process plan, process runs recorded
with their operator and parameters, genealogy that names its broken links,
drift detected against the process's own history before disposition, and an
explicit rate model that names its binding constraint.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from ngsh_core.app import create_service
from ngsh_core.config import Settings, load_settings
from ngsh_core.envelope import EventEnvelope
from ngsh_core.errors import NotFoundError, ValidationError
from ngsh_core.graph import GraphProjector
from ngsh_core.ids import new_ulid
from ngsh_core.manufacturing import (
    assemble_genealogy,
    build_traveller,
    detect_drift,
    simulate_rate,
)
from ngsh_core.ontology import OntologyLoader
from ngsh_core.production_sim import simulate_production
from ngsh_core.publish import actor_for, entity_document, publish
from ngsh_core.store import open_database
from ngsh_core.workforce import clearance_current, clearance_rank

SERVICE_NAME = "manufacturing"
DESCRIPTION = (
    "Pillar B: travellers from released process plans, process runs and "
    "genealogy, drift detection before disposition, and an inspectable rate model."
)

router = APIRouter(prefix="/v1", tags=["manufacturing"])


def _projector(request: Request) -> GraphProjector:
    return request.app.state.projector


def _attrs(entity: dict[str, Any] | None) -> dict[str, Any]:
    return (entity or {}).get("attributes") or {}


def _require(request: Request, entity_type: str, entity_id: str) -> dict[str, Any]:
    entity = _projector(request).entity(entity_type, entity_id)
    if entity is None:
        raise NotFoundError(f"no {entity_type} with id {entity_id!r}")
    return entity


def _runs_for(request: Request, process_plan_id: str) -> list[dict[str, Any]]:
    runs = []
    for run in _projector(request).entities(entity_type="ProcessRun", limit=5000):
        attributes = _attrs(run)
        if attributes.get("processPlanId") == process_plan_id:
            runs.append({**attributes, "runId": run["id"]})
    return runs


@router.post("/process-runs", summary="Record a completed process run", status_code=201)
async def record_run(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    process_plan_id = body.get("processPlanId")
    if not isinstance(process_plan_id, str) or not process_plan_id:
        raise ValidationError("'processPlanId' is required")
    plan = _require(request, "ProcessPlan", process_plan_id)

    operator_id = body.get("operatorId")
    operator = None
    if operator_id:
        operator = _attrs(_require(request, "Person", operator_id))
        if not clearance_current(operator, datetime.now(UTC)):
            return JSONResponse(
                status_code=422,
                content={
                    "error": {
                        "code": "constraint_violation",
                        "message": "C-006: the operator's clearance is not current",
                    }
                },
            )

    started_at = body.get("startedAt") or datetime.now(UTC).isoformat()
    run_id = f"PR:{new_ulid()}"
    attributes = {
        "processPlanId": process_plan_id,
        "materialId": body.get("materialId"),
        "partId": body.get("partId"),
        "facilityId": body.get("facilityId"),
        "startedAt": started_at,
        "endedAt": body.get("endedAt"),
        "measuredParameters": body.get("measuredParameters") or {},
        "operatorId": operator_id,
        "disposition": body.get("disposition") or "ACCEPTED",
        "nonconformanceId": body.get("nonconformanceId"),
        "driftFlags": body.get("driftFlags") or [],
        "opId": body.get("opId") or body.get("operationId"),
    }

    settings: Settings = request.app.state.settings
    actor = actor_for(settings, request)
    document = entity_document(
        "ProcessRun",
        run_id,
        {key: value for key, value in attributes.items() if value is not None},
        tenant=settings.tenant,
        program=settings.program,
        created_by=actor.subjectId,
        provenance={"source": "manufacturing-service", "method": "process-run"},
    )
    from ngsh_core.envelope import Entity

    errors = request.app.state.registry.validate_entity(Entity.model_validate(document))
    if errors:
        raise ValidationError(f"ProcessRun {run_id} does not satisfy the ontology", detail=errors)

    event = EventEnvelope(
        eventType="process.run.completed",
        aggregateType="ProcessRun",
        aggregateId=run_id,
        sequence=1,
        tenant=settings.tenant,
        program=settings.program,
        actor=actor,
        payload={"processRun": document, "processPlanRevision": plan.get("attributes", {}).get("revision")},
    )
    await publish(request, event)

    if body.get("testResultId"):
        from ngsh_core.publish import relation_document, relation_event

        relation = relation_document(
            "characterizedBy",
            ("ProcessRun", run_id),
            ("TestResult", str(body["testResultId"])),
            tenant=settings.tenant,
            asserted_by=actor.subjectId,
        )
        await publish(request, relation_event(relation, actor, registry=request.app.state.registry))

    return JSONResponse(status_code=201, content={"processRun": document})


@router.post("/travellers", summary="Build a traveller from a released process plan")
async def traveller(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    plan_id = body.get("processPlanId")
    if not isinstance(plan_id, str) or not plan_id:
        raise ValidationError("'processPlanId' is required")
    plan_entity = _require(request, "ProcessPlan", plan_id)
    plan_attributes = _attrs(plan_entity)
    runs = _runs_for(request, plan_id)
    return build_traveller({"id": plan_id, **plan_attributes}, runs)


@router.post("/drift", summary="Detect process drift against the run history")
async def drift(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    plan_id = body.get("processPlanId")
    if not isinstance(plan_id, str) or not plan_id:
        raise ValidationError("'processPlanId' is required")
    candidate = body.get("candidate")
    if not isinstance(candidate, dict):
        raise ValidationError("'candidate' must carry the measuredParameters under test")
    reference = _runs_for(request, plan_id)
    return detect_drift(reference, candidate, sigma_limit=float(body.get("sigmaLimit", 3.0)))


@router.post("/simulate-rate", summary="Simulate achievable rate for a facility")
async def simulate(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    facility_id = body.get("facilityId")
    if not isinstance(facility_id, str) or not facility_id:
        raise ValidationError("'facilityId' is required")
    facility = _require(request, "Facility", facility_id)
    facility_attributes = {**_attrs(facility), "id": facility_id}
    units = body.get("units")
    if not isinstance(units, int) or units <= 0:
        raise ValidationError("'units' must be a positive integer")
    return simulate_rate(
        facility_attributes,
        units=units,
        horizon_days=int(body.get("horizonDays", 90)),
        shifts=body.get("shifts"),
        efficiency=float(body.get("efficiency", 0.85)),
        setup_days=int(body.get("setupDays", 1)),
        unit_cost=body.get("unitCost"),
    )


@router.post("/production/simulate", summary="Run a discrete-event production simulation")
async def production_simulation(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Simulate the line as it is described, not as it is hoped to be.

    Stations are supplied explicitly so the same endpoint serves a what-if
    study, a surge plan and an industrial-base assessment. The result is
    reproducible from the request; ``seed`` changes the yield draws, nothing
    else.
    """
    stations = body.get("stations")
    if not isinstance(stations, list) or not stations:
        raise ValidationError("'stations' must be a non-empty list")
    demand_units = body.get("demandUnits")
    if not isinstance(demand_units, int) or demand_units <= 0:
        raise ValidationError("'demandUnits' must be a positive integer")
    return simulate_production(
        stations,
        demand_units=demand_units,
        shifts_per_day=int(body.get("shiftsPerDay", 2)),
        shift_hours=float(body.get("shiftHours", 8.0)),
        horizon_days=int(body.get("horizonDays", 30)),
        seed=int(body.get("seed", 2026)),
    )


@router.get("/genealogy/{part_id}", summary="Genealogy chain of custody for a part")
async def genealogy(request: Request, part_id: str) -> dict[str, Any]:
    _require(request, "Part", part_id)
    projector = _projector(request)
    provenance_entity = None
    for entity in projector.entities(entity_type="PartProvenance", limit=5000):
        if _attrs(entity).get("partId") == part_id:
            provenance_entity = _attrs(entity)
            break

    known_runs = {entity["id"] for entity in projector.entities(entity_type="ProcessRun", limit=5000)}
    known_materials = {entity["id"] for entity in projector.entities(entity_type="Material", limit=5000)}
    known_parts = {entity["id"] for entity in projector.entities(entity_type="Part", limit=5000)}
    report = assemble_genealogy(
        part_id,
        provenance_entity,
        known_runs=known_runs,
        known_materials=known_materials,
        known_parts=known_parts,
    )
    if provenance_entity:
        report["chainOfCustody"] = provenance_entity.get("chainOfCustody") or []
    return report


@router.get("/operators/{person_id}/authorised", summary="Is this operator's clearance current?")
async def operator_authorisation(
    request: Request,
    person_id: str,
    skillId: str | None = Query(None),
) -> dict[str, Any]:
    person = _attrs(_require(request, "Person", person_id))
    current = clearance_current(person, datetime.now(UTC))
    reasons = [] if current else ["C-006: the operator's clearance is not current"]
    if skillId:
        skill = _attrs(_require(request, "Skill", skillId))
        if clearance_rank(person.get("clearanceLevel")) < clearance_rank(skill.get("clearanceRequired")):
            reasons.append("the operator's clearance is below the skill requirement")
    return {"personId": person_id, "allowed": not reasons, "reasons": reasons}


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
            {"name": "manufacturing", "description": "Pillar B: travellers, runs, drift, rate."},
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
