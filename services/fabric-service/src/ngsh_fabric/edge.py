"""Edge reconciliation endpoint for the fabric service.

The fabric is the authority on reconciliation: it holds the global sequence
space and the authoritative state, so it applies the conflict rule of
ADR-0006 to the batches that edge nodes submit.

The endpoint is deliberately shaped like a batch acknowledgement rather than
a fire-and-forget publish. The edge needs to know, per event, whether its
write was accepted, was a duplicate, or was quarantined for a human, and it
needs the resulting global high-water mark per aggregate so that it can set
its next branch point.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, FastAPI, Request
from ngsh_core.envelope import Actor, Classification, EventEnvelope, utcnow
from ngsh_core.errors import ValidationError
from ngsh_core.ontology import OntologyLoader
from ngsh_core.reconcile import ConflictClass, FabricState, Reconciler, Resolution

router = APIRouter(prefix="/v1/edge", tags=["edge"])


def _entity_from(envelope: EventEnvelope) -> dict[str, Any]:
    """The entity an event carries, if it carries one."""
    for key in ("entity", "testResult", "processRun", "campaign", "threatSystem"):
        candidate = envelope.payload.get(key)
        if isinstance(candidate, dict) and candidate.get("id") and candidate.get("type"):
            return candidate
    return {}


def _state(request: Request) -> FabricState:
    """Build the fabric's state snapshot for the aggregates a batch touches."""
    executor = request.app.state.executor
    registry = request.app.state.registry

    aggregate_sequences = {
        row["aggregate_id"]: int(row["last_sequence"])
        for row in executor.fetchall("SELECT aggregate_id, last_sequence FROM aggregate_heads")
    }

    known_event_ids = {row["event_id"] for row in executor.fetchall("SELECT event_id FROM events")}

    # The fabric derives everything it needs from its own log. It must not
    # depend on the thread projection, which lives in another service and
    # may be behind, or rebuilt, independently of the log.
    entity_classifications: dict[str, str] = {}
    incumbents: dict[str, EventEnvelope] = {}
    immutable_keys: set[tuple[str, str]] = set()

    for row in executor.fetchall("SELECT envelope_json FROM events ORDER BY seq ASC"):
        envelope = EventEnvelope.model_validate(json.loads(row["envelope_json"]))
        incumbents[envelope.aggregateId] = envelope

        entity = _entity_from(envelope)
        if not entity:
            continue
        entity_classifications[entity["id"]] = (entity.get("classification") or {}).get(
            "level", envelope.classification.level
        )

        # Immutable keys: a test result is identified by its article and
        # campaign, not by its aggregate id, because two sites may use
        # different aggregate ids for the same physical test.
        if entity.get("type") == "TestResult":
            attributes = entity.get("attributes", {}) or {}
            campaign = attributes.get("campaignId")
            article = attributes.get("testArticleId")
            if campaign and article:
                immutable_keys.add((str(campaign), str(article)))

    classification_floors = {spec.type: spec.classificationFloor for spec in registry.entities.values()}

    return FabricState(
        aggregate_sequences=aggregate_sequences,
        known_event_ids=known_event_ids,
        entity_classifications=entity_classifications,
        immutable_keys=immutable_keys,
        classification_floors=classification_floors,
        incumbents=incumbents,
    )


@router.post("/reconcile", summary="Reconcile a batch submitted by an edge node")
async def reconcile(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Apply the ADR-0006 conflict rule to an edge batch."""
    raw_events = body.get("events")
    if not isinstance(raw_events, list):
        raise ValidationError("body must contain an 'events' array")

    node_id = body.get("nodeId") or "edge:unknown"
    clock_skew = float(body.get("clockSkewMs") or 0.0)

    envelopes: list[EventEnvelope] = []
    for index, raw in enumerate(raw_events):
        try:
            envelopes.append(EventEnvelope.model_validate(raw))
        except Exception as exc:
            raise ValidationError(f"event at index {index} is not a valid envelope", detail=str(exc)) from exc

    state = _state(request)
    state.clock_skew_ms = clock_skew

    reconciler = Reconciler(state)
    result = reconciler.reconcile(envelopes)

    log = request.app.state.eventlog
    actor = Actor(
        subjectId=f"edge:{node_id}",
        kind="edge-agent",
        clearance="SECRET",
        citizenship="US",
        tenant=request.app.state.settings.tenant,
    )

    accepted_payloads: list[dict[str, Any]] = []
    duplicate_payloads: list[dict[str, Any]] = []
    quarantined_payloads: list[dict[str, Any]] = []
    rejected_payloads: list[dict[str, Any]] = []

    # Accepted events are applied in the edge's local sequence order, per
    # aggregate, so that the fabric's own ordering is deterministic and
    # matches the order the edge produced.
    for outcome in result.outcomes:
        envelope = next(e for e in envelopes if e.eventId == outcome.eventId)
        if outcome.resolution is Resolution.ACCEPTED:
            stamped = envelope.model_copy(
                update={
                    "actor": actor,
                    "recordedAt": utcnow(),
                    "edge": {
                        **(envelope.edge or {}),
                        "nodeId": node_id,
                        "reconciledAt": utcnow().isoformat(),
                        "clockSkewMs": clock_skew,
                    },
                }
            )
            log.append(stamped, assign_sequence=True)
            accepted_payloads.append({"eventId": outcome.eventId})
        elif outcome.resolution is Resolution.DUPLICATE:
            duplicate_payloads.append({"eventId": outcome.eventId})
        elif outcome.resolution is Resolution.QUARANTINED:
            quarantined_payloads.append(
                {
                    "eventId": outcome.eventId,
                    "reason": outcome.reason,
                    "conflictClass": outcome.conflictClass.value if outcome.conflictClass else None,
                }
            )
        elif outcome.resolution is Resolution.REJECTED:
            rejected_payloads.append(
                {
                    "eventId": outcome.eventId,
                    "reason": outcome.reason,
                    "conflictClass": outcome.conflictClass.value if outcome.conflictClass else None,
                }
            )

    # Conflicts are first-class records, not only ledger entries.
    for payload in quarantined_payloads + rejected_payloads:
        _record_conflict(request, actor, payload, node_id, clock_skew)

    aggregate_sequences = {
        row["aggregate_id"]: int(row["last_sequence"])
        for row in request.app.state.executor.fetchall(
            "SELECT aggregate_id, last_sequence FROM aggregate_heads"
        )
    }

    return {
        "accepted": accepted_payloads,
        "duplicates": duplicate_payloads,
        "quarantined": quarantined_payloads,
        "rejected": rejected_payloads,
        "clockSkewMs": clock_skew,
        "aggregateSequences": aggregate_sequences,
        "nodeId": node_id,
    }


def _record_conflict(
    request: Request,
    actor: Actor,
    payload: dict[str, Any],
    node_id: str,
    clock_skew: float,
) -> None:
    """Write a ``reconcile.conflict.recorded`` event for an escalated conflict."""
    log = request.app.state.eventlog
    conflict_class = payload.get("conflictClass") or ConflictClass.MUTABLE_CONFLICT.value

    task_type = {
        ConflictClass.IMMUTABLE_CONFLICT.value: "safety-review",
        ConflictClass.GAP.value: "data-completeness",
        ConflictClass.DIVERGENT_SEQUENCE.value: "edge-incident",
        ConflictClass.CLOCK_SKEW.value: "edge-incident",
        ConflictClass.CLASSIFICATION_VIOLATION.value: "security-review",
        ConflictClass.MUTABLE_CONFLICT.value: "engineering-review",
    }.get(conflict_class, "engineering-review")

    sequence = log.next_sequence(f"CONFLICT:{payload.get('eventId', 'unknown')}")

    event = EventEnvelope(
        eventType="reconcile.conflict.recorded",
        aggregateType="ReconcileConflict",
        aggregateId=f"CONFLICT:{payload.get('eventId', 'unknown')}",
        sequence=sequence,
        tenant=request.app.state.settings.tenant,
        actor=actor,
        classification=Classification(level="CUI"),
        causationId=payload.get("eventId"),
        payload={
            "aggregateId": payload.get("eventId"),
            "conflictClass": conflict_class,
            "resolution": "quarantined" if conflict_class else "escalated",
            "edgeNodeId": node_id,
            "reason": payload.get("reason", ""),
            "escalationTask": {
                "taskType": task_type,
                "assignedTo": "programme-quality-authority"
                if task_type == "safety-review"
                else "platform-operations",
                "raisedAt": utcnow().isoformat(),
            },
        },
        edge={"nodeId": node_id, "clockSkewMs": clock_skew},
    )
    log.append(event, assign_sequence=True)


def register(app: FastAPI) -> None:
    """Attach the edge router to a service application."""
    app.include_router(router)


def load_registry(settings: Any) -> Any:
    return OntologyLoader(settings.contracts_dir).load()
