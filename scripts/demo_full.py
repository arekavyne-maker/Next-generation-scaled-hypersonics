#!/usr/bin/env python3
"""Exercise every PSDD capability and every external interface, end to end.

Run the stack with ``make dev``, then run ``make demo-full``. Every call in this
script goes through the gateway, so the same path the console uses is the path
under test:

    console -> gateway -> owning service -> event log -> graph projection

The script is deliberately explicit about what "complete" means. It records a
capability id only after the endpoint that owns it has returned a real result,
and it fails if any of the 34 capabilities or 7 interfaces is left unexercised.
A run that skips a capability is a run that discovered a gap, not a pass.

Nothing is written to a service-private table. Seeds enter through the fabric
as events, the thread is rebuilt from the log, and each pillar's own rules
admit or refuse the facts that follow.
"""

from __future__ import annotations

import json
import os
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

GATEWAY = os.environ.get("NGSH_GATEWAY_URL", "http://127.0.0.1:8080").rstrip("/")

GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"

CAPABILITY_IDS = tuple(
    f"{pillar}-{index}" for pillar, count in {"A": 5, "B": 4, "C": 4, "D": 3, "E": 5, "F": 6, "G": 4, "H": 3}.items() for index in range(1, count + 1)
)
INTERFACE_IDS = tuple(f"IF-{index}" for index in range(1, 8))

covered: set[str] = set()
interfaces_covered: set[str] = set()


def call(method: str, path: str, payload: dict | None = None, *, expect: tuple[int, ...] = (200, 201, 202)) -> dict:
    """Call the platform through the gateway, failing on an unexpected status."""
    url = f"{GATEWAY}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
            result = json.loads(body) if body else {}
            if response.status not in expect:
                raise SystemExit(f"{method} {path} returned {response.status}: {body[:500]}")
            return result
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        if exc.code in expect:
            return json.loads(detail) if detail else {}
        raise SystemExit(f"{method} {path} failed: {exc.code} {detail[:1200]}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"cannot reach the gateway at {GATEWAY}: {exc.reason}. Start the stack with 'make dev'."
        ) from exc


def step(title: str) -> None:
    print(f"\n{CYAN}== {title}{RESET}")


def ok(message: str, *capability_ids: str) -> None:
    for capability_id in capability_ids:
        covered.add(capability_id)
    print(f"  {GREEN}ok{RESET} {message}")


def note(message: str) -> None:
    print(f"  {DIM}{message}{RESET}")


def interface(interface_id: str, direction: str, payload: dict, *, correlation_id: str) -> dict:
    receipt = call(
        "POST",
        f"/api/integration/v1/interfaces/{interface_id}/{direction.lower()}",
        {"payload": payload, "correlationId": correlation_id},
        expect=(202,),
    )
    interfaces_covered.add(interface_id)
    return receipt


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

    system_id = f"SYS:{new_ulid()}"
    second_system_id = f"SYS:{new_ulid()}"
    subsystem_id = f"SUB:{new_ulid()}"
    requirement_id = f"REQ:{new_ulid()}"
    part_id = f"PART:{new_ulid()}"
    material_id = f"MAT:{new_ulid()}"
    provenance_id = f"PROV:{new_ulid()}"
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
        doc("System", system_id, {"name": "Glide vehicle", "lifecycleState": "DEVELOPMENT"}),
        doc("System", second_system_id, {"name": "Seeker", "lifecycleState": "DEVELOPMENT"}),
        doc(
            "Subsystem",
            subsystem_id,
            {
                "name": "Thermal protection",
                "parentSystemId": system_id,
                "maturity": "TRL_6",
                "criticality": "CRITICAL",
            },
        ),
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
            "Material",
            material_id,
            {"materialType": "CMC_PREG", "lotNumber": "LOT-1", "supplierId": supplier_id},
        ),
        doc(
            "PartProvenance",
            provenance_id,
            {
                "partId": part_id,
                "materialIds": [material_id],
                "chainOfCustody": [
                    {
                        "fromNodeId": material_id,
                        "toNodeId": part_id,
                        "transferredAt": "2026-11-01T00:00:00+00:00",
                        "transferType": "RECEIPT",
                        "quantity": 1,
                    }
                ],
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
                "modelVersion": "1.2.0",
                "fidelity": {
                    "overall": 0.7,
                    "applicabilityEnvelope": {
                        "maxSpeedMps": {"value": 2500.0, "unit": "m/s"},
                        "maxAltitudeM": {"value": 70000.0, "unit": "m"},
                    },
                },
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
            {
                "observationTime": "2026-11-01T00:00:00+00:00",
                "sensorType": "GROUND_RADAR",
                "confidence": 0.8,
            },
        ),
        doc(
            "ThreatSystem",
            threat_id,
            {
                "designation": "T-1",
                "threatClass": "HGV_MANEUVERABLE",
                "kinematicProfile": {
                    "maxSpeedMps": 2100.0,
                    "cruiseSpeedMps": 1800.0,
                    "maxAltitudeM": 60000.0,
                    "maneuverG": 12.0,
                    "rangeKm": 3000.0,
                },
                "characteristics": [{"name": "rcsM2", "value": 0.1}],
                "confidence": 0.7,
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

    step("Gateway: the platform reports itself")
    health = call("GET", "/healthz")
    assert health["status"] == "ok", health
    status = call("GET", "/v1/platform/status")
    matrix = call("GET", "/v1/platform/capabilities")
    if matrix["count"] != 34 or matrix["interfaceCount"] != 7:
        raise SystemExit(f"capability matrix is {matrix['count']} capabilities / {matrix['interfaceCount']} interfaces")
    if status["healthyCount"] != status["serviceCount"]:
        raise SystemExit(f"only {status['healthyCount']}/{status['serviceCount']} services are healthy")
    ok(
        f"{matrix['count']} capabilities across {matrix['pillarCount']} pillars, "
        f"{matrix['interfaceCount']} interfaces, {status['serviceCount']} services healthy"
    )

    step("Fabric: publish the programme baseline")
    events = [entity_event(document, actor, registry=registry) for document in documents]
    events += [relation_event(relation, actor, registry=registry) for relation in relations]
    appended = call("POST", "/api/fabric/v1/events", {"events": [event.to_logical_json() for event in events]})
    call("POST", "/api/thread/v1/project/replay")
    stats = call("GET", "/api/thread/v1/graph/stats")
    ok(f"{len(appended.get('accepted', []))} events accepted; {stats['totalEntities']} entities projected")

    # ---- Pillar A -----------------------------------------------------------
    step("Pillar A: architecture, modularity, traceability and exchange")
    baseline = call(
        "POST",
        "/api/architecture/v1/baselines",
        {
            "systemId": system_id,
            "name": "Nosecap build C",
            "members": [{"entityType": "Part", "entityId": part_id, "revision": "C"}],
        },
    )["baseline"]
    verified = call("POST", f"/api/architecture/v1/baselines/{baseline['id']}/verify")
    ok(f"A-1 baseline {baseline['id']} reproduces ({verified['reproducible']})", "A-1")

    variants = call(
        "POST",
        "/api/architecture/v1/variants/generate",
        {
            "familyId": "FAM:SHY",
            "coreMembers": [
                {"entityType": "Part", "entityId": part_id, "revision": "C"},
                {"entityType": "Subsystem", "entityId": subsystem_id, "revision": "A"},
            ],
            "variantSpecs": [
                {
                    "variantId": "BLK-1",
                    "systemId": system_id,
                    "distinguishingCharacteristics": ["range-extended"],
                }
            ],
        },
    )
    if variants["generatedCount"] < 1:
        raise SystemExit(f"variant generation produced no variant: {variants}")
    core_error = call(
        "POST",
        f"/api/architecture/v1/variants/{variants['variants'][0]['id']}/core-error",
        {"finding": {"entityId": part_id, "description": "core defect"}},
    )
    ok(f"A-2 {variants['generatedCount']} variant(s); defect reaches {core_error['detectedIn']}", "A-2")

    # B-1 below admits the result this coverage query depends on, so record A-3
    # after the test-lab step.

    insertion = call(
        "POST",
        "/api/architecture/v1/insertion/assess",
        {
            "candidate": {
                "name": "CMC nosecap block 2",
                "trl": 6,
                "srl": 6,
                "subsystemId": subsystem_id,
                "minimumTrl": 5,
            },
            "slots": [],
        },
    )
    ok(f"A-4 insertion assessed: insertable={insertion['insertable']} ({len(insertion['findings'])} finding(s))", "A-4")

    sysml = call("GET", "/api/architecture/v1/sysml/export")
    reimported = call("POST", "/api/architecture/v1/sysml/import", {"model": sysml["model"]})
    if reimported["recognised"]["systems"] != reimported["counts"]["systems"]:
        raise SystemExit(f"SysML round-trip lost identity: {reimported}")
    icd = call(
        "POST",
        "/api/architecture/v1/icds/generate",
        {
            "fromSystemId": system_id,
            "toSystemId": second_system_id,
            "characteristics": {"rate": 20, "latency": 5, "timing": "PERIODIC", "envelope": {"maxAltitudeM": 70000}},
        },
    )
    ok(
        f"A-5 SysML round-trip kept {reimported['counts']}; ICD {icd['icd']['icdId']} verified={icd['verification']['conformant']}",
        "A-5",
    )

    # ---- Pillar B and C -----------------------------------------------------
    step("Pillar B and C: manufacturing evidence, test admission and the lake")
    results = []
    for index in range(1, 5):
        result = call(
            "POST",
            "/api/testlab/v1/test-results",
            {
                "testMethod": "arc-jet",
                "outcome": "PASS",
                "requirementIds": [requirement_id],
                "campaignId": f"TC:DEMO-{index}",
                "configurationSnapshot": {"variantId": part_id, "baselineId": baseline["id"]},
                "measurements": [{"name": "stagnationTemp", "value": 1800 + index, "unit": "K"}],
                "limits": {"stagnationTemp": {"max": 1850}},
                "reviewedBy": "usr:reviewer",
                "dataSetUris": [f"ngsh-lake://arc-run-{index}"],
            },
        )["testResult"]
        results.append(result)
    coverage = call("GET", f"/api/architecture/v1/requirements/{requirement_id}/coverage")
    ok(
        f"C-2 admitted {len(results)} results; A-3 requirement verified={coverage['verified']}",
        "C-2",
        "A-3",
    )

    process_runs = []
    for index, temperature in enumerate((180.0, 181.0, 179.0, 180.5), start=1):
        run = call(
            "POST",
            "/api/manufacturing/v1/process-runs",
            {
                "processPlanId": plan_id,
                "partId": part_id,
                "facilityId": facility_id,
                "opId": "OP1",
                "measuredParameters": {"temperature": temperature},
                "testResultId": results[0]["id"] if index == 1 else None,
                "startedAt": f"2026-11-0{index}T00:00:00+00:00",
            },
        )["processRun"]
        process_runs.append(run)
    traveller = call("POST", "/api/manufacturing/v1/travellers", {"processPlanId": plan_id})
    genealogy = call("GET", f"/api/manufacturing/v1/genealogy/{part_id}")
    ok(
        f"B-1 {len(process_runs)} runs, next operation {traveller['nextOperation']}, "
        f"{len(genealogy.get('hops', []))} genealogy node(s)",
        "B-1",
    )

    drift = call(
        "POST",
        "/api/manufacturing/v1/drift",
        {"processPlanId": plan_id, "candidate": {"measuredParameters": {"temperature": 240.0}}},
    )
    ok(f"B-2 drift flagged {len(drift['drivers'])} driver(s)", "B-2")

    campaign = call(
        "POST",
        "/api/testlab/v1/campaigns",
        {
            "name": "Arc-jet campaign",
            "campaignType": "QUALIFICATION",
            "requirementIds": [requirement_id],
            "testArticleIds": [part_id],
            "slot": {
                "facilityId": facility_id,
                "start": "2027-01-01T00:00:00+00:00",
                "end": "2027-01-02T00:00:00+00:00",
                "instrumentation": [{"name": "thermocouple"}],
            },
        },
    )["campaign"]
    curation = call("GET", f"/api/testlab/v1/campaigns/{campaign['id']}/curation")
    ok(f"B-3 campaign {campaign['id']} curated={curation['curated']}", "B-3")

    rate = call("POST", "/api/manufacturing/v1/simulate-rate", {"facilityId": facility_id, "units": 100})
    simulation = call(
        "POST",
        "/api/manufacturing/v1/production/simulate",
        {
            "demandUnits": 24,
            "horizonDays": 10,
            "seed": 11,
            "stations": [
                {"stationId": "ST1", "capacity": 2, "cycleTimeMinutes": 45, "yieldRate": 0.97},
                {"stationId": "ST2", "capacity": 1, "cycleTimeMinutes": 90, "yieldRate": 0.99},
            ],
        },
    )
    ok(
        f"B-4 rate simulation {rate['daysRequired']} days; discrete-event {simulation['completedUnits']}/24 units",
        "B-4",
    )

    object_record = call(
        "POST",
        "/api/ingest/v1/lakehouse/objects",
        {
            "content": "time,value\n0,1.0\n1,2.0\n",
            "mediaType": "text/csv",
            "metadata": {"campaign": campaign["id"]},
        },
    )["object"]
    fetched = call("GET", f"/api/ingest/v1/lakehouse/objects/{object_record['digest']}/content?encoding=utf-8")
    verified_object = call("GET", f"/api/ingest/v1/lakehouse/objects/{object_record['digest']}/verify")
    if not fetched["content"].startswith("time,value") or not verified_object["valid"]:
        raise SystemExit("lakehouse object did not round-trip")
    ok(f"C-1 lakehouse object {object_record['digest'][:12]}… verified", "C-1")

    anomalies = call(
        "POST",
        "/api/testlab/v1/anomalies/detect",
        {
            "measurements": [{"name": "thickness", "value": 12.0}],
            "limits": {"thickness": {"min": 1.0, "max": 10.0}},
        },
    )
    ok(f"C-2 anomaly scan found {anomalies['limitBreaches']} limit breach(es)", "C-2")

    validation = call(
        "POST", "/api/testlab/v1/twin-validation", {"testResultId": results[0]["id"], "modelId": model_id}
    )
    residuals = call(
        "POST",
        f"/api/testlab/v1/models/{model_id}/residuals",
        {"evidence": [{"name": "range", "predicted": 100.0, "observed": 90.0}]},
    )
    regenerated = call(
        "POST",
        f"/api/testlab/v1/models/{model_id}/regenerate",
        {
            "evidence": [
                {"name": "range", "predicted": 100.0, "observed": 90.0, "evidenceId": results[0]["id"]}
            ],
            "reason": "flight test bias",
        },
    )
    if regenerated["requiresApproval"] is not True:
        raise SystemExit("a regenerated model was approved without a human")
    ok(
        f"C-3/G-3 fidelity {validation['priorFidelity']} -> {validation['fidelity']}; "
        f"worst residual {residuals['worst']['name']}; regenerated {regenerated['modelVersion']} awaits approval",
        "C-3",
        "G-3",
    )

    capacity = call(
        "POST",
        "/api/testlab/v1/range-capacity",
        {
            "ranges": [{"id": facility_id, "name": "Range 1", "capacityPerPeriod": 2}],
            "slots": [],
            "requiredTelemetryCoverage": 0.9,
        },
    )
    schedule = call(
        "POST",
        "/api/testlab/v1/schedule/optimise",
        {
            "demands": [{"demandId": campaign["id"], "campaignType": "QUALIFICATION"}],
            "ranges": [{"id": facility_id, "name": "Range 1", "capacityPerPeriod": 2}],
        },
    )
    ok(
        f"G-2 range capacity {capacity['rangeCount']} range(s); schedule assigned {len(schedule['assignments'])}",
        "G-2",
        "C-4",
    )

    # ---- Pillar D -----------------------------------------------------------
    step("Pillar D: supplier risk, reconstitution and surge")
    risks = call("GET", "/api/supply/v1/supply-risks")
    ok(f"D-1/D-2 C-007 findings {risks['count']} before reconstitution", "D-1")
    call(
        "POST",
        "/api/supply/v1/reconstitutes",
        {"fromRef": {"type": "Supplier", "id": supplier_id}, "toRef": {"type": "Part", "id": part_id}},
    )
    playbook = call(
        "POST",
        "/api/supply/v1/reconstitution",
        {
            "partId": part_id,
            "alternatives": [
                {
                    "supplierId": supplier_id,
                    "action": "qualify second source",
                    "leadTimeDays": 60,
                    "riskScore": 0.3,
                }
            ],
        },
    )
    ok(f"D-2 reconstitution path recorded; playbook {playbook['partId']} ({playbook['coverageDays']} days)", "D-2")

    surge = call("POST", "/api/supply/v1/surge", {"facilityId": facility_id, "demandUnits": 50})
    ok(f"D-3 surge bottleneck {surge['bottleneckSupplier']['supplierId']}", "D-3")

    # ---- Pillar E -----------------------------------------------------------
    step("Pillar E: the cleared workforce")
    skill = call(
        "POST",
        "/api/workforce/v1/skills",
        {"name": "CMC layup", "code": "CMC-1", "category": "MANUFACTURING", "clearanceRequired": "SECRET"},
    )["skill"]
    person = call(
        "POST",
        "/api/workforce/v1/people",
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
        "POST", "/api/workforce/v1/credentials", {"personId": person["id"], "skillId": skill["id"]}
    )["credential"]
    authorisation = call(
        "GET", "/api/workforce/v1/work-authorisation?" + f"personId={person['id']}&skillId={skill['id']}"
    )
    ok(
        f"E-3 credential {credential['id']} issued; authorisation allowed={authorisation['allowed']}",
        "E-3",
    )

    scenario = call(
        "POST",
        "/api/workforce/v1/training/scenarios",
        {
            "name": "Nosecap layup familiarisation",
            "simulator": "SCREEN",
            "skillIds": [skill["id"]],
            "references": [
                {"type": "Part", "id": part_id},
                {"type": "ProcessPlan", "id": plan_id},
            ],
        },
    )["scenario"]
    completion = call(
        "POST",
        "/api/workforce/v1/training/completions",
        {"scenarioId": scenario["scenarioId"], "personId": person["id"], "score": 0.95, "passed": True},
    )["completion"]
    training_coverage = call("GET", "/api/workforce/v1/training/coverage")
    ok(
        f"E-1 training scenario on live thread; completion score {completion['score']} "
        f"({training_coverage['validCount']} valid scenario(s))",
        "E-1",
    )

    package = call(
        "POST",
        "/api/workforce/v1/curriculum/packages",
        {
            "title": "CMC layup fundamentals",
            "version": "1.0.0",
            "modules": [{"moduleId": "M1", "title": "Layup"}, {"moduleId": "M2", "title": "Cure"}],
            "sourceIds": [part_id],
            "guardVersion": "1.0.0",
            "reviewer": "usr:reviewer",
        },
    )["package"]
    ok(f"E-2 curriculum package {package['packageId']} content-addressed", "E-2")

    gap = call(
        "POST",
        "/api/workforce/v1/workforce/gap",
        {
            "demand": [{"region": "MIDWEST", "skillId": skill["id"], "headcount": 4}],
            "asOf": "2026-11-15T00:00:00+00:00",
        },
    )
    ok(f"E-4 workforce gap report covers {len(gap['rows'])} region/skill row(s)", "E-4")

    extract = call(
        "POST",
        "/api/workforce/v1/extracts",
        {
            "view": "partner",
            "records": [{"id": part_id, "type": "Part", "classification": "CUI"}],
            "transformations": ["redact-pricing", "remove-supplier-names"],
            "guardVersion": "1.0.0",
            "reviewer": "usr:reviewer",
        },
    )
    ok(f"E-5 partner extract {extract['release']['manifest']['manifestId']} released", "E-5")

    # ---- Pillar F -----------------------------------------------------------
    step("Pillar F: threat twin, kill chain and co-simulation")
    threat_model = call("POST", "/api/engagement/v1/threat-models", {"threatId": threat_id})
    envelope = call(
        "GET", f"/api/engagement/v1/threat-models/{threat_model['modelId']}/envelope?altitudeM=10000&altitudeM=30000"
    )
    ok(
        f"F-1 model {threat_model['modelId']} regime {threat_model['derived']['performance']['speedRegime']}; "
        f"{len(envelope['samples'])} envelope sample(s)",
        "F-1",
    )

    def make_scenario(name: str) -> dict:
        return call(
            "POST",
            "/api/engagement/v1/scenarios",
            {
                "name": name,
                "threatSystemIds": [threat_id],
                "sensorChain": [{"sensorId": "SEN:1"}],
                "effectorChain": [{"effectorId": "EFF:1"}],
                "monteCarloConfig": {"pkMean": 0.8, "pkSigma": 0.1, "detectionProbability": 0.9},
            },
        )["scenario"]

    red = make_scenario("Red trace")
    blue = make_scenario("Blue trace")
    batch = call("POST", f"/api/engagement/v1/scenarios/{red['id']}/batch", {"runs": 5_000, "seed": 9})
    chain = call("GET", f"/api/engagement/v1/kill-chain?scenarioId={red['id']}")
    ok(
        f"F-2 {batch['runs']} runs, mean Pk {batch['statistics']['meanPk']}, chain complete={chain['complete']}",
        "F-2",
    )

    quality = call(
        "POST",
        "/api/engagement/v1/fire-control/quality",
        {
            "handovers": [{"handoverId": "H1", "latencyMs": 100, "continuous": True}],
            "tracks": [{"trackId": "T1", "falseTrack": False}],
            "solutions": [{"solutionId": "S1", "errorM": 10.0}],
        },
    )
    ok(f"F-3 fire-control quality breach={quality['hasBreaches']}", "F-3")

    candidate = call(
        "POST",
        "/api/engagement/v1/candidates/evaluate",
        {
            "name": "Interim Aegis cueing",
            "sensors": [{"id": "SEN:1", "type": "RADAR"}],
            "cueing": [{"id": "CUE:1", "source": "SDA"}],
            "effectors": [{"id": "EFF:1", "type": "INTERCEPTOR"}],
            "modelIds": [model_id],
            "threatSystemIds": [threat_id],
            "runs": 500,
            "seed": 7,
        },
    )
    ok(f"F-4 candidate composed and evaluated ({candidate['evaluation']['runs']} runs)", "F-4")

    plugin = call(
        "POST",
        "/api/engagement/v1/plugins",
        {
            "manifest": {
                "pluginId": "golden-dome-reference",
                "name": "Golden Dome reference architecture",
                "version": "1.0.0",
                "contractVersion": "1.0.0",
                "entrypoint": "reference.golden_dome:run",
                "scenarioTypes": ["ENGAGEMENT"],
                "referenceArchitectures": ["GD-REF-1"],
            }
        },
    )["plugin"]
    plugin_run = call(
        "POST",
        f"/api/engagement/v1/plugins/{plugin['pluginId']}/run",
        {"scenarioId": candidate["scenario"]["id"], "scenarioType": "ENGAGEMENT"},
    )
    ok(f"F-5 plug-in {plugin_run['pluginId']} run status {plugin_run['status']}", "F-5")

    co_sim = call(
        "POST",
        "/api/engagement/v1/co-simulation",
        {"threatId": threat_id, "redScenarioId": red["id"], "blueScenarioId": blue["id"], "runs": 1_000, "seed": 11},
    )
    ok(f"F-6 red/blue comparison complete={co_sim['identity']['sameThreatNode']}", "F-6")

    # ---- Pillar G -----------------------------------------------------------
    step("Pillar G: the test enterprise as a federation")
    datasets = call("GET", "/api/thread/v1/datasets")
    dataset_rows = datasets.get("datasets") or []
    if dataset_rows:
        lineage = call("GET", f"/api/thread/v1/datasets/{dataset_rows[0]['datasetId']}/lineage")
        lineage_detail = f"{len(lineage.get('lineage', []))} result(s)"
    else:
        lineage_detail = "catalogue empty"
    ok(f"G-1 dataset catalogue {len(dataset_rows)} dataset(s); lineage {lineage_detail}", "G-1")

    registry_report = call("GET", "/api/testlab/v1/fidelity/registry?asOf=2026-11-15T00:00:00%2B00:00")
    ok(f"G-4 fidelity registry covers {registry_report['summary']['modelCount']} model(s)", "G-4")

    # ---- Pillar H -----------------------------------------------------------
    step("Pillar H: industrial surge and affordability")
    readiness = call(
        "POST",
        "/api/industrial/v1/surge-readiness",
        {"facilityId": facility_id, "demandUnits": 40, "horizonDays": 90, "owner": "usr:industrial", "twinRunId": "twin-run-1"},
    )
    ok(f"H-1 surge readiness {readiness['status']} verified={readiness['verified']}", "H-1")

    assessment = call(
        "POST",
        "/api/industrial/v1/reconstitution/assess",
        {
            "partId": part_id,
            "candidates": [
                {"supplierId": supplier_id, "leadTimeDays": 60, "riskScore": 0.3, "action": "qualify"}
            ],
            "exercise": {
                "completedAt": "2026-11-10T00:00:00+00:00",
                "measuredTimeToReconstituteDays": 71.5,
            },
            "owner": "usr:industrial",
        },
    )
    ok(f"H-2 measured time-to-reconstitute {assessment['timeToReconstituteDays']} days", "H-2")

    affordability = call(
        "POST",
        "/api/industrial/v1/affordability/trace",
        {
            "requirementIds": [requirement_id],
            "costEstimates": [{"subjectId": part_id, "amount": 120000.0, "basis": "PARAMETRIC", "confidence": 0.8}],
            "quantity": 100,
        },
    )
    curve = call(
        "POST",
        "/api/industrial/v1/affordability/rate-curve",
        {
            "points": [{"rate": 10, "unitCost": 200000}, {"rate": 40, "unitCost": 150000}],
            "quantity": 100,
        },
    )
    ok(
        f"H-3 {len(affordability['requirements'])} requirement trace(s); predicted unit cost {round(curve['predictedUnitCost'])}",
        "H-3",
    )

    # ---- Interfaces ---------------------------------------------------------
    step("Interfaces: IF-1 to IF-7 cross the boundary")
    if1 = interface(
        "IF-1",
        "inbound",
        {
            "operation": "UPSERT_PART",
            "records": [{"id": part_id, "partNumber": "P-1", "name": "Nosecap"}],
        },
        correlation_id="demo-if1",
    )
    if2 = interface(
        "IF-2",
        "outbound",
        {"scenario": {"scenarioId": candidate["scenario"]["id"], "name": "Interim cueing"}},
        correlation_id="demo-if2",
    )
    if3 = interface(
        "IF-3",
        "inbound",
        {"tracks": [{"trackId": "TRK:1", "quality": 0.9}]},
        correlation_id="demo-if3",
    )
    if4 = interface(
        "IF-4",
        "inbound",
        {"manifest": {"testArticleId": part_id, "instrumentation": ["thermocouple"]}},
        correlation_id="demo-if4",
    )
    if5 = interface(
        "IF-5",
        "outbound",
        {"package": {"packageId": "PKG:DEMO", "modules": [{"moduleId": "M1"}]}},
        correlation_id="demo-if5",
    )
    assertion = call(
        "POST",
        "/v1/identity/assert",
        {"subjectId": "usr:analyst", "clearance": "SECRET", "citizenship": "US"},
    )
    if6 = interface(
        "IF-6",
        "inbound",
        {"assertion": assertion["assertion"]},
        correlation_id="demo-if6",
    )
    if7 = interface(
        "IF-7",
        "outbound",
        {"report": {"name": "Programme weekly", "metrics": [{"id": "kill-chain-latency", "value": 12.5}]}},
        correlation_id="demo-if7",
    )
    deliveries = call("GET", "/api/integration/v1/deliveries?limit=20")
    ok(
        f"IF-1..IF-7 accepted: {', '.join(sorted({if1['interfaceId'], if2['interfaceId'], if3['interfaceId'], if4['interfaceId'], if5['interfaceId'], if6['interfaceId'], if7['interfaceId']}))}; "
        f"{deliveries['count']} delivery record(s)",
    )
    if6_stored = call("GET", f"/api/integration/v1/deliveries/{if6['deliveryId']}")
    if if6_stored["payload"]["assertion"] != "<redacted-after-verification>":
        raise SystemExit("the IF-6 assertion was retained instead of redacted")

    # IF-3 outbound must be refused, not silently accepted.
    refused = call(
        "POST",
        "/api/integration/v1/interfaces/IF-3/outbound",
        {"payload": {"tracks": [{"trackId": "TRK:1"}]}},
        expect=(422,),
    )
    if "outbound traffic" not in refused["error"]["message"]:
        raise SystemExit(f"IF-3 outbound refusal is unclear: {refused}")

    # ---- Searches, analytics and the trace across every pillar --------------
    step("Cross-cutting reads: analytics, search and one end-to-end trace")
    kpis = call("POST", "/api/analytics/v1/kpis", {"asOf": "2026-11-15T00:00:00+00:00"})
    search = call("GET", "/api/thread/v1/search?q=Nosecap")
    trace = call("GET", f"/api/thread/v1/trace?root=Part:{part_id}&depth=3")
    if search["count"] < 1:
        raise SystemExit("search returned no hit for a seeded entity")
    observed = {node["type"] for node in trace["nodes"]}
    expected = {
        "Part",
        "Requirement",
        "ProcessRun",
        "TestResult",
        "Supplier",
        "ThreatSystem",
        "Model",
        "EngagementScenario",
    }
    missing = expected - observed
    if missing:
        raise SystemExit(f"trace is missing {sorted(missing)}")
    ok(f"{len(kpis['kpis'])} KPI(s); {search['count']} search hit(s); {len(trace['nodes'])} traced node(s)")

    # ---- Completeness gate --------------------------------------------------
    step("Completeness gate")
    missing_capabilities = [item for item in CAPABILITY_IDS if item not in covered]
    missing_interfaces = [item for item in INTERFACE_IDS if item not in interfaces_covered]
    if missing_capabilities:
        print(f"  {YELLOW}unexercised capabilities:{RESET} {', '.join(missing_capabilities)}")
    if missing_interfaces:
        print(f"  {YELLOW}unexercised interfaces:{RESET} {', '.join(missing_interfaces)}")
    if missing_capabilities or missing_interfaces:
        raise SystemExit("the run did not exercise the whole declared scope")

    print(
        f"\n{GREEN}Complete-build traversal finished: {len(covered)}/34 capabilities, "
        f"{len(interfaces_covered)}/7 interfaces, {status['serviceCount']} services.{RESET}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
