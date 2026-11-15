"""Interface register: the seven external interfaces, as a checked catalogue.

The PSDD names IF-1 to IF-7. A register that lives in a slide deck drifts from
the platform the first time an interface is deferred. This module keeps the
register in one place, checks that it is complete and that every direction is
one the platform actually supports, and records the programme-office decision
that IF-3 is inbound-only in v1.

The register is metadata, not programme facts: the *messages* are recorded in
the event log when they arrive. What this module guarantees is that the
platform can always say which interfaces it claims, in which direction, and
which of them are incomplete.
"""

from __future__ import annotations

from typing import Any

from .errors import ValidationError

REGISTER_VERSION = "1.0.0"

DIRECTIONS = {"IN", "OUT", "BI-DIR"}
STATUSES = {"ACTIVE", "PLANNED", "INBOUND_ONLY", "DEFERRED"}

REQUIRED_INTERFACE_FIELDS = (
    "id",
    "name",
    "direction",
    "purpose",
    "protocol",
    "counterpart",
    "status",
    "owner",
)

#: The seven interfaces named by PSDD section 7. IF-3 carries the recorded
#: decision that NGSH ingests SDA/PWSA custody data but does not send to it in
#: v1; that is a programme-office position, not an implementation gap.
INTERFACE_REGISTER: tuple[dict[str, Any], ...] = (
    {
        "id": "IF-1",
        "name": "Prime PLM/MES APIs",
        "direction": "BI-DIR",
        "purpose": "Sync part, BOM and process data with Teamcenter/Windchill/SAP-class systems.",
        "protocol": "REST + STEP AP242 / OPC-UA",
        "counterpart": "Prime contractor PLM/MES",
        "status": "PLANNED",
        "owner": "Pillar B",
        "classificationBoundary": "CUI",
    },
    {
        "id": "IF-2",
        "name": "MDA/Aegis systems",
        "direction": "BI-DIR",
        "purpose": "Ingest threat tracks and engagement results; export scenario definitions for BMC3 test.",
        "protocol": "Link-16 / MTConnect-style message bus",
        "counterpart": "MDA / Aegis",
        "status": "PLANNED",
        "owner": "Pillar F",
        "classificationBoundary": "SECRET",
    },
    {
        "id": "IF-3",
        "name": "SDA PWSA / HBTSS data feeds",
        "direction": "IN",
        "purpose": "Ingest tracking-layer custody and fire-control data quality.",
        "protocol": "SDA track message",
        "counterpart": "SDA / PWSA",
        "status": "INBOUND_ONLY",
        "owner": "Pillar F",
        "classificationBoundary": "SECRET",
        "note": "v1 is inbound-only; no outbound path to SDA/PWSA is implemented.",
    },
    {
        "id": "IF-4",
        "name": "Range instrumentation",
        "direction": "BI-DIR",
        "purpose": "Exchange test article manifests, telemetry and schedules.",
        "protocol": "REST + TDMS/HDF5",
        "counterpart": "National range operators",
        "status": "PLANNED",
        "owner": "Pillar C",
        "classificationBoundary": "CUI",
    },
    {
        "id": "IF-5",
        "name": "University LMS / AR-VR clients",
        "direction": "OUT",
        "purpose": "Deliver curriculum packages and training environments.",
        "protocol": "LTI 1.3 + glTF/USDZ",
        "counterpart": "Academic partners",
        "status": "ACTIVE",
        "owner": "Pillar E",
        "classificationBoundary": "UNCLASSIFIED",
    },
    {
        "id": "IF-6",
        "name": "Government identity (PIV/ICAM)",
        "direction": "IN",
        "purpose": "Authenticate users and verify clearance.",
        "protocol": "SAML 2.0 / OIDC + PIV",
        "counterpart": "DoD ICAM",
        "status": "PLANNED",
        "owner": "Platform security",
        "classificationBoundary": "CUI",
    },
    {
        "id": "IF-7",
        "name": "Analytics/BI",
        "direction": "OUT",
        "purpose": "Programme-office dashboards and Congressional reporting metrics.",
        "protocol": "REST + OData",
        "counterpart": "Programme office / BI consumers",
        "status": "ACTIVE",
        "owner": "Platform analytics",
        "classificationBoundary": "CUI",
    },
)


def _problems(entry: dict[str, Any]) -> list[str]:
    if not isinstance(entry, dict):
        return ["interface entry must be an object"]
    problems = [
        f"{field} is required"
        for field in REQUIRED_INTERFACE_FIELDS
        if entry.get(field) in (None, "", [], {})
    ]
    direction = str(entry.get("direction") or "").upper()
    if direction and direction not in DIRECTIONS:
        problems.append(f"unknown direction {direction!r}; expected {sorted(DIRECTIONS)}")
    status = str(entry.get("status") or "").upper()
    if status and status not in STATUSES:
        problems.append(f"unknown status {status!r}; expected {sorted(STATUSES)}")
    return problems


def interface_register_report(entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Validate the register and report what it does not cover.

    The expected id set is derived from the PSDD, so a register missing IF-6 is
    reported as incomplete rather than passing because it is internally
    consistent.
    """
    catalogue = [dict(entry) for entry in (entries if entries is not None else INTERFACE_REGISTER)]
    expected = {f"IF-{number}" for number in range(1, 8)}
    identifiers = [str(entry.get("id")) for entry in catalogue if entry.get("id")]
    duplicates = sorted({item for item in identifiers if identifiers.count(item) > 1})
    missing = sorted(expected - set(identifiers))
    unexpected = sorted(set(identifiers) - expected)

    problems: list[dict[str, Any]] = []
    for entry in catalogue:
        entry_problems = _problems(entry)
        if entry_problems:
            problems.append({"id": entry.get("id"), "problems": entry_problems})

    inbound_only = [
        entry["id"]
        for entry in catalogue
        if str(entry.get("status") or "").upper() == "INBOUND_ONLY"
    ]
    active = [entry["id"] for entry in catalogue if str(entry.get("status") or "").upper() == "ACTIVE"]
    return {
        "version": REGISTER_VERSION,
        "interfaces": catalogue,
        "count": len(catalogue),
        "expectedCount": len(expected),
        "missing": missing,
        "unexpected": unexpected,
        "duplicates": duplicates,
        "problems": problems,
        "inboundOnly": inbound_only,
        "active": active,
        "complete": not (missing or unexpected or duplicates or problems),
        "blockedOutbound": inbound_only,
    }


def interface_check(interface_id: str, entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Fetch one interface and state whether it is usable for a message."""
    catalogue = entries if entries is not None else INTERFACE_REGISTER
    entry = next((item for item in catalogue if item.get("id") == interface_id), None)
    if entry is None:
        raise ValidationError(f"no interface {interface_id!r} in the register")
    problems = _problems(entry)
    status = str(entry.get("status") or "").upper()
    return {
        "interface": entry,
        "usable": not problems and status in {"ACTIVE", "PLANNED", "INBOUND_ONLY"},
        "outboundBlocked": status == "INBOUND_ONLY",
        "problems": problems,
    }


def outbound_allowed(interface_id: str, entries: list[dict[str, Any]] | None = None) -> bool:
    """Whether the platform may send on this interface in v1."""
    catalogue = entries if entries is not None else INTERFACE_REGISTER
    entry = next((item for item in catalogue if item.get("id") == interface_id), None)
    if entry is None:
        return False
    if str(entry.get("status") or "").upper() in {"INBOUND_ONLY", "DEFERRED"}:
        return False
    return str(entry.get("direction") or "").upper() in {"OUT", "BI-DIR"}
