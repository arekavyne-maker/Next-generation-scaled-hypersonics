"""The programme traversal: one thread from a requirement to an engagement.

This test ties the six pillars together on a single platform database:

* Pillar A records the configuration baseline the test article was built to and
  answers requirement coverage from the evidence.
* Pillar E credentials the operator who runs the process.
* Pillar B records the process run against the released plan.
* Pillar C admits the test result, surfaces its anomaly, and validates the model.
* Pillar D computes the single-source exposure and plans reconstitution.
* Pillars F and G register the threat, engage it, and report the kill chain.

The final assertion is the one that matters: a single traversal rooted at the
part reaches every pillar's evidence. If the graph holds what the log holds,
the programme has one thread rather than six silos.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from ngsh_core.envelope import Actor
from ngsh_core.eventlog import EventLog
from ngsh_core.publish import entity_document, entity_event, relation_document, relation_event

pytestmark = pytest.mark.e2e

FAR_FUTURE = "2030-01-01T00:00:00+00:00"


def _doc(entity_type: str, entity_id: str, attributes: dict[str, Any]) -> dict[str, Any]:
    return entity_document(
        entity_type, entity_id, attributes, tenant="ngsh", program="NGSH-SHY", created_by="usr:engineer"
    )


def _seed(app, actor: Actor, documents: list[dict[str, Any]], relations: list[dict[str, Any]]) -> None:
    log = EventLog(app.state.executor)
    for document in documents:
        envelope = entity_event(document, actor, registry=app.state.registry)
        log.append(envelope)
        app.state.projector.apply(envelope)
    for relation in relations:
        envelope = relation_event(relation, actor, registry=app.state.registry)
        log.append(envelope)
        app.state.projector.apply(envelope)


def _relation(relation_type: str, source: tuple[str, str], target: tuple[str, str]) -> dict[str, Any]:
    return relation_document(relation_type, source, target, tenant="ngsh", asserted_by="usr:engineer")


@pytest.fixture
def programme(settings, operator):
    from ngsh_architecture.app import create_app as create_architecture_app
    from ngsh_engagement.app import create_app as create_engagement_app
    from ngsh_manufacturing.app import create_app as create_manufacturing_app
    from ngsh_supply.app import create_app as create_supply_app
    from ngsh_testlab.app import create_app as create_testlab_app
    from ngsh_thread.app import create_app as create_thread_app
    from ngsh_workforce.app import create_app as create_workforce_app

    apps = {
        "architecture": create_architecture_app(settings),
        "workforce": create_workforce_app(settings),
        "manufacturing": create_manufacturing_app(settings),
        "testlab": create_testlab_app(settings),
        "supply": create_supply_app(settings),
        "engagement": create_engagement_app(settings),
        "thread": create_thread_app(settings),
    }
    clients = {name: TestClient(app) for name, app in apps.items()}
    yield apps, clients
    for client in clients.values():
        client.close()


def test_programme_traversal_ties_all_pillars(programme, operator):
    apps, clients = programme
    thread = clients["thread"]

    _seed(
        apps["architecture"],
        operator,
        [
            _doc(
                "Requirement",
                "REQ:1",
                {
                    "statement": "The nosecap shall survive 1800 K for 300 s.",
                    "verificationMethod": "TEST",
                    "status": "BASELINED",
                },
            ),
            _doc("System", "SYS:1", {"name": "Booster", "lifecycleState": "DEVELOPMENT"}),
            _doc(
                "Part",
                "PART:1",
                {
                    "partNumber": "P-1",
                    "name": "Nosecap",
                    "revision": "C",
                    "criticality": "CRITICAL",
                    "isSingleSource": True,
                },
            ),
            _doc(
                "Facility",
                "FAC:1",
                {
                    "name": "Plant 1",
                    "facilityType": "MANUFACTURING",
                    "surgeCapacity": {"unitsPerHour": 4, "shiftsPerDay": 2},
                },
            ),
            _doc(
                "ProcessPlan",
                "PP:1",
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
            _doc(
                "Model",
                "MDL:1",
                {
                    "name": "Aero twin",
                    "modelType": "AERODYNAMIC",
                    "modelVersion": "1.2",
                    "fidelity": {"overall": 0.7},
                    "approvedForUse": True,
                },
            ),
            _doc(
                "Supplier",
                "SUP:1",
                {"name": "Source A", "tier": 1, "riskScore": 0.3, "leadTimeDays": 60},
            ),
            _doc(
                "ThreatObservation",
                "TOBS:1",
                {"observationTime": "2026-11-01T00:00:00Z", "sensorType": "GROUND_RADAR"},
            ),
            _doc(
                "ThreatSystem",
                "THR:1",
                {
                    "designation": "T-1",
                    "threatClass": "HGV",
                    "kinematicProfile": {"mach": 6},
                    "observationIds": ["TOBS:1"],
                },
            ),
        ],
        [
            _relation("satisfies", ("Part", "PART:1"), ("Requirement", "REQ:1")),
            _relation("manufacturedBy", ("Part", "PART:1"), ("Facility", "FAC:1")),
            _relation("supplies", ("Supplier", "SUP:1"), ("Part", "PART:1")),
            _relation("threatens", ("ThreatSystem", "THR:1"), ("Part", "PART:1")),
            _relation("derivedFrom", ("ThreatSystem", "THR:1"), ("ThreatObservation", "TOBS:1")),
        ],
    )

    # -- Pillar E: the operator is credentialed for the released process -----
    workforce = clients["workforce"]
    skill = workforce.post(
        "/v1/skills",
        json={
            "name": "CMC layup",
            "code": "CMC-1",
            "category": "MANUFACTURING",
            "clearanceRequired": "SECRET",
        },
    )
    assert skill.status_code == 201
    skill_id = skill.json()["skill"]["id"]

    person = workforce.post(
        "/v1/people",
        json={
            "employeeId": "E-1",
            "name": "A Person",
            "citizenship": "US",
            "clearanceLevel": "TOP SECRET",
            "clearanceExpiry": FAR_FUTURE,
            "region": "MIDWEST",
            "skillIds": [skill_id],
        },
    )
    assert person.status_code == 201
    person_id = person.json()["person"]["id"]
    assert (
        workforce.post("/v1/credentials", json={"personId": person_id, "skillId": skill_id}).status_code
        == 201
    )
    assert workforce.get(
        "/v1/work-authorisation", params={"personId": person_id, "skillId": skill_id}
    ).json()["allowed"]

    # -- Pillar A: the article was built to a reproducible baseline ---------
    architecture = clients["architecture"]
    baseline = architecture.post(
        "/v1/baselines",
        json={
            "systemId": "SYS:1",
            "name": "Nosecap build C",
            "members": [{"entityType": "Part", "entityId": "PART:1", "revision": "C"}],
        },
    )
    assert baseline.status_code == 201
    baseline_id = baseline.json()["baseline"]["id"]

    # -- Pillar C: admit the result against that baseline -------------------
    testlab = clients["testlab"]
    result = testlab.post(
        "/v1/test-results",
        json={
            "testMethod": "arc-jet",
            "outcome": "PASS",
            "campaignId": None,
            "requirementIds": ["REQ:1"],
            "configurationSnapshot": {"variantId": "PART:1", "baselineId": baseline_id},
            "measurements": [{"name": "stagnationTemp", "value": 1800, "unit": "K"}],
            "limits": {"stagnationTemp": {"max": 1850}},
            "reviewedBy": "usr:reviewer",
            "dataSetUris": ["s3://ngsh-test/arc/run-001"],
        },
    )
    assert result.status_code == 201
    result_id = result.json()["testResult"]["id"]
    assert result.json()["anomalies"] == []

    coverage = architecture.get("/v1/requirements/REQ:1/coverage")
    assert coverage.status_code == 200
    assert coverage.json()["verified"] is True

    # -- Pillar B: the operator records the run against the plan ------------
    manufacturing = clients["manufacturing"]
    run = manufacturing.post(
        "/v1/process-runs",
        json={
            "processPlanId": "PP:1",
            "partId": "PART:1",
            "facilityId": "FAC:1",
            "operatorId": person_id,
            "opId": "OP1",
            "measuredParameters": {"temperature": 180.0},
            "testResultId": result_id,
        },
    )
    assert run.status_code == 201
    traveller = manufacturing.post("/v1/travellers", json={"processPlanId": "PP:1"}).json()
    assert traveller["nextOperation"] == "OP2"
    rate = manufacturing.post(
        "/v1/simulate-rate", json={"facilityId": "FAC:1", "units": 100, "horizonDays": 30}
    ).json()
    assert rate["meetsDemand"] is True

    # -- Pillar C closes the twin loop from the evidence --------------------
    validation = testlab.post("/v1/twin-validation", json={"testResultId": result_id, "modelId": "MDL:1"})
    assert validation.status_code == 200
    assert validation.json()["fidelity"] == 0.72

    # -- Pillar D: exposure becomes a programme risk, then a play -----------
    supply = clients["supply"]
    assert supply.get("/v1/supply-risks").json()["count"] == 1
    assert (
        supply.post(
            "/v1/reconstitutes",
            json={"fromRef": {"type": "Supplier", "id": "SUP:1"}, "toRef": {"type": "Part", "id": "PART:1"}},
        ).status_code
        == 201
    )
    assert supply.get("/v1/supply-risks").json()["count"] == 0
    surge = supply.post(
        "/v1/surge", json={"facilityId": "FAC:1", "demandUnits": 50, "horizonDays": 120}
    ).json()
    assert surge["bottleneckSupplier"]["supplierId"] == "SUP:1"

    # -- Pillars F and G: engage the threat and report the kill chain -------
    engagement = clients["engagement"]
    scenario = engagement.post(
        "/v1/scenarios",
        json={
            "name": "Terminal defence",
            "threatSystemIds": ["THR:1"],
            "sensorChain": [{"sensorId": "SEN:1"}],
            "effectorChain": [{"effectorId": "EFF:1"}],
            "monteCarloConfig": {"pkMean": 0.8, "pkSigma": 0.1, "detectionProbability": 0.9},
        },
    )
    assert scenario.status_code == 201
    scenario_id = scenario.json()["scenario"]["id"]

    batch = engagement.post(f"/v1/scenarios/{scenario_id}/batch", json={"runs": 2_000, "seed": 9})
    assert batch.status_code == 200
    assert batch.json()["statistics"]["meanPk"] > 0.5

    chain = engagement.get("/v1/kill-chain", params={"scenarioId": scenario_id}).json()
    assert chain["complete"] is True, chain

    # -- One traversal reaches every pillar --------------------------------
    trace = thread.get("/v1/trace", params={"root": "Part:PART:1", "depth": 3}).json()
    observed = {node["type"] for node in trace["nodes"]}
    assert {
        "Requirement",
        "TestResult",
        "ProcessRun",
        "Model",
        "Supplier",
        "ThreatSystem",
        "ThreatObservation",
        "EngagementScenario",
        "Facility",
    } <= observed, observed

    # And the graph is derived from the log: the same traversal survives a
    # projection rebuild.
    rebuild = thread.post("/v1/project/replay")
    assert rebuild.status_code == 200
    replayed = thread.get("/v1/trace", params={"root": "Part:PART:1", "depth": 3}).json()
    assert {node["type"] for node in replayed["nodes"]} == observed
