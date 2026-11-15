"""Publishing pillar entities and relations to the fabric.

Every pillar service writes the same way the foundation does: by appending
events to the log. There is no pillar-specific bypass, no service-private
table of authoritative facts, and no direct write to the graph. A credential
is an event. A process run is an event. An engagement scenario is an event.
The graph projection then serves them all.

This module is the small amount of glue every pillar needs:

* build the entity or relation document in the ontology's shape;
* validate it against the registry before it can reach the log;
* wrap it in an envelope with tenant, program, actor and classification;
* append it either directly (single-process development) or over HTTP to the
  fabric (multi-process deployment), then bring the local projection up to
  date so the service's own reads see its own writes.

The last point matters. A service that writes an event and then reads a stale
projection will appear to lose its own data, and the usual fix - a private
cache - is exactly the second source of truth the platform forbids.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any

from fastapi import Request

from .classification import at_least
from .envelope import Actor, Classification, Entity, EventEnvelope, Relation
from .errors import ValidationError
from .ontology import OntologyRegistry

DEFAULT_CLASSIFICATION = "CUI"


def utcnow() -> datetime:
    return datetime.now(UTC)


def now_iso() -> str:
    return utcnow().isoformat()


def entity_document(
    entity_type: str,
    entity_id: str,
    attributes: dict[str, Any],
    *,
    tenant: str,
    program: str | None = None,
    classification: str = DEFAULT_CLASSIFICATION,
    created_by: str,
    provenance: dict[str, Any] | None = None,
    version: int = 1,
    annotations: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build an entity document in the shape the ontology expects.

    Optional attributes supplied as ``None`` are dropped rather than written
    as JSON ``null``. The contracts describe an optional field as one that is
    absent, and a null is not the same thing: it asserts the field exists and
    has no value, which the entity schemas reject. Dropping happens here, once,
    so that every pillar service inherits the same behaviour.
    """
    attributes = {key: value for key, value in attributes.items() if value is not None}
    stamp = now_iso()
    return {
        "id": entity_id,
        "type": entity_type,
        "tenant": tenant,
        "program": program,
        "version": version,
        "createdAt": stamp,
        "updatedAt": stamp,
        "createdBy": created_by,
        "updatedBy": created_by,
        "provenance": provenance or {"source": f"service:{created_by}", "method": "pillar-write"},
        "labels": {},
        "annotations": annotations or {},
        "deleted": False,
        "classification": {"level": classification},
        "attributes": attributes,
    }


def relation_document(
    relation_type: str,
    from_ref: tuple[str, str],
    to_ref: tuple[str, str],
    *,
    tenant: str,
    asserted_by: str,
    classification: str = DEFAULT_CLASSIFICATION,
    confidence: float | None = 1.0,
    relation_id: str | None = None,
) -> dict[str, Any]:
    """Build a relation document in the shape the ontology expects."""
    from .ids import new_ulid

    return {
        "id": relation_id or f"REL:{new_ulid()}",
        "type": relation_type,
        "from": {"type": from_ref[0], "id": from_ref[1]},
        "to": {"type": to_ref[0], "id": to_ref[1]},
        "tenant": tenant,
        "classification": {"level": classification},
        "assertedAt": now_iso(),
        "assertedBy": asserted_by,
        "provenance": {"source": f"service:{asserted_by}", "method": "pillar-write"},
        "confidence": confidence,
    }


def entity_event(
    document: dict[str, Any],
    actor: Actor,
    *,
    event_type: str = "entity.created",
    sequence: int = 1,
    registry: OntologyRegistry | None = None,
    idempotency_key: str | None = None,
    causation_id: str | None = None,
    correlation_id: str | None = None,
) -> EventEnvelope:
    """Validate an entity document and wrap it in an event envelope.

    The type's classification floor (C-001) is applied here, before
    validation. A caller may mark an entity higher than its floor but never
    lower, so the floor is a max rather than a replacement.
    """
    if registry is not None:
        spec = registry.entity_type(document["type"])
        if spec is not None:
            level = (document.get("classification") or {}).get("level") or "UNCLASSIFIED"
            if not at_least(level, spec.classificationFloor):
                document["classification"] = {"level": spec.classificationFloor}

        entity = Entity.model_validate(document)
        errors = registry.validate_entity(entity)
        if errors:
            raise ValidationError(
                f"{document.get('type')} {document.get('id')} does not satisfy the ontology",
                detail=errors,
            )

    return EventEnvelope(
        eventType=event_type,
        aggregateType=document["type"],
        aggregateId=document["id"],
        sequence=sequence,
        tenant=document["tenant"],
        program=document.get("program"),
        actor=actor,
        classification=Classification.model_validate(document.get("classification") or {}),
        payload={"entity": document},
        idempotencyKey=idempotency_key,
        causationId=causation_id,
        correlationId=correlation_id,
    )


def relation_event(
    document: dict[str, Any],
    actor: Actor,
    *,
    registry: OntologyRegistry | None = None,
    sequence: int = 1,
) -> EventEnvelope:
    """Validate a relation document and wrap it in an event envelope."""
    if registry is not None:
        relation = Relation.model_validate(document)
        errors = registry.validate_relation(relation)
        if errors:
            raise ValidationError(
                f"relation {document.get('type')} does not satisfy the ontology", detail=errors
            )

    return EventEnvelope(
        eventType="entity.relation.asserted",
        aggregateType="Relation",
        aggregateId=document["id"],
        sequence=sequence,
        tenant=document["tenant"],
        actor=actor,
        classification=Classification.model_validate(document.get("classification") or {}),
        payload={"relation": document},
    )


def next_sequence(executor: Any, aggregate_id: str) -> int:
    """The next sequence number for an aggregate in the shared log."""
    row = executor.fetchone(
        "SELECT last_sequence FROM aggregate_heads WHERE aggregate_id = ?", (aggregate_id,)
    )
    return int(row["last_sequence"]) + 1 if row else 1


async def publish(request: Request, *envelopes: EventEnvelope) -> dict[str, Any]:
    """Append events, then apply them to the local projection.

    A projection application failure never fails the append: the log is
    authoritative and the projection is rebuildable.
    """
    if not envelopes:
        return {"status": "no-op", "accepted": 0}

    fabric_url = request.app.state.settings.fabric_url
    accepted = 0
    rejected: list[dict[str, Any]] = []

    if fabric_url:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{fabric_url}/v1/events",
                json={"events": [envelope.to_logical_json() for envelope in envelopes]},
            )
        if response.status_code >= 300:
            return {"status": "failed", "code": response.status_code, "detail": response.text[:400]}
        body = response.json()
        accepted = len(body.get("accepted", []))
        rejected = body.get("rejected", [])
    else:
        from .eventlog import EventLog

        outcomes = EventLog(request.app.state.executor).append_batch(list(envelopes))
        accepted = sum(1 for outcome in outcomes if outcome.accepted)
        rejected = [{"eventId": o.eventId, "reason": o.reason} for o in outcomes if not o.accepted]

    projector = getattr(request.app.state, "projector", None)
    if projector is not None:
        for envelope in envelopes:
            # A projection failure must not fail the write: the log is
            # authoritative and the projection is rebuildable.
            with contextlib.suppress(Exception):
                projector.apply(envelope)

    return {"status": "appended", "accepted": accepted, "rejected": rejected}


def actor_for(settings: Any, request: Request) -> Actor:
    """The actor a pillar service writes as.

    The service identity is used for automated writes; a verified human
    identity carried on the request is used where the request is a human
    action and the deployment supplies one.
    """
    identity = getattr(request.state, "identity", None)
    subject = getattr(identity, "subjectId", None)
    if subject:
        return Actor(
            subjectId=subject,
            kind="user",
            clearance=getattr(identity, "clearance", None),
            citizenship=getattr(identity, "citizenship", None),
            tenant=settings.tenant,
            programs=[settings.program] if settings.program else [],
        )
    return Actor(
        subjectId=request.headers.get("X-NGSH-Subject") or f"svc:{settings.service_name}",
        kind="service",
        clearance="SECRET",
        citizenship="US",
        tenant=settings.tenant,
        programs=[settings.program] if settings.program else [],
    )
