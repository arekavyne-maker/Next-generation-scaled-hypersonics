"""Rules of the workforce pillar.

Each test names the programme constraint it exercises, because these rules are
the evidence an assessor will ask for.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ngsh_core.errors import ValidationError
from ngsh_core.workforce import (
    assess_issue,
    authorise,
    clearance_rank,
    credential_state,
    gap_report,
    transition,
)

NOW = datetime(2026, 11, 15, tzinfo=UTC)


def _person(**overrides):
    person = {
        "employeeId": "E-1",
        "name": "A Person",
        "citizenship": "US",
        "clearanceLevel": "SECRET",
        "clearanceExpiry": "2027-01-01T00:00:00+00:00",
    }
    person.update(overrides)
    return person


def _skill(**overrides):
    skill = {"name": "CMC layup", "clearanceRequired": "SECRET"}
    skill.update(overrides)
    return skill


def _credential(**overrides):
    credential = {
        "personId": "PER:1",
        "skillId": "SKL:1",
        "issuedAt": "2026-01-01T00:00:00+00:00",
        "expiresAt": "2027-01-01T00:00:00+00:00",
        "status": "ACTIVE",
    }
    credential.update(overrides)
    return credential


def test_issue_allows_a_current_cleared_us_person():
    assessment = assess_issue(_person(), _skill(), NOW)
    assert assessment.allowed
    assert assessment.reasons == []


def test_issue_refuses_a_non_permitted_citizenship():
    assessment = assess_issue(_person(citizenship="FOREIGN"), _skill(), NOW)
    assert not assessment.allowed
    assert any("C-005" in reason and "FOREIGN" in reason for reason in assessment.reasons)


def test_issue_refuses_an_expired_clearance_even_when_no_expiry_is_recorded():
    missing = assess_issue(_person(clearanceExpiry=None), _skill(), NOW)
    assert not missing.allowed

    lapsed = assess_issue(_person(clearanceExpiry="2025-01-01T00:00:00+00:00"), _skill(), NOW)
    assert not lapsed.allowed
    assert any("C-006" in reason for reason in lapsed.reasons)


def test_issue_refuses_clearance_below_the_skill_requirement():
    assessment = assess_issue(_person(clearanceLevel="SECRET"), _skill(clearanceRequired="TOP SECRET"), NOW)
    assert not assessment.allowed
    assert any("below" in reason for reason in assessment.reasons)


def test_clearance_rank_is_a_personnel_vocabulary_not_a_data_vocabulary():
    assert clearance_rank("TOP SECRET") > clearance_rank("SECRET") > clearance_rank("NONE")
    assert clearance_rank("UNKNOWN") == 0


def test_expiry_makes_an_active_credential_expired():
    credential = _credential(expiresAt="2026-06-01T00:00:00+00:00")
    assert credential_state(credential, NOW) == "EXPIRED"


def test_revocation_is_terminal_and_suspension_is_not():
    assert credential_state(_credential(status="REVOKED"), NOW) == "REVOKED"
    assert credential_state(_credential(status="SUSPENDED"), NOW) == "SUSPENDED"

    with pytest.raises(ValidationError):
        transition(_credential(status="REVOKED"), "reinstate", NOW)


def test_suspend_then_reinstate_returns_to_active():
    assert transition(_credential(), "suspend", NOW) == "SUSPENDED"
    suspended = _credential(status="SUSPENDED")
    assert transition(suspended, "reinstate", NOW) == "ACTIVE"


def test_revoke_refuses_an_already_expired_credential():
    with pytest.raises(ValidationError):
        transition(_credential(expiresAt="2026-01-02T00:00:00+00:00"), "revoke", NOW)


def test_authorise_denies_when_the_credential_is_suspended():
    decision = authorise(_person(), _credential(status="SUSPENDED"), _skill(), NOW)
    assert not decision.allowed
    assert decision.credentialState == "SUSPENDED"


def test_authorise_denies_a_credential_for_a_different_skill():
    decision = authorise(_person(), _credential(), _skill(), NOW, permit_skill_id="SKL:2")
    assert not decision.allowed
    assert any("different skill" in reason for reason in decision.reasons)


def test_gap_counts_credentialed_supply_not_nominal_headcount():
    report = gap_report(
        demand=[{"region": "MIDWEST", "skillId": "SKL:1", "headcount": 4}],
        persons=[
            {"id": "PER:1", "region": "MIDWEST", "skillIds": ["SKL:1"]},
            {"id": "PER:2", "region": "MIDWEST", "skillIds": ["SKL:1"]},
        ],
        credentials=[_credential(personId="PER:1")],
        skills=[{"id": "SKL:1", "name": "Layup"}],
        at=NOW,
    )

    row = report["rows"][0]
    assert row["nominalHeadcount"] == 2
    assert row["credentialedSupply"] == 1
    assert row["gap"] == 3
    assert row["status"] == "SHORTFALL"
    assert report["summary"]["coverage"] == 0.25


def test_gap_rejects_a_demand_row_without_a_skill():
    with pytest.raises(ValidationError):
        gap_report(
            demand=[{"region": "MIDWEST", "headcount": 3}],
            persons=[],
            credentials=[],
            skills=[],
            at=NOW,
        )
