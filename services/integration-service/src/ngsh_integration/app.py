"""NGSH integration service: the external interface register, enforced.

The seven PSDD interfaces are declared in one checked catalogue. The service is
not an ESB: it does not route messages. What it does is make an interface's
claimed direction and status *operational*:

* a caller can ask whether an interface is usable and in which direction;
* an outbound attempt on an interface recorded as inbound-only is refused, with
  the programme-office decision named - the v1 position on IF-3;
* the register reports itself incomplete when an interface from the PSDD is
  missing, rather than passing because it is internally consistent.

Keeping the register here, and checking it at the boundary, means the claim in
a briefing and the behaviour of the platform cannot diverge silently.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Body, FastAPI, Request
from fastapi.responses import JSONResponse
from ngsh_core.app import create_service
from ngsh_core.config import Settings, load_settings
from ngsh_core.errors import ValidationError
from ngsh_core.integration import (
    INTERFACE_REGISTER,
    interface_check,
    interface_register_report,
    outbound_allowed,
)

SERVICE_NAME = "integration"
DESCRIPTION = (
    "The external interface register (IF-1 to IF-7), its completeness, and the "
    "enforcement of each interface's direction and status."
)

router = APIRouter(prefix="/v1", tags=["integration"])


def _register(request: Request) -> list[dict[str, Any]]:
    return request.app.state.interfaces


@router.get("/interfaces", summary="The interface register and its completeness")
async def interfaces(request: Request) -> dict[str, Any]:
    """Report every interface, and what the register does not cover."""
    return interface_register_report(_register(request))


@router.get("/interfaces/{interface_id}", summary="Check one interface")
async def interface(request: Request, interface_id: str) -> dict[str, Any]:
    return interface_check(interface_id, _register(request))


@router.get("/interfaces/{interface_id}/outbound", summary="Is outbound traffic allowed?")
async def outbound(request: Request, interface_id: str) -> dict[str, Any]:
    """Answer the single question a sender has, with the reason."""
    allowed = outbound_allowed(interface_id, _register(request))
    entry = next(
        (item for item in _register(request) if item.get("id") == interface_id),
        None,
    )
    return {
        "interfaceId": interface_id,
        "outboundAllowed": allowed,
        "status": (entry or {}).get("status"),
        "direction": (entry or {}).get("direction"),
        "reason": None
        if allowed
        else (
            "the interface is recorded as inbound-only or deferred in v1"
            if entry is not None
            else "no such interface is registered"
        ),
    }


@router.post("/outbound", summary="Submit an outbound message for an interface")
async def submit_outbound(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    """Accept or refuse an outbound message at the boundary.

    An accepted message receives a deterministic transport key derived from the
    interface, its body and the correlation id, so a retried submission is
    recognisable. A refused message names the interface decision that stopped
    it; it is never silently dropped.
    """
    interface_id = body.get("interfaceId")
    if not isinstance(interface_id, str) or not interface_id:
        raise ValidationError("'interfaceId' is required")
    payload = body.get("payload")
    if not isinstance(payload, dict):
        raise ValidationError("'payload' must be an object")
    correlation_id = body.get("correlationId")
    if correlation_id is not None and not isinstance(correlation_id, str):
        raise ValidationError("'correlationId' must be a string")

    entry = next(
        (item for item in _register(request) if item.get("id") == interface_id), None
    )
    if entry is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "not_found",
                    "message": f"no interface {interface_id!r} in the register",
                }
            },
        )

    if not outbound_allowed(interface_id, _register(request)):
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "outbound_blocked",
                    "message": (
                        f"interface {interface_id} does not permit outbound traffic in v1"
                    ),
                    "context": {
                        "interfaceId": interface_id,
                        "direction": entry.get("direction"),
                        "status": entry.get("status"),
                        "note": entry.get("note"),
                    },
                }
            },
        )

    digest = hashlib.sha256(
        json.dumps(
            {
                "interfaceId": interface_id,
                "correlationId": correlation_id,
                "payload": payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return JSONResponse(
        status_code=202,
        content={
            "interfaceId": interface_id,
            "accepted": True,
            "transportKey": f"MSG:{digest[:26].upper()}",
            "correlationId": correlation_id,
            "direction": entry.get("direction"),
            "protocol": entry.get("protocol"),
        },
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()

    app = create_service(
        SERVICE_NAME,
        settings=resolved,
        description=DESCRIPTION,
        routers=[router],
        tags=[
            {"name": "integration", "description": "External interface register and enforcement."},
            {"name": "operations", "description": "Health and metadata."},
        ],
    )
    app.state.interfaces = [dict(entry) for entry in INTERFACE_REGISTER]
    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
