"""HTTP behaviour of the capabilities added after the six-pillar slice.

Every test seeds authoritative facts through the real event log and projection,
then exercises the service's HTTP surface. Nothing here writes to a service
table directly, because a second write path would be a second source of truth.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from ngsh_core.envelope import Actor
from ngsh_core.eventlog import EventLog
from ngsh_core.publish import (
    entity_document,
    entity_event,
    relation_document,
    relation_event,
)

pytestmark = pytest.mark.integration

FAR_FUTURE = "2030-01-01T00:00:00+00:00"


def _doc(
    entity_type: str,
    entity_id: str,
    attributes: dict[str, Any],
    *,
    classification: str = "CUI",
) -> dict[str, Any]:
    return entity_document(
        entity_type,
        entity_id,
        attributes,
        tenant="ngsh",
        program="NGSH-SHY",
        created_by="usr:operator",
        classification=classification,
    )


def _registry(app):
    registry = getattr(app.state, "registry", None)
    if registry is not None:
        return registry
    from ngsh_core.ontology import OntologyLoader

    return OntologyLoader(app.state.settings.contracts_dir).load()


def _seed(app, actor: Actor, documents: list[dict[str, Any]]) -> None:
    log = EventLog(app.state.executor)
    registry = _registry(app)
    for document in documents:
        envelope = entity_event(document, actor, registry=registry)
        log.append(envelope)
        app.state.projector.apply(envelope)


def _seed_relation(app, actor: Actor, relation_type: str, source, target) -> None:
    log = EventLog(app.state.executor)
    document = relation_document(
        relation_type,
        source,
        target,
        tenant="ngsh",
        asserted_by=actor.subjectId,
    )
    envelope = relation_event(document, actor, registry=_registry(app))
    log.append(envelope)
    app.state.projector.apply(envelope)


class Service:
    def __init__(self, factory) -> None:
        self.app = factory
        self.client = TestClient(self.app)
        self.client.__enter__()

    def close(self) -> None:
        self.client.__exit__(None, None, None)


def _service(settings, module: str, attribute: str = "create_app") -> Service:
    imported = __import__(module, fromlist=[attribute])
    return Service(getattr(imported, attribute)(settings))


@pytest.fixture
def industrial(settings):
    service = _service(settings, "ngsh_industrial.app")
    yield service
    service.close()


@pytest.fixture
def architecture(settings):
    service = _service(settings, "ngsh_architecture.app")
    yield service
    service.close()


@pytest.fixture
def testlab(settings):
    service = _service(settings, "ngsh_testlab.app")
    yield service
    service.close()


@pytest.fixture
def workforce(settings):
    service = _service(settings, "ngsh_workforce.app")
    yield service
    service.close()


@pytest.fixture
def engagement(settings):
    service = _service(settings, "ngsh_engagement.app")
    yield service
    service.close()


@pytest.fixture
def thread(settings):
    service = _service(settings, "ngsh_thread.app")
    yield service
    service.close()


@pytest.fixture
def analytics(settings):
    service = _service(settings, "ngsh_analytics.app")
    yield service
    service.close()


@pytest.fixture
def integration(settings):
    service = _service(settings, "ngsh_integration.app")
    yield service
    service.close()


# -- Pillar H ---------------------------------------------------------------


def test_industrial_surge_is_verified_annotated_and_readable(industrial, operator):
    _seed(
        industrial.app,
        operator,
        [
            _doc(
                "Facility",
                "FAC:1",
                {
                    "name": "Plant 1",
                    "facilityType": "MANUFACTURING",
                    "surgeCapacity": {"unitsPerHour": 4, "shiftsPerDay": 2},
                },
            ),
            _doc("Supplier", "SUP:1", {"name": "Supplier 1", "tier": 1, "riskScore": 0.1, "leadTimeDays": 10}),
        ],
    )
    response = industrial.client.post(
        "/v1/surge-readiness",
        json={"facilityId": "FAC:1", "demandUnits": 100, "twinRunId": "RUN:1", "owner": "usr:programme"},
    )
    assert response.status_code == 200
    report = response.json()
    assert report["verified"] is True
    assert report["evidence"]["twinRunId"] == "RUN:1"

    stored = industrial.client.get("/v1/surge-readiness/FAC:1")
    assert stored.status_code == 200
    assert stored.json()["confidenceInterval"]["level"] == 0.9


def test_industrial_reconstitution_and_affordability(industrial, operator):
    _seed(
        industrial.app,
        operator,
        [
            _doc("Part", "PART:1", {"partNumber": "P-1", "name": "Nozzle"}),
            _doc("Requirement", "REQ:1", {"statement": "The nozzle shall survive 300 s.", "verificationMethod": "TEST", "status": "BASELINED"}),
        ],
    )
    _seed_relation(industrial.app, operator, "satisfies", ("Part", "PART:1"), ("Requirement", "REQ:1"))

    reconstitution = industrial.client.post(
        "/v1/reconstitution/assess",
        json={
            "partId": "PART:1",
            "candidates": [{"supplierId": "SUP:2", "leadTimeDays": 20, "riskScore": 0.2}],
            "exercise": {
                "completedAt": "2026-01-01T00:00:00+00:00",
                "measuredTimeToReconstituteDays": 27.0,
            },
            "owner": "usr:supply",
        },
    )
    assert reconstitution.status_code == 200
    assert reconstitution.json()["timeToReconstituteDays"] == 27.0

    affordability = industrial.client.post(
        "/v1/affordability/trace",
        json={
            "requirementIds": ["REQ:1"],
            "quantity": 10,
            "costEstimates": [
                {"subjectId": "PART:1", "amount": 900.0, "basis": "ACTUAL", "confidence": 0.9}
            ],
        },
    )
    assert affordability.status_code == 200
    assert affordability.json()["summary"]["tracedCount"] == 1
    assert affordability.json()["summary"]["unitCostAtQuantity"] == 90.0


def test_industrial_computes_a_rate_curve(industrial):
    response = industrial.client.post(
        "/v1/affordability/rate-curve",
        json={
            "points": [
                {"rate": 10, "unitCost": 100.0},
                {"rate": 20, "unitCost": 90.0},
            ],
            "quantity": 40,
        },
    )
    assert response.status_code == 200
    assert response.json()["predictedUnitCost"] > 0


# -- Pillar A extensions ----------------------------------------------------


def test_architecture_generates_a_variant_family(architecture, operator):
    response = architecture.client.post(
        "/v1/variants/generate",
        json={
            "familyId": "FAM:1",
            "coreMembers": [{"entityType": "Part", "entityId": "PART:A", "revision": "A"}],
            "variantSpecs": [
                {"variantId": "BLK-1", "systemId": "SYS:1"},
                {"variantId": "BLK-2", "systemId": "SYS:2"},
            ],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["generatedCount"] == 2
    assert architecture.app.state.projector.entities(entity_type="Variant")
    assert architecture.client.get("/v1/reference-architectures").json()["sufficient"] is True


def test_architecture_generates_an_icd_from_a_registered_interface(architecture, operator):
    _seed(
        architecture.app,
        operator,
        [
            _doc("System", "SYS:1", {"name": "HBTSS", "systemType": "SENSOR", "lifecycleState": "FIELDED"}),
            _doc("System", "SYS:2", {"name": "Aegis", "systemType": "C2", "lifecycleState": "FIELDED"}),
        ],
    )
    registered = architecture.client.post(
        "/v1/interfaces",
        json={
            "interfaceId": "IFACE:1",
            "fromSystemId": "SYS:1",
            "toSystemId": "SYS:2",
            "characteristics": {
                "rate": 1000,
                "latency": 20,
                "timing": "PERIODIC",
                "envelope": {"rangeKm": 500},
            },
        },
    )
    assert registered.status_code == 201
    digest = registered.json()["interface"]["digest"]

    generated = architecture.client.post("/v1/icds/generate", json={"interfaceDigest": digest})
    assert generated.status_code == 200
    assert generated.json()["verification"]["conformant"] is True


def test_architecture_assesses_insertion_against_the_projected_subsystem(architecture, operator):
    _seed(
        architecture.app,
        operator,
        [_doc("Subsystem", "SUB:TPS", {"parentSystemId": "SYS:1", "name": "TPS", "subsystemType": "THERMAL", "maturity": "TRL_5"})],
    )
    response = architecture.client.post(
        "/v1/insertion/assess",
        json={
            "candidate": {"name": "new TPS", "subsystemId": "SUB:TPS", "trl": 7, "srl": 6},
            "slots": [],
        },
    )
    assert response.status_code == 200
    assert response.json()["insertable"] is False


# -- Pillar C/G extensions --------------------------------------------------


def test_testlab_models_range_capacity_and_schedule(testlab, operator):
    _seed(
        testlab.app,
        operator,
        [
            _doc(
                "Facility",
                "FAC:R1",
                {
                    "name": "Range 1",
                    "facilityType": "RANGE",
                    "capacityPerPeriod": 2,
                    "telemetryCoverage": {"overall": 0.95},
                    "accreditations": ["CUI"],
                },
            ),
            _doc(
                "TestCampaign",
                "TC:1",
                {"name": "Campaign 1", "campaignType": "GROUND", "status": "PLANNED", "priority": 9, "durationDays": 1},
            ),
        ],
    )
    capacity = testlab.client.post("/v1/range-capacity", json={})
    assert capacity.status_code == 200
    assert capacity.json()["rangeCount"] == 1

    schedule = testlab.client.post("/v1/schedule/optimise", json={})
    assert schedule.status_code == 200
    assert schedule.json()["assignments"][0]["rangeId"] == "FAC:R1"


def test_testlab_fidelity_registry_withdraws_approval_on_drift(testlab, operator):
    _seed(
        testlab.app,
        operator,
        [
            _doc(
                "Model",
                "MDL:1",
                {
                    "name": "Aero twin",
                    "modelType": "AERODYNAMIC",
                    "modelVersion": "1.0",
                    "fidelity": {
                        "overall": 0.9,
                        "applicabilityEnvelope": {"mach": {"min": 4, "max": 12}},
                    },
                    "provenance": {"source": "wind tunnel"},
                    "validationHistory": [{"campaignId": "TC:1", "fidelityDelta": 0.02}],
                    "approvedForUse": True,
                    "lastApprovedAt": "2026-01-01T00:00:00+00:00",
                },
            )
        ],
    )
    registry = testlab.client.get("/v1/fidelity/registry", params={"asOf": "2026-02-01T00:00:00+00:00"})
    assert registry.status_code == 200
    assert registry.json()["summary"]["releaseGatePassed"] is True

    drift = testlab.client.post(
        "/v1/fidelity/MDL:1/drift",
        json={"driftMetric": "rmse", "driftValue": 0.12},
    )
    assert drift.status_code == 200
    assert drift.json()["approvalWithdrawn"] is True
    updated = testlab.app.state.projector.entity("Model", "MDL:1")
    assert updated["attributes"]["approvedForUse"] is False


# -- Pillar E extensions ----------------------------------------------------


def test_workforce_training_completion_maps_to_a_skill(workforce, operator):
    _seed(
        workforce.app,
        operator,
        [
            _doc("Part", "PART:1", {"partNumber": "P-1", "name": "Panel"}),
            _doc("Skill", "SKL:1", {"name": "CMC layup", "code": "CMC-1", "category": "MANUFACTURING"}),
            _doc(
                "Person",
                "PER:1",
                {
                    "employeeId": "E-1",
                    "name": "A Person",
                    "citizenship": "US",
                    "clearanceLevel": "SECRET",
                    "clearanceExpiry": FAR_FUTURE,
                    "region": "MIDWEST",
                    "skillIds": ["SKL:1"],
                },
            ),
        ],
    )
    scenario = workforce.client.post(
        "/v1/training/scenarios",
        json={
            "name": "CMC cell walkthrough",
            "references": [{"type": "Part", "id": "PART:1"}],
            "skillIds": ["SKL:1"],
        },
    )
    assert scenario.status_code == 201
    scenario_id = scenario.json()["scenario"]["scenarioId"]

    completion = workforce.client.post(
        "/v1/training/completions",
        json={
            "personId": "PER:1",
            "scenarioId": scenario_id,
            "skillId": "SKL:1",
            "score": 91,
            "passed": True,
            "completedAt": "2026-02-01T00:00:00+00:00",
        },
    )
    assert completion.status_code == 201
    assert completion.json()["completion"]["mapsToSkill"] == "SKL:1"

    listed = workforce.client.get("/v1/training/completions", params={"personId": "PER:1"})
    assert listed.json()["count"] == 1
    assert workforce.client.get("/v1/training/coverage").json()["meetsLiveReferenceTarget"] is True


def test_workforce_packages_curriculum_and_blocks_a_restricted_extract(workforce, operator):
    _seed(
        workforce.app,
        operator,
        [
            _doc("Part", "PART:OPEN", {"partNumber": "P-2", "name": "Open panel"}, classification="UNCLASSIFIED"),
            _doc("Part", "PART:HIDDEN", {"partNumber": "P-3", "name": "Secret panel"}, classification="RESTRICTED"),
        ],
    )
    package = workforce.client.post(
        "/v1/curriculum/packages",
        json={
            "title": "CMC fundamentals",
            "version": "1.0.0",
            "modules": [{"moduleId": "MOD:1"}],
            "sources": [{"id": "PART:OPEN"}],
            "guardVersion": "2026.1",
            "reviewer": "usr:professor",
        },
    )
    assert package.status_code == 201
    package_id = package.json()["package"]["packageId"]
    fetched = workforce.client.get(f"/v1/curriculum/packages/{package_id}")
    assert fetched.json()["verification"]["reproducible"] is True

    blocked = workforce.client.post(
        "/v1/extracts",
        json={
            "view": "academic",
            "records": [{"id": "PART:HIDDEN"}],
            "transformations": ["strip-cost"],
            "guardVersion": "2026.1",
            "reviewer": "usr:security",
        },
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["context"]["recorded"] is True
    assert blocked.json()["error"]["context"]["auditEntry"]["hash"]


# -- Pillar F extensions ----------------------------------------------------


def _engagement_seed(app, actor: Actor, *, scenario_type: str = "CUSTODY") -> None:
    _seed(
        app,
        actor,
        [
            _doc("ThreatSystem", "THR:1", {"designation": "HGV-1", "threatClass": "HGV"}),
            _doc(
                "ThreatObservation",
                "TOBS:1",
                {
                    "observationTime": "2026-01-01T00:00:00+00:00",
                    "trackQuality": 0.92,
                    "measurements": [
                        {"name": "handoverLatencyMs", "value": 100, "unit": "ms"},
                        {"name": "custodyContinuous", "value": 1},
                        {"name": "solutionErrorM", "value": 12.0, "unit": "m"},
                        {"name": "falseTrack", "value": 0},
                    ],
                },
                classification="RESTRICTED",
            ),
            _doc(
                "EngagementScenario",
                "ESC:R",
                {
                    "name": "red trace",
                    "scenarioType": scenario_type,
                    "threatSystemIds": ["THR:1"],
                    "sensorChain": [{"sensorId": "SEN:1"}],
                    "effectorChain": [{"effectorId": "EFF:1"}],
                },
            ),
            _doc(
                "EngagementScenario",
                "ESC:B",
                {
                    "name": "blue trace",
                    "scenarioType": scenario_type,
                    "threatSystemIds": ["THR:1"],
                    "sensorChain": [{"sensorId": "SEN:2"}],
                    "effectorChain": [{"effectorId": "EFF:2"}],
                },
            ),
            _doc(
                "Model",
                "MDL:1",
                {
                    "name": "aero",
                    "modelType": "AERODYNAMIC",
                    "modelVersion": "1.0",
                    "approvedForUse": True,
                    "fidelity": {"overall": 0.85, "applicabilityEnvelope": {"mach": {"min": 4, "max": 12}}},
                },
            ),
        ],
    )


def test_engagement_scores_fire_control_quality_from_observations(engagement, operator):
    _engagement_seed(engagement.app, operator)
    response = engagement.client.post(
        "/v1/fire-control/measure", json={"observationIds": ["TOBS:1"]}
    )
    assert response.status_code == 200
    metrics = {row["metric"]: row for row in response.json()["metrics"]}
    assert metrics["trackPurity"]["value"] == 1.0
    assert metrics["fireControlSolutionErrorM"]["value"] == 12.0


def test_engagement_composes_a_candidate_and_runs_a_plugin(engagement, operator):
    _engagement_seed(engagement.app, operator)
    candidate = engagement.client.post(
        "/v1/candidates/evaluate",
        json={
            "name": "interim cueing",
            "sensors": [{"id": "SEN:1"}],
            "effectors": [{"id": "EFF:1"}],
            "modelIds": ["MDL:1"],
            "envelope": {"mach": 8},
            "threatSystemIds": ["THR:1"],
            "runs": 100,
        },
    )
    assert candidate.status_code == 201
    scenario_id = candidate.json()["scenario"]["id"]
    stored = engagement.app.state.projector.entity("EngagementScenario", scenario_id)
    assert stored["attributes"]["resultsSummary"]["runs"] == 100

    loaded = engagement.client.post(
        "/v1/plugins",
        json={
            "manifest": {
                "pluginId": "PLUG:1",
                "name": "Cueing",
                "version": "1.0.0",
                "contractVersion": "1.0.0",
                "entrypoint": "cueing:run",
                "scenarioTypes": ["CUSTODY"],
                "referenceArchitectures": ["RA:HBTSS-AEGIS"],
            },
            "hostEnvelope": {"mach": 8},
        },
    )
    assert loaded.status_code == 201

    run = engagement.client.post(
        "/v1/plugins/PLUG:1/run",
        json={"scenarioId": "ESC:R", "scenarioType": "CUSTODY"},
    )
    assert run.status_code == 200
    assert run.json()["status"] == "COMPLETE"
    assert engagement.client.delete("/v1/plugins/PLUG:1").json()["hostAffected"] is False


def test_engagement_co_simulates_red_and_blue_on_the_same_threat(engagement, operator):
    _engagement_seed(engagement.app, operator)
    response = engagement.client.post(
        "/v1/co-simulation",
        json={"threatId": "THR:1", "redScenarioId": "ESC:R", "blueScenarioId": "ESC:B", "runs": 100},
    )
    assert response.status_code == 200
    assert response.json()["identity"]["sameThreatNode"] is True


# -- thread, analytics and integration --------------------------------------


def test_thread_searches_and_catalogues_datasets(thread, operator):
    _seed(
        thread.app,
        operator,
        [
            _doc("Part", "PART:NSN-4472", {"partNumber": "NSN-4472", "name": "TPS ablative panel"}),
            _doc(
                "TestResult",
                "TR:1",
                {
                    "campaignId": "TC:1",
                    "testMethod": "GROUND",
                    "outcome": "PASS",
                    "configurationSnapshot": {"variantId": "VAR:1", "baselineId": "BL:1"},
                    "dataSetUris": ["s3://range/run1.parquet"],
                },
            ),
        ],
    )
    found = thread.client.get("/v1/search", params={"q": "PART:NSN-4472"})
    assert found.status_code == 200
    assert found.json()["results"][0]["id"] == "PART:NSN-4472"

    datasets = thread.client.get("/v1/datasets")
    assert datasets.status_code == 200
    assert datasets.json()["summary"]["configuredCount"] == 1
    dataset_id = datasets.json()["datasets"][0]["datasetId"]
    lineage = thread.client.get(f"/v1/datasets/{dataset_id}/lineage")
    assert lineage.status_code == 200
    assert lineage.json()["lineage"][0]["resultId"] == "TR:1"


def test_analytics_reports_the_virtual_to_physical_ratio(analytics, operator):
    _seed(
        analytics.app,
        operator,
        [
            _doc(
                "EngagementScenario",
                "ESC:1",
                {"name": "engagement", "resultsSummary": {"runs": 20_000}},
            ),
            _doc("TestResult", "TR:1", {"testMethod": "FLIGHT_TEST", "outcome": "PASS"}),
        ],
    )
    report = analytics.client.post("/v1/kpis", json={"asOf": "2026-03-01T00:00:00+00:00"})
    assert report.status_code == 200
    kpi = next(row for row in report.json()["kpis"] if row["id"] == "virtual-to-physical")
    assert kpi["value"] == 20_000
    assert kpi["status"] == "MEETS"
    assert analytics.client.get("/v1/kpis/definitions").json()["count"] == 7


def test_integration_blocks_outbound_if3_and_accepts_if2(integration):
    register = integration.client.get("/v1/interfaces")
    assert register.status_code == 200
    assert register.json()["complete"] is True

    blocked = integration.client.post(
        "/v1/outbound",
        json={"interfaceId": "IF-3", "payload": {"track": "x"}},
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "outbound_blocked"

    accepted = integration.client.post(
        "/v1/outbound",
        json={"interfaceId": "IF-2", "payload": {"scenario": "x"}, "correlationId": "corr-1"},
    )
    assert accepted.status_code == 202
    assert accepted.json()["transportKey"].startswith("MSG:")
