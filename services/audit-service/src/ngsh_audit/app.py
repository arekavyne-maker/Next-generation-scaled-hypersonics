"""NGSH audit service.

The tamper-evident record. Entries form a hash chain: each entry commits to
its predecessor, so a rewritten history breaks every subsequent hash
(ADR-0005).

What this store proves is narrow and should be stated precisely: it proves
that the recorded history has not been altered since it was written. It does
not prove that a recorded decision was correct, nor that an entry was not
written in the first place. Those are assurance questions answered by the
process around the platform, not by the hash chain.

The service is append-only through the API. No endpoint mutates or deletes a
ledger entry, and the policy set refuses such operations even from platform
administrators.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from ngsh_core.app import create_service
from ngsh_core.audit import AuditLedger
from ngsh_core.config import Settings, load_settings
from ngsh_core.errors import ValidationError
from ngsh_core.store import open_database

SERVICE_NAME = "audit"
DESCRIPTION = "The tamper-evident audit ledger. Append-only, hash-chained, verifiable on demand."

router = APIRouter(prefix="/v1", tags=["audit"])


def _ledger(request: Request) -> AuditLedger:
    return request.app.state.ledger


@router.post("/ledger", summary="Append an entry to the ledger")
async def append_entry(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Append one entry.

    The entry body is hashed together with its predecessor, so the caller
    cannot influence the chain beyond choosing what the entry says.
    """
    event_type = body.get("eventType")
    entry = body.get("entry")
    if not event_type or not isinstance(entry, dict):
        raise ValidationError("body must supply 'eventType' and an 'entry' object")
    record = _ledger(request).append(event_type, entry)
    return record.to_dict()


@router.get("/ledger", summary="Read ledger entries")
async def read_ledger(
    request: Request,
    after: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    entries = _ledger(request).read(after=after, limit=limit)
    return {
        "entries": [entry.to_dict() for entry in entries],
        "cursor": entries[-1].seq if entries else after,
        "head": _ledger(request).head(),
    }


@router.get("/ledger/verify", summary="Verify the hash chain")
async def verify(request: Request) -> dict[str, Any]:
    """Recompute the chain and report where it breaks, if it does.

    Verification is a full-chain operation by default. It is cheap relative
    to the cost of the doubt it removes, and it is the operation an assessor
    asks for.
    """
    return _ledger(request).verify().to_dict()


@router.get("/ledger/head", summary="Current chain head")
async def head(request: Request) -> dict[str, Any]:
    ledger = _ledger(request)
    return {"head": ledger.head(), "entries": ledger.count()}


@router.get("/ledger/{digest}", summary="Fetch one entry by hash")
async def get_entry(request: Request, digest: str) -> dict[str, Any]:
    entry = _ledger(request).get(digest)
    if entry is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": "no ledger entry with that hash"}},
        )
    return entry.to_dict()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()
    executor = open_database(resolved.dsn)

    app = create_service(
        SERVICE_NAME,
        settings=resolved,
        description=DESCRIPTION,
        routers=[router],
        tags=[
            {"name": "audit", "description": "Ledger append, read and verification."},
            {"name": "operations", "description": "Health and metadata."},
        ],
    )
    app.state.executor = executor
    app.state.ledger = AuditLedger(executor)
    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
