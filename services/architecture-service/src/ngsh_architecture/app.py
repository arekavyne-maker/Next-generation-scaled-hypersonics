"""NGSH architecture service: the Pillar A first slice.

Increment 1 delivers two Pillar A capabilities in their first, deliberately
narrow form:

* **A-1, the digital twin backbone**: a configuration baseline that pins every
  part revision and software build, content-addressed so that the same inputs
  produce the same baseline identifier; and an interface registry that refuses
  an interface whose characteristics are incomplete.
* **A-3, requirements-to-test traceability**: a requirement's verification
  status computed from its ``verifies`` evidence, with the hierarchy rolled up
  deterministically and every gap named.

The service reads graph facts from the thread projection and writes only the
baselines and interfaces it owns. It does not keep a second copy of the
digital thread, because a second copy is a second truth.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from ngsh_core.app import create_service
from ngsh_core.architecture import (
    create_baseline,
    interface_digest,
    rollup_tree,
    validate_interface,
    verify_baseline,
)
from ngsh_core.config import Settings, load_settings
from ngsh_core.errors import NotFoundError, ValidationError
from ngsh_core.graph import GraphProjector
from ngsh_core.ontology import OntologyLoader
from ngsh_core.store import open_database

from .repository import BaselineRepository, InterfaceRepository

SERVICE_NAME = "architecture"
DESCRIPTION = (
    "Pillar A first slice: content-addressed configuration baselines, the "
    "interface registry, and requirement-to-test traceability for the NGSH "
    "digital thread."
)

router = APIRouter(prefix="/v1", tags=["architecture"])


def _projector(request: Request) -> GraphProjector:
    return request.app.state.projector


def _repo(request: Request) -> BaselineRepository:
    return request.app.state.baselines


def _interfaces(request: Request) -> InterfaceRepository:
    return request.app.state.interfaces


# -- configuration baselines -------------------------------------------------


@router.post("/baselines", summary="Create or fetch a configuration baseline", status_code=201)
async def create(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Create a baseline, or return the existing one for identical content.

    The operation is idempotent because the identifier is derived from the
    content, not from a database sequence. Calling it twice with the same
    pinned members is not a duplicate, it is the same baseline.
    """
    settings: Settings = request.app.state.settings
    baseline = create_baseline(
        system_id=body.get("systemId"),
        name=body.get("name"),
        raw_members=body.get("members"),
        software_builds=body.get("softwareBuilds"),
        created_by=_subject(request),
        created_at=_now(),
        notes=body.get("notes"),
        registry=request.app.state.registry,
    )

    created = _repo(request).put(baseline, tenant=settings.tenant)
    status = 201 if created else 200
    return JSONResponse(status_code=status, content={"baseline": baseline.to_dict(), "created": created})


@router.get("/baselines", summary="List configuration baselines")
async def list_baselines(
    request: Request,
    systemId: str | None = Query(None, description="Filter by System id."),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    rows = _repo(request).list(system_id=systemId, limit=limit, offset=offset)
    return {"baselines": [row.to_dict() for row in rows], "count": len(rows)}


@router.get("/baselines/resolve/{test_article_id}", summary="Resolve a test article to its baseline")
async def resolve(request: Request, test_article_id: str) -> dict[str, Any]:
    """Resolve a ``TestArticle`` to the baseline it was built against.

    The article names its baseline through ``buildConfigurationId``. If the
    article names no baseline, or names one the service does not hold, that is
    reported as unresolved rather than guessed: a test article with an
    ambiguous configuration is not evidence.
    """
    projector = _projector(request)
    article = projector.entity("TestArticle", test_article_id)
    if article is None:
        raise NotFoundError(f"no TestArticle with id {test_article_id!r}")

    baseline_id = (article.get("attributes") or {}).get("buildConfigurationId")
    if not isinstance(baseline_id, str) or not baseline_id:
        return {
            "testArticleId": test_article_id,
            "baselineId": None,
            "resolved": False,
            "reason": "the test article does not name a build configuration",
        }

    baseline = _repo(request).get(baseline_id)
    if baseline is None:
        return {
            "testArticleId": test_article_id,
            "baselineId": baseline_id,
            "resolved": False,
            "reason": "the named baseline is not registered with this service",
        }
    return {
        "testArticleId": test_article_id,
        "baselineId": baseline_id,
        "resolved": True,
        "baseline": baseline.to_dict(),
    }


@router.get("/baselines/{baseline_id}", summary="Fetch one baseline")
async def get_baseline(request: Request, baseline_id: str) -> dict[str, Any]:
    baseline = _repo(request).get(baseline_id)
    if baseline is None:
        raise NotFoundError(f"no baseline with id {baseline_id!r}")
    return {"baseline": baseline.to_dict()}


@router.post("/baselines/{baseline_id}/verify", summary="Prove a baseline is reproducible")
async def verify(request: Request, baseline_id: str) -> dict[str, Any]:
    """Recompute the baseline identity from its stored content."""
    baseline = _repo(request).get(baseline_id)
    if baseline is None:
        raise NotFoundError(f"no baseline with id {baseline_id!r}")
    return verify_baseline(baseline)


# -- interfaces --------------------------------------------------------------


@router.post("/interfaces", summary="Register an interface definition", status_code=201)
async def register_interface(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    """Validate and register an interface's characteristics.

    The ``Interface`` entity itself is written through the normal ontology
    path. What this endpoint adds is the guarantee that the characteristics a
    baseline pins are complete: rate, latency, timing model and envelope.
    """
    characteristics = validate_interface(
        from_system_id=body.get("fromSystemId"),
        to_system_id=body.get("toSystemId"),
        characteristics=body.get("characteristics"),
    )
    digest = interface_digest(
        from_system_id=body["fromSystemId"],
        to_system_id=body["toSystemId"],
        characteristics=characteristics,
    )
    record = {
        "interfaceId": body.get("interfaceId"),
        "fromSystemId": body["fromSystemId"],
        "toSystemId": body["toSystemId"],
        "characteristics": characteristics,
        "digest": digest,
    }
    created = _interfaces(request).put(
        record, created_by=_subject(request), created_at=_now(), tenant=request.app.state.settings.tenant
    )
    return JSONResponse(
        status_code=201 if created else 200, content={"interface": record, "created": created}
    )


@router.get("/interfaces", summary="List registered interfaces")
async def list_interfaces(
    request: Request,
    fromSystemId: str | None = Query(None),
    toSystemId: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    rows = _interfaces(request).list(from_system_id=fromSystemId, to_system_id=toSystemId, limit=limit)
    return {"interfaces": rows, "count": len(rows)}


# -- requirements and traceability ------------------------------------------


@router.get("/requirements/{requirement_id}/coverage", summary="Verification coverage for one requirement")
async def coverage(request: Request, requirement_id: str) -> dict[str, Any]:
    projector = _projector(request)
    if projector.entity("Requirement", requirement_id) is None:
        raise NotFoundError(f"no Requirement with id {requirement_id!r}")
    return projector.requirement_coverage(requirement_id)


@router.post("/requirements/rollup", summary="Roll verification status up a requirement tree")
async def rollup(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Compute the rollup for a set of requirements.

    Accepts either an explicit ``requirementIds`` list or a ``root`` from
    which the subtree is discovered. Statuses are derived from evidence, never
    read from the stored ``verificationStatus`` attribute, because a stored
    status is an assertion and the rollup is supposed to be a computation.
    """
    projector = _projector(request)
    ids = _requirement_ids(projector, body)

    coverage_by_id: dict[str, dict[str, Any]] = {}
    parents: dict[str, str | None] = {}
    for requirement_id in ids:
        entity = projector.entity("Requirement", requirement_id)
        if entity is None:
            continue
        parents[requirement_id] = (entity.get("attributes") or {}).get("parentId")
        coverage_by_id[requirement_id] = projector.requirement_coverage(requirement_id)

    report = rollup_tree(coverage_by_id, parents)
    report["requirements"] = [coverage_by_id[requirement_id] for requirement_id in sorted(coverage_by_id)]
    report["missing"] = sorted(set(ids) - set(parents))
    return report


@router.get("/requirements/gaps", summary="Requirements with an open gap or review item")
async def gaps(
    request: Request,
    limit: int = Query(200, ge=1, le=2000),
) -> dict[str, Any]:
    projector = _projector(request)
    open_items: list[dict[str, Any]] = []
    for entity in projector.entities(entity_type="Requirement", limit=limit):
        report = projector.requirement_coverage(entity["id"])
        if report["gaps"] or report["reviewItems"]:
            open_items.append(report)
    return {"requirements": open_items, "count": len(open_items)}


def _requirement_ids(projector: GraphProjector, body: dict[str, Any]) -> list[str]:
    explicit = body.get("requirementIds")
    if explicit is not None:
        if not isinstance(explicit, list) or not all(isinstance(item, str) for item in explicit):
            raise ValidationError("'requirementIds' must be a list of requirement ids")
        return sorted(set(explicit))

    root = body.get("root")
    if not isinstance(root, str) or not root:
        raise ValidationError("supply either 'requirementIds' or a 'root' requirement id")

    root_id = root if root.startswith("REQ:") else f"REQ:{root}"
    found = {root_id}
    for entity in projector.entities(entity_type="Requirement", limit=2000):
        parent = (entity.get("attributes") or {}).get("parentId")
        if parent == root_id or parent in found:
            found.add(entity["id"])
    # parents are discovered depth-first from the store, so a deeper chain is
    # closed by one pass; an orphan simply does not appear under this root.
    changed = True
    while changed:
        changed = False
        for entity in projector.entities(entity_type="Requirement", limit=2000):
            parent = (entity.get("attributes") or {}).get("parentId")
            if parent in found and entity["id"] not in found:
                found.add(entity["id"])
                changed = True
    return sorted(found)


def _subject(request: Request) -> str:
    identity = getattr(request.state, "identity", None)
    subject = getattr(identity, "subjectId", None)
    return subject or request.headers.get("X-NGSH-Subject") or "svc:architecture"


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


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
            {"name": "architecture", "description": "Pillar A: baselines, interfaces and traceability."},
            {"name": "operations", "description": "Health and metadata."},
        ],
    )
    app.state.executor = executor
    app.state.registry = registry
    app.state.projector = GraphProjector(executor)
    app.state.baselines = BaselineRepository(executor)
    app.state.interfaces = InterfaceRepository(executor)
    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
