#!/usr/bin/env python3
"""Walk the programme across all six pillars against a running stack.

Run ``make dev`` in one terminal and this script in another. It is the
end-to-end story in executable form:

    requirement -> part -> process run -> test result -> model validation
    supplier -> threat -> engagement

The seeds are published through the fabric, exactly as an importer would, and
the thread is rebuilt from the log before any pillar reads it. That is
deliberate: the script proves the graph is a projection, not a private store.

Nothing here is a shortcut around a pillar's own rules. The credential is
issued by the workforce service, the test result is admitted by the test-lab
service, the C-007 risk is computed by the supply service, and the batch is run
by the engagement service.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "libs" / "ngsh-core"))

from ngsh_core.envelope import Actor  # noqa: E402
from ngsh_core.ids import new_ulid  # noqa: E402
from ngsh_core.ontology import OntologyLoader  # noqa: E402
from ngsh_core.publish import (  # noqa: E402
    entity_document,
    entity_event,
    relation_document,
    relation_event,
)

FABRIC = "http://127.0.0.1:8082"
THREAD = "http://127.0.0.1:8085"
ARCHITECTURE = "http://127.0.0.1:8088"
WORKFORCE = "http://127.0.0.1:8089"
MANUFACTURING = "http://127.0.0.1:8090"
TESTLAB = "http://127.0.0.1:8091"
SUPPLY = "http://127.0.0.1:8092"
ENGAGEMENT = "http://127.0.0.1:8093"

GREEN = "\033[32m"
CYAN = "\033[36m"
DIM = "\033[2m"
RESET = "\033[0m"


def call(method: str, url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise SystemExit(f"{method} {url} failed: {exc.code} {detail}") from exc


def step(title: str) -> None:
    print(f"\n{CYAN}== {title}{RESET}")


def ok(message: str) -> None:
    print(f"  {GREEN}ok{RESET} {message}")


def main() -> int:
    registry = OntologyLoader(REPO_ROOT / "contracts").load()
    actor = Actor(
        subjectId="usr:engineer",
        kind="user",
        clearance="TOP SECRET",
        citizenship="US",
        tenant="ngsh",
        programs=["NGSH-SHY"],
    )

    requirement_id = f"REQ:{new_ulid()}"
    system_id = f"SYS:{new_ulid()}"
    part_id = f"PART:{new_ulid()}"
    facility_id = f"FAC:{new_ulid()}"
    plan_id = f"PP:{new_ulid()}"
    model_id = f"MDL:{new_ulid()}"
    supplier_id = f"SUP:{new_ulid()}"
    observation_id = f"TOBS:{new_ulid()}"
    threat_id = f"THR:{new_ulid()}"

    def doc(entity_type: str, entity_id: str, attributes: dict) -> dict:
        return entity_document(
            entity_type,
            entity_id,
            attributes,
            tenant="ngsh",
            program="NGSH-SHY",
            created_by="usr:engineer",
        )

    documents = [
        doc(
            "Requirement",
            requirement_id,
            {
                "statement": "The nosecap shall survive 1800 K for 300 s.",
                "verificationMethod": "TEST",
                "status": "BASELINED",
            },
        ),
        doc("System", system_id, {"name": "Booster", "lifecycleState": "DEVELOPMENT"}),
        doc(
            "Part",
            part_id,
            {
                "partNumber": "P-1",
                "name": "Nosecap",
                "revision": "C",
                "criticality": "CRITICAL",
                "isSingleSource": True,
            },
        ),
        doc(
            "Facility",
            facility_id,
            {
                "name": "Plant 1",
                "facilityType": "MANUFACTURING",
                "surgeCapacity": {"unitsPerHour": 4, "shiftsPerDay": 2},
            },
        ),
        doc(
            "ProcessPlan",
            plan_id,
            {
                "name": "Nosecap layup",
                "processType": "AUTOCLAVE",
                "revision": "C",
                "operations": [
                    {"opId": "OP1", "sequence": 1, "name": "Layup"},
                    {"opId": "OP2", "sequence": 2, "name": "Cure"},
                ],
            },
        ),
        doc(
            "Model",
            model_id,
            {
                "name": "Aero twin",
                "modelType": "AERODYNAMIC",
                "modelVersion": "1.2",
                "fidelity": {"overall": 0.7},
                "approvedForUse": True,
            },
        ),
        doc(
            "Supplier",
            supplier_id,
            {"name": "Source A", "tier": 1, "riskScore": 0.3, "leadTimeDays": 60},
        ),
        doc(
            "ThreatObservation",
            observation_id,
            {"observationTime": "2026-11-01T00:00:00+00:00", "sensorType": "GROUND_RADAR"},
        ),
        doc(
            "ThreatSystem",
            threat_id,
            {
                "designation": "T-1",
                "threatClass": "HGV",
                "kinematicProfile": {"mach": 6},
                "observationIds": [observation_id],
            },
        ),
    ]
    relations = [
        relation_document("satisfies", ("Part", part_id), ("Requirement", requirement_id), tenant="ngsh", asserted_by="usr:engineer"),
        relation_document("manufacturedBy", ("Part", part_id), ("Facility", facility_id), tenant="ngsh", asserted_by="usr:engineer"),
        relation_document("supplies", ("Supplier", supplier_id), ("Part", part_id), tenant="ngsh", asserted_by="usr:engineer"),
        relation_document("threatens", ("ThreatSystem", threat_id), ("Part", part_id), tenant="ngsh", asserted_by="usr:engineer"),
        relation_document("derivedFrom", ("ThreatSystem", threat_id), ("ThreatObservation", observation_id), tenant="ngsh", asserted_by="usr:engineer"),
    ]

    events = [entity_event(document, actor, registry=registry) for document in documents]
    events += [relation_event(relation, actor, registry=registry) for relation in relations]

    step("Fabric: publish the programme baseline")
    appended = call("POST", f"{FABRIC}/v1/events", {"events": [event.to_logical_json() for event in events]})
    ok(f"{len(appended.get('accepted', []))} events accepted")

    step("Thread: rebuild the projection from the log")
    call("POST", f"{THREAD}/v1/project/replay")
    stats = call("GET", f"{THREAD}/v1/graph/stats")
    ok(f"{stats['totalEntities']} entities, {stats['totalRelations']} relations projected")

    step("Pillar E: credential the operator")
    skill = call(
        "POST",
        f"{WORKFORCE}/v1/skills",
        {"name": "CMC layup", "code": "CMC-1", "category": "MANUFACTURING", "clearanceRequired": "SECRET"},
    )["skill"]
    person = call(
        "POST",
        f"{WORKFORCE}/v1/people",
        {
            "employeeId": "E-1",
            "name": "A Person",
            "citizenship": "US",
            "clearanceLevel": "TOP SECRET",
            "clearanceExpiry": "2030-01-01T00:00:00+00:00",
            "region": "MIDWEST",
            "skillIds": [skill["id"]],
        },
    )["person"]
    credential = call(
        "POST", f"{WORKFORCE}/v1/credentials", {"personId": person["id"], "skillId": skill["id"]}
    )["credential"]
    decision = call(
        "GET",
        f"{WORKFORCE}/v1/work-authorisation?personId={person['id']}&skillId={skill['id']}",
    )
    ok(f"credential {credential['id']} active, authorisation allowed={decision['allowed']}")

    step("Pillar A: pin the configuration baseline")
    baseline = call(
        "POST",
        f"{ARCHITECTURE}/v1/baselines",
        {
            "systemId": system_id,
            "name": "Nosecap build C",
            "members": [{"entityType": "Part", "entityId": part_id, "revision": "C"}],
        },
    )["baseline"]
    ok(f"baseline {baseline['id']} ({baseline['digest'][:12]}…)")

    step("Pillar C: admit the test result against that baseline")
    result = call(
        "POST",
        f"{TESTLAB}/v1/test-results",
        {
            "testMethod": "arc-jet",
            "outcome": "PASS",
            "requirementIds": [requirement_id],
            "configurationSnapshot": {"variantId": part_id, "baselineId": baseline["id"]},
            "measurements": [{"name": "stagnationTemp", "value": 1800, "unit": "K"}],
            "limits": {"stagnationTemp": {"max": 1850}},
            "reviewedBy": "usr:reviewer",
            "dataSetUris": ["s3://ngsh-test/arc/run-001"],
        },
    )["testResult"]
    coverage = call("GET", f"{ARCHITECTURE}/v1/requirements/{requirement_id}/coverage")
    ok(f"result {result['id']} admitted, requirement verified={coverage['verified']}")

    step("Pillar B: record the run and check the traveller")
    process_run = call(
        "POST",
        f"{MANUFACTURING}/v1/process-runs",
        {
            "processPlanId": plan_id,
            "partId": part_id,
            "facilityId": facility_id,
            "operatorId": person["id"],
            "opId": "OP1",
            "measuredParameters": {"temperature": 180.0},
            "testResultId": result["id"],
        },
    )["processRun"]
    traveller = call("POST", f"{MANUFACTURING}/v1/travellers", {"processPlanId": plan_id})
    rate = call(
        "POST", f"{MANUFACTURING}/v1/simulate-rate", {"facilityId": facility_id, "units": 100}
    )
    ok(f"run {process_run['id']} recorded, next operation {traveller['nextOperation']}, days required {rate['daysRequired']}")

    step("Pillar C: close the twin loop from the evidence")
    validation = call(
        "POST", f"{TESTLAB}/v1/twin-validation", {"testResultId": result["id"], "modelId": model_id}
    )
    ok(f"model fidelity {validation['priorFidelity']} -> {validation['fidelity']}")

    step("Pillar D: exposure, reconstitution and surge")
    risks = call("GET", f"{SUPPLY}/v1/supply-risks")
    call(
        "POST",
        f"{SUPPLY}/v1/reconstitutes",
        {"fromRef": {"type": "Supplier", "id": supplier_id}, "toRef": {"type": "Part", "id": part_id}},
    )
    cleared = call("GET", f"{SUPPLY}/v1/supply-risks")
    surge = call("POST", f"{SUPPLY}/v1/surge", {"facilityId": facility_id, "demandUnits": 50})
    ok(
        f"C-007 findings {risks['count']} -> {cleared['count']}; "
        f"bottleneck {surge['bottleneckSupplier']['supplierId']}"
    )

    step("Pillars F and G: engage the threat")
    scenario = call(
        "POST",
        f"{ENGAGEMENT}/v1/scenarios",
        {
            "name": "Terminal defence",
            "threatSystemIds": [threat_id],
            "sensorChain": [{"sensorId": "SEN:1"}],
            "effectorChain": [{"effectorId": "EFF:1"}],
            "monteCarloConfig": {"pkMean": 0.8, "pkSigma": 0.1, "detectionProbability": 0.9},
        },
    )["scenario"]
    batch = call("POST", f"{ENGAGEMENT}/v1/scenarios/{scenario['id']}/batch", {"runs": 20_000, "seed": 9})
    chain = call("GET", f"{ENGAGEMENT}/v1/kill-chain?scenarioId={scenario['id']}")
    ok(
        f"{batch['runs']} runs in {batch['elapsedSeconds']}s, "
        f"mean Pk {batch['statistics']['meanPk']}, kill chain complete={chain['complete']}"
    )

    step("Thread: one traversal reaches every pillar")
    trace = call("GET", f"{THREAD}/v1/trace?root=Part:{part_id}&depth=3")
    observed = sorted({node["type"] for node in trace["nodes"]})
    print(f"  {DIM}{', '.join(observed)}{RESET}")
    expected = {
        "Requirement",
        "TestResult",
        "ProcessRun",
        "Model",
        "Supplier",
        "ThreatSystem",
        "ThreatObservation",
        "EngagementScenario",
        "Facility",
    }
    missing = expected - set(observed)
    if missing:
        raise SystemExit(f"traversal is missing {sorted(missing)}")
    ok(f"{len(trace['nodes'])} nodes and {len(trace['edges'])} edges across all pillars")

    print(f"\n{GREEN}Programme traversal complete.{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
