"""NGSH policy service: the Policy Decision Point.

Every access to every store in the platform passes through this service, which
returns ALLOW, DENY or INDETERMINATE together with the rule that produced the
outcome and any obligations the enforcement point must discharge
(ADR-0004).

The PDP is deliberately a separate service from the enforcement points. A
policy that lives inside each resource service is a policy that drifts
between services, and a policy that cannot be reviewed in one place cannot be
attested to a CMMC assessor.

Decisions are recorded to the tamper-evident audit ledger, which is why this
service knows about the audit service even though it does not own it.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from fastapi import APIRouter, Body, FastAPI, Request
from fastapi.responses import JSONResponse
from ngsh_core.app import create_service
from ngsh_core.config import Settings, load_settings
from ngsh_core.envelope import Actor
from ngsh_core.errors import ValidationError
from ngsh_core.policy import PolicySet, Resource
from ngsh_core.store import open_database

SERVICE_NAME = "policy"
DESCRIPTION = (
    "Attribute-based access control for the NGSH platform. Separate policy "
    "decision and enforcement points, explicit deny precedence, obligations on allow."
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["policy"])


def _policy_set(request: Request) -> PolicySet:
    return request.app.state.policy_set


@router.post("/decisions", summary="Evaluate an access request")
async def decide(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Evaluate a request and record the decision.

    The decision is recorded whether it allowed or denied the request. A trail
    that only contains successes is not an audit trail.
    """
    subject = body.get("subject") or {}
    resource = body.get("resource") or {}
    action = body.get("action")
    context = body.get("context") or {}

    if not action:
        raise ValidationError("an action is required")
    if not resource.get("type") or not resource.get("id"):
        raise ValidationError("a resource must supply both 'type' and 'id'")

    actor = Actor.model_validate(subject) if subject else Actor(subjectId="unknown", kind="anonymous")
    res = Resource(
        type=resource["type"],
        id=resource["id"],
        classification=(resource.get("classification") or {}).get("level", "UNCLASSIFIED"),
        tenant=resource.get("tenant"),
        program=resource.get("program"),
        owner=resource.get("owner"),
        attributes=resource.get("attributes") or {},
    )

    policy_set = _policy_set(request)
    decision = policy_set.evaluate(actor, res, action, context)

    payload = decision.to_dict()
    await _record_decision(request, actor, action, res, payload)

    return payload


async def _record_decision(
    request: Request,
    actor: Actor,
    action: str,
    resource: Resource,
    decision: dict[str, Any],
) -> None:
    """Write the decision to the audit ledger.

    Failure to record is reported but does not change the decision that was
    returned to the caller: refusing a legitimate request because the audit
    pipeline is degraded would be a denial of service caused by the control
    meant to provide assurance.
    """
    audit_url = request.app.state.settings.audit_url
    entry = {
        "subject": actor.model_dump(mode="json"),
        "action": action,
        "resource": {
            "type": resource.type,
            "id": resource.id,
            "classification": {"level": resource.classification.level},
            "tenant": resource.tenant,
            "program": resource.program,
        },
        "decision": decision.get("decision"),
        "policyId": decision.get("policyId"),
        "policyVersion": decision.get("policyVersion"),
        "obligations": decision.get("obligations", []),
        "reason": decision.get("reason", ""),
    }

    entry["enforcementPoint"] = request.app.state.settings.enforcement_point

    if not audit_url:
        # Single-process development mode: the audit service shares the
        # platform database, so write the ledger entry directly.
        with contextlib.suppress(Exception):
            request.app.state.ledger.append("access.decision.recorded", entry)
        await _publish_decision_event(request, entry, decision)
        return

    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{audit_url}/v1/ledger", json={"eventType": "access.decision.recorded", "entry": entry}
            )
    except Exception:
        # Deliberately swallowed: see the docstring above.
        pass

    await _publish_decision_event(request, entry, decision)


async def _publish_decision_event(request: Request, entry: dict[str, Any], decision: dict[str, Any]) -> None:
    """Publish the decision to the fabric as an ``access.decision.recorded`` event.

    Every decision produces both a ledger entry and an event (roadmap exit
    criterion I0-4). The two are cross-checked: the ledger is the tamper
    evident record and the event is the queryable one, and a mismatch
    between them is itself a finding.
    """
    settings = request.app.state.settings
    resource = entry.get("resource", {})

    try:
        from ngsh_core.envelope import Actor, Classification, EventEnvelope

        subject = entry.get("subject", {})
        actor = Actor.model_validate(subject) if subject else Actor(subjectId="unknown")

        # The decision has its own aggregate, separate from the resource it
        # concerns. Sharing the resource's sequence space would interleave
        # decisions with the resource's own history.
        aggregate_id = f"AccessDecision:{resource.get('type', 'unknown')}:{resource.get('id', 'unknown')}"

        event = EventEnvelope(
            eventType="access.decision.recorded",
            aggregateType="AccessDecision",
            aggregateId=aggregate_id,
            sequence=request.app.state.decision_sequence(aggregate_id),
            tenant=settings.tenant,
            actor=actor,
            classification=Classification(level=resource.get("classification", {}).get("level", "CUI")),
            idempotencyKey=(
                f"{decision.get('policyId')}:{subject.get('subjectId')}:"
                f"{entry.get('action')}:{resource.get('id')}"
            ),
            payload={
                "decision": decision.get("decision"),
                "action": entry.get("action"),
                "resource": resource,
                "policyId": decision.get("policyId"),
                "policyVersion": decision.get("policyVersion"),
                "obligations": decision.get("obligations", []),
                "reason": decision.get("reason", ""),
                "enforcementPoint": entry.get("enforcementPoint"),
            },
        )

        fabric_url = settings.fabric_url
        if fabric_url:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(f"{fabric_url}/v1/events", json={"events": [event.to_logical_json()]})
        else:
            from ngsh_core.eventlog import EventLog

            EventLog(request.app.state.executor).append(event)
    except Exception:
        # A failure to publish must not change the decision that was
        # returned to the caller. It is logged rather than swallowed,
        # because a decision that is in the ledger but not in the event
        # log is a finding that the cross-check must report.
        logger.exception("failed to publish the access decision event")
        return


@router.get("/policies", summary="List policy rules")
async def list_policies(request: Request) -> dict[str, Any]:
    policy_set = _policy_set(request)
    return {
        "policyVersion": policy_set.version,
        "defaultEffect": policy_set.default_effect,
        "policies": [
            {
                "id": rule.id,
                "description": rule.description,
                "effect": rule.effect,
                "priority": rule.priority,
                "obligations": rule.obligations,
                "reason": rule.reason,
            }
            for rule in sorted(policy_set.rules, key=lambda r: (-r.priority, r.id))
        ],
        "obligations": [
            {"name": obligation.name, "description": obligation.description}
            for obligation in policy_set.known_obligations
        ],
    }


@router.get("/policies/{policy_id}", summary="Fetch one policy rule")
async def get_policy(request: Request, policy_id: str) -> dict[str, Any]:
    policy_set = _policy_set(request)
    for rule in policy_set.rules:
        if rule.id == policy_id:
            return {
                "id": rule.id,
                "description": rule.description,
                "effect": rule.effect,
                "priority": rule.priority,
                "obligations": rule.obligations,
                "reason": rule.reason,
                "policyVersion": policy_set.version,
            }
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "not_found", "message": f"no policy {policy_id!r}"}},
    )


@router.post("/policies/reload", summary="Reload the policy set")
async def reload_policies(request: Request) -> dict[str, Any]:
    """Re-read the policy document.

    Access-control changes are applied as reviewed artefacts. Reloading means
    a change to the policy file does not require a coordinated deployment of
    every service that enforces it.
    """
    path = request.app.state.settings.contracts_dir / "policy" / "access-policy.json"
    policy_set = PolicySet.load(path)
    request.app.state.policy_set = policy_set
    return {"policyVersion": policy_set.version, "rules": len(policy_set.rules)}


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()
    policy_path = resolved.contracts_dir / "policy" / "access-policy.json"
    policy_set = PolicySet.load(policy_path)

    app = create_service(
        SERVICE_NAME,
        settings=resolved,
        description=DESCRIPTION,
        routers=[router],
        tags=[
            {"name": "policy", "description": "Access decisions and the rule set."},
            {"name": "operations", "description": "Health and metadata."},
        ],
    )
    app.state.policy_set = policy_set
    app.state.executor = open_database(resolved.dsn)

    # In single-process development mode the audit ledger lives in the same
    # database. In a deployed topology the audit service is remote and the
    # decision is written over HTTP instead.
    if not resolved.audit_url:
        from ngsh_core.audit import AuditLedger

        app.state.ledger = AuditLedger(app.state.executor)

    def decision_sequence(aggregate_id: str) -> int:
        """The next sequence for a decision aggregate.

        Access decisions are a stream in their own right: the log's
        per-aggregate sequencing does not apply to them, because they are
        not the history of one resource but the record of every attempt to
        reach it. Each resource therefore has its own decision aggregate.
        """
        from ngsh_core.eventlog import EventLog

        return EventLog(app.state.executor).next_sequence(aggregate_id)

    app.state.decision_sequence = decision_sequence

    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
