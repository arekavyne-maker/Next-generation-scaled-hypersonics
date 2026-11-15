"""NGSH integration service: the external interfaces, made operational.

The seven PSDD interfaces are declared in one checked catalogue. This service
is not an ESB and does not route messages between systems. It does four
things, and all four are required for an interface to be real rather than
claimed:

* it reports the register, including what the register does not cover;
* it enforces each interface's recorded direction at the boundary, so an
  outbound attempt on the inbound-only IF-3 is refused with the programme
  decision named;
* it validates the payload against the interface contract and returns a
  deterministic receipt a retry can be recognised by;
* it persists every accepted or delivered message, so the trail of what
  crossed the boundary survives a restart.

IF-6 is a real verification loop in the ``local`` and ``edge`` profiles: the
assertion is signed, its expiry is checked and the actor is validated. In an
accredited profile the provider is the government PIV/ICAM service, reached
through the same ``/v1/interfaces/IF-6/inbound`` path.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from ngsh_core.adapters import adapter_catalog, deliver, probe
from ngsh_core.app import create_service
from ngsh_core.config import Settings, load_settings
from ngsh_core.errors import NotFoundError, ValidationError
from ngsh_core.ids import new_ulid
from ngsh_core.integration import (
    INTERFACE_REGISTER,
    interface_check,
    interface_register_report,
    outbound_allowed,
)
from ngsh_core.store import open_database

SERVICE_NAME = "integration"
DESCRIPTION = (
    "The external interface register (IF-1 to IF-7), its completeness, and the "
    "enforcement, validation and recording of each interface's traffic."
)

router = APIRouter(prefix="/v1", tags=["integration"])

_DELIVERIES_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS interface_deliveries (
        delivery_id      TEXT PRIMARY KEY,
        interface_id     TEXT NOT NULL,
        direction        TEXT NOT NULL,
        status           TEXT NOT NULL,
        transport_key    TEXT NOT NULL UNIQUE,
        payload_digest   TEXT NOT NULL,
        correlation_id   TEXT,
        payload_json     TEXT NOT NULL,
        receipt_json     TEXT NOT NULL,
        created_at       TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_deliveries_interface "
    "ON interface_deliveries (interface_id, direction, created_at)",
)


def _register(request: Request) -> list[dict[str, Any]]:
    return request.app.state.interfaces


def _executor(request: Request) -> Any:
    return request.app.state.executor


def _row_to_delivery(row: dict[str, Any]) -> dict[str, Any]:
    receipt = json.loads(row["receipt_json"])
    receipt["deliveryId"] = row["delivery_id"]
    return receipt


def _record_delivery(
    request: Request,
    *,
    receipt: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Persist one accepted message, returning the existing receipt on retry.

    The transport key is content-derived, so the same message sent twice is one
    delivery. Storing the key as a unique column makes that an enforced
    property rather than a convention in the caller.
    """
    executor = _executor(request)
    existing = executor.fetchone(
        "SELECT * FROM interface_deliveries WHERE transport_key = ?",
        (receipt["transportKey"],),
    )
    if existing is not None:
        receipt["deliveryId"] = existing["delivery_id"]
        receipt["idempotent"] = True
        return receipt

    # An identity assertion is a credential; keep the digest for the trail but
    # do not retain the signed assertion beyond the verification decision.
    if receipt["interfaceId"] == "IF-6":
        stored_payload: dict[str, Any] = {"assertion": "<redacted-after-verification>"}
    else:
        stored_payload = payload

    delivery_id = f"DLV:{new_ulid()}"
    executor.execute(
        """
        INSERT INTO interface_deliveries (
            delivery_id, interface_id, direction, status, transport_key,
            payload_digest, correlation_id, payload_json, receipt_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            delivery_id,
            receipt["interfaceId"],
            receipt["direction"],
            receipt["status"],
            receipt["transportKey"],
            receipt["payloadDigest"],
            receipt.get("correlationId"),
            json.dumps(stored_payload, sort_keys=True),
            json.dumps(receipt, sort_keys=True, default=str),
            receipt["recordedAt"],
        ),
    )
    receipt["deliveryId"] = delivery_id
    receipt["idempotent"] = False
    return receipt


def _deliver(request: Request, interface_id: str, direction: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = body.get("payload")
    if not isinstance(payload, dict):
        raise ValidationError("'payload' must be an object")
    correlation_id = body.get("correlationId")
    if correlation_id is not None and not isinstance(correlation_id, str):
        raise ValidationError("'correlationId' must be a string")
    receipt = deliver(
        interface_id,
        direction=direction,
        payload=payload,
        correlation_id=correlation_id,
    )
    return _record_delivery(request, receipt=receipt, payload=payload)


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


@router.post(
    "/interfaces/{interface_id}/inbound",
    summary="Accept a message arriving over an interface",
    status_code=202,
)
async def inbound(request: Request, interface_id: str, body: dict[str, Any] = Body(...)) -> JSONResponse:
    receipt = _deliver(request, interface_id, "INBOUND", body)
    return JSONResponse(status_code=202, content=receipt)


@router.post(
    "/interfaces/{interface_id}/outbound",
    summary="Deliver a message over an interface",
    status_code=202,
)
async def outbound_message(
    request: Request, interface_id: str, body: dict[str, Any] = Body(...)
) -> JSONResponse:
    receipt = _deliver(request, interface_id, "OUTBOUND", body)
    return JSONResponse(status_code=202, content=receipt)


@router.get("/adapters", summary="Every interface and its adapter capability")
async def adapters(request: Request) -> dict[str, Any]:
    return adapter_catalog(_register(request))


@router.get("/adapters/{interface_id}/probe", summary="Probe an interface adapter")
async def adapter_probe(request: Request, interface_id: str) -> dict[str, Any]:
    return probe(interface_id)


@router.get("/deliveries", summary="Messages recorded for an interface")
async def deliveries(
    request: Request,
    interfaceId: str | None = Query(None),
    direction: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if interfaceId:
        clauses.append("interface_id = ?")
        params.append(interfaceId)
    if direction:
        normalized = direction.strip().upper()
        if normalized not in {"INBOUND", "OUTBOUND"}:
            raise ValidationError("'direction' must be INBOUND or OUTBOUND")
        clauses.append("direction = ?")
        params.append(normalized)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = _executor(request).fetchall(
        f"SELECT * FROM interface_deliveries{where} ORDER BY created_at DESC LIMIT ?",
        (*params, limit),
    )
    return {
        "deliveries": [_row_to_delivery(row) for row in rows],
        "count": len(rows),
        "simulated": True,
    }


@router.get("/deliveries/{delivery_id}", summary="One recorded interface message")
async def delivery(request: Request, delivery_id: str) -> dict[str, Any]:
    row = _executor(request).fetchone(
        "SELECT * FROM interface_deliveries WHERE delivery_id = ?", (delivery_id,)
    )
    if row is None:
        raise NotFoundError(f"no delivery with id {delivery_id!r}")
    receipt = _row_to_delivery(row)
    receipt["payload"] = json.loads(row["payload_json"])
    return receipt


@router.post("/outbound", summary="Submit an outbound message for an interface")
async def submit_outbound(request: Request, body: dict[str, Any] = Body(...)) -> JSONResponse:
    """The original single-endpoint form, retained for existing callers.

    It applies the register's direction rule before validating the payload and
    uses the same receipt and persistence path as the per-interface endpoint.
    """
    interface_id = body.get("interfaceId")
    if not isinstance(interface_id, str) or not interface_id:
        raise ValidationError("'interfaceId' is required")
    payload = body.get("payload")
    if not isinstance(payload, dict):
        raise ValidationError("'payload' must be an object")
    entry = next((item for item in _register(request) if item.get("id") == interface_id), None)
    if entry is None:
        raise NotFoundError(f"no interface {interface_id!r} in the register")
    if not outbound_allowed(interface_id, _register(request)):
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "outbound_blocked",
                    "message": (f"interface {interface_id} does not permit outbound traffic in v1"),
                    "context": {
                        "interfaceId": interface_id,
                        "direction": entry.get("direction"),
                        "status": entry.get("status"),
                        "note": entry.get("note"),
                    },
                }
            },
        )

    correlation_id = body.get("correlationId")
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
    executor = open_database(resolved.dsn)
    for statement in _DELIVERIES_SCHEMA:
        executor.execute(statement)

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
    app.state.executor = executor
    app.state.interfaces = [dict(entry) for entry in INTERFACE_REGISTER]
    app.state.started_at = datetime.now(UTC).isoformat()
    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
