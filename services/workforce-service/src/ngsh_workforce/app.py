"""NGSH workforce service (Pillar E): skills, credentials and the demand gap.

Two capabilities from Increment 1 live here: E-3, skills credentialing tied to
real process qualifications, and E-4, the cleared-workforce demand model. The
service owns the lifecycle of a credential and the authorisation decision that
uses it. It does not own the person or the skill taxonomy shape; those are
ontology entities and are validated against the registry like everything else.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from ngsh_core.app import create_service
from ngsh_core.audit import AuditLedger
from ngsh_core.classification import max_level
from ngsh_core.config import Settings, load_settings
from ngsh_core.envelope import Actor
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
)
from ngsh_core.store import open_database
from ngsh_core.training import (
    curriculum_package,
    sanitised_extract,
    training_completion,
    training_coverage,
    validate_training_scenario,
    verify_package,
)
from ngsh_core.workforce import (
    assess_issue,
    authorise,
    credential_state,
    gap_report,
    transition,
)

from .repository import ArtefactRepository

SERVICE_NAME = "workforce"
DESCRIPTION = (
    "Pillar E: skills and credentials tied to real qualifications, work "
    "authorisation against current clearance, and the cleared-workforce gap."
)

router = APIRouter(prefix="/v1", tags=["workforce"])

DEFAULT_VALIDITY_DAYS = 365


def _projector(request: Request) -> GraphProjector:
    return request.app.state.projector


def _at(request: Request, value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"'at' is not an ISO-8601 timestamp: {value!r}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _attributes(entity: dict[str, Any] | None) -> dict[str, Any]:
    return (entity or {}).get("attributes") or {}


def _with_ids(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attribute blocks with the entity id folded back in.

    The domain rules take plain attribute dictionaries, but they key people and
    skills by id. Folding the id in here keeps the rule signatures free of
    envelope concerns.
    """
    return [{"id": entity["id"], **_attributes(entity)} for entity in entities]


def _require(request: Request, entity_type: str, entity_id: str) -> dict[str, Any]:
    entity = _projector(request).entity(entity_type, entity_id)
    if entity is None:
        raise NotFoundError(f"no {entity_type} with id {entity_id!r}")
    return _attributes(entity)


# -- skills and people -------------------------------------------------------


@router.post("/skills", summary="Register a skill", status_code=201)
async def create_skill(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    for key in ("name", "code", "category"):
        if not isinstance(body.get(key), str) or not body[key].strip():
            raise ValidationError(f"'{key}' is required")
    skill_id = body.get("skillId") or f"SKL:{new_ulid()}"
    settings: Settings = request.app.state.settings
    actor: Actor = actor_for(settings, request)
    document = entity_document(
        "Skill",
        skill_id,
        {
            "name": body["name"],
            "code": body["code"],
            "category": body["category"],
            "level": body.get("level"),
            "qualificationCriteria": body.get("qualificationCriteria") or [],
            "clearanceRequired": body.get("clearanceRequired"),
        },
        tenant=settings.tenant,
        program=settings.program,
        created_by=actor.subjectId,
    )
    await publish(request, entity_event(document, actor, registry=request.app.state.registry))
    return {"skill": document}


@router.get("/skills", summary="List skills")
async def list_skills(request: Request, limit: int = Query(500, ge=1, le=5000)) -> dict[str, Any]:
    skills = _projector(request).entities(entity_type="Skill", limit=limit)
    return {"skills": skills, "count": len(skills)}


@router.post("/people", summary="Register a person", status_code=201)
async def create_person(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    for key in ("employeeId", "name", "citizenship", "clearanceLevel"):
        if not isinstance(body.get(key), str) or not body[key].strip():
            raise ValidationError(f"'{key}' is required")
    person_id = body.get("personId") or f"PER:{new_ulid()}"
    settings: Settings = request.app.state.settings
    actor: Actor = actor_for(settings, request)
    document = entity_document(
        "Person",
        person_id,
        {
            "employeeId": body["employeeId"],
            "name": body["name"],
            "citizenship": body["citizenship"],
            "clearanceLevel": body["clearanceLevel"],
            "clearanceExpiry": body.get("clearanceExpiry"),
            "skillIds": body.get("skillIds") or [],
            "role": body.get("role"),
            "organization": body.get("organization"),
            "region": body.get("region"),
        },
        tenant=settings.tenant,
        program=settings.program,
        created_by=actor.subjectId,
    )
    await publish(request, entity_event(document, actor, registry=request.app.state.registry))
    return {"person": document}


@router.get("/people", summary="List people")
async def list_people(request: Request, limit: int = Query(500, ge=1, le=5000)) -> dict[str, Any]:
    people = _projector(request).entities(entity_type="Person", limit=limit)
    return {"people": people, "count": len(people)}


# -- credentials -------------------------------------------------------------


@router.post("/credentials", summary="Issue a credential", status_code=201)
async def issue_credential(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    person_id = body.get("personId")
    skill_id = body.get("skillId")
    if not isinstance(person_id, str) or not person_id:
        raise ValidationError("'personId' is required")
    if not isinstance(skill_id, str) or not skill_id:
        raise ValidationError("'skillId' is required")

    person = _require(request, "Person", person_id)
    skill = _require(request, "Skill", skill_id)
    issued_at = _at(request, body.get("issuedAt"))
    permitted = tuple(request.app.state.settings.permitted_citizenships)

    assessment = assess_issue(person, skill, issued_at, permitted_citizenships=permitted)
    if not assessment.allowed:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "constraint_violation",
                    "message": "C-005/C-006 prevent issuing this credential",
                    "context": {"reasons": assessment.reasons},
                }
            },
        )

    expires_at = body.get("expiresAt") or (issued_at + timedelta(days=DEFAULT_VALIDITY_DAYS)).isoformat()
    credential_id = f"CRD:{new_ulid()}"
    actor: Actor = actor_for(request.app.state.settings, request)
    settings: Settings = request.app.state.settings
    document = entity_document(
        "Credential",
        credential_id,
        {
            "personId": person_id,
            "skillId": skill_id,
            "issuedAt": issued_at.isoformat(),
            "expiresAt": expires_at,
            "issuingAuthority": body.get("issuingAuthority") or "NGSH workforce office",
            "status": "ACTIVE",
            "evidenceRefs": body.get("evidenceRefs") or [],
            "workAuthorizationIds": [],
        },
        tenant=settings.tenant,
        program=settings.program,
        created_by=actor.subjectId,
        provenance={"source": "workforce-service", "method": "credential-issue"},
    )
    await publish(request, entity_event(document, actor, registry=request.app.state.registry))
    return JSONResponse(status_code=201, content={"credential": document})


@router.get("/credentials", summary="List credentials")
async def list_credentials(
    request: Request,
    personId: str | None = Query(None),
    at: str | None = Query(None),
    limit: int = Query(500, ge=1, le=5000),
) -> dict[str, Any]:
    when = _at(request, at)
    credentials = _projector(request).entities(entity_type="Credential", limit=limit)
    rows: list[dict[str, Any]] = []
    for credential in credentials:
        attributes = _attributes(credential)
        if personId and attributes.get("personId") != personId:
            continue
        rows.append({**credential, "effectiveState": credential_state(attributes, when)})
    return {"credentials": rows, "count": len(rows)}


@router.get("/credentials/{credential_id}", summary="Fetch a credential with its effective state")
async def get_credential(
    request: Request,
    credential_id: str,
    at: str | None = Query(None),
) -> dict[str, Any]:
    attributes = _require(request, "Credential", credential_id)
    return {
        "credentialId": credential_id,
        "attributes": attributes,
        "effectiveState": credential_state(attributes, _at(request, at)),
    }


@router.post("/credentials/{credential_id}/{action}", summary="Suspend, reinstate or revoke a credential")
async def change_credential_state(
    request: Request,
    credential_id: str,
    action: str,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    projector = _projector(request)
    entity = projector.entity("Credential", credential_id)
    if entity is None:
        raise NotFoundError(f"no Credential with id {credential_id!r}")

    attributes = _attributes(entity)
    when = _at(request, body.get("at"))
    new_status = transition(attributes, action, when)

    settings: Settings = request.app.state.settings
    actor: Actor = actor_for(settings, request)
    document = entity_document(
        "Credential",
        credential_id,
        {**attributes, "status": new_status},
        tenant=settings.tenant,
        program=settings.program,
        created_by=entity.get("createdBy") or actor.subjectId,
        version=int(entity.get("version") or 1) + 1,
        provenance={"source": "workforce-service", "method": f"credential-{action}"},
        annotations={"lastAction": action, "lastActionAt": when.isoformat()},
    )
    await publish(
        request,
        entity_event(
            document,
            actor,
            event_type="entity.updated",
            sequence=next_sequence(request.app.state.executor, credential_id),
            registry=request.app.state.registry,
        ),
    )
    return {"credentialId": credential_id, "status": new_status, "action": action}


# -- authorisation and gap ---------------------------------------------------


@router.get("/work-authorisation", summary="Decide whether a person may do a skill now")
async def work_authorisation(
    request: Request,
    personId: str = Query(...),
    skillId: str = Query(...),
    at: str | None = Query(None),
    facilityId: str | None = Query(None),
) -> dict[str, Any]:
    when = _at(request, at)
    person = _require(request, "Person", personId)
    skill = _require(request, "Skill", skillId)

    credentials = [
        credential
        for credential in _projector(request).entities(entity_type="Credential", limit=5000)
        if _attributes(credential).get("personId") == personId
        and _attributes(credential).get("skillId") == skillId
    ]
    if not credentials:
        return {
            "personId": personId,
            "skillId": skillId,
            "facilityId": facilityId,
            "allowed": False,
            "credentialState": "NONE",
            "reasons": ["no credential has been issued for this person and skill"],
        }

    best = None
    for credential in credentials:
        decision = authorise(person, _attributes(credential), skill, when, permit_skill_id=skillId)
        candidate = {"credentialId": credential["id"], **decision.to_dict()}
        if decision.allowed:
            best = candidate
            break
        if best is None or len(candidate["reasons"]) < len(best["reasons"]):
            best = candidate

    return {"personId": personId, "skillId": skillId, "facilityId": facilityId, **(best or {})}


@router.post("/workforce/gap", summary="Cleared-workforce gap by region and trade")
async def workforce_gap(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    demand = body.get("demand")
    if not isinstance(demand, list):
        raise ValidationError("'demand' must be a list of {region, skillId, headcount}")
    projector = _projector(request)
    report = gap_report(
        demand=demand,
        persons=_with_ids(projector.entities(entity_type="Person", limit=5000)),
        credentials=_with_ids(projector.entities(entity_type="Credential", limit=5000)),
        skills=_with_ids(projector.entities(entity_type="Skill", limit=5000)),
        at=_at(request, body.get("asOf")),
    )
    return report


# -- E-1: digital-twin training ----------------------------------------------


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _entity_map(projector: GraphProjector) -> dict[str, dict[str, Any]]:
    return {entity["id"]: entity for entity in projector.entities(limit=10_000)}


def _subject(request: Request) -> str:
    identity = getattr(request.state, "identity", None)
    subject = getattr(identity, "subjectId", None)
    return subject or request.headers.get("X-NGSH-Subject") or "svc:workforce"


def _artefacts(request: Request) -> ArtefactRepository:
    return request.app.state.artefacts


async def _anchor(request: Request, event_type: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Anchor an entry in the audit ledger, locally or over HTTP.

    The ledger is the only place a release decision becomes tamper-evident, so
    an extract that cannot be anchored is not released.
    """
    settings: Settings = request.app.state.settings
    if settings.audit_url:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{settings.audit_url}/ledger", json={"eventType": event_type, "entry": entry}
            )
        if response.status_code >= 300:
            raise ValidationError(
                "the audit ledger refused the anchor",
                detail=[response.text[:400]],
            )
        return response.json()
    return AuditLedger(request.app.state.executor).append(event_type, entry).to_dict()


@router.post("/training/scenarios", summary="Register a digital-twin training scenario", status_code=201)
async def create_training_scenario(request: Request, body: dict[str, Any]) -> JSONResponse:
    """Validate a scenario against the live thread and store it.

    A scenario referencing an entity that does not exist, or carrying a
    placeholder marker, is refused. That is E-1's zero-placeholder rule applied
    at the door rather than audited later.
    """
    projector = _projector(request)
    live = {(entity["type"], entity["id"]) for entity in projector.entities(limit=10_000)}
    validation = validate_training_scenario(body, live_references=live)
    if not validation["valid"]:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "constraint_violation",
                    "message": "the training scenario is not built on the live digital thread",
                    "context": {"reasons": validation["gaps"]},
                }
            },
        )

    skill_ids = [str(item) for item in body.get("skillIds") or []]
    for skill_id in skill_ids:
        _require(request, "Skill", skill_id)

    scenario_id = f"TSC:{new_ulid()}"
    settings: Settings = request.app.state.settings
    record = {
        "scenarioId": scenario_id,
        "name": validation["name"],
        "simulator": body.get("simulator") or "SCREEN",
        "skillIds": skill_ids,
        "references": validation["references"],
        "validation": validation,
        "createdBy": _subject(request),
        "createdAt": _now(),
    }
    _artefacts(request).put(
        "training_scenario",
        scenario_id,
        record,
        created_by=_subject(request),
        created_at=record["createdAt"],
        tenant=settings.tenant,
    )
    return JSONResponse(status_code=201, content={"scenario": record})


@router.get("/training/scenarios", summary="List training scenarios")
async def list_training_scenarios(
    request: Request,
    limit: int = Query(200, ge=1, le=2000),
) -> dict[str, Any]:
    rows = _artefacts(request).list("training_scenario", limit=limit)
    return {"scenarios": rows, "count": len(rows)}


@router.get("/training/scenarios/{scenario_id}", summary="Fetch one training scenario")
async def get_training_scenario(request: Request, scenario_id: str) -> dict[str, Any]:
    scenario = _artefacts(request).get("training_scenario", scenario_id)
    if scenario is None:
        raise NotFoundError(f"no training scenario with id {scenario_id!r}")
    return {"scenario": scenario}


@router.get("/training/coverage", summary="Training scenarios built on the live thread")
async def training_coverage_report(request: Request) -> dict[str, Any]:
    scenarios = _artefacts(request).list("training_scenario", limit=5000)
    return training_coverage([scenario.get("validation") or {} for scenario in scenarios])


@router.post("/training/completions", summary="Record a training completion", status_code=201)
async def record_training_completion(request: Request, body: dict[str, Any]) -> JSONResponse:
    """Record a completion and write it back to the person as a fact.

    The completion is an ``entity.updated`` event on the ``Person``, not a
    service-private row: a person's qualifications are authoritative facts and
    belong in the log with the rest of their record.
    """
    scenario_id = body.get("scenarioId")
    if not isinstance(scenario_id, str) or not scenario_id:
        raise ValidationError("'scenarioId' is required")
    scenario = _artefacts(request).get("training_scenario", scenario_id)
    if scenario is None:
        raise NotFoundError(f"no training scenario with id {scenario_id!r}")

    person_id = body.get("personId")
    if not isinstance(person_id, str) or not person_id:
        raise ValidationError("'personId' is required")
    scenario_skills = [str(item) for item in scenario.get("skillIds") or []]
    skill_id = body.get("skillId") or (scenario_skills[0] if scenario_skills else None)
    if not isinstance(skill_id, str) or not skill_id:
        raise ValidationError("'skillId' is required unless the scenario names the skill it exercises")

    person_entity = _require_entity(request, "Person", person_id)
    _require(request, "Skill", skill_id)
    completion = training_completion(
        person_id=person_id,
        scenario_id=scenario_id,
        skill_id=skill_id,
        score=body.get("score", 0),
        passed=bool(body.get("passed", False)),
        completed_at=body.get("completedAt") or _now(),
        evidence_refs=body.get("evidenceRefs"),
    )

    settings: Settings = request.app.state.settings
    actor: Actor = actor_for(settings, request)
    attributes = dict(_attributes(person_entity))
    history = list(attributes.get("trainingCompletions") or [])
    history.append(completion)
    attributes["trainingCompletions"] = history
    document = entity_document(
        "Person",
        person_id,
        attributes,
        tenant=settings.tenant,
        program=settings.program,
        created_by=person_entity.get("createdBy") or actor.subjectId,
        version=int(person_entity.get("version") or 1) + 1,
        provenance={"source": "workforce-service", "method": "training-completion"},
    )
    await publish(
        request,
        entity_event(
            document,
            actor,
            event_type="entity.updated",
            sequence=next_sequence(request.app.state.executor, person_id),
            registry=request.app.state.registry,
        ),
    )
    return JSONResponse(status_code=201, content={"completion": completion})


@router.get("/training/completions", summary="Training completions for a person")
async def list_training_completions(
    request: Request,
    personId: str = Query(...),
) -> dict[str, Any]:
    person = _attributes(_require_entity(request, "Person", personId))
    completions = list(person.get("trainingCompletions") or [])
    return {"personId": personId, "completions": completions, "count": len(completions)}


# -- E-2: curriculum replication ---------------------------------------------


@router.post("/curriculum/packages", summary="Build a content-addressed curriculum package", status_code=201)
async def build_curriculum_package(request: Request, body: dict[str, Any]) -> JSONResponse:
    projector = _projector(request)
    entities = _entity_map(projector)
    sources = body.get("sources")
    source_records: list[dict[str, Any]] = []
    if isinstance(sources, list) and sources:
        for source in sources:
            if not isinstance(source, dict) or not source.get("id"):
                raise ValidationError("each source must carry an 'id'")
            entity = entities.get(str(source["id"]))
            graph_level = ((entity or {}).get("classification") or {}).get("level")
            source_records.append(
                {
                    "id": str(source["id"]),
                    "classification": max_level(graph_level, source.get("classification")).label,
                }
            )
    else:
        for source_id in body.get("sourceIds") or []:
            entity = entities.get(str(source_id))
            if entity is None:
                raise ValidationError(
                    f"source {source_id!r} does not resolve in the thread; its classification "
                    "cannot be established"
                )
            source_records.append(
                {
                    "id": str(source_id),
                    "classification": (entity.get("classification") or {}).get("level") or "CUI",
                }
            )

    try:
        manifest = curriculum_package(
            title=body.get("title"),
            version=body.get("version"),
            modules=body.get("modules"),
            source_records=source_records,
            guard_version=body.get("guardVersion"),
            reviewer=body.get("reviewer") or _subject(request),
            supersedes=body.get("supersedes"),
        )
    except ValidationError as exc:
        return JSONResponse(status_code=422, content=exc.to_dict())

    settings: Settings = request.app.state.settings
    _artefacts(request).put(
        "curriculum_package",
        manifest["packageId"],
        manifest,
        created_by=_subject(request),
        created_at=_now(),
        tenant=settings.tenant,
    )
    return JSONResponse(status_code=201, content={"package": manifest})


@router.get("/curriculum/packages", summary="List curriculum packages")
async def list_curriculum_packages(
    request: Request,
    limit: int = Query(200, ge=1, le=2000),
) -> dict[str, Any]:
    packages = _artefacts(request).list("curriculum_package", limit=limit)
    return {"packages": packages, "count": len(packages)}


@router.get("/curriculum/packages/{package_id}", summary="Fetch one curriculum package")
async def get_curriculum_package(request: Request, package_id: str) -> dict[str, Any]:
    package = _artefacts(request).get("curriculum_package", package_id)
    if package is None:
        raise NotFoundError(f"no curriculum package with id {package_id!r}")
    return {"package": package, "verification": verify_package(package)}


# -- E-5: sanitised extracts -------------------------------------------------


@router.post("/extracts", summary="Build or block a sanitised partner extract", status_code=201)
async def build_extract(request: Request, body: dict[str, Any]) -> JSONResponse:
    """Release an extract, or block and record an attempt.

    The classification used for the guard is the maximum of the record's
    classification in the thread and any classification supplied in the
    request. A caller cannot downgrade a record by asserting a lower marking.
    """
    entities = _entity_map(_projector(request))
    records = body.get("records")
    if not isinstance(records, list) or not records:
        raise ValidationError("'records' must be a non-empty list")

    resolved: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict) or not record.get("id"):
            raise ValidationError("each record must carry an 'id'")
        entity = entities.get(str(record["id"]))
        graph_level = ((entity or {}).get("classification") or {}).get("level")
        level = max_level(graph_level, record.get("classification"))
        resolved.append(
            {
                "id": str(record["id"]),
                "type": record.get("type") or (entity or {}).get("type"),
                "classification": level.label,
            }
        )

    settings: Settings = request.app.state.settings
    ledger = AuditLedger(request.app.state.executor) if not settings.audit_url else None
    previous_anchor = ledger.head() if ledger is not None else None
    outcome = sanitised_extract(
        view=body.get("view"),
        records=resolved,
        transformations=body.get("transformations"),
        guard_version=body.get("guardVersion"),
        reviewer=body.get("reviewer") or _subject(request),
        previous_anchor=previous_anchor,
    )

    if not outcome["released"]:
        attempt_id = f"EXTA:{new_ulid()}"
        attempt = {
            "attemptId": attempt_id,
            "view": outcome["view"],
            "blocked": outcome["blocked"],
            "guardVersion": outcome["guardVersion"],
            "reviewer": outcome["reviewer"],
            "recorded": True,
        }
        _artefacts(request).put(
            "extract_attempt",
            attempt_id,
            attempt,
            created_by=_subject(request),
            created_at=_now(),
            tenant=settings.tenant,
        )
        anchor = await _anchor(request, "extract.blocked", attempt)
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "sanitisation_blocked",
                    "message": "a RESTRICTED or above record is not eligible for partner release",
                    "context": {
                        "blocked": outcome["blocked"],
                        "attemptId": attempt_id,
                        "recorded": True,
                        "auditEntry": anchor,
                    },
                }
            },
        )

    manifest = outcome["manifest"]
    anchor = await _anchor(
        request,
        "extract.released",
        {"manifestId": manifest["manifestId"], "manifestDigest": manifest["manifestDigest"]},
    )
    manifest["auditEntry"] = anchor
    _artefacts(request).put(
        "extract_manifest",
        manifest["manifestId"],
        manifest,
        created_by=_subject(request),
        created_at=_now(),
        tenant=settings.tenant,
    )
    return JSONResponse(status_code=201, content={"release": outcome, "auditEntry": anchor})


@router.get("/extracts", summary="List released extract manifests")
async def list_extracts(
    request: Request,
    limit: int = Query(200, ge=1, le=2000),
) -> dict[str, Any]:
    manifests = _artefacts(request).list("extract_manifest", limit=limit)
    return {"manifests": manifests, "count": len(manifests)}


@router.get("/extracts/{manifest_id}", summary="Fetch one extract manifest")
async def get_extract(request: Request, manifest_id: str) -> dict[str, Any]:
    manifest = _artefacts(request).get("extract_manifest", manifest_id)
    if manifest is None:
        raise NotFoundError(f"no extract manifest with id {manifest_id!r}")
    return {"manifest": manifest}


def _require_entity(request: Request, entity_type: str, entity_id: str) -> dict[str, Any]:
    entity = _projector(request).entity(entity_type, entity_id)
    if entity is None:
        raise NotFoundError(f"no {entity_type} with id {entity_id!r}")
    return entity


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
            {"name": "workforce", "description": "Pillar E: skills, credentials and demand."},
            {"name": "operations", "description": "Health and metadata."},
        ],
    )
    app.state.executor = executor
    app.state.registry = registry
    app.state.projector = GraphProjector(executor)
    app.state.artefacts = ArtefactRepository(executor)
    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
