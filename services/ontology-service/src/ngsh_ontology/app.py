"""NGSH ontology service.

Serves the shared ontology and acts as the gate every write passes through.
The contract files under ``contracts/`` are the source of truth; this service
loads them, validates against them and enforces the registry invariants
(C-001 .. C-008).

Nothing else in the platform is allowed to invent an entity shape. A pillar
that wants a new attribute on ``TestResult`` proposes a change to the
contract, the ontology service picks it up on reload, and every service
regenerates its codecs from the same artefact.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, FastAPI, Query, Request
from ngsh_core.app import create_service
from ngsh_core.config import Settings, load_settings
from ngsh_core.envelope import Entity, Relation
from ngsh_core.errors import NotFoundError, OntologyError, ValidationError
from ngsh_core.ontology import OntologyLoader, OntologyRegistry

SERVICE_NAME = "ontology"
DESCRIPTION = (
    "The NGSH shared ontology: 23 entity types, 10 relation types and the "
    "cross-entity invariants that make them a model rather than a list of tables."
)

router = APIRouter(prefix="/v1", tags=["ontology"])


def _registry(request: Request) -> OntologyRegistry:
    return request.app.state.registry


@router.get("/ontology/registry", summary="Full ontology registry")
async def registry(request: Request) -> dict[str, Any]:
    return _registry(request).to_dict()


@router.get("/ontology/types", summary="List entity types")
async def list_types(
    request: Request,
    pillar: str | None = Query(None, description="Filter by owning pillar, e.g. 'B' or 'FOUNDATION'."),
) -> dict[str, Any]:
    reg = _registry(request)
    specs = reg.entities.values()
    if pillar:
        specs = [spec for spec in specs if pillar in spec.pillars]
    return {
        "ontologyVersion": reg.version,
        "types": [
            {
                "type": spec.type,
                "idPrefix": spec.idPrefix,
                "description": spec.description,
                "pillars": list(spec.pillars),
                "classificationFloor": spec.classificationFloor,
                "pii": spec.pii,
            }
            for spec in sorted(specs, key=lambda s: s.type)
        ],
    }


@router.get("/ontology/types/{entity_type}", summary="Schema for one entity type")
async def get_type(request: Request, entity_type: str) -> dict[str, Any]:
    reg = _registry(request)
    spec = reg.entity_type(entity_type)
    if spec is None:
        raise NotFoundError(f"unknown entity type {entity_type!r}")
    schema = _attribute_schema(request.app.state.settings, entity_type)
    return {
        "type": spec.type,
        "idPrefix": spec.idPrefix,
        "description": spec.description,
        "pillars": list(spec.pillars),
        "classificationFloor": spec.classificationFloor,
        "pii": spec.pii,
        "schema": schema,
    }


@router.get("/ontology/relations", summary="List relation types")
async def list_relations(request: Request) -> dict[str, Any]:
    reg = _registry(request)
    return {
        "relations": [
            {
                "type": spec.type,
                "fromTypes": list(spec.fromTypes),
                "toTypes": list(spec.toTypes),
                "cardinality": spec.cardinality,
                "description": spec.description,
                "mayCrossClassification": spec.mayCrossClassification,
                "requiresProvenance": spec.requiresProvenance,
                "supportsRollup": spec.supportsRollup,
            }
            for spec in sorted(reg.relations.values(), key=lambda s: s.type)
        ]
    }


@router.get("/ontology/constraints", summary="Cross-entity invariants")
async def list_constraints(request: Request) -> dict[str, Any]:
    return {"constraints": _registry(request).constraints}


@router.post("/ontology/validate", summary="Validate an entity or a relation")
async def validate(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    reg = _registry(request)
    kind = (body.get("kind") or "entity").lower()

    if kind == "entity":
        entity = _coerce_entity(body.get("entity") or body)
        errors = reg.validate_entity(entity)
        return {"valid": not errors, "kind": "entity", "errors": errors}

    if kind == "relation":
        relation = _coerce_relation(body.get("relation") or body)
        errors = reg.validate_relation(
            relation,
            from_classification=body.get("fromClassification"),
            to_classification=body.get("toClassification"),
        )
        return {"valid": not errors, "kind": "relation", "errors": errors}

    raise ValidationError(f"unknown validation kind {kind!r}; expected 'entity' or 'relation'")


@router.get("/events/catalog", summary="Event type catalog")
async def event_catalog(request: Request) -> dict[str, Any]:
    path = request.app.state.settings.contracts_dir / "events" / "catalog.json"
    if not path.exists():
        raise OntologyError("event catalog is unavailable")
    return json.loads(path.read_text(encoding="utf-8"))


@router.post("/ontology/reload", summary="Reload the contract layer")
async def reload_contracts(request: Request) -> dict[str, Any]:
    """Re-read the contract files.

    Governance changes to the ontology are applied by editing the contract
    files and reloading, which means an ontology change is a reviewed
    artefact rather than a coordinated deployment across every service.
    """
    loader: OntologyLoader = request.app.state.loader
    reg = loader.reload()
    request.app.state.registry = reg
    return {
        "ontologyVersion": reg.version,
        "entities": len(reg.entities),
        "relations": len(reg.relations),
        "constraints": len(reg.constraints),
    }


def _attribute_schema(settings: Settings, entity_type: str) -> dict[str, Any]:
    path = settings.contracts_dir / "ontology" / "entities.schema.json"
    if not path.exists():
        return {}
    document = json.loads(path.read_text(encoding="utf-8"))
    definitions = document.get("$defs", {})
    key = f"{entity_type}Attributes"
    return definitions.get(key, {})


def _coerce_entity(raw: dict[str, Any]) -> Entity:
    try:
        return Entity.model_validate(raw)
    except Exception as exc:
        raise ValidationError("entity does not match the entity envelope", detail=str(exc)) from exc


def _coerce_relation(raw: dict[str, Any]) -> Relation:
    try:
        return Relation.model_validate(raw)
    except Exception as exc:
        raise ValidationError("relation does not match the relation envelope", detail=str(exc)) from exc


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()
    loader = OntologyLoader(resolved.contracts_dir)
    registry = loader.load()

    app = create_service(
        SERVICE_NAME,
        settings=resolved,
        description=DESCRIPTION,
        routers=[router],
        tags=[
            {"name": "ontology", "description": "Ontology registry, schemas and validation."},
            {"name": "operations", "description": "Health and metadata."},
        ],
    )
    app.state.loader = loader
    app.state.registry = registry
    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
