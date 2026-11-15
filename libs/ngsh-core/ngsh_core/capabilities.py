"""The capability matrix the platform reports about itself.

The PSDD names 34 capability ids across eight pillars and seven external
interfaces. Keeping that list in one checked module means the console, the
gateway and the documentation cannot drift into claiming different scopes.

``status`` is deliberately about the *reference implementation*:

* ``IMPLEMENTED`` — a runnable path exists and is covered by a test;
* ``INBOUND_ONLY`` — the interface is intentionally one-way in v1;
* ``ADAPTER`` — a simulated/portable adapter is provided; a real counterpart
  is supplied by the programme.

It is not an accreditation statement. ``limitations`` records what a real
deployment still has to connect or certify.
"""

from __future__ import annotations

from typing import Any

from .integration import INTERFACE_REGISTER

CAPABILITIES: tuple[dict[str, Any], ...] = (
    # Pillar A — MBSE and the digital thread core
    {
        "id": "A-1",
        "pillar": "A",
        "name": "Digital twin backbone",
        "service": "architecture",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/baselines", "/v1/baselines/{id}/verify"],
        "limitations": [],
    },
    {
        "id": "A-2",
        "pillar": "A",
        "name": "Modularity engine",
        "service": "architecture",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/variants/generate", "/v1/variants/{id}/core-error"],
        "limitations": ["Library rules are supplied by the programme; no external PLM sync."],
    },
    {
        "id": "A-3",
        "pillar": "A",
        "name": "Requirements-to-test traceability",
        "service": "architecture",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/requirements/{id}/coverage", "/v1/requirements/gaps"],
        "limitations": [],
    },
    {
        "id": "A-4",
        "pillar": "A",
        "name": "Technology insertion planner",
        "service": "architecture",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/insertion/assess"],
        "limitations": ["Maturity records must be maintained by the programme."],
    },
    {
        "id": "A-5",
        "pillar": "A",
        "name": "Digital engineering SaaS",
        "service": "architecture",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/icds/generate", "/v1/sysml/export", "/v1/sysml/import"],
        "limitations": ["SysML v2 is exchanged as text; the authoring UI is the console."],
    },
    # Pillar B — manufacturing and materials
    {
        "id": "B-1",
        "pillar": "B",
        "name": "Defense MES",
        "service": "manufacturing",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/travellers", "/v1/process-runs", "/v1/genealogy/{id}"],
        "limitations": ["Prime PLM/MES connect through IF-1."],
    },
    {
        "id": "B-2",
        "pillar": "B",
        "name": "CMC process characterisation",
        "service": "manufacturing",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/drift", "/v1/process-runs"],
        "limitations": ["Microstructure models are supplied as process evidence."],
    },
    {
        "id": "B-3",
        "pillar": "B",
        "name": "Test capability management",
        "service": "testlab",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/campaigns", "/v1/campaigns/{id}/curation"],
        "limitations": ["Range coordination connects through IF-4."],
    },
    {
        "id": "B-4",
        "pillar": "B",
        "name": "Rate and cost simulation",
        "service": "manufacturing",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/simulate-rate", "/v1/production/simulate"],
        "limitations": ["Simulation parameters come from the production baseline."],
    },
    # Pillar C — test, evaluation and flight data
    {
        "id": "C-1",
        "pillar": "C",
        "name": "Unified test data lake",
        "service": "ingest",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/lakehouse/objects", "/v1/lakehouse/objects/{digest}/verify"],
        "limitations": [
            "Object storage is local content-addressed storage; swap the backend for the accredited store."
        ],
    },
    {
        "id": "C-2",
        "pillar": "C",
        "name": "Automated reduction and anomaly detection",
        "service": "testlab",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/anomalies/detect", "/v1/test-results"],
        "limitations": ["Detection is deterministic statistics; domain ML models are supplied by the lab."],
    },
    {
        "id": "C-3",
        "pillar": "C",
        "name": "Twin validation loop",
        "service": "testlab",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/twin-validation", "/v1/models/{id}/regenerate"],
        "limitations": ["Model regeneration is a deterministic correction, not a CFD solver."],
    },
    {
        "id": "C-4",
        "pillar": "C",
        "name": "Campaign management",
        "service": "testlab",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/campaigns", "/v1/schedule/optimise"],
        "limitations": ["Instrumentation manifests connect through IF-4."],
    },
    # Pillar D — supply and production scaling
    {
        "id": "D-1",
        "pillar": "D",
        "name": "Multi-tier visibility",
        "service": "supply",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/supply-risks", "/v1/suppliers"],
        "limitations": ["Supplier portals connect through IF-1."],
    },
    {
        "id": "D-2",
        "pillar": "D",
        "name": "Foreign dependency mapping",
        "service": "supply",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/reconstitutes", "/v1/supply-risks"],
        "limitations": [],
    },
    {
        "id": "D-3",
        "pillar": "D",
        "name": "Surge readiness twin",
        "service": "supply",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/surge"],
        "limitations": ["Verified surge evidence is produced by Pillar H."],
    },
    # Pillar E — cleared workforce
    {
        "id": "E-1",
        "pillar": "E",
        "name": "Digital-twin training",
        "service": "workforce",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/training/scenarios", "/v1/training/coverage"],
        "limitations": ["The browser training viewer replaces AR/VR hardware locally."],
    },
    {
        "id": "E-2",
        "pillar": "E",
        "name": "Replicable curriculum engine",
        "service": "workforce",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/curriculum/packages"],
        "limitations": ["Delivery to an LMS connects through IF-5."],
    },
    {
        "id": "E-3",
        "pillar": "E",
        "name": "Skills credentialing",
        "service": "workforce",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/credentials", "/v1/work-authorisation"],
        "limitations": ["Identity assertions connect through IF-6."],
    },
    {
        "id": "E-4",
        "pillar": "E",
        "name": "Workforce demand model",
        "service": "workforce",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/workforce/gap"],
        "limitations": ["Classified demand is an explicit programme input."],
    },
    {
        "id": "E-5",
        "pillar": "E",
        "name": "Industry-academia sandbox",
        "service": "workforce",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/extracts"],
        "limitations": ["Extracts leave only through an approved IF-5 channel."],
    },
    # Pillar F — counter-hypersonic kill chain
    {
        "id": "F-1",
        "pillar": "F",
        "name": "Threat digital twins",
        "service": "engagement",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/threats", "/v1/threat-models"],
        "limitations": ["Intel-derived model libraries are supplied by the threat community."],
    },
    {
        "id": "F-2",
        "pillar": "F",
        "name": "Kill-chain simulator",
        "service": "engagement",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/scenarios/{id}/batch", "/v1/kill-chain"],
        "limitations": [],
    },
    {
        "id": "F-3",
        "pillar": "F",
        "name": "Fire-control data quality scoring",
        "service": "engagement",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/fire-control/measure", "/v1/fire-control/quality"],
        "limitations": ["Feeds connect through IF-3 inbound."],
    },
    {
        "id": "F-4",
        "pillar": "F",
        "name": "Interim architecture workbench",
        "service": "engagement",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/candidates/evaluate"],
        "limitations": [],
    },
    {
        "id": "F-5",
        "pillar": "F",
        "name": "Golden Dome readiness",
        "service": "engagement",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/plugins", "/v1/plugins/{id}/run"],
        "limitations": [
            "Plug-ins are trusted in-process handlers; native sandboxing is a deployment control."
        ],
    },
    {
        "id": "F-6",
        "pillar": "F",
        "name": "Red/blue co-simulation",
        "service": "engagement",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/co-simulation"],
        "limitations": [],
    },
    # Pillar G — test enterprise and M&S federation
    {
        "id": "G-1",
        "pillar": "G",
        "name": "Virtual test range",
        "service": "thread",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/datasets", "/v1/datasets/{id}/lineage"],
        "limitations": ["Physics M&S federates through IF-4; the catalogue and lineage are here."],
    },
    {
        "id": "G-2",
        "pillar": "G",
        "name": "Campaign digital twin",
        "service": "testlab",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/range-capacity", "/v1/schedule/optimise"],
        "limitations": [],
    },
    {
        "id": "G-3",
        "pillar": "G",
        "name": "Automated model validation",
        "service": "testlab",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/twin-validation", "/v1/models/{id}/regenerate"],
        "limitations": ["Model physics is external; the platform records and versions the change."],
    },
    {
        "id": "G-4",
        "pillar": "G",
        "name": "Fidelity registry",
        "service": "testlab",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/fidelity/registry", "/v1/fidelity/{id}/drift"],
        "limitations": [],
    },
    # Pillar H — industrial surge and affordability
    {
        "id": "H-1",
        "pillar": "H",
        "name": "Surge readiness command",
        "service": "industrial",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/surge-readiness"],
        "limitations": ["Twin runs are supplied by the production simulation."],
    },
    {
        "id": "H-2",
        "pillar": "H",
        "name": "Reconstitution planning",
        "service": "industrial",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/reconstitution/assess"],
        "limitations": ["Measured times require an executed exercise."],
    },
    {
        "id": "H-3",
        "pillar": "H",
        "name": "Affordability engineering",
        "service": "industrial",
        "status": "IMPLEMENTED",
        "endpoints": ["/v1/affordability/trace", "/v1/affordability/rate-curve"],
        "limitations": ["Cost data comes from the programme cost office."],
    },
)

#: Interfaces whose v1 position is intentionally one-way. The register is the
#: authority; this tuple exists so a caller can ask the matrix without parsing
#: notes.
INBOUND_ONLY_INTERFACES = ("IF-3",)


def _interface_status(entry: dict[str, Any]) -> str:
    if entry.get("id") in INBOUND_ONLY_INTERFACES:
        return "INBOUND_ONLY"
    return "ADAPTER"


def capability_matrix() -> dict[str, Any]:
    """Every PSDD capability, its owning service and its reference status."""
    pillars: dict[str, list[dict[str, Any]]] = {}
    for row in CAPABILITIES:
        pillars.setdefault(row["pillar"], []).append(dict(row))
    return {
        "capabilities": [dict(row) for row in CAPABILITIES],
        "count": len(CAPABILITIES),
        "pillars": pillars,
        "pillarCount": len(pillars),
        "interfaces": [
            {
                "id": entry["id"],
                "name": entry["name"],
                "direction": entry["direction"],
                "status": _interface_status(entry),
                "protocol": entry["protocol"],
                "counterpart": entry["counterpart"],
                "note": entry.get("note"),
            }
            for entry in INTERFACE_REGISTER
        ],
        "interfaceCount": len(INTERFACE_REGISTER),
    }


def capability(capability_id: str) -> dict[str, Any] | None:
    """Look up one capability by id."""
    for row in CAPABILITIES:
        if row["id"] == capability_id:
            return dict(row)
    return None
