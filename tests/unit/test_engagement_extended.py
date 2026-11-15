"""Pillars F and G extended rules: quality, candidates, plug-ins, co-simulation."""

from __future__ import annotations

import pytest
from ngsh_core.engagement import (
    co_simulation,
    compose_interim_candidate,
    fire_control_quality,
    load_plugin,
    run_plugin,
    unload_plugin,
)
from ngsh_core.errors import ValidationError

THREAT = {"id": "THR:1", "attributes": {"observationIds": ["OBS:1"]}}


def test_fire_control_quality_measures_handover_purity_and_error():
    report = fire_control_quality(
        handovers=[
            {"handoverId": "H1", "latencyMs": 100, "continuous": True},
            {"handoverId": "H2", "latencyMs": 900, "continuous": False},
        ],
        tracks=[
            {"trackId": "T1", "falseTrack": False},
            {"trackId": "T2", "falseTrack": True},
        ],
        solutions=[{"solutionId": "S1", "errorM": 10.0}, {"solutionId": "S2", "errorM": 30.0}],
    )
    metrics = {row["metric"]: row for row in report["metrics"]}
    assert metrics["custodyHandoverQuality"]["value"] == 0.5
    assert metrics["trackPurity"]["value"] == 0.5
    assert metrics["fireControlSolutionErrorM"]["value"] == 20.0
    assert report["hasBreaches"] is True
    assert metrics["trackPurity"]["evidence"] == ["T1", "T2"]


def test_empty_fire_control_data_is_insufficient_not_perfect():
    report = fire_control_quality()
    assert report["hasBreaches"] is False
    assert report["insufficientData"] == [
        "custodyHandoverQuality",
        "trackPurity",
        "fireControlSolutionErrorM",
    ]


def _model(**overrides) -> dict:
    body = {
        "id": "MDL:1",
        "modelVersion": "2.1",
        "approvedForUse": True,
        "fidelity": {"overall": 0.85, "applicabilityEnvelope": {"mach": {"min": 4, "max": 12}}},
    }
    body.update(overrides)
    return body


def test_an_interim_candidate_is_composed_when_its_models_are_in_envelope():
    candidate = compose_interim_candidate(
        name="interim cueing",
        sensors=[{"id": "SEN:1"}],
        cueing=[{"id": "CUE:1"}],
        effectors=[{"id": "EFF:1"}],
        models=[_model()],
        envelope={"mach": 8},
        threat_system_ids=["THR:1"],
    )
    assert candidate["accepted"] is True
    assert candidate["virtualValidation"]["allModelsApproved"] is True


def test_a_model_outside_its_envelope_stops_the_candidate():
    with pytest.raises(ValidationError):
        compose_interim_candidate(
            name="too fast",
            sensors=[{"id": "SEN:1"}],
            cueing=[],
            effectors=[{"id": "EFF:1"}],
            models=[_model()],
            envelope={"mach": 20},
        )


def test_an_unapproved_model_stops_the_candidate():
    with pytest.raises(ValidationError):
        compose_interim_candidate(
            name="unapproved",
            sensors=[{"id": "SEN:1"}],
            cueing=[],
            effectors=[{"id": "EFF:1"}],
            models=[_model(approvedForUse=False)],
            envelope={"mach": 8},
        )


def _plugin(**overrides) -> dict:
    body = {
        "pluginId": "PLUG:HBTSS",
        "name": "HBTSS cueing",
        "version": "1.0.0",
        "contractVersion": "1.2.0",
        "entrypoint": "hbtss.cueing:run",
        "scenarioTypes": ["CUSTODY"],
        "referenceArchitectures": ["RA:HBTSS-AEGIS"],
    }
    body.update(overrides)
    return body


def test_a_plugin_is_loaded_isolated_and_runs_deterministically():
    plugin = load_plugin(_plugin(), host_envelope={"mach": 8})
    assert plugin["loaded"] is True
    scenario = {"id": "ESC:1", "scenarioType": "CUSTODY", "threatSystemIds": ["THR:1"]}
    first = run_plugin(plugin, scenario=scenario)
    second = run_plugin(plugin, scenario=scenario)
    assert first["deterministicKey"] == second["deterministicKey"]
    assert first["referenceArchitecture"] == "RA:HBTSS-AEGIS"


def test_an_incompatible_plugin_contract_is_refused():
    with pytest.raises(ValidationError):
        load_plugin(_plugin(contractVersion="2.0.0"))


def test_a_plugin_dependency_outside_the_host_envelope_is_refused():
    plugin = _plugin(dependencies=[{"name": "high-mach aero", "envelope": {"mach": {"min": 10, "max": 20}}}])
    with pytest.raises(ValidationError):
        load_plugin(plugin, host_envelope={"mach": 8})


def test_unloading_a_plugin_does_not_touch_the_host():
    report = unload_plugin(_plugin())
    assert report["unloaded"] is True
    assert report["hostAffected"] is False
    assert report["siblingPluginsAffected"] == []


def test_co_simulation_requires_the_identical_threat_node():
    with pytest.raises(ValidationError):
        co_simulation(
            threat=THREAT,
            red_scenario={"id": "ESC:R", "threatSystemIds": ["THR:1"]},
            blue_scenario={"id": "ESC:B", "threatSystemIds": ["THR:2"]},
            runs=50,
        )


def test_co_simulation_compares_red_and_blue_on_one_threat():
    report = co_simulation(
        threat=THREAT,
        red_scenario={"id": "ESC:R", "threatSystemIds": ["THR:1"]},
        blue_scenario={"id": "ESC:B", "threatSystemIds": ["THR:1"]},
        runs=100,
        seed=7,
    )
    assert report["identity"]["sameThreatNode"] is True
    assert report["identity"]["duplicateThreatModel"] is False
    assert report["comparison"]["runs"] == 100
    assert set(report["comparison"]) >= {"interceptProbabilityDelta", "meanPkDelta"}
