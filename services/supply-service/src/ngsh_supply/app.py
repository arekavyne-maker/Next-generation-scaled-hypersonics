"""NGSH supply service (Pillar D).

Increment 3's supply capabilities: the computed C-007 program risk for
critical single-source parts, a surge plan that names its binding supplier,
and a reconstitution playbook with lead times and coverage.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from ngsh_core.app import create_service
from ngsh_core.config import Settings, load_settings
from ngsh_core.errors import NotFoundError, ValidationError
from ngsh_core.graph import GraphProjector
from ngsh_core.ids import new_ulid
from ngsh_core.ontology import OntologyLoader
from ngsh_core.publish import actor_for, entity_document, entity_event, publish
from ngsh_core.store import open_database
from ngsh_core.supply import reconstitution_playbook, single_source_risks, surge_plan

SERVICE_NAME = "supply"
DESCRIPTION = (
    "Pillar D: single-source exposure as a program risk, surge under supplier "
    "constraints, and a reconstitution playbook per critical part."
)

router = APIRouter(prefix="/v1", tags=["supply"])


def _projector(request: Request) -> GraphProjector:
    return request.app.state.projector


def _attrs(entity: dict[str, Any] | None) -> dict[str, Any]:
    return (entity or {}).get("attributes") or {}


@router.post("/suppliers", summary="Register a supplier", status_code=201)
async def create_supplier(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    for key in ("name", "tier"):
        if body.get(key) is None:
            raise ValidationError(f"'{key}' is required")
    supplier_id = body.get("supplierId") or f"SUP:{new_ulid()}"
    settings: Settings = request.app.state.settings
    actor = actor_for(settings, request)
    document = entity_document(
        "Supplier",
        supplier_id,
        {
            "name": body["name"],
            "tier": body["tier"],
            "riskScore": body.get("riskScore"),
            "capabilities": body.get("capabilities") or [],
            "certifications": body.get("certifications") or [],
            "leadTimeDays": body.get("leadTimeDays"),
            "dependencies": body.get("dependencies") or [],
            "facilityIds": body.get("facilityIds") or [],
            "domesticContent": body.get("domesticContent"),
            "exportControlled": body.get("exportControlled"),
        },
        tenant=settings.tenant,
        program=settings.program,
        created_by=actor.subjectId,
    )
    await publish(request, entity_event(document, actor, registry=request.app.state.registry))
    return {"supplier": document}


@router.get("/supply-risks", summary="C-007 program risks")
async def supply_risks(request: Request, limit: int = Query(2000, ge=1, le=5000)) -> dict[str, Any]:
    projector = _projector(request)
    parts = [
        {"id": entity["id"], **_attrs(entity)}
        for entity in projector.entities(entity_type="Part", limit=limit)
    ]
    reconstitutes = projector.relations(relation_type="reconstitutes", limit=5000)
    targets = {
        edge["to"]["id"]
        for edge in reconstitutes
        if isinstance(edge.get("to"), dict) and edge["to"].get("id")
    }
    findings = single_source_risks(parts, reconstitutes_targets=targets)
    return {"findings": findings, "count": len(findings)}


@router.post("/surge", summary="Plan surge under supplier constraints")
async def surge(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    facility_id = body.get("facilityId")
    if not isinstance(facility_id, str) or not facility_id:
        raise ValidationError("'facilityId' is required")
    facility = _projector(request).entity("Facility", facility_id)
    if facility is None:
        raise NotFoundError(f"no Facility with id {facility_id!r}")

    suppliers = [
        {"id": entity["id"], **_attrs(entity)}
        for entity in _projector(request).entities(entity_type="Supplier", limit=5000)
    ]
    requested = body.get("supplierIds")
    if isinstance(requested, list) and requested:
        wanted = {str(item) for item in requested}
        suppliers = [supplier for supplier in suppliers if supplier["id"] in wanted]

    units = body.get("demandUnits")
    if not isinstance(units, int) or units <= 0:
        raise ValidationError("'demandUnits' must be a positive integer")
    return surge_plan(
        facility={**_attrs(facility), "id": facility_id},
        suppliers=suppliers,
        demand_units=units,
        horizon_days=int(body.get("horizonDays", 90)),
    )


@router.post("/reconstitution", summary="Generate a reconstitution playbook")
async def reconstitution(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    part_id = body.get("partId")
    if not isinstance(part_id, str) or not part_id:
        raise ValidationError("'partId' is required")
    part = _projector(request).entity("Part", part_id)
    if part is None:
        raise NotFoundError(f"no Part with id {part_id!r}")
    alternatives = body.get("alternatives")
    if not isinstance(alternatives, list):
        raise ValidationError("'alternatives' must be a list")
    return reconstitution_playbook({**_attrs(part), "id": part_id}, alternatives)


@router.post("/reconstitutes", summary="Record a reconstitution path", status_code=201)
async def link_reconstitution(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    from ngsh_core.publish import relation_document, relation_event

    from_ref = body.get("fromRef")
    to_ref = body.get("toRef")
    if not isinstance(from_ref, dict) or not isinstance(to_ref, dict):
        raise ValidationError("'fromRef' and 'toRef' must be {type, id} objects")
    settings: Settings = request.app.state.settings
    actor = actor_for(settings, request)
    document = relation_document(
        "reconstitutes",
        (str(from_ref["type"]), str(from_ref["id"])),
        (str(to_ref["type"]), str(to_ref["id"])),
        tenant=settings.tenant,
        asserted_by=actor.subjectId,
    )
    await publish(request, relation_event(document, actor, registry=request.app.state.registry))
    return JSONResponse(status_code=201, content={"relation": document})


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
            {"name": "supply", "description": "Pillar D: exposure, surge and reconstitution."},
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
