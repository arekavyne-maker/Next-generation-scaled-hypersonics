#!/usr/bin/env python3
"""Load a demonstration dataset into the NGSH fabric.

The dataset is deliberately small but complete enough to exercise the shared
ontology across both mission sides: a CMC nosecap qualification chain on the
strike side, and a threat reconstruction on the shield side. They share
entities — the same ``Requirement`` type, the same ``TestResult`` type, the
same ``Model`` type — which is the central architectural claim of the
platform stated as data.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

FABRIC = "http://127.0.0.1:8082"
THREAD = "http://127.0.0.1:8085"

ACTOR = {
    "subjectId": "usr:seed",
    "kind": "service",
    "clearance": "TOP SECRET",
    "citizenship": "US",
    "tenant": "ngsh",
    "programs": ["NGSH-SHY", "NGSH-MAVERICK"],
    "needToKnow": ["NGSH-SHY", "NGSH-MAVERICK"],
}


def call(method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise SystemExit(f"cannot reach {url} — is the stack running? Start it with 'make dev'.") from exc


def entity(
    entity_id: str,
    entity_type: str,
    attributes: dict[str, Any],
    *,
    classification: str = "CUI",
    program: str = "NGSH-SHY",
) -> dict[str, Any]:
    return {
        "id": entity_id,
        "type": entity_type,
        "tenant": "ngsh",
        "program": program,
        "version": 1,
        "createdAt": "2026-11-14T00:00:00Z",
        "updatedAt": "2026-11-14T00:00:00Z",
        "createdBy": "usr:seed",
        "updatedBy": "usr:seed",
        "provenance": {"source": "seed", "method": "seed-dataset"},
        "labels": {},
        "annotations": {},
        "deleted": False,
        "classification": {"level": classification},
        "attributes": attributes,
    }


def created(aggregate_type: str, aggregate_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventType": "entity.created",
        "aggregateType": aggregate_type,
        "aggregateId": aggregate_id,
        "sequence": 1,
        "tenant": "ngsh",
        "program": body.get("program"),
        "actor": ACTOR,
        "classification": body["classification"],
        "payload": {"entity": body},
    }


def asserted(
    relation_id: str,
    relation_type: str,
    from_ref: tuple[str, str],
    to_ref: tuple[str, str],
    *,
    classification: str = "CUI",
    program: str = "NGSH-SHY",
    confidence: float = 0.95,
) -> dict[str, Any]:
    return {
        "eventType": "entity.relation.asserted",
        "aggregateType": "Relation",
        "aggregateId": relation_id,
        "sequence": 1,
        "tenant": "ngsh",
        "program": program,
        "actor": ACTOR,
        "classification": {"level": classification},
        "payload": {
            "relation": {
                "id": relation_id,
                "type": relation_type,
                "from": {"type": from_ref[0], "id": from_ref[1]},
                "to": {"type": to_ref[0], "id": to_ref[1]},
                "tenant": "ngsh",
                "program": program,
                "classification": {"level": classification},
                "assertedAt": "2026-11-14T00:10:00Z",
                "assertedBy": "usr:seed",
                "provenance": {"source": "seed"},
                "confidence": confidence,
            }
        },
    }


def build_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    # -- strike side: CMC nosecap qualification -------------------------
    events.append(
        created(
            "System",
            "SYS:NSECAP",
            entity(
                "SYS:NSECAP",
                "System",
                {
                    "name": "Hypersonic nosecap assembly",
                    "systemType": "HYPERSONIC_WEAPON",
                    "lifecycleState": "QUALIFICATION",
                    "platform": "SHY-COMMON-CORE",
                },
            ),
        )
    )
    events.append(
        created(
            "Requirement",
            "REQ:NSECAP-TEMP",
            entity(
                "REQ:NSECAP-TEMP",
                "Requirement",
                {
                    "statement": "The nosecap shall survive 1800 K for 30 minutes without structural failure.",
                    "reqType": "PERFORMANCE",
                    "verificationMethod": "TEST",
                    "status": "BASELINED",
                    "verificationStatus": "COMPLETE",
                    "text": "The nosecap shall survive 1800 K for 30 minutes without structural failure.",
                },
            ),
        )
    )
    events.append(
        created(
            "Material",
            "MAT:CMC-PREG-0091",
            entity(
                "MAT:CMC-PREG-0091",
                "Material",
                {
                    "materialType": "CMC_PREG",
                    "lotNumber": "LOT-0091",
                    "batchId": "BATCH-0091-A",
                    "microstructureSummary": "2D orthogonal weave, 8 harness plies, carbonised at 2200 C",
                    "receivedAt": "2026-10-02T00:00:00Z",
                },
            ),
        )
    )
    events.append(
        created(
            "ProcessPlan",
            "PP:AUTOCLAVE-CMC-04",
            entity(
                "PP:AUTOCLAVE-CMC-04",
                "ProcessPlan",
                {
                    "name": "CMC autoclave cure — cycle 4",
                    "processType": "AUTOCLAVE",
                    "revision": "C",
                    "qualificationStatus": "QUALIFIED",
                    "operations": [
                        {
                            "opId": "OP-10",
                            "name": "Vacuum debulk",
                            "parameters": {"pressure_kPa": -95, "duration_min": 45},
                            "specLimits": {"pressure_kPa": [-100, -90]},
                        },
                        {
                            "opId": "OP-20",
                            "name": "Cure",
                            "parameters": {"temperature_K": 1850, "pressure_kPa": 690, "duration_min": 180},
                            "specLimits": {"temperature_K": [1820, 1880]},
                        },
                    ],
                },
            ),
        )
    )
    events.append(
        created(
            "ProcessRun",
            "PR:2026-11-00214",
            entity(
                "PR:2026-11-00214",
                "ProcessRun",
                {
                    "processPlanId": "PP:AUTOCLAVE-CMC-04",
                    "materialId": "MAT:CMC-PREG-0091",
                    "facilityId": "FAC:CMCF-1",
                    "startedAt": "2026-11-04T08:00:00Z",
                    "endedAt": "2026-11-04T13:40:00Z",
                    "measuredParameters": {"temperature_K": 1856, "pressure_kPa": 688, "duration_min": 182},
                    "disposition": "ACCEPTED",
                    "driftFlags": [],
                },
            ),
        )
    )
    events.append(
        created(
            "TestArticle",
            "TA:NSECAP-0007",
            entity(
                "TA:NSECAP-0007",
                "TestArticle",
                {
                    "serialNumber": "TA-NSECAP-0007",
                    "variantId": "VAR:NSECAP-B1",
                    "buildConfigurationId": "BL:NSECAP-B1-r3",
                    "asBuiltStatus": "AS_BUILT",
                    "partIds": ["PART:NSECAP-001"],
                },
            ),
        )
    )
    events.append(
        created(
            "TestCampaign",
            "TC:PAH-2026-Q4",
            entity(
                "TC:PAH-2026-Q4",
                "TestCampaign",
                {
                    "name": "Plasma arc heater qualification — Q4 2026",
                    "campaignType": "QUALIFICATION",
                    "status": "COMPLETE",
                    "objectives": ["Verify REQ:NSECAP-TEMP"],
                    "requirementIds": ["REQ:NSECAP-TEMP"],
                    "testArticleIds": ["TA:NSECAP-0007"],
                },
            ),
        )
    )
    events.append(
        created(
            "TestResult",
            "TR:PAH-2026-Q4-007",
            entity(
                "TR:PAH-2026-Q4-007",
                "TestResult",
                {
                    "campaignId": "TC:PAH-2026-Q4",
                    "testArticleId": "TA:NSECAP-0007",
                    "testMethod": "plasma-arc-heater",
                    "outcome": "PASS",
                    "measurements": [
                        {"name": "peak_temperature", "value": 1841.0, "unit": "K", "uncertainty": 25.0},
                        {"name": "hold_duration", "value": 1830.0, "unit": "s", "uncertainty": 5.0},
                    ],
                    "configurationSnapshot": {
                        "variant": "VAR:NSECAP-B1",
                        "materialLot": "LOT-0091",
                        "processRun": "PR:2026-11-00214",
                        "baseline": "BL:NSECAP-B1-r3",
                    },
                    "reviewedBy": "usr:chief-thermal",
                    "modelVersionIds": ["MDL:THERMAL-004"],
                },
            ),
        )
    )
    events.append(
        created(
            "Model",
            "MDL:THERMAL-004",
            entity(
                "MDL:THERMAL-004",
                "Model",
                {
                    "name": "Nosecap thermal response model",
                    "modelType": "THERMAL",
                    "modelVersion": "4.2.0",
                    "fidelity": {
                        "overall": 0.87,
                        "method": "rmse-vs-baseline-normalised",
                        "components": {"thermal": 0.87, "structural": 0.79},
                        "evaluatedAt": "2026-11-10T00:00:00Z",
                    },
                    "approvedForUse": True,
                    "modelCard": "model-cards/thermal-004.md",
                },
            ),
        )
    )

    for relation in (
        asserted("REL:1", "satisfies", ("Part", "PART:NSECAP-001"), ("Requirement", "REQ:NSECAP-TEMP")),
        asserted(
            "REL:2", "verifies", ("TestResult", "TR:PAH-2026-Q4-007"), ("Requirement", "REQ:NSECAP-TEMP")
        ),
        asserted("REL:3", "manufacturedBy", ("Part", "PART:NSECAP-001"), ("Facility", "FAC:CMCF-1")),
        asserted("REL:4", "characterizedBy", ("Material", "MAT:CMC-PREG-0091"), ("Model", "MDL:THERMAL-004")),
        asserted("REL:5", "derivedFrom", ("Model", "MDL:THERMAL-004"), ("TestResult", "TR:PAH-2026-Q4-007")),
    ):
        events.append(relation)

    # -- shield side: threat reconstruction ------------------------------
    events.append(
        created(
            "ThreatSystem",
            "THR:HGV-UNKNOWN-7",
            entity(
                "THR:HGV-UNKNOWN-7",
                "ThreatSystem",
                {
                    "designation": "HGV-UNKNOWN-7",
                    "threatClass": "HGV",
                    "kinematicProfile": {"mach": 8.2, "altitude_km": 58, "range_km": 2400},
                    "confidence": 0.61,
                    "observationIds": ["TOBS:2026-11-09-A", "TOBS:2026-11-09-B"],
                },
                classification="RESTRICTED",
                program="NGSH-MAVERICK",
            ),
        )
    )
    events.append(
        created(
            "ThreatObservation",
            "TOBS:2026-11-09-A",
            entity(
                "TOBS:2026-11-09-A",
                "ThreatObservation",
                {
                    "observationTime": "2026-11-09T04:12:00Z",
                    "sensorIds": ["SBIR-P3"],
                    "sensorType": "SPACE_IR",
                    "measurements": [{"name": "estimated_mach", "value": 8.2, "unit": "M"}],
                    "trackQuality": 0.72,
                    "source": "space-ir-processing",
                },
                classification="RESTRICTED",
                program="NGSH-MAVERICK",
            ),
        )
    )
    events.append(
        created(
            "EngagementScenario",
            "ESC:MAV-BASE-01",
            entity(
                "ESC:MAV-BASE-01",
                "EngagementScenario",
                {
                    "name": "Interim architecture — HBTSS cue to Aegis",
                    "threatSystemIds": ["THR:HGV-UNKNOWN-7"],
                    "defensiveArchitecture": "HBTSS-cued-Aegis-GPI",
                    "monteCarloConfig": {"runs": 10000, "seed": 20261114, "confidenceLevel": 0.95},
                    "resultsSummary": {"detection_to_custody_min": 18.4, "single_shot_pk": 0.21},
                },
                classification="RESTRICTED",
                program="NGSH-MAVERICK",
            ),
        )
    )
    events.append(
        asserted(
            "REL:6",
            "engages",
            ("EngagementScenario", "ESC:MAV-BASE-01"),
            ("ThreatSystem", "THR:HGV-UNKNOWN-7"),
            classification="RESTRICTED",
            program="NGSH-MAVERICK",
        )
    )
    events.append(
        asserted(
            "REL:7",
            "derivedFrom",
            ("ThreatSystem", "THR:HGV-UNKNOWN-7"),
            ("ThreatObservation", "TOBS:2026-11-09-A"),
            classification="RESTRICTED",
            program="NGSH-MAVERICK",
            confidence=0.61,
        )
    )

    return events


def main() -> int:
    events = build_events()
    result = call("POST", f"{FABRIC}/v1/events", {"events": events})
    accepted = len(result["accepted"])
    rejected = result["rejected"]
    print(f"published {accepted} events, {len(rejected)} rejected")
    for entry in rejected:
        print(f"  rejected {entry['eventId']}: {entry['reason']}")

    replay = call("POST", f"{THREAD}/v1/project/replay")
    stats = replay["stats"]
    print(
        f"projected {replay['replayed']} events -> {stats['totalEntities']} entities, {stats['totalRelations']} relations"
    )
    return 0 if not rejected else 1


if __name__ == "__main__":
    raise SystemExit(main())
