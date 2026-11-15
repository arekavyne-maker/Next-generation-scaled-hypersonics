"""Rules of the test pillar: admission, anomaly surfacing, curation and the twin loop."""

from __future__ import annotations

import pytest
from ngsh_core.errors import ValidationError
from ngsh_core.testlab import (
    curate_campaign,
    find_slot_conflicts,
    surface_anomalies,
    twin_validation,
    validate_result,
)

SNAPSHOT = {"variantId": "VAR:1", "baselineId": "BL:1"}


def _result(**overrides):
    result = {
        "id": "TR:1",
        "testMethod": "arc-jet",
        "outcome": "PASS",
        "configurationSnapshot": dict(SNAPSHOT),
        "measurements": [{"name": "temp", "value": 1800, "unit": "K"}],
        "limits": {"temp": {"max": 1750}},
    }
    result.update(overrides)
    return result


def _model(**overrides):
    model = {
        "id": "MDL:1",
        "modelVersion": "1.2",
        "approvedForUse": True,
        "fidelity": {"overall": 0.7, "applicabilityEnvelope": {"mach": [1, 5]}},
    }
    model.update(overrides)
    return model


def test_admission_accepts_a_result_that_names_its_configuration():
    assert validate_result(_result()) == []


def test_admission_refuses_a_result_without_a_configuration_snapshot():
    errors = validate_result({"testMethod": "arc-jet", "outcome": "PASS"})
    assert any("configurationSnapshot" in error for error in errors)


def test_admission_refuses_an_incomplete_configuration_snapshot():
    errors = validate_result(_result(configurationSnapshot={"variantId": "VAR:1"}))
    assert any("baselineId" in error for error in errors)


def test_admission_refuses_an_unknown_outcome():
    errors = validate_result(_result(outcome="PROBABLY"))
    assert any("outcome" in error for error in errors)


def test_anomalies_surface_limit_breaches_without_changing_the_outcome():
    result = _result()
    report = surface_anomalies(result)
    assert report["hasAnomalies"] is True
    assert report["anomalies"][0]["kind"] == "above_limit"
    assert result["outcome"] == "PASS"


def test_anomalies_surface_a_trend_departure_against_the_campaign():
    reference = [{"measurements": [{"name": "temp", "value": value}]} for value in (1000, 1010, 990, 1005)]
    report = surface_anomalies(
        {"id": "TR:9", "measurements": [{"name": "temp", "value": 1400, "unit": "K"}]},
        reference_results=reference,
    )
    assert any(item["kind"] == "trend_departure" for item in report["anomalies"])


def test_curation_reports_a_pass_rate_and_flags_uncited_results():
    results = [
        _result(id="TR:1", outcome="PASS"),
        _result(id="TR:2", outcome="FAIL"),
        {"id": "TR:3", "outcome": "PASS"},
    ]
    report = curate_campaign({"id": "TC:1"}, results)
    assert report["results"] == 3
    assert report["outcomes"]["PASS"] == 2
    assert report["passRate"] == 0.6667
    assert report["curated"] is False


def test_curation_is_complete_when_every_result_cites_a_snapshot():
    report = curate_campaign({"id": "TC:1"}, [_result(), _result(id="TR:2")])
    assert report["curated"] is True


def test_twin_validation_moves_fidelity_by_the_measured_outcome():
    validation = twin_validation(_result(outcome="FAIL"), _model())
    assert validation["priorFidelity"] == 0.7
    assert validation["fidelity"] == 0.6
    assert validation["validatedByTestResultId"] == "TR:1"


def test_twin_validation_refuses_an_unapproved_model():
    with pytest.raises(ValidationError):
        twin_validation(_result(), _model(approvedForUse=False))


def test_twin_validation_refuses_a_model_without_a_fidelity_score():
    with pytest.raises(ValidationError):
        twin_validation(_result(), _model(fidelity={}))


def test_slot_conflicts_detect_an_overlap_and_ignore_an_adjacent_booking():
    candidate = {"facilityId": "FAC:1", "start": "2026-01-10T00:00:00Z", "end": "2026-01-12T00:00:00Z"}
    existing = [
        {
            "id": "RS:1",
            "facilityId": "FAC:1",
            "start": "2026-01-11T00:00:00Z",
            "end": "2026-01-13T00:00:00Z",
            "status": "BOOKED",
        }
    ]
    assert find_slot_conflicts(candidate, existing)[0]["slotId"] == "RS:1"

    adjacent = [dict(existing[0], start="2026-01-12T00:00:00Z", end="2026-01-13T00:00:00Z")]
    assert find_slot_conflicts(candidate, adjacent) == []


def test_slot_conflicts_ignore_a_released_booking():
    candidate = {"facilityId": "FAC:1", "start": "2026-01-10T00:00:00Z", "end": "2026-01-12T00:00:00Z"}
    existing = [
        {
            "id": "RS:1",
            "facilityId": "FAC:1",
            "start": "2026-01-11T00:00:00Z",
            "end": "2026-01-13T00:00:00Z",
            "status": "RELEASED",
        }
    ]
    assert find_slot_conflicts(candidate, existing) == []


def test_slot_booking_a_different_facility_does_not_conflict():
    candidate = {"facilityId": "FAC:2", "start": "2026-01-10T00:00:00Z", "end": "2026-01-12T00:00:00Z"}
    existing = [
        {
            "id": "RS:1",
            "facilityId": "FAC:1",
            "start": "2026-01-11T00:00:00Z",
            "end": "2026-01-13T00:00:00Z",
            "status": "BOOKED",
        }
    ]
    assert find_slot_conflicts(candidate, existing) == []


def test_a_slot_must_end_after_it_starts():
    with pytest.raises(ValidationError):
        find_slot_conflicts(
            {"facilityId": "FAC:1", "start": "2026-01-12T00:00:00Z", "end": "2026-01-10T00:00:00Z"}, []
        )
