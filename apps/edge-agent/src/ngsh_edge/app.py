"""NGSH edge annex agent.

The service that runs at a factory floor, a test range, or an air-gapped
analysis node. It provides the local console replica's API and the capture
and reconciliation paths described in ADR-0006.

The behaviour that distinguishes this from an ordinary service:

* **Capture never touches the network.** Writing a test result at the edge
  succeeds whether or not the fabric is reachable.
* **Reads are local.** The local projection cache answers reads. An operator
  at a site with a bad link gets the same answer they would get connected.
* **Reconciliation is explicit.** The agent never reconnects on its own
  schedule; a sync is a deliberate act, because a reconcile is a negotiation
  with the fabric and not a heartbeat.
* **Nothing is lost silently.** Queue overflow, quarantined events and
  undecidable conflicts are all visible through this API.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, FastAPI, Request
from fastapi.responses import JSONResponse
from ngsh_core.app import create_service
from ngsh_core.config import Settings, load_settings
from ngsh_core.edge import EdgeAgent, EdgeQueue, http_transport
from ngsh_core.envelope import EventEnvelope
from ngsh_core.errors import ValidationError

SERVICE_NAME = "edge"
DESCRIPTION = (
    "The NGSH edge annex agent: local capture, local reads, and deterministic "
    "reconciliation with the central fabric."
)

router = APIRouter(prefix="/v1/edge", tags=["edge"])


def _agent(request: Request) -> EdgeAgent:
    return request.app.state.agent


@router.post("/capture", summary="Capture an event locally")
async def capture(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Capture an event into the local queue.

    This is the write path at the edge. It does not contact the fabric and
    it does not fail because the fabric is unreachable.
    """
    try:
        envelope = EventEnvelope.model_validate(body)
    except Exception as exc:
        raise ValidationError("event is not a valid envelope", detail=str(exc)) from exc

    entry = _agent(request).capture(envelope)
    return {
        "eventId": entry.eventId,
        "aggregateId": entry.aggregateId,
        "localSequence": entry.localSequence,
        "branchedFromSeq": entry.branchedFromSeq,
        "capturedAt": entry.capturedAt,
        "pending": _agent(request).queue.pending_count(),
    }


@router.get("/queue", summary="Pending events")
async def pending(request: Request, limit: int = 200) -> dict[str, Any]:
    agent = _agent(request)
    return {
        "pending": [entry.to_dict() for entry in agent.queue.pending(limit=limit)],
        "count": agent.queue.pending_count(),
        "quarantined": agent.queue.quarantined(),
    }


@router.get("/drops", summary="Events discarded by queue overflow")
async def drops(request: Request) -> dict[str, Any]:
    """Every event the queue has discarded.

    Silent loss is prohibited, so this is an operator-facing endpoint, not
    an internal counter.
    """
    agent = _agent(request)
    return {"dropped": agent.dropped(), "count": len(agent.dropped())}


@router.get("/status", summary="Link state, backlog and drops")
async def status(request: Request) -> dict[str, Any]:
    return _agent(request).status()


@router.get("/local/{aggregate_id:path}", summary="Read from the local projection")
async def local_read(request: Request, aggregate_id: str) -> dict[str, Any]:
    """Read an aggregate from the local cache.

    The result is identical whether or not the fabric is reachable, which
    is a hard requirement of the degraded mode rather than a best effort.
    """
    cached = _agent(request).read(aggregate_id)
    if cached is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": f"no local state for {aggregate_id!r}"}},
        )
    return {"entity": cached, "source": "local-projection-cache"}


@router.post("/sync", summary="Reconcile with the fabric")
async def sync(request: Request) -> dict[str, Any]:
    """Attempt one reconciliation cycle.

    A reconcile is a negotiation with the fabric, not a heartbeat, so it is
    triggered explicitly rather than run on a timer.
    """
    agent = _agent(request)
    if not agent.fabric_url:
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "not_configured", "message": "no fabric URL is configured"}},
        )

    report = agent.sync(lambda url, payload: http_transport(url, payload))
    return report.to_dict()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()

    node_id = os.environ.get("NGSH_EDGE_NODE_ID") or f"edge:{resolved.deployment_zone}"

    # The edge queue is a separate store from the platform database. It is
    # the node's own durable buffer and is never shared.
    queue_path = Path(
        os.environ.get("NGSH_EDGE_QUEUE_PATH")
        or Path(resolved.sqlite_path or "data/ngsh.db").parent / "edge-queue.db"
    )

    app = create_service(
        SERVICE_NAME,
        settings=resolved,
        description=DESCRIPTION,
        routers=[router],
        tags=[
            {"name": "edge", "description": "Local capture, reads and reconciliation."},
            {"name": "operations", "description": "Health and metadata."},
        ],
    )
    app.state.agent = EdgeAgent(
        node_id,
        EdgeQueue(queue_path, node_id=node_id),
        fabric_url=resolved.fabric_url,
    )
    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
