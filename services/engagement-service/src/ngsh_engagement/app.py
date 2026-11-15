"""NGSH engagement service (Pillars F and G).

Increment 4's kill-chain and virtual-range capabilities: threat systems and
observations, engagement scenarios that name their sensor and effector chains,
a deterministic Monte Carlo batch with a measured throughput, a kill-chain
report that names missing stages, and range bookings that refuse to overlap.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from ngsh_core.app import create_service
from ngsh_core.config import Settings, load_settings
from ngsh_core.engagement import (
    co_simulation,
    compose_interim_candidate,
    fire_control_quality,
    kill_chain,
    load_plugin,
    run_batch,
    run_plugin,
    slot_conflicts,
    unload_plugin,
)
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


def _measurements(rows: Any) -> dict[str, float]:
    """Index an ontology ``Measurement`` array by name.

    A measurement is the contract's way of carrying a named quantity; a metric
    reader must not guess which arbitrary attribute a service happened to use.
    Non-numeric values are ignored rather than coerced.
    """
    indexed: dict[str, float] = {}
    if not isinstance(rows, list):
        return indexed
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        value = row.get("value")
        if isinstance(name, str) and isinstance(value, int | float) and not isinstance(value, bool):
            indexed[name] = float(value)
    return indexed


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
    """Run a batch and record its run count, seed and confidence on the scenario.

    F-2 requires the study's parameters to live on the ``EngagementScenario``,
    not only in the response, so the batch is followed by an
    ``entity.updated`` event carrying ``resultsSummary``.
    """
    entity = _require(request, "EngagementScenario", scenario_id)
    scenario = _attrs(entity)
    runs = body.get("runs", 10_000)
    if not isinstance(runs, int) or runs <= 0:
        raise ValidationError("'runs' must be a positive integer")
    seed = int(body.get("seed", 1234))
    report = run_batch(
        {"id": scenario_id, **scenario},
        runs=runs,
        seed=seed,
        pk_threshold=float(body.get("pkThreshold", 0.7)),
    )

    settings: Settings = request.app.state.settings
    actor = actor_for(settings, request)
    summary = {
        "runs": runs,
        "seed": seed,
        "pkThreshold": report["pkThreshold"],
        "confidenceLevel": float(body.get("confidenceLevel", 0.95)),
        "statistics": report["statistics"],
        "elapsedSeconds": report["elapsedSeconds"],
        "completedAt": datetime.now(UTC).isoformat(),
    }
    document = entity_document(
        "EngagementScenario",
        scenario_id,
        {**scenario, "resultsSummary": summary},
        tenant=settings.tenant,
        program=settings.program,
        created_by=entity.get("createdBy") or actor.subjectId,
        version=int(entity.get("version") or 1) + 1,
        provenance={"source": "engagement-service", "method": "engagement-batch"},
    )
    await publish(
        request,
        entity_event(
            document,
            actor,
            event_type="entity.updated",
            sequence=next_sequence(request.app.state.executor, scenario_id),
            registry=request.app.state.registry,
        ),
    )
    report["recorded"] = True
    report["resultsSummary"] = summary
    return report


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


# -- F-3: fire-control data quality -----------------------------------------


@router.post("/fire-control/quality", summary="Score fire-control data quality")
async def fire_control(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Measure custody handover quality, track purity and solution error."""
    return fire_control_quality(
        handovers=body.get("handovers") or [],
        tracks=body.get("tracks") or [],
        solutions=body.get("solutions") or [],
        thresholds=body.get("thresholds"),
    )


@router.post("/fire-control/measure", summary="Score quality from threat observations")
async def fire_control_from_observations(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Derive the three metrics from received threat observations.

    Observations are the IF-3 feed's landing point in the thread. A caller names
    the observations and this endpoint reads their measurements, so the metric
    is tied to the platform's evidence rather than to a private copy.
    """
    observation_ids = body.get("observationIds")
    if not isinstance(observation_ids, list) or not observation_ids:
        raise ValidationError("'observationIds' must be a non-empty list")
    projector = _projector(request)
    observations = {
        entity["id"]: _attrs(entity)
        for entity in projector.entities(entity_type="ThreatObservation", limit=5000)
    }
    missing = [item for item in observation_ids if item not in observations]
    if missing:
        raise NotFoundError(f"no ThreatObservation with id {missing[0]!r}")

    handovers: list[dict[str, Any]] = []
    tracks: list[dict[str, Any]] = []
    solutions: list[dict[str, Any]] = []
    for observation_id in observation_ids:
        attributes = observations[observation_id]
        # The ontology's ``trackQuality`` is a number; the detailed quantities
        # that make a fire-control chain assessable arrive as named
        # measurements. Read both, so a metric is never invented from a field
        # that the contract does not carry.
        measured = _measurements(attributes.get("measurements"))
        quality = attributes.get("trackQuality")
        confidence = quality if isinstance(quality, int | float) else None

        false_track = measured.get("falseTrack")
        tracks.append(
            {
                "trackId": observation_id,
                "falseTrack": bool(false_track) if false_track is not None else False,
                "confidence": confidence,
            }
        )

        latency = measured.get("handoverLatencyMs")
        if isinstance(latency, int | float):
            custody = measured.get("custodyContinuous")
            handovers.append(
                {
                    "handoverId": f"{observation_id}:handover",
                    "latencyMs": latency,
                    "continuous": bool(custody) if custody is not None else True,
                }
            )

        error = measured.get("solutionErrorM")
        if isinstance(error, int | float):
            solutions.append(
                {"solutionId": f"{observation_id}:solution", "errorM": error}
            )

    return {
        "observationIds": sorted(str(item) for item in observation_ids),
        **fire_control_quality(
            handovers=handovers,
            tracks=tracks,
            solutions=solutions,
            thresholds=body.get("thresholds"),
        ),
    }


# -- F-4: interim architecture workbench ------------------------------------


@router.post("/candidates/evaluate", summary="Compose and virtually evaluate an interim candidate", status_code=201)
async def evaluate_candidate(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    """Compose a candidate, validate its models, run it and store the scenario.

    The candidate's sensor and effector chains are stored as
    ``EngagementScenario`` attributes, and its evaluation records the models it
    used. An out-of-envelope model stops the composition before a scenario is
    written.
    """
    model_ids = body.get("modelIds")
    if not isinstance(model_ids, list) or not model_ids:
        raise ValidationError("'modelIds' must be a non-empty list")
    models = []
    for model_id in model_ids:
        entity = _require(request, "Model", str(model_id))
        models.append({"id": entity["id"], **_attrs(entity)})

    threat_ids = [str(item) for item in body.get("threatSystemIds") or []]
    for threat_id in threat_ids:
        _require(request, "ThreatSystem", threat_id)

    candidate = compose_interim_candidate(
        name=body.get("name"),
        sensors=body.get("sensors"),
        cueing=body.get("cueing") or [],
        effectors=body.get("effectors"),
        models=models,
        envelope=body.get("envelope") or {},
        threat_system_ids=threat_ids,
    )

    scenario_id = f"ESC:{new_ulid()}"
    settings: Settings = request.app.state.settings
    actor = actor_for(settings, request)
    attributes = {
        "name": candidate["name"],
        "threatSystemIds": candidate["threatSystemIds"],
        "sensorChain": candidate["sensorChain"],
        "effectorChain": candidate["effectorChain"],
        "cueingChain": candidate["cueingChain"],
        "modelVersionIds": candidate["modelVersionIds"],
        "envelope": candidate["envelope"],
        "monteCarloConfig": body.get("monteCarloConfig") or {},
        "resultsSummary": {},
    }
    document = entity_document(
        "EngagementScenario",
        scenario_id,
        attributes,
        tenant=settings.tenant,
        program=settings.program,
        created_by=actor.subjectId,
        provenance={"source": "engagement-service", "method": "interim-candidate"},
    )
    events = [entity_event(document, actor, registry=request.app.state.registry)]
    for threat_id in candidate["threatSystemIds"]:
        relation = relation_document(
            "engages",
            ("EngagementScenario", scenario_id),
            ("ThreatSystem", threat_id),
            tenant=settings.tenant,
            asserted_by=actor.subjectId,
        )
        events.append(relation_event(relation, actor, registry=request.app.state.registry))
    await publish(request, *events)

    runs = body.get("runs", 2_000)
    seed = int(body.get("seed", 1234))
    evaluation = run_batch(
        {"id": scenario_id, **attributes},
        runs=runs,
        seed=seed,
        pk_threshold=float(body.get("pkThreshold", 0.7)),
    )
    summary = _summary(report=evaluation, runs=runs, seed=seed, body=body)
    await _record_summary(request, scenario_id, document, summary)
    return JSONResponse(
        status_code=201,
        content={
            "candidate": candidate,
            "scenario": {**document, "attributes": {**attributes, "resultsSummary": summary}},
            "evaluation": {**evaluation, "modelsUsed": candidate["virtualValidation"]["modelsUsed"]},
        },
    )


def _summary(
    *,
    report: dict[str, Any],
    runs: int,
    seed: int,
    body: dict[str, Any],
) -> dict[str, Any]:
    return {
        "runs": runs,
        "seed": seed,
        "pkThreshold": report["pkThreshold"],
        "confidenceLevel": float(body.get("confidenceLevel", 0.95)),
        "statistics": report["statistics"],
        "elapsedSeconds": report["elapsedSeconds"],
        "completedAt": datetime.now(UTC).isoformat(),
    }


async def _record_summary(
    request: Request,
    scenario_id: str,
    entity: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    actor = actor_for(settings, request)
    attributes = {**_attrs(entity), "resultsSummary": summary}
    document = entity_document(
        "EngagementScenario",
        scenario_id,
        attributes,
        tenant=settings.tenant,
        program=settings.program,
        created_by=entity.get("createdBy") or actor.subjectId,
        version=int(entity.get("version") or 1) + 1,
        provenance={"source": "engagement-service", "method": "engagement-batch"},
    )
    await publish(
        request,
        entity_event(
            document,
            actor,
            event_type="entity.updated",
            sequence=next_sequence(request.app.state.executor, scenario_id),
            registry=request.app.state.registry,
        ),
    )
    return document


# -- F-5: Golden Dome plug-ins ----------------------------------------------


@router.post("/plugins", summary="Load a reference-architecture plug-in", status_code=201)
async def load_reference_plugin(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    manifest = body.get("manifest")
    if not isinstance(manifest, dict):
        raise ValidationError("'manifest' must be an object")
    plugin = load_plugin(manifest, host_envelope=body.get("hostEnvelope") or {})
    request.app.state.plugins[plugin["pluginId"]] = plugin
    return {"plugin": plugin}


@router.get("/plugins", summary="List loaded plug-ins")
async def list_plugins(request: Request) -> dict[str, Any]:
    plugins = [request.app.state.plugins[key] for key in sorted(request.app.state.plugins)]
    return {"plugins": plugins, "count": len(plugins)}


@router.delete("/plugins/{plugin_id}", summary="Unload a plug-in")
async def delete_plugin(request: Request, plugin_id: str) -> dict[str, Any]:
    plugin = request.app.state.plugins.pop(plugin_id, None)
    if plugin is None:
        raise NotFoundError(f"no loaded plug-in with id {plugin_id!r}")
    return unload_plugin(plugin)


@router.post("/plugins/{plugin_id}/run", summary="Run a plug-in against a scenario")
async def run_reference_plugin(
    request: Request,
    plugin_id: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    plugin = request.app.state.plugins.get(plugin_id)
    if plugin is None:
        raise NotFoundError(f"no loaded plug-in with id {plugin_id!r}")
    scenario_id = body.get("scenarioId")
    if not isinstance(scenario_id, str) or not scenario_id:
        raise ValidationError("'scenarioId' is required")
    entity = _require(request, "EngagementScenario", scenario_id)
    scenario = {"id": scenario_id, **(_attrs(entity))}
    if body.get("scenarioType"):
        scenario["scenarioType"] = body["scenarioType"]
    return run_plugin(plugin, scenario=scenario)


# -- F-6: red/blue co-simulation --------------------------------------------


@router.post("/co-simulation", summary="Run red and blue traces against one threat model")
async def red_blue(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    threat_id = body.get("threatId")
    if not isinstance(threat_id, str) or not threat_id:
        raise ValidationError("'threatId' is required")
    threat = _require(request, "ThreatSystem", threat_id)
    red = _require(request, "EngagementScenario", str(body.get("redScenarioId")))
    blue = _require(request, "EngagementScenario", str(body.get("blueScenarioId")))

    report = co_simulation(
        threat={"id": threat_id, **_attrs(threat)},
        red_scenario={"id": red["id"], **_attrs(red)},
        blue_scenario={"id": blue["id"], **_attrs(blue)},
        runs=int(body.get("runs", 1_000)),
        seed=int(body.get("seed", 1234)),
        pk_threshold=float(body.get("pkThreshold", 0.7)),
    )
    settings: Settings = request.app.state.settings
    actor = actor_for(settings, request)
    annotations = {
        **(red.get("annotations") or {}),
        "lastCoSimulation": str(report["comparison"]),
    }
    document = entity_document(
        "EngagementScenario",
        red["id"],
        dict(_attrs(red)),
        tenant=settings.tenant,
        program=settings.program,
        created_by=red.get("createdBy") or actor.subjectId,
        version=int(red.get("version") or 1) + 1,
        provenance={"source": "engagement-service", "method": "red-blue-co-simulation"},
        annotations=annotations,
    )
    await publish(
        request,
        entity_event(
            document,
            actor,
            event_type="entity.updated",
            sequence=next_sequence(request.app.state.executor, red["id"]),
            registry=request.app.state.registry,
        ),
    )
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
            {"name": "engagement", "description": "Pillars F and G: threats, scenarios, batches, range."},
            {"name": "operations", "description": "Health and metadata."},
        ],
    )
    app.state.executor = executor
    app.state.registry = registry
    app.state.projector = GraphProjector(executor)
    app.state.plugins = {}
    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
