"""Rules of the engagement pillar: deterministic batches, kill chain, range slots."""

from __future__ import annotations

import pytest
from ngsh_core.engagement import kill_chain, run_batch, slot_conflicts
from ngsh_core.errors import ValidationError

SCENARIO = {
    "id": "ESC:1",
    "sensorChain": [{"sensorId": "SEN:1"}],
    "effectorChain": [{"effectorId": "EFF:1"}],
    "monteCarloConfig": {"pkMean": 0.8, "pkSigma": 0.1, "detectionProbability": 0.9},
}


def test_batch_is_reproducible_from_its_seed():
    first = run_batch(SCENARIO, runs=2000, seed=42)
    second = run_batch(SCENARIO, runs=2000, seed=42)
    assert first["statistics"] == second["statistics"]
    assert first["statistics"]["meanPk"] == second["statistics"]["meanPk"]


def test_a_different_seed_produces_a_different_batch():
    first = run_batch(SCENARIO, runs=1000, seed=1)
    second = run_batch(SCENARIO, runs=1000, seed=2)
    assert first["statistics"] != second["statistics"]


def test_batch_statistics_are_ordered_and_bounded():
    statistics = run_batch(SCENARIO, runs=5000, seed=7)["statistics"]
    assert 0.0 <= statistics["p10Pk"] <= statistics["medianPk"] <= statistics["p90Pk"] <= 1.0
    assert 0.0 <= statistics["interceptProbability"] <= statistics["detectionProbability"] <= 1.0


def test_a_higher_threshold_cannot_increase_intercepts():
    low = run_batch(SCENARIO, runs=5000, seed=11, pk_threshold=0.5)["statistics"]
    high = run_batch(SCENARIO, runs=5000, seed=11, pk_threshold=0.95)["statistics"]
    assert high["intercepts"] <= low["intercepts"]


def test_batch_rejects_a_non_positive_run_count():
    with pytest.raises(ValidationError):
        run_batch(SCENARIO, runs=0)


def test_batch_rejects_a_threshold_outside_the_unit_interval():
    with pytest.raises(ValidationError):
        run_batch(SCENARIO, runs=10, pk_threshold=1.5)


def test_kill_chain_names_every_missing_stage():
    report = kill_chain(observation=None, threat=None, scenario=None, models=[])
    assert report["complete"] is False
    assert report["missing"] == ["DETECT", "CLASSIFY", "ENGAGE", "ASSESS"]


def test_kill_chain_is_complete_with_evidence_at_every_stage():
    report = kill_chain(
        observation={"id": "OBS:1"},
        threat={"id": "THR:1"},
        scenario=SCENARIO,
        models=[{"id": "MDL:1", "approvedForUse": True}],
    )
    assert report["complete"] is True
    assert report["missing"] == []


def test_an_unapproved_model_cannot_close_the_assess_stage():
    report = kill_chain(
        observation={"id": "OBS:1"},
        threat={"id": "THR:1"},
        scenario=SCENARIO,
        models=[{"id": "MDL:1", "approvedForUse": False}],
    )
    assert "ASSESS" in report["missing"]


def test_range_slots_refuse_an_overlap():
    candidate = {"facilityId": "RNG:1", "start": "2026-02-01T00:00:00Z", "end": "2026-02-03T00:00:00Z"}
    existing = [
        {
            "id": "RS:1",
            "facilityId": "RNG:1",
            "start": "2026-02-02T00:00:00Z",
            "end": "2026-02-04T00:00:00Z",
            "status": "BOOKED",
        }
    ]
    assert slot_conflicts(candidate, existing)[0]["slotId"] == "RS:1"
