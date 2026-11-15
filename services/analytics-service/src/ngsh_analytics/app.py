"""NGSH analytics service: the PSDD section 12 measures of vitality.

The service exists so that a programme figure is never a slide. It reads the
digital thread, computes each KPI from named evidence, and reports an
unavailable figure as ``NOT_COMPUTED`` with its reason rather than as zero.

One rule is enforced here rather than left to a caller: the classification
demand used for the workforce gap is an input, because classified production
demand is not derivable from the thread. Omit it and the KPI is reported as
not computed, with the missing input named.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, FastAPI, Query, Request
from ngsh_core.analytics import programme_kpis
from ngsh_core.app import create_service
from ngsh_core.config import Settings, load_settings
from ngsh_core.errors import NotFoundError, ValidationError
from ngsh_core.graph import GraphProjector
from ngsh_core.store import open_database

SERVICE_NAME = "analytics"
DESCRIPTION = (
    "Programme KPIs computed from the digital thread: kill-chain compression, "
    "virtual-to-physical ratio, surge, reconstitution, workforce gap and "
    "development speed."
)

router = APIRouter(prefix="/v1", tags=["analytics"])

#: The entity types each KPI family is computed from. Keeping the list explicit
#: means a missing projection is visible here rather than as a silent zero.
KPI_INPUTS: dict[str, tuple[str, ...]] = {
    "scenarios": ("EngagementScenario",),
    "test_results": ("TestResult",),
    "campaigns": ("TestCampaign",),
    "models": ("Model",),
    "persons": ("Person",),
    "credentials": ("Credential",),
    "skills": ("Skill",),
}


def _projector(request: Request) -> GraphProjector:
    return request.app.state.projector


def _rows(request: Request, key: str) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for entity_type in KPI_INPUTS[key]:
        entities.extend(
            _projector(request).entities(entity_type=entity_type, limit=10_000)
        )
    return entities


def _report(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    as_of = body.get("asOf") or datetime.now(UTC).isoformat()
    demand = body.get("workforceDemand")
    if demand is not None and not isinstance(demand, list):
        raise ValidationError("'workforceDemand' must be a list of demand rows")
    return programme_kpis(
        as_of=str(as_of),
        scenarios=_rows(request, "scenarios"),
        test_results=_rows(request, "test_results"),
        campaigns=_rows(request, "campaigns"),
        models=_rows(request, "models"),
        persons=_rows(request, "persons"),
        credentials=_rows(request, "credentials"),
        skills=_rows(request, "skills"),
        reconstitutions=body.get("reconstitutions") or [],
        surge_reports=body.get("surgeReports") or [],
        workforce_demand=demand,
    )


@router.post("/kpis", summary="Compute the programme KPIs from the thread")
async def kpis(request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Every KPI the thread can support, with evidence or a named reason."""
    return _report(request, body)


@router.get("/kpis", summary="Compute the programme KPIs as of now")
async def kpis_get(
    request: Request,
    asOf: str | None = Query(None, description="ISO-8601 instant; defaults to now."),
) -> dict[str, Any]:
    return _report(request, {"asOf": asOf} if asOf else {})


@router.get("/kpis/definitions", summary="The KPI catalogue")
async def definitions() -> dict[str, Any]:
    """The six PSDD section 12 outcomes and the metrics that measure them."""
    rows = [
        {
            "outcome": "Compress counter-hypersonic kill chain",
            "kpiId": "kill-chain-latency",
            "metric": "Simulated time detection to custody per architecture",
        },
        {
            "outcome": "Stretch defense dollars",
            "kpiId": "virtual-to-physical",
            "metric": "Virtual engagements per flight test consumed",
        },
        {
            "outcome": "Deter by capacity",
            "kpiId": "surge-readiness",
            "metric": "Verified surge production rate",
        },
        {
            "outcome": "Sustain under attack",
            "kpiId": "time-to-reconstitute",
            "metric": "Measured time to reconstitute a critical node",
        },
        {
            "outcome": "Workforce guarantee",
            "kpiId": "workforce-gap",
            "metric": "Cleared-skills supply versus classified demand",
        },
        {
            "outcome": "Development speed",
            "kpiId": "design-iterate-cycles",
            "metric": "Design-iterate cycles per flight test",
        },
        {
            "outcome": "Development speed",
            "kpiId": "model-fidelity-improvement",
            "metric": "Model fidelity improvement per campaign",
        },
    ]
    return {"definitions": rows, "count": len(rows)}


@router.get("/kpis/{kpi_id}", summary="Fetch one KPI")
async def kpi(request: Request, kpi_id: str, asOf: str | None = Query(None)) -> dict[str, Any]:
    report = _report(request, {"asOf": asOf} if asOf else {})
    for row in report["kpis"]:
        if row["id"] == kpi_id:
            return {"asOf": report["asOf"], "kpi": row}
    raise NotFoundError(f"no KPI with id {kpi_id!r}")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()
    executor = open_database(resolved.dsn)

    app = create_service(
        SERVICE_NAME,
        settings=resolved,
        description=DESCRIPTION,
        routers=[router],
        tags=[
            {"name": "analytics", "description": "Programme KPIs computed from the thread."},
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
