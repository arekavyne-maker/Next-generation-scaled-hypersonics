"""Unit tests for the runnable-completion engines.

These modules are deliberately pure: they take facts and return a reviewable
result. Testing them here keeps the HTTP tests focused on transport and
persistence rather than on arithmetic.
"""

from __future__ import annotations

import pytest
from ngsh_core.adapters import adapter_catalog, deliver, probe
from ngsh_core.anomaly import detect_anomalies, scan_measurements
from ngsh_core.blobstore import BlobStore
from ngsh_core.errors import AuthenticationError, NotFoundError, ValidationError
from ngsh_core.identity import issue_assertion, verify_assertion
from ngsh_core.production_sim import simulate_production
from ngsh_core.regeneration import regenerate_model, residual_report
from ngsh_core.sysml import export_sysml, import_sysml
from ngsh_core.threatmodel import derive_threat_model, detection_envelope, model_attributes

# -- adapters ---------------------------------------------------------------


def test_if1_inbound_payload_is_validated_and_receipted():
    receipt = deliver(
        "IF-1",
        direction="INBOUND",
        payload={
            "operation": "UPSERT_PART",
            "records": [{"id": "PART:1", "partNumber": "A-1", "name": "Nose cap"}],
        },
        correlation_id="corr-1",
    )
    assert receipt["interfaceId"] == "IF-1"
    assert receipt["status"] == "ACCEPTED"
    assert receipt["validation"] == {"records": 1}
    assert receipt["transportKey"].startswith("MSG:")
    assert receipt["simulated"] is True


def test_if1_rejects_empty_records():
    with pytest.raises(ValidationError):
        deliver("IF-1", direction="INBOUND", payload={"operation": "SYNC", "records": []})


def test_if3_outbound_is_refused_by_the_programme_decision():
    with pytest.raises(ValidationError) as excinfo:
        deliver("IF-3", direction="OUTBOUND", payload={"tracks": [{"trackId": "T1"}]})
    assert "outbound traffic" in str(excinfo.value)


def test_if3_inbound_accepts_tracks():
    receipt = deliver("IF-3", direction="INBOUND", payload={"tracks": [{"trackId": "T1"}]})
    assert receipt["validation"] == {"tracks": 1}


def test_if6_requires_a_signed_assertion():
    assertion = issue_assertion(
        {
            "subjectId": "usr:analyst",
            "kind": "user",
            "clearance": "SECRET",
            "citizenship": "US",
            "tenant": "ngsh",
        }
    )
    receipt = deliver("IF-6", direction="INBOUND", payload={"assertion": assertion})
    assert receipt["validation"]["subjectId"] == "usr:analyst"
    assert receipt["validation"]["clearance"] == "SECRET"

    with pytest.raises(AuthenticationError):
        deliver("IF-6", direction="INBOUND", payload={"assertion": {**assertion, "clearance": "TOP SECRET"}})


def test_adapter_catalog_covers_every_registered_interface():
    catalog = adapter_catalog()
    assert catalog["count"] == 7
    assert catalog["inboundCount"] >= 1
    assert catalog["outboundCount"] >= 1
    if3 = next(row for row in catalog["adapters"] if row["interfaceId"] == "IF-3")
    assert if3["inbound"] is True
    assert if3["outbound"] is False


def test_probe_is_explicitly_simulated():
    result = probe("IF-2")
    assert result["simulated"] is True
    assert result["reachable"] is False
    assert result["counterpart"]


# -- production simulation --------------------------------------------------

STATIONS = [
    {
        "stationId": "ST1",
        "name": "Layup",
        "capacity": 2,
        "cycleTimeMinutes": 30,
        "yieldRate": 0.98,
        "setupMinutes": 10,
    },
    {
        "stationId": "ST2",
        "name": "Cure",
        "capacity": 1,
        "cycleTimeMinutes": 60,
        "yieldRate": 0.99,
    },
    {
        "stationId": "ST3",
        "name": "Machine",
        "capacity": 1,
        "cycleTimeMinutes": 20,
        "yieldRate": 0.995,
        "mtbfMinutes": 500,
        "mttrMinutes": 30,
    },
]


def test_production_simulation_is_reproducible():
    first = simulate_production(STATIONS, demand_units=12, horizon_days=5, seed=7)
    second = simulate_production(STATIONS, demand_units=12, horizon_days=5, seed=7)
    assert first["digest"] == second["digest"]
    assert first["completedUnits"] == second["completedUnits"]
    assert first["bottleneckStationId"] in {"ST1", "ST2", "ST3"}


def test_production_simulation_names_a_shortfall():
    result = simulate_production(
        [{"stationId": "ONLY", "capacity": 1, "cycleTimeMinutes": 600, "yieldRate": 1.0}],
        demand_units=10,
        horizon_days=1,
    )
    assert result["meetsDemand"] is False
    assert result["shortfallUnits"] > 0
    assert result["bottleneckStationId"] == "ONLY"


def test_production_simulation_refuses_bad_station_input():
    with pytest.raises(ValidationError):
        simulate_production([{"stationId": "X", "capacity": 1, "cycleTimeMinutes": 0}], demand_units=1)
    with pytest.raises(ValidationError):
        simulate_production(STATIONS, demand_units=0)


# -- anomaly detection ------------------------------------------------------


def test_zscore_detects_a_late_outlier():
    report = detect_anomalies([10.0, 10.2, 9.8, 10.1, 40.0], threshold=3.0)
    assert report["count"] == 1
    assert report["flags"][0]["value"] == 40.0


def test_limits_are_separate_from_variation():
    report = scan_measurements(
        [{"name": "thickness", "value": 12.0}],
        limits={"thickness": {"min": 1.0, "max": 10.0}},
    )
    assert report["limitBreaches"] == 1
    assert report["variationFlags"] == 0
    assert report["reviewRequired"] is True


def test_history_outlier_is_flagged_only_after_a_baseline():
    report = scan_measurements(
        [{"name": "force", "value": 100.0}],
        history={"force": [10.0, 10.2, 9.8, 10.1]},
        min_samples=3,
    )
    assert report["variationFlags"] == 1
    assert report["flags"][0]["severity"] == "VARIATION"


# -- blob store -------------------------------------------------------------


def test_blobstore_is_content_addressed_and_verifies(tmp_path):
    store = BlobStore(tmp_path / "lake")
    record = store.put(b"telemetry,value\n1,42\n", media_type="text/csv", metadata={"source": "test"})
    assert record["uri"] == f"ngsh-lake://{record['digest']}"
    content, metadata = store.get(record["digest"])
    assert content.startswith(b"telemetry")
    assert metadata["mediaType"] == "text/csv"
    assert store.verify(record["digest"])["valid"] is True
    assert store.list()[0]["digest"] == record["digest"]


def test_blobstore_refuses_missing_objects(tmp_path):
    store = BlobStore(tmp_path / "lake")
    with pytest.raises(NotFoundError):
        store.get("0" * 64)
    with pytest.raises(ValidationError):
        store.get("not-a-digest")


# -- sysml ------------------------------------------------------------------


def test_sysml_roundtrip_preserves_identity_and_scalars():
    exported = export_sysml(
        systems=[
            {
                "id": "SYS:1",
                "attributes": {"name": "Glide vehicle", "lifecycleState": "DEVELOPMENT", "massKg": 1200.5},
            }
        ],
        interfaces=[
            {
                "interfaceId": "IFC:1",
                "fromSystemId": "SYS:1",
                "toSystemId": "SYS:2",
                "characteristics": {"rateHz": 20, "envelope": {"min": 1, "max": 2}},
            }
        ],
        requirements=[{"id": "REQ:1", "attributes": {"statement": "Survive re-entry"}}],
    )
    imported = import_sysml(exported["model"])
    assert imported["counts"] == {"systems": 1, "interfaces": 1, "requirements": 1}
    assert imported["systems"][0]["attributes"]["massKg"] == 1200.5
    assert imported["interfaces"][0]["characteristics"]["envelope"] == {"min": 1, "max": 2}
    assert imported["requirements"][0]["attributes"]["statement"] == "Survive re-entry"


def test_sysml_export_requires_identifiers():
    with pytest.raises(ValidationError):
        export_sysml(systems=[{"attributes": {}}])


# -- threat model -----------------------------------------------------------

THREAT = {
    "id": "THR:1",
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
    "observationIds": ["TOBS:1", "TOBS:2"],
}


def test_threat_model_is_deterministic_and_names_its_assumptions():
    first = derive_threat_model(THREAT, model_id="MDL:1", generated_at="2026-01-01T00:00:00+00:00")
    second = derive_threat_model(THREAT, model_id="MDL:1", generated_at="2026-01-01T00:00:00+00:00")
    assert first["digest"] == second["digest"]
    assert first["performance"]["speedRegime"] == "HYPERSONIC"
    assert first["performance"]["maneuverRegime"] == "HIGH"
    assert first["confidence"]["observationCount"] == 2
    assert first["assumptions"]["detectionIsFirstOrder"] is True


def test_threat_model_requires_a_kinematic_profile():
    with pytest.raises(ValidationError):
        derive_threat_model({"designation": "X", "threatClass": "UNKNOWN", "kinematicProfile": {}})


def test_threat_model_enters_the_model_card_and_envelope():
    derived = derive_threat_model(THREAT, model_id="MDL:1")
    attributes = model_attributes(derived)
    assert attributes["modelType"] == "THREAT_KINEMATIC"
    assert attributes["approvedForUse"] is False
    envelope = detection_envelope(derived, altitudes=[10000.0, 30000.0])
    assert len(envelope["samples"]) == 2
    assert envelope["samples"][1]["effectiveRangeKm"] >= envelope["samples"][0]["effectiveRangeKm"]


# -- regeneration -----------------------------------------------------------

MODEL = {
    "id": "MDL:1",
    "name": "Trajectory model",
    "modelType": "TRAJECTORY",
    "modelVersion": "1.2.3",
    "fidelity": {"overall": 0.8},
    "codeRef": "traj@v1.2.3",
}


def test_regeneration_bumps_version_and_requires_approval():
    report = regenerate_model(
        MODEL,
        evidence=[
            {"name": "range", "predicted": 100.0, "observed": 90.0, "evidenceId": "TR:1"},
            {"name": "range", "predicted": 200.0, "observed": 180.0, "evidenceId": "TR:2"},
        ],
        reason="flight test bias",
    )
    assert report["modelVersion"] == "1.2.4"
    assert report["attributes"]["parentModelId"] == "MDL:1"
    assert report["attributes"]["approvedForUse"] is False
    assert report["correction"]["range"]["scale"] == pytest.approx(0.9)
    assert report["summary"]["rmse"] == pytest.approx(0.0)
    assert report["requiresApproval"] is True


def test_regeneration_refuses_unpaired_evidence():
    with pytest.raises(ValidationError):
        regenerate_model(MODEL, evidence=[{"name": "range", "predicted": 1.0}])


def test_residual_report_names_the_worst_disagreement():
    report = residual_report(
        MODEL,
        evidence=[
            {"name": "range", "predicted": 100.0, "observed": 95.0},
            {"name": "altitude", "predicted": 50.0, "observed": 70.0},
        ],
    )
    assert report["worst"]["name"] == "altitude"
    assert report["count"] == 2


# -- local identity assertions ---------------------------------------------


def test_assertion_roundtrip_and_tamper_detection():
    assertion = issue_assertion(
        {
            "subjectId": "usr:test",
            "kind": "user",
            "clearance": "SECRET",
            "citizenship": "US",
            "tenant": "ngsh",
        }
    )
    actor = verify_assertion(assertion)
    assert actor["subjectId"] == "usr:test"

    with pytest.raises(AuthenticationError):
        verify_assertion({**assertion, "subjectId": "usr:other"})


def test_expired_assertion_is_refused():
    assertion = issue_assertion(
        {"subjectId": "usr:test", "kind": "user", "tenant": "ngsh"},
        expires_at="2000-01-01T00:00:00+00:00",
    )
    with pytest.raises(AuthenticationError):
        verify_assertion(assertion)
