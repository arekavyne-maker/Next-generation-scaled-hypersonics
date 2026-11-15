"""NGSH industrial service (Pillar H).

The programme-facing surface of the surge model, the reconstitution playbooks
and the cost trace. Three things distinguish this service from a dashboard:

* every surge figure carries a confidence interval, a named owner and the twin
  run behind it, so the SHY question is answered continuously and defensibly;
* a reconstitution time is only reported when a tabletop exercise measured it,
  never from a sum of lead times;
* a cost trace names the requirements it covers and reports an estimate
  presented as an actual as a violation.

Surge and reconstitution reports are stored as annotations on the Facility and
Part they concern. That keeps the derived figure in the event log beside the
entity it describes, rather than in a service-private table.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, FastAPI, Query, Request
from ngsh_core.app import create_service
from ngsh_core.config import Settings, load_settings
from ngsh_core.errors import NotFoundError, ValidationError
from ngsh_core.graph import GraphProjector
from ngsh_core.industrial import (
    affordability_trace,
    reconstitution_assessment,
    surge_readiness,
    unit_cost_curve,
)
from ngsh_core.ontology import OntologyLoader
from ngsh_core.publish import (
    actor_for,
    entity_document,
    entity_event,
    next_sequence,
    publish,
)
from ngsh_core.store import open_database

SERVICE_NAME = "industrial"
DESCRIPTION = (
    "Pillar H: verified surge readiness with an interval and an owner, measured "
    "reconstitution plans, and the requirement-to-unit-cost affordability trace."
)

router = APIRouter(prefix="/v1", tags=["industrial"])

SURGE_ANNOTATION = "lastSurgeReadiness"
RECONSTITUTION_ANNOTATION = "lastReconstitutionAssessment"


def _projector(request: Request) -> GraphProjector:
    return request.app.state.projector


def _attrs(entity: dict[str, Any] | None) -> dict[str, Any]:
    return (entity or {}).get("attributes") or {}


def _require(request: Request, entity_type: str, entity_id: str) -> dict[str, Any]:
    entity = _projector(request).entity(entity_type, entity_id)
    if entity is None:
        raise NotFoundError(f"no {entity_type} with id {entity_id!r}")
    return entity


async def _annotate(request: Request, entity: dict[str, Any], key: str, value: Any) -> dict[str, Any]:
    """Write an annotation onto an existing entity as an ``entity.updated`` event."""
    settings: Settings = request.app.state.settings
    actor = actor_for(settings, request)
    annotations = {**(entity.get("annotations") or {}), key: json.dumps(value, sort_keys=True)}
    document = entity_document(
        entity["type"],
        entity["id"],
        dict(_attrs(entity)),
        tenant=entity.get("tenant") or settings.tenant,
        program=entity.get("program") or settings.program,
        classification=(entity.get("classification") or {}).get("level") or "CUI",
        created_by=entity.get("createdBy") or actor.subjectId,
        version=int(entity.get("version") or 1) + 1,
        provenance={"source": "industrial-service", "method": f"annotate-{key}"},
        annotations=annotations,
    )
    await publish(
        request,
        entity_event(
            document,
            actor,
            event_type="entity.updated",
            sequence=next_sequence(request.app.state.executor, entity["id"]),
            registry=request.app.state.registry,
        ),
    )
    return document


def _annotation(entity: dict[str, Any], key: str) -> dict[str, Any] | None:
    raw = (entity.get("annotations") or {}).get(key)
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


# -- H-1: surge readiness ----------------------------------------------------


@router.post("/surge-readiness", summary="Report verified surge readiness")
async def surge(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    facility_id = body.get("facilityId")
    if not isinstance(facility_id, str) or not facility_id:
        raise ValidationError("'facilityId' is required")
    facility = _require(request, "Facility", facility_id)

    suppliers = [
        {"id": entity["id"], **_attrs(entity)}
        for entity in _projector(request).entities(entity_type="Supplier", limit=5000)
    ]
    requested = body.get("supplierIds")
    if isinstance(requested, list) and requested:
        wanted = {str(item) for item in requested}
        suppliers = [supplier for supplier in suppliers if supplier["id"] in wanted]

    demand = body.get("demandUnits")
    if not isinstance(demand, int) or demand <= 0:
        raise ValidationError("'demandUnits' must be a positive integer")

    report = surge_readiness(
        facility={"id": facility_id, **_attrs(facility)},
        suppliers=suppliers,
        demand_units=demand,
        horizon_days=int(body.get("horizonDays", 90)),
        confidence_level=float(body.get("confidenceLevel", 0.90)),
        twin_run_id=body.get("twinRunId"),
        owner=body.get("owner"),
    )
    await _annotate(request, facility, SURGE_ANNOTATION, report)
    return report


@router.get("/surge-readiness/{facility_id}", summary="Latest stored surge report")
async def get_surge(request: Request, facility_id: str) -> dict[str, Any]:
    facility = _require(request, "Facility", facility_id)
    report = _annotation(facility, SURGE_ANNOTATION)
    if report is None:
        raise NotFoundError(f"no surge report has been recorded for Facility {facility_id!r}")
    return report


@router.get("/surge-readiness", summary="Latest surge report for every facility")
async def list_surge(
    request: Request,
    limit: int = Query(200, ge=1, le=2000),
) -> dict[str, Any]:
    reports = []
    for facility in _projector(request).entities(entity_type="Facility", limit=limit):
        report = _annotation(facility, SURGE_ANNOTATION)
        if report is not None:
            reports.append(report)
    return {"reports": reports, "count": len(reports)}


# -- H-3: affordability ------------------------------------------------------


@router.post("/affordability/trace", summary="Trace requirements to unit cost")
async def affordability(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    requirement_ids = body.get("requirementIds")
    if not isinstance(requirement_ids, list) or not requirement_ids:
        raise ValidationError("'requirementIds' must be a non-empty list")
    estimates = body.get("costEstimates")
    if not isinstance(estimates, list):
        raise ValidationError("'costEstimates' must be a list of cost estimates")

    edges = _projector(request).relations(relation_type="satisfies", limit=10_000)
    return affordability_trace(
        requirement_ids=[str(item) for item in requirement_ids],
        satisfies_edges=edges,
        cost_estimates=estimates,
        quantity=body.get("quantity"),
    )


@router.post("/affordability/rate-curve", summary="Predict unit cost against a rate curve")
async def rate_curve(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    points = body.get("points")
    if not isinstance(points, list):
        raise ValidationError("'points' must be a list of {rate, unitCost}")
    quantity = body.get("quantity")
    if not isinstance(quantity, int) or quantity <= 0:
        raise ValidationError("'quantity' must be a positive integer")
    return unit_cost_curve(
        points=points,
        quantity=quantity,
        actual_unit_cost=body.get("actualUnitCost"),
    )


# -- H-2: reconstitution -----------------------------------------------------


@router.post("/reconstitution/assess", summary="Assess a reconstitution playbook")
async def reconstitution(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    part_id = body.get("partId")
    if not isinstance(part_id, str) or not part_id:
        raise ValidationError("'partId' is required")
    part = _require(request, "Part", part_id)
    candidates = body.get("candidates")
    if not isinstance(candidates, list):
        raise ValidationError("'candidates' must be a list")

    report = reconstitution_assessment(
        critical_node={"id": part_id, "type": "Part", **_attrs(part)},
        candidates=candidates,
        exercise=body.get("exercise"),
        owner=body.get("owner"),
    )
    await _annotate(request, part, RECONSTITUTION_ANNOTATION, report)
    return report


@router.get("/reconstitution/assessments", summary="Latest reconstitution assessment per part")
async def list_reconstitution(
    request: Request,
    limit: int = Query(200, ge=1, le=2000),
) -> dict[str, Any]:
    reports = []
    for part in _projector(request).entities(entity_type="Part", limit=limit):
        report = _annotation(part, RECONSTITUTION_ANNOTATION)
        if report is not None:
            reports.append(report)
    return {"assessments": reports, "count": len(reports)}


@router.get("/reconstitution/assessments/{part_id}", summary="Latest assessment for one part")
async def get_reconstitution(request: Request, part_id: str) -> dict[str, Any]:
    part = _require(request, "Part", part_id)
    report = _annotation(part, RECONSTITUTION_ANNOTATION)
    if report is None:
        raise NotFoundError(f"no reconstitution assessment has been recorded for {part_id!r}")
    return report


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
            {"name": "industrial", "description": "Pillar H: surge, reconstitution and affordability."},
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
