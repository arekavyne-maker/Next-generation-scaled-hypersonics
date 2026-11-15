"""HTTP behaviour of the runnable-completion layer.

The tests seed authoritative facts through the event log and then exercise the
new endpoints. They assert two kinds of property: the capability does the work
it claims, and a refusal is explicit rather than a silent empty result.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from ngsh_core.envelope import Actor
from ngsh_core.eventlog import EventLog
from ngsh_core.identity import issue_assertion
from ngsh_core.publish import (
    entity_document,
    entity_event,
    relation_document,
    relation_event,
)

pytestmark = pytest.mark.integration


def _doc(
    entity_type: str,
    entity_id: str,
    attributes: dict[str, Any],
    *,
    annotations: dict[str, str] | None = None,
) -> dict[str, Any]:
    return entity_document(
        entity_type,
        entity_id,
        attributes,
        tenant="ngsh",
        program="NGSH-SHY",
        created_by="usr:operator",
        annotations=annotations,
    )


def _registry(app):
    return app.state.registry


def _seed(app, actor: Actor, documents: list[dict[str, Any]]) -> None:
    log = EventLog(app.state.executor)
    for document in documents:
        envelope = entity_event(document, actor, registry=_registry(app))
        log.append(envelope)
        app.state.projector.apply(envelope)


def _seed_relation(app, actor: Actor, relation_type: str, source, target) -> None:
    log = EventLog(app.state.executor)
    document = relation_document(relation_type, source, target, tenant="ngsh", asserted_by=actor.subjectId)
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


def _service(settings, module: str) -> Service:
    imported = __import__(module, fromlist=["create_app"])
    return Service(imported.create_app(settings))


@pytest.fixture
def integration(settings):
    service = _service(settings, "ngsh_integration.app")
    yield service
    service.close()


@pytest.fixture
def manufacturing(settings):
    service = _service(settings, "ngsh_manufacturing.app")
    yield service
    service.close()


@pytest.fixture
def testlab(settings):
    service = _service(settings, "ngsh_testlab.app")
    yield service
    service.close()


@pytest.fixture
def ingest(settings):
    service = _service(settings, "ngsh_ingest.app")
    yield service
    service.close()


@pytest.fixture
def architecture(settings):
    service = _service(settings, "ngsh_architecture.app")
    yield service
    service.close()


@pytest.fixture
def engagement(settings):
    service = _service(settings, "ngsh_engagement.app")
    yield service
    service.close()


@pytest.fixture
def gateway(settings):
    service = _service(settings, "ngsh_gateway.app")
    yield service
    service.close()


# -- integration: adapters, receipts and persistence ------------------------

IF1_PAYLOAD = {
    "operation": "UPSERT_PART",
    "records": [{"id": "PART:1", "partNumber": "P-1", "name": "Nose cap", "revision": "C"}],
}


def test_integration_adapter_catalog_and_receipt_persistence(integration):
    catalog = integration.client.get("/v1/adapters")
    assert catalog.status_code == 200
    assert catalog.json()["count"] == 7
    assert catalog.json()["simulated"] is True

    first = integration.client.post(
        "/v1/interfaces/IF-1/inbound", json={"payload": IF1_PAYLOAD, "correlationId": "c-1"}
    )
    assert first.status_code == 202
    receipt = first.json()
    assert receipt["status"] == "ACCEPTED"
    assert receipt["deliveryId"].startswith("DLV:")
    assert receipt["idempotent"] is False

    retry = integration.client.post(
        "/v1/interfaces/IF-1/inbound", json={"payload": IF1_PAYLOAD, "correlationId": "c-1"}
    )
    assert retry.status_code == 202
    assert retry.json()["deliveryId"] == receipt["deliveryId"]
    assert retry.json()["idempotent"] is True

    listed = integration.client.get("/v1/deliveries", params={"interfaceId": "IF-1"})
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    stored = integration.client.get(f"/v1/deliveries/{receipt['deliveryId']}")
    assert stored.status_code == 200
    assert stored.json()["payload"]["operation"] == "UPSERT_PART"


def test_integration_refuses_if3_outbound_and_if6_unsigned(integration):
    blocked = integration.client.post(
        "/v1/interfaces/IF-3/outbound", json={"payload": {"tracks": [{"trackId": "T1"}]}}
    )
    assert blocked.status_code == 422
    assert "outbound traffic" in blocked.json()["error"]["message"]

    unsigned = integration.client.post(
        "/v1/interfaces/IF-6/inbound", json={"payload": {"assertion": {"subjectId": "usr:x"}}}
    )
    assert unsigned.status_code == 401


def test_integration_verifies_signed_if6_and_redacts_the_credential(integration):
    assertion = issue_assertion(
        {
            "subjectId": "usr:analyst",
            "kind": "user",
            "clearance": "SECRET",
            "citizenship": "US",
            "tenant": "ngsh",
            "programs": ["NGSH-SHY"],
            "needToKnow": ["NGSH-SHY"],
        }
    )
    response = integration.client.post(
        "/v1/interfaces/IF-6/inbound", json={"payload": {"assertion": assertion}}
    )
    assert response.status_code == 202
    receipt = response.json()
    assert receipt["validation"]["subjectId"] == "usr:analyst"

    stored = integration.client.get(f"/v1/deliveries/{receipt['deliveryId']}").json()
    assert stored["payload"]["assertion"] == "<redacted-after-verification>"


def test_integration_if5_package_is_validated(integration):
    rejected = integration.client.post(
        "/v1/interfaces/IF-5/outbound", json={"payload": {"package": {"modules": []}}}
    )
    assert rejected.status_code == 422
    accepted = integration.client.post(
        "/v1/interfaces/IF-5/outbound",
        json={"payload": {"package": {"packageId": "PKG:1", "modules": [{"moduleId": "M1"}]}}},
    )
    assert accepted.status_code == 202
    assert accepted.json()["validation"]["modules"] == 1


# -- manufacturing: production simulation -----------------------------------


def test_production_simulation_endpoint(manufacturing):
    body = {
        "demandUnits": 24,
        "horizonDays": 10,
        "seed": 11,
        "stations": [
            {"stationId": "ST1", "capacity": 2, "cycleTimeMinutes": 45, "yieldRate": 0.97},
            {"stationId": "ST2", "capacity": 1, "cycleTimeMinutes": 90, "yieldRate": 0.99},
        ],
    }
    first = manufacturing.client.post("/v1/production/simulate", json=body)
    assert first.status_code == 200
    assert first.json()["reproducible"] is True
    second = manufacturing.client.post("/v1/production/simulate", json=body)
    assert second.json()["digest"] == first.json()["digest"]
    assert first.json()["bottleneckStationId"] in {"ST1", "ST2"}


def test_production_simulation_refuses_an_empty_line(manufacturing):
    response = manufacturing.client.post("/v1/production/simulate", json={"demandUnits": 1, "stations": []})
    assert response.status_code == 422


# -- testlab: anomalies and regeneration ------------------------------------


def test_testlab_detects_limits_and_variation(testlab):
    series = testlab.client.post(
        "/v1/anomalies/detect",
        json={"series": [10.0, 10.2, 9.8, 10.1, 40.0], "threshold": 3.0},
    )
    assert series.status_code == 200
    assert series.json()["mode"] == "series"
    assert series.json()["count"] == 1

    measurements = testlab.client.post(
        "/v1/anomalies/detect",
        json={
            "measurements": [{"name": "thickness", "value": 12.0}],
            "limits": {"thickness": {"min": 1.0, "max": 10.0}},
        },
    )
    assert measurements.status_code == 200
    assert measurements.json()["limitBreaches"] == 1


def test_testlab_regenerates_a_model_from_recorded_evidence(testlab, operator):
    _seed(
        testlab.app,
        operator,
        [
            _doc(
                "Model",
                "MDL:1",
                {
                    "name": "Trajectory model",
                    "modelType": "TRAJECTORY",
                    "modelVersion": "1.0.0",
                    "fidelity": {"overall": 0.7},
                    "approvedForUse": True,
                },
            ),
            _doc(
                "TestResult",
                "TR:1",
                {
                    "testMethod": "FLIGHT_TEST",
                    "outcome": "PASS",
                    "configurationSnapshot": {"baselineId": "BL:1"},
                    "measurements": [
                        {"name": "range", "value": 90.0, "unit": "km"},
                        {"name": "range", "value": 180.0, "unit": "km"},
                    ],
                },
                annotations={
                    "predictionEvidence": (
                        '[{"name": "range", "predicted": 100.0, "observed": 90.0, "unit": "km"},'
                        ' {"name": "range", "predicted": 200.0, "observed": 180.0, "unit": "km"}]'
                    )
                },
            ),
        ],
    )

    residuals = testlab.client.post("/v1/models/MDL:1/residuals", json={"testResultIds": ["TR:1"]})
    assert residuals.status_code == 200
    assert residuals.json()["count"] == 2

    response = testlab.client.post(
        "/v1/models/MDL:1/regenerate",
        json={"testResultIds": ["TR:1"], "reason": "flight test bias"},
    )
    assert response.status_code == 201
    report = response.json()
    assert report["modelVersion"] == "1.0.1"
    assert report["requiresApproval"] is True
    assert report["correction"]["range"]["scale"] == pytest.approx(0.9)

    created = testlab.app.state.projector.entity("Model", report["modelId"])
    assert created is not None
    assert created["attributes"]["approvedForUse"] is False
    assert created["attributes"]["parentModelId"] == "MDL:1"

    relations = testlab.app.state.projector.relations_for("Model", report["modelId"])
    assert any(relation["type"] == "derivedFrom" for relation in relations)


# -- ingest: the lakehouse ---------------------------------------------------


def test_lakehouse_upload_list_fetch_and_verify(ingest):
    uploaded = ingest.client.post(
        "/v1/lakehouse/objects",
        json={
            "content": "time,value\n0,1.0\n1,2.0\n",
            "mediaType": "text/csv",
            "metadata": {"campaign": "TC:1"},
        },
    )
    assert uploaded.status_code == 201
    record = uploaded.json()["object"]
    assert record["uri"] == f"ngsh-lake://{record['digest']}"

    listed = ingest.client.get("/v1/lakehouse/objects")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    metadata = ingest.client.get(f"/v1/lakehouse/objects/{record['digest']}")
    assert metadata.json()["object"]["mediaType"] == "text/csv"

    content = ingest.client.get(
        f"/v1/lakehouse/objects/{record['digest']}/content", params={"encoding": "utf-8"}
    )
    assert content.status_code == 200
    assert content.json()["content"].startswith("time,value")

    verified = ingest.client.get(f"/v1/lakehouse/objects/{record['digest']}/verify")
    assert verified.json()["valid"] is True


def test_lakehouse_refuses_invalid_content(ingest):
    assert ingest.client.post("/v1/lakehouse/objects", json={"content": ""}).status_code == 422
    bad_base64 = ingest.client.post(
        "/v1/lakehouse/objects", json={"content": "not base64!", "encoding": "base64"}
    )
    assert bad_base64.status_code == 422
    assert ingest.client.get(f"/v1/lakehouse/objects/{'0' * 64}").status_code == 404


# -- architecture: SysML exchange -------------------------------------------


def test_sysml_export_and_import_round_trip(architecture, operator):
    _seed(
        architecture.app,
        operator,
        [
            _doc("System", "SYS:1", {"name": "Glide vehicle", "lifecycleState": "DEVELOPMENT"}),
            _doc(
                "Interface",
                "IFC:1",
                {
                    "name": "Seeker data",
                    "fromSystemId": "SYS:1",
                    "toSystemId": "SYS:1",
                    "icdVersion": "1.0",
                    "characteristics": {"rateHz": 20, "envelope": {"min": 1, "max": 2}},
                },
            ),
            _doc(
                "Requirement",
                "REQ:1",
                {"statement": "Survive re-entry.", "verificationMethod": "TEST", "status": "BASELINED"},
            ),
        ],
    )
    exported = architecture.client.get("/v1/sysml/export")
    assert exported.status_code == 200
    model = exported.json()["model"]
    assert exported.json()["counts"]["systems"] == 1

    imported = architecture.client.post("/v1/sysml/import", json={"model": model})
    assert imported.status_code == 200
    report = imported.json()
    assert report["counts"] == {"systems": 1, "interfaces": 1, "requirements": 1}
    assert report["recognised"] == {"systems": 1, "interfaces": 1, "requirements": 1}
    assert report["interfaces"][0]["characteristics"]["envelope"] == {"min": 1, "max": 2}


def test_sysml_import_names_unknown_identifiers(architecture):
    parsed = architecture.client.post(
        "/v1/sysml/import",
        json={"model": 'package X {\n part def SYS_999 {\n  attribute name = "new";\n }\n}\n'},
    )
    assert parsed.status_code == 200
    assert parsed.json()["unknown"]["systems"] == ["SYS_999"]


# -- engagement: threat digital twins ---------------------------------------


THREAT = {
    "designation": "HGV-A",
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
    "observationIds": ["TOBS:1"],
}


def test_threat_model_is_derived_linked_and_idempotent(engagement, operator):
    _seed(engagement.app, operator, [_doc("ThreatSystem", "THR:1", THREAT)])

    first = engagement.client.post("/v1/threat-models", json={"threatId": "THR:1"})
    assert first.status_code == 201
    body = first.json()
    assert body["modelId"].startswith("MDL:")
    assert body["derived"]["performance"]["speedRegime"] == "HYPERSONIC"
    assert body["requiresApproval"] is True

    threat = engagement.app.state.projector.entity("ThreatSystem", "THR:1")
    assert threat is not None
    assert body["modelId"] in threat["attributes"]["modelVersionIds"]

    again = engagement.client.post("/v1/threat-models", json={"threatId": "THR:1"})
    assert again.status_code == 200
    assert again.json()["idempotent"] is True
    assert again.json()["modelId"] == body["modelId"]

    listed = engagement.client.get("/v1/threat-models")
    assert listed.status_code == 200
    assert listed.json()["count"] >= 1

    envelope = engagement.client.get(
        f"/v1/threat-models/{body['modelId']}/envelope", params={"altitudeM": [10000, 30000]}
    )
    assert envelope.status_code == 200
    assert len(envelope.json()["samples"]) == 2


# -- gateway ----------------------------------------------------------------


def test_gateway_reports_services_and_capabilities(gateway):
    services = gateway.client.get("/v1/platform/services")
    assert services.status_code == 200
    assert services.json()["count"] == 16

    capabilities = gateway.client.get("/v1/platform/capabilities")
    assert capabilities.status_code == 200
    body = capabilities.json()
    assert body["count"] == 34
    assert body["pillarCount"] == 8
    assert body["interfaceCount"] == 7
    assert any(row["id"] == "IF-3" and row["status"] == "INBOUND_ONLY" for row in body["interfaces"])


def test_gateway_issues_only_local_assertions(gateway):
    response = gateway.client.post(
        "/v1/identity/assert",
        json={
            "subjectId": "usr:demo",
            "clearance": "SECRET",
            "citizenship": "US",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["authorization"].startswith("Bearer ")
    assert body["assertion"]["signature"]

    refused = gateway.client.post("/v1/identity/assert", json={"subjectId": "usr:demo"})
    assert refused.status_code == 422


def test_gateway_proxy_reports_an_unreachable_service_honestly(gateway, monkeypatch):
    monkeypatch.setenv("NGSH_ONTOLOGY_URL", "http://127.0.0.1:9")
    response = gateway.client.get("/api/ontology/healthz")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unreachable"


def test_gateway_refuses_local_identity_outside_local_profiles(settings, monkeypatch):
    from dataclasses import replace

    from ngsh_gateway.app import create_app

    accredited = replace(settings, deployment_profile="il5", identity_provider="piv")
    app = create_app(accredited)
    with TestClient(app) as client:
        response = client.post(
            "/v1/identity/assert",
            json={"subjectId": "usr:demo", "clearance": "SECRET", "citizenship": "US"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "local_identity_refused"
