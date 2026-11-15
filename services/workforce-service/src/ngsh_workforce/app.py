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
from ngsh_core.workforce import (
    assess_issue,
    authorise,
    credential_state,
    gap_report,
    transition,
)

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
    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
