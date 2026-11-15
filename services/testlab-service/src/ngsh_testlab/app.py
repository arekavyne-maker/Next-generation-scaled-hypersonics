"""NGSH test-lab service (Pillar C).

Increment 2's test capabilities: campaign planning with range-slot conflict
detection, admission of test results only when they carry configuration
context, anomaly surfacing within the ingest path, and the twin validation
loop that turns a result into a model fidelity change with a causation chain.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from ngsh_core.app import create_service
from ngsh_core.config import Settings, load_settings
from ngsh_core.envelope import EventEnvelope
from ngsh_core.errors import NotFoundError, ValidationError
from ngsh_core.graph import GraphProjector
from ngsh_core.ids import new_ulid
from ngsh_core.ontology import OntologyLoader
from ngsh_core.publish import (
    actor_for,
    entity_document,
    entity_event,
    next_sequence,
    publish,
    relation_document,
    relation_event,
)
from ngsh_core.store import open_database
from ngsh_core.testlab import (
    curate_campaign,
    find_slot_conflicts,
    surface_anomalies,
    twin_validation,
    validate_result,
)

SERVICE_NAME = "testlab"
DESCRIPTION = (
    "Pillar C: test campaign planning, configuration-gated result admission, "
    "anomaly surfacing and the flight-to-simulation validation loop."
)

router = APIRouter(prefix="/v1", tags=["testlab"])


def _projector(request: Request) -> GraphProjector:
    return request.app.state.projector


def _attrs(entity: dict[str, Any] | None) -> dict[str, Any]:
    return (entity or {}).get("attributes") or {}


def _require(request: Request, entity_type: str, entity_id: str) -> dict[str, Any]:
    entity = _projector(request).entity(entity_type, entity_id)
    if entity is None:
        raise NotFoundError(f"no {entity_type} with id {entity_id!r}")
    return entity


@router.post("/test-results", summary="Admit a test result", status_code=201)
async def record_result(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    """Admit a result only if it names its configuration.

    Anomalies are surfaced as flags on the result; they never change the
    result's own outcome, because disposition is a human decision.
    """
    errors = validate_result(body)
    if errors:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "constraint_violation",
                    "message": "the test result cannot be admitted without configuration context",
                    "context": {"reasons": errors},
                }
            },
        )

    campaign_id = body.get("campaignId")
    reference_results: list[dict[str, Any]] = []
    if campaign_id:
        reference_results = [
            _attrs(result)
            for result in _projector(request).entities(entity_type="TestResult", limit=5000)
            if _attrs(result).get("campaignId") == campaign_id
        ]

    anomaly_report = surface_anomalies(body, reference_results=reference_results)
    result_id = f"TR:{new_ulid()}"
    attributes = {
        "campaignId": campaign_id,
        "testArticleId": body.get("testArticleId"),
        "testMethod": body["testMethod"],
        "outcome": body["outcome"],
        "measurements": body.get("measurements") or [],
        "limits": body.get("limits") or {},
        "configurationSnapshot": body["configurationSnapshot"],
        "dataSetUris": body.get("dataSetUris") or [],
        "modelVersionIds": body.get("modelVersionIds") or [],
        "baselineId": body.get("baselineId") or body["configurationSnapshot"].get("baselineId"),
        "anomalyFlags": [item["kind"] for item in anomaly_report["anomalies"]],
        "reviewedBy": body.get("reviewedBy"),
    }

    settings: Settings = request.app.state.settings
    actor = actor_for(settings, request)
    document = entity_document(
        "TestResult",
        result_id,
        {key: value for key, value in attributes.items() if value is not None},
        tenant=settings.tenant,
        program=settings.program,
        created_by=actor.subjectId,
        provenance={"source": "testlab-service", "method": "test-admission"},
    )
    event = EventEnvelope(
        eventType="test.result.recorded",
        aggregateType="TestResult",
        aggregateId=result_id,
        sequence=1,
        tenant=settings.tenant,
        program=settings.program,
        actor=actor,
        payload={"testResult": document, "reductionPipeline": body.get("reductionPipeline")},
    )

    events = [event]
    for requirement_id in body.get("requirementIds") or []:
        relation = relation_document(
            "verifies",
            ("TestResult", result_id),
            ("Requirement", str(requirement_id)),
            tenant=settings.tenant,
            asserted_by=actor.subjectId,
        )
        events.append(relation_event(relation, actor, registry=request.app.state.registry))

    # The result is published before its relations: a verification edge whose
    # source does not yet exist is a dangling projection, and the log order is
    # what the projector replays.
    await publish(request, *events)
    return JSONResponse(
        status_code=201,
        content={"testResult": document, "anomalies": anomaly_report["anomalies"]},
    )


@router.get("/test-results", summary="List admitted test results")
async def list_results(
    request: Request,
    campaignId: str | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
) -> dict[str, Any]:
    results = _projector(request).entities(entity_type="TestResult", limit=limit)
    if campaignId:
        results = [result for result in results if _attrs(result).get("campaignId") == campaignId]
    return {"testResults": results, "count": len(results)}


@router.post("/campaigns", summary="Plan a test campaign against range capacity", status_code=201)
async def plan_campaign(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    name = body.get("name")
    if not isinstance(name, str) or not name:
        raise ValidationError("'name' is required")
    if body.get("campaignType") is None:
        raise ValidationError("'campaignType' is required")

    slot = body.get("slot")
    if isinstance(slot, dict):
        existing = [
            {**_attrs(entity), "id": entity["id"]}
            for entity in _projector(request).entities(entity_type="RangeSlot", limit=5000)
        ]
        conflicts = find_slot_conflicts(slot, existing)
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

    campaign_id = f"TC:{new_ulid()}"
    settings: Settings = request.app.state.settings
    actor = actor_for(settings, request)
    attributes = {
        "name": name,
        "campaignType": body["campaignType"],
        "status": body.get("status") or "PLANNED",
        "objectives": body.get("objectives") or [],
        "requirementIds": body.get("requirementIds") or [],
        "testArticleIds": body.get("testArticleIds") or [],
        "startDate": body.get("startDate"),
        "endDate": body.get("endDate"),
    }
    document = entity_document(
        "TestCampaign",
        campaign_id,
        {key: value for key, value in attributes.items() if value is not None},
        tenant=settings.tenant,
        program=settings.program,
        created_by=actor.subjectId,
    )
    events: list[EventEnvelope] = [
        EventEnvelope(
            eventType="test.campaign.planned",
            aggregateType="TestCampaign",
            aggregateId=campaign_id,
            sequence=1,
            tenant=settings.tenant,
            program=settings.program,
            actor=actor,
            payload={"campaign": document, "capacityModel": body.get("capacityModel")},
        )
    ]

    if isinstance(slot, dict):
        slot_id = f"RS:{new_ulid()}"
        slot_document = entity_document(
            "RangeSlot",
            slot_id,
            {
                "facilityId": slot.get("facilityId") or body.get("facilityId"),
                "start": slot.get("start"),
                "end": slot.get("end"),
                "campaignId": campaign_id,
                "instrumentation": slot.get("instrumentation") or [],
                "telemetryCoverage": slot.get("telemetryCoverage") or {},
                "status": "CONFIRMED",
            },
            tenant=settings.tenant,
            program=settings.program,
            created_by=actor.subjectId,
        )
        events.append(entity_event(slot_document, actor, registry=request.app.state.registry))

    await publish(request, *events)
    return JSONResponse(status_code=201, content={"campaign": document, "slot": events[-1].payload.get("entity") if slot else None})


@router.get("/campaigns/{campaign_id}/curation", summary="Curate a campaign into a reusable dataset")
async def curation(request: Request, campaign_id: str) -> dict[str, Any]:
    campaign = _attrs(_require(request, "TestCampaign", campaign_id))
    results = [
        _attrs(result)
        for result in _projector(request).entities(entity_type="TestResult", limit=5000)
        if _attrs(result).get("campaignId") == campaign_id
    ]
    return curate_campaign({"id": campaign_id, **campaign}, results)


@router.post("/twin-validation", summary="Validate a model from a test result")
async def validate_model(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    result_id = body.get("testResultId")
    model_id = body.get("modelId")
    if not isinstance(result_id, str) or not isinstance(model_id, str):
        raise ValidationError("'testResultId' and 'modelId' are required")

    result = _require(request, "TestResult", result_id)
    model_entity = _require(request, "Model", model_id)
    validation = twin_validation(
        {**_attrs(result), "id": result_id}, {**_attrs(model_entity), "id": model_id}
    )

    settings: Settings = request.app.state.settings
    actor = actor_for(settings, request)
    base_sequence = next_sequence(request.app.state.executor, model_id)
    documents = [
        EventEnvelope(
            eventType="model.validated",
            aggregateType="Model",
            aggregateId=model_id,
            sequence=base_sequence,
            tenant=settings.tenant,
            program=settings.program,
            actor=actor,
            payload={
                "modelId": model_id,
                "modelVersion": validation["modelVersion"],
                "fidelity": validation["fidelity"],
                "priorFidelity": validation["priorFidelity"],
                "evidenceTestResultIds": validation["evidenceTestResultIds"],
                "approvedBy": body.get("approvedBy"),
            },
        )
    ]

    fidelity = _attrs(model_entity).get("fidelity") or {}
    updated_attributes = {
        **_attrs(model_entity),
        "fidelity": {**fidelity, "overall": validation["fidelity"]},
    }
    updated = entity_document(
        "Model",
        model_id,
        updated_attributes,
        tenant=settings.tenant,
        program=settings.program,
        created_by=model_entity.get("createdBy") or actor.subjectId,
        version=int(model_entity.get("version") or 1) + 1,
        provenance={"source": "testlab-service", "method": "twin-validation"},
    )
    documents.append(
        entity_event(
            updated,
            actor,
            event_type="entity.updated",
            sequence=base_sequence + 1,
            registry=request.app.state.registry,
            causation_id=documents[0].eventId,
        )
    )

    relation = relation_document(
        "derivedFrom",
        ("TestResult", result_id),
        ("Model", model_id),
        tenant=settings.tenant,
        asserted_by=actor.subjectId,
    )
    documents.append(relation_event(relation, actor, registry=request.app.state.registry))

    await publish(request, *documents)
    return validation


@router.post("/range-slots", summary="Book a range slot", status_code=201)
async def book_slot(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    existing = [
        {**_attrs(entity), "id": entity["id"]}
        for entity in _projector(request).entities(entity_type="RangeSlot", limit=5000)
    ]
    conflicts = find_slot_conflicts(body, existing)
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
            "status": body.get("status") or "CONFIRMED",
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
            {"name": "testlab", "description": "Pillar C: campaigns, results, anomalies, twin loop."},
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
