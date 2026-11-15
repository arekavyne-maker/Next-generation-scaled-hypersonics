"""Service-level behaviour of the five pillar services.

Every test goes through the HTTP surface, because that is what the console and
the other pillars see. Events are seeded through the real log and projection so
the services read the same tables they read in a running stack.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from ngsh_core.envelope import Actor
from ngsh_core.eventlog import EventLog
from ngsh_core.publish import entity_document, entity_event

pytestmark = pytest.mark.integration

FAR_FUTURE = "2030-01-01T00:00:00+00:00"
PAST = "2025-01-01T00:00:00+00:00"


def _doc(entity_type: str, entity_id: str, attributes: dict[str, Any]) -> dict[str, Any]:
    return entity_document(
        entity_type,
        entity_id,
        attributes,
        tenant="ngsh",
        program="NGSH-SHY",
        created_by="usr:operator",
    )


def _seed(app, actor: Actor, documents: list[dict[str, Any]]) -> None:
    log = EventLog(app.state.executor)
    for document in documents:
        envelope = entity_event(document, actor, registry=app.state.registry)
        log.append(envelope)
        app.state.projector.apply(envelope)


def _person(person_id: str = "PER:1", **overrides) -> dict[str, Any]:
    attributes = {
        "employeeId": person_id,
        "name": "A Person",
        "citizenship": "US",
        "clearanceLevel": "TOP SECRET",
        "clearanceExpiry": FAR_FUTURE,
        "region": "MIDWEST",
        "skillIds": ["SKL:1"],
    }
    attributes.update(overrides)
    return _doc("Person", person_id, attributes)


def _facility(facility_id: str = "FAC:1") -> dict[str, Any]:
    return _doc(
        "Facility",
        facility_id,
        {
            "name": "Plant 1",
            "facilityType": "MANUFACTURING",
            "surgeCapacity": {"unitsPerHour": 4, "shiftsPerDay": 2},
        },
    )


def _process_plan(plan_id: str = "PP:1") -> dict[str, Any]:
    return _doc(
        "ProcessPlan",
        plan_id,
        {
            "name": "Nosecap layup",
            "processType": "AUTOCLAVE",
            "revision": "C",
            "operations": [
                {"opId": "OP1", "sequence": 1, "name": "Layup", "requiredSkillIds": ["SKL:1"]},
                {"opId": "OP2", "sequence": 2, "name": "Cure"},
            ],
        },
    )


def _model(model_id: str = "MDL:1") -> dict[str, Any]:
    return _doc(
        "Model",
        model_id,
        {
            "name": "Aero twin",
            "modelType": "AERODYNAMIC",
            "modelVersion": "1.2",
            "fidelity": {"overall": 0.7, "method": "rmse-normalised"},
            "approvedForUse": True,
        },
    )


class Workforce:
    """Small wrapper that keeps a TestClient and its app together."""

    def __init__(self, settings) -> None:
        from ngsh_workforce.app import create_app

        self.app = create_app(settings)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def close(self) -> None:
        self.client.__exit__(None, None, None)


@pytest.fixture
def workforce(settings, operator):
    service = Workforce(settings)
    yield service
    service.close()


def test_credential_lifecycle_and_authorisation(workforce, operator):
    client = workforce.client
    skill = client.post(
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

    person = client.post(
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

    credential = client.post("/v1/credentials", json={"personId": person_id, "skillId": skill_id})
    assert credential.status_code == 201
    credential_id = credential.json()["credential"]["id"]

    allowed = client.get("/v1/work-authorisation", params={"personId": person_id, "skillId": skill_id}).json()
    assert allowed["allowed"] is True
    assert allowed["credentialState"] == "ACTIVE"

    suspended = client.post(f"/v1/credentials/{credential_id}/suspend", json={})
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "SUSPENDED"

    denied = client.get("/v1/work-authorisation", params={"personId": person_id, "skillId": skill_id}).json()
    assert denied["allowed"] is False
    assert denied["credentialState"] == "SUSPENDED"

    assert client.post(f"/v1/credentials/{credential_id}/reinstate", json={}).json()["status"] == "ACTIVE"
    assert client.get("/v1/credentials", params={"personId": person_id}).json()["count"] == 1


def test_credential_issue_refuses_an_expired_clearance(workforce):
    client = workforce.client
    skill_id = client.post(
        "/v1/skills", json={"name": "Layup", "code": "L-1", "category": "MANUFACTURING"}
    ).json()["skill"]["id"]
    person_id = client.post(
        "/v1/people",
        json={
            "employeeId": "E-2",
            "name": "Lapsed Person",
            "citizenship": "US",
            "clearanceLevel": "SECRET",
            "clearanceExpiry": PAST,
        },
    ).json()["person"]["id"]

    response = client.post("/v1/credentials", json={"personId": person_id, "skillId": skill_id})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "constraint_violation"


def test_credential_issue_refuses_a_foreign_citizen(workforce):
    client = workforce.client
    skill_id = client.post(
        "/v1/skills", json={"name": "Layup", "code": "L-1", "category": "MANUFACTURING"}
    ).json()["skill"]["id"]
    person_id = client.post(
        "/v1/people",
        json={
            "employeeId": "E-3",
            "name": "Foreign Person",
            "citizenship": "FOREIGN",
            "clearanceLevel": "SECRET",
            "clearanceExpiry": FAR_FUTURE,
        },
    ).json()["person"]["id"]

    response = client.post("/v1/credentials", json={"personId": person_id, "skillId": skill_id})
    assert response.status_code == 422
    assert any("C-005" in reason for reason in response.json()["error"]["context"]["reasons"])


def test_workforce_gap_uses_credentialed_supply(workforce):
    client = workforce.client
    skill_id = client.post(
        "/v1/skills", json={"name": "Layup", "code": "L-1", "category": "MANUFACTURING"}
    ).json()["skill"]["id"]
    person_id = client.post(
        "/v1/people",
        json={
            "employeeId": "E-4",
            "name": "Qualified Person",
            "citizenship": "US",
            "clearanceLevel": "SECRET",
            "clearanceExpiry": FAR_FUTURE,
            "region": "MIDWEST",
            "skillIds": [skill_id],
        },
    ).json()["person"]["id"]
    client.post("/v1/credentials", json={"personId": person_id, "skillId": skill_id})

    report = client.post(
        "/v1/workforce/gap",
        json={"demand": [{"region": "MIDWEST", "skillId": skill_id, "headcount": 4}]},
    ).json()
    assert report["rows"][0]["credentialedSupply"] == 1
    assert report["summary"]["gap"] == 3


@pytest.fixture
def manufacturing(settings, operator):
    from ngsh_manufacturing.app import create_app

    app = create_app(settings)
    _seed(
        app,
        operator,
        [
            _person("PER:2"),
            _facility(),
            _process_plan(),
            _doc("Part", "PART:1", {"partNumber": "P-1", "name": "Nosecap", "revision": "C"}),
        ],
    )
    with TestClient(app) as client:
        yield app, client


def test_process_run_advances_the_traveller(manufacturing):
    app, client = manufacturing
    response = client.post(
        "/v1/process-runs",
        json={
            "processPlanId": "PP:1",
            "partId": "PART:1",
            "operatorId": "PER:2",
            "opId": "OP1",
            "measuredParameters": {"temperature": 180.0},
        },
    )
    assert response.status_code == 201
    assert response.json()["processRun"]["attributes"]["opId"] == "OP1"

    traveller = client.post("/v1/travellers", json={"processPlanId": "PP:1"}).json()
    assert traveller["operations"][0]["status"] == "COMPLETE"
    assert traveller["nextOperation"] == "OP2"
    assert traveller["complete"] is False


def test_process_run_refuses_an_operator_with_lapsed_clearance(settings, operator):
    from ngsh_manufacturing.app import create_app

    app = create_app(settings)
    _seed(
        app,
        operator,
        [
            _person("PER:9", clearanceExpiry=PAST),
            _facility(),
            _process_plan(),
        ],
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/process-runs",
            json={"processPlanId": "PP:1", "operatorId": "PER:9", "opId": "OP1"},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "constraint_violation"


def test_genealogy_names_an_unrecorded_provenance_chain(manufacturing):
    _, client = manufacturing
    report = client.get("/v1/genealogy/PART:1").json()
    assert report["complete"] is False
    assert report["gaps"]


def test_rate_simulation_reports_the_binding_constraint(manufacturing):
    _, client = manufacturing
    report = client.post(
        "/v1/simulate-rate", json={"facilityId": "FAC:1", "units": 5_000, "horizonDays": 30}
    ).json()
    assert report["meetsDemand"] is False
    assert report["constraints"]


@pytest.fixture
def testlab(settings, operator):
    from ngsh_testlab.app import create_app

    app = create_app(settings)
    _seed(app, operator, [_model()])
    with TestClient(app) as client:
        yield app, client


def _admissible_result(**overrides):
    body = {
        "testMethod": "arc-jet",
        "outcome": "PASS",
        "configurationSnapshot": {"variantId": "VAR:1", "baselineId": "BL:1"},
        "measurements": [{"name": "stagnationTemp", "value": 1800, "unit": "K"}],
        "limits": {"stagnationTemp": {"max": 1750}},
    }
    body.update(overrides)
    return body


def test_result_without_configuration_is_refused(testlab):
    _, client = testlab
    response = client.post("/v1/test-results", json={"testMethod": "arc-jet", "outcome": "PASS"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "constraint_violation"


def test_result_is_admitted_with_anomalies_surfaced(testlab):
    _, client = testlab
    response = client.post("/v1/test-results", json=_admissible_result())
    assert response.status_code == 201
    body = response.json()
    assert body["anomalies"][0]["kind"] == "above_limit"
    assert body["testResult"]["attributes"]["anomalyFlags"] == ["above_limit"]


def test_twin_validation_updates_the_model_and_asserts_the_evidence_edge(testlab):
    app, client = testlab
    result_id = client.post("/v1/test-results", json=_admissible_result()).json()["testResult"]["id"]

    validation = client.post("/v1/twin-validation", json={"testResultId": result_id, "modelId": "MDL:1"})
    assert validation.status_code == 200
    body = validation.json()
    assert body["validatedByTestResultId"] == result_id
    assert body["priorFidelity"] == 0.7
    assert body["fidelity"] == 0.72

    updated = app.state.projector.entity("Model", "MDL:1")
    assert updated["attributes"]["fidelity"]["overall"] == 0.72

    edges = [
        edge
        for edge in app.state.projector.relations(relation_type="derivedFrom", limit=10)
        if edge["from"]["id"] == result_id
    ]
    assert edges[0]["to"]["id"] == "MDL:1"


def test_result_publishes_verifies_after_the_result_itself(settings, operator):
    from ngsh_testlab.app import create_app

    app = create_app(settings)
    _seed(
        app,
        operator,
        [
            _doc(
                "Requirement",
                "REQ:1",
                {
                    "statement": "Survive the flight envelope",
                    "verificationMethod": "TEST",
                    "status": "BASELINED",
                },
            )
        ],
    )
    with TestClient(app) as client:
        response = client.post("/v1/test-results", json=_admissible_result(requirementIds=["REQ:1"]))
        assert response.status_code == 201
    edges = app.state.projector.relations(relation_type="verifies", limit=10)
    assert edges and edges[0]["from"]["id"].startswith("TR:")


def test_range_slot_conflict_is_a_409(testlab):
    _, client = testlab
    slot = {
        "facilityId": "RNG:1",
        "start": "2026-03-01T00:00:00Z",
        "end": "2026-03-03T00:00:00Z",
    }
    assert client.post("/v1/range-slots", json=slot).status_code == 201
    overlapping = dict(slot, start="2026-03-02T00:00:00Z", end="2026-03-04T00:00:00Z")
    response = client.post("/v1/range-slots", json=overlapping)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "range_slot_conflict"


@pytest.fixture
def supply(settings, operator):
    from ngsh_supply.app import create_app

    app = create_app(settings)
    _seed(
        app,
        operator,
        [
            _doc(
                "Part",
                "PART:1",
                {"partNumber": "P-1", "name": "Nosecap", "criticality": "CRITICAL", "isSingleSource": True},
            ),
            _facility(),
            _doc("Supplier", "SUP:1", {"name": "Source A", "tier": 1, "riskScore": 0.3, "leadTimeDays": 60}),
        ],
    )
    with TestClient(app) as client:
        yield app, client


def test_c007_risk_is_cleared_by_a_reconstitution_path(supply):
    app, client = supply
    assert client.get("/v1/supply-risks").json()["count"] == 1

    response = client.post(
        "/v1/reconstitutes",
        json={"fromRef": {"type": "Supplier", "id": "SUP:1"}, "toRef": {"type": "Part", "id": "PART:1"}},
    )
    assert response.status_code == 201
    assert client.get("/v1/supply-risks").json()["count"] == 0


def test_surge_names_the_bottleneck_supplier(supply):
    _, client = supply
    report = client.post(
        "/v1/surge", json={"facilityId": "FAC:1", "demandUnits": 100, "horizonDays": 120}
    ).json()
    assert report["bottleneckSupplier"]["supplierId"] == "SUP:1"
    assert report["supplierCount"] == 1


def test_reconstitution_playbook_ranks_alternatives(supply):
    _, client = supply
    report = client.post(
        "/v1/reconstitution",
        json={
            "partId": "PART:1",
            "alternatives": [
                {"supplierId": "SUP:slow", "leadTimeDays": 120, "riskScore": 0.1},
                {"supplierId": "SUP:fast", "leadTimeDays": 30, "riskScore": 0.2},
            ],
        },
    ).json()
    assert report["steps"][0]["target"] == "SUP:fast"
    assert report["coverageDays"] == 150


@pytest.fixture
def engagement(settings, operator):
    from ngsh_engagement.app import create_app

    app = create_app(settings)
    _seed(
        app,
        operator,
        [
            _doc(
                "ThreatSystem",
                "THR:1",
                {"designation": "T-1", "threatClass": "HGV", "kinematicProfile": {"mach": 6}},
            )
        ],
    )
    with TestClient(app) as client:
        yield app, client


def _scenario_body() -> dict[str, Any]:
    return {
        "name": "Terminal defence",
        "threatSystemIds": ["THR:1"],
        "sensorChain": [{"sensorId": "SEN:1", "type": "RADAR"}],
        "effectorChain": [{"effectorId": "EFF:1", "type": "INTERCEPTOR"}],
        "monteCarloConfig": {"pkMean": 0.8, "pkSigma": 0.1, "detectionProbability": 0.9},
    }


def test_scenario_batch_is_reproducible(engagement):
    _, client = engagement
    scenario = client.post("/v1/scenarios", json=_scenario_body())
    assert scenario.status_code == 201
    scenario_id = scenario.json()["scenario"]["id"]

    first = client.post(f"/v1/scenarios/{scenario_id}/batch", json={"runs": 2_000, "seed": 5}).json()
    second = client.post(f"/v1/scenarios/{scenario_id}/batch", json={"runs": 2_000, "seed": 5}).json()
    assert first["statistics"] == second["statistics"]
    assert first["runs"] == 2_000


def test_kill_chain_names_missing_stages(engagement):
    _, client = engagement
    scenario_id = client.post("/v1/scenarios", json=_scenario_body()).json()["scenario"]["id"]
    report = client.get("/v1/kill-chain", params={"scenarioId": scenario_id}).json()
    assert "DETECT" in report["missing"]
    assert "ASSESS" in report["missing"]
    assert "ENGAGE" not in report["missing"]
