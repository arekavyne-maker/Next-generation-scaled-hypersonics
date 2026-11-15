"""Portable interface adapters for IF-1 to IF-7.

The integration register states what each PSDD interface is. This module makes
the statement executable. Every interface has:

* a direction check (a one-way interface refuses the other direction);
* a payload contract, so an empty or malformed message is refused at the
  boundary rather than accepted as a receipt;
* a **simulated counterpart** that returns a deterministic receipt with a
  content-addressed transport key.

The simulated counterpart is not a pretend success. It validates the payload,
records what it accepted and returns a key that a retry can be recognised by.
A real deployment replaces the counterpart with the programme's gateway; the
contract, the direction rule and the receipt shape stay the same.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from .errors import ValidationError
from .identity import verify_assertion
from .integration import INTERFACE_REGISTER

#: The interfaces this build can exchange messages with. IF-3 is present but
#: inbound-only by the recorded programme decision.
ADAPTER_INTERFACES = tuple(entry["id"] for entry in INTERFACE_REGISTER)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _entry(interface_id: str) -> dict[str, Any]:
    for entry in INTERFACE_REGISTER:
        if entry["id"] == interface_id:
            return entry
    raise ValidationError(f"no interface {interface_id!r} in the register")


def _direction_allowed(entry: dict[str, Any], direction: str) -> bool:
    normalized = direction.strip().upper()
    if normalized not in {"INBOUND", "OUTBOUND"}:
        raise ValidationError("'direction' must be INBOUND or OUTBOUND")
    if normalized == "INBOUND":
        return entry["direction"] in {"IN", "BI-DIR"}
    return entry["direction"] in {"OUT", "BI-DIR"}


def _require(payload: dict[str, Any], key: str, kind: type | tuple[type, ...] | None = None) -> Any:
    if key not in payload:
        raise ValidationError(f"interface payload requires {key!r}")
    value = payload[key]
    if kind is not None and not isinstance(value, kind):
        raise ValidationError(f"interface payload {key!r} has the wrong type")
    return value


def _validate(interface_id: str, payload: dict[str, Any], direction: str) -> dict[str, Any]:
    """Validate one message against its interface contract.

    The checks are intentionally small and explicit. A permissive adapter that
    accepts anything would move failure to the far side of a classification
    boundary, where it is much more expensive to diagnose.
    """
    if not isinstance(payload, dict):
        raise ValidationError("interface payload must be an object")

    if interface_id == "IF-1":
        _require(payload, "operation", str)
        if payload["operation"].upper() not in {
            "UPSERT_PART",
            "UPSERT_BOM",
            "UPSERT_PROCESS_PLAN",
            "SYNC",
        }:
            raise ValidationError("IF-1 operation is not a PLM/MES operation")
        records = _require(payload, "records", list)
        if not records:
            raise ValidationError("IF-1 records must not be empty")
        for record in records:
            if not isinstance(record, dict) or not record.get("id"):
                raise ValidationError("every IF-1 record needs an id")
        return {"records": len(records)}

    if interface_id == "IF-2":
        if direction == "OUTBOUND":
            scenario = _require(payload, "scenario", dict)
            if not scenario.get("scenarioId") and not scenario.get("name"):
                raise ValidationError("IF-2 outbound scenario needs a scenarioId or name")
            return {"scenarioId": scenario.get("scenarioId") or scenario.get("name")}
        tracks = _require(payload, "tracks", list)
        if not tracks:
            raise ValidationError("IF-2 inbound tracks must not be empty")
        return {"tracks": len(tracks)}

    if interface_id == "IF-3":
        if direction == "OUTBOUND":
            raise ValidationError("IF-3 is inbound-only in v1; no outbound path is implemented")
        tracks = _require(payload, "tracks", list)
        if not tracks:
            raise ValidationError("IF-3 tracks must not be empty")
        for track in tracks:
            if not isinstance(track, dict) or not track.get("trackId"):
                raise ValidationError("every IF-3 track needs a trackId")
        return {"tracks": len(tracks)}

    if interface_id == "IF-4":
        present = [key for key in ("manifest", "telemetry", "schedule") if key in payload]
        if not present:
            raise ValidationError("IF-4 payload needs a manifest, telemetry or schedule block")
        for key in present:
            if not isinstance(payload[key], (dict, list)):
                raise ValidationError(f"IF-4 {key!r} must be an object or list")
        return {"blocks": present}

    if interface_id == "IF-5":
        package = _require(payload, "package", dict)
        modules = _require(package, "modules", list)
        if not modules:
            raise ValidationError("IF-5 package must contain modules")
        return {"packageId": package.get("packageId") or package.get("title"), "modules": len(modules)}

    if interface_id == "IF-6":
        assertion = _require(payload, "assertion", dict)
        attributes = verify_assertion(assertion)
        return {
            "subjectId": attributes.get("subjectId"),
            "clearance": attributes.get("clearance"),
            "citizenship": attributes.get("citizenship"),
            "expiresAt": assertion.get("expiresAt"),
        }

    if interface_id == "IF-7":
        report = _require(payload, "report", dict)
        if not report.get("name"):
            raise ValidationError("IF-7 report needs a name")
        metrics = report.get("metrics")
        if metrics is None:
            raise ValidationError("IF-7 report needs metrics")
        return {"report": report["name"], "metricCount": len(metrics)}

    raise ValidationError(f"interface {interface_id!r} has no adapter contract")


def deliver(
    interface_id: str,
    *,
    direction: str,
    payload: dict[str, Any],
    correlation_id: str | None = None,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Validate and accept one message for an interface.

    Returns the receipt the caller stores. The transport key is a digest of the
    interface, direction, correlation id and canonical payload, so a retry of
    the same message is recognisable and a changed payload is not.
    """
    entry = _entry(interface_id)
    normalized = direction.strip().upper()
    if not _direction_allowed(entry, normalized):
        raise ValidationError(
            f"{interface_id} does not permit {normalized.lower()} traffic in v1",
            detail={
                "interfaceId": interface_id,
                "direction": entry["direction"],
                "status": entry["status"],
                "note": entry.get("note"),
            },
        )

    summary = _validate(interface_id, payload, normalized)
    digest = _digest(
        {
            "interfaceId": interface_id,
            "direction": normalized,
            "correlationId": correlation_id,
            "payload": payload,
        }
    )
    return {
        "interfaceId": interface_id,
        "name": entry["name"],
        "direction": normalized,
        "counterpart": entry["counterpart"],
        "protocol": entry["protocol"],
        "status": "ACCEPTED" if normalized == "INBOUND" else "DELIVERED",
        "transportKey": f"MSG:{digest[:26].upper()}",
        "payloadDigest": digest,
        "correlationId": correlation_id,
        "validation": summary,
        "recordedAt": recorded_at or datetime.now(UTC).isoformat(),
        "simulated": True,
    }


def adapter_catalog(entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Every interface with its adapter capabilities and readiness."""
    register = entries if entries is not None else [dict(entry) for entry in INTERFACE_REGISTER]
    rows: list[dict[str, Any]] = []
    for entry in register:
        interface_id = entry.get("id")
        if interface_id not in ADAPTER_INTERFACES:
            continue
        inbound = entry.get("direction") in {"IN", "BI-DIR"}
        outbound = entry.get("direction") in {"OUT", "BI-DIR"}
        rows.append(
            {
                "interfaceId": interface_id,
                "name": entry.get("name"),
                "direction": entry.get("direction"),
                "status": entry.get("status"),
                "protocol": entry.get("protocol"),
                "counterpart": entry.get("counterpart"),
                "inbound": inbound,
                "outbound": outbound,
                "inboundEndpoint": f"/v1/interfaces/{interface_id}/inbound" if inbound else None,
                "outboundEndpoint": f"/v1/interfaces/{interface_id}/outbound" if outbound else None,
                "adapter": "simulated-counterpart",
                "note": entry.get("note"),
            }
        )
    return {
        "adapters": rows,
        "count": len(rows),
        "inboundCount": sum(1 for row in rows if row["inbound"]),
        "outboundCount": sum(1 for row in rows if row["outbound"]),
        "simulated": True,
    }


def probe(interface_id: str) -> dict[str, Any]:
    """A deterministic handshake for one interface.

    A probe says whether this build can accept or emit a message for the
    interface, not whether the real counterpart is reachable. That distinction
    is in the payload so an operator cannot mistake a simulated probe for a
    network test.
    """
    entry = _entry(interface_id)
    catalog = {row["interfaceId"]: row for row in adapter_catalog()["adapters"]}
    row = catalog.get(interface_id)
    return {
        "interfaceId": interface_id,
        "reachable": False,
        "simulated": True,
        "counterpart": entry["counterpart"],
        "protocol": entry["protocol"],
        "inbound": bool(row and row["inbound"]),
        "outbound": bool(row and row["outbound"]),
        "note": ("simulated counterpart; replace with the programme gateway for a live probe"),
    }
