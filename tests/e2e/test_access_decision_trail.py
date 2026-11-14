"""Every access decision produces both a ledger entry and an event.

Roadmap exit criterion I0-4: *100% of test requests produce both an
`access.decision.recorded` event and a ledger entry. The ledger-to-event
cross-check reports zero unexplained mismatches.*

The two records serve different purposes and neither substitutes for the
other. The ledger entry is the tamper-evident record: it commits to its
predecessor, so a rewritten history is detectable. The event is the
queryable record: it flows through the fabric, is projected, and can be
correlated with the rest of the platform's history.

If only one of them is written, the assurance is weaker in a way that is
hard to notice: a ledger with no events is a ledger nobody can query, and
events with no ledger are a history that can be rewritten without detection.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from ngsh_audit.app import create_app as create_audit_app
from ngsh_fabric.app import create_app as create_fabric_app
from ngsh_policy.app import create_app as create_policy_app

pytestmark = pytest.mark.e2e

SUBJECT = {
    "subjectId": "usr:engineer",
    "kind": "user",
    "clearance": "TOP SECRET",
    "citizenship": "US",
    "tenant": "ngsh",
    "programs": ["NGSH-SHY"],
    "needToKnow": ["NGSH-SHY"],
}

RESOURCE = {
    "type": "TestResult",
    "id": "TR:0001",
    "classification": {"level": "CUI"},
    "tenant": "ngsh",
    "program": "NGSH-SHY",
}


@pytest.fixture
def stack(settings):
    clients = {
        "policy": TestClient(create_policy_app(settings)),
        "audit": TestClient(create_audit_app(settings)),
        "fabric": TestClient(create_fabric_app(settings)),
    }
    yield clients
    for client in clients.values():
        client.close()


def _decide(policy: TestClient, action: str = "read") -> dict:
    response = policy.post(
        "/v1/decisions",
        json={"subject": SUBJECT, "resource": RESOURCE, "action": action},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_a_decision_produces_both_a_ledger_entry_and_an_event(stack) -> None:
    decision = _decide(stack["policy"])
    assert decision["decision"] == "ALLOW"

    ledger = stack["audit"].get("/v1/ledger").json()
    assert len(ledger["entries"]) == 1
    assert ledger["entries"][0]["decision"] == "ALLOW"

    events = stack["fabric"].get("/v1/events", params={"types": "access.*"}).json()["events"]
    assert len(events) == 1
    assert events[0]["eventType"] == "access.decision.recorded"
    assert events[0]["payload"]["decision"] == "ALLOW"


def test_the_two_records_agree(stack) -> None:
    """The cross-check must report zero unexplained mismatches."""
    _decide(stack["policy"], "read")
    _decide(stack["policy"], "write")

    ledger = stack["audit"].get("/v1/ledger").json()["entries"]
    events = stack["fabric"].get("/v1/events", params={"types": "access.*"}).json()["events"]

    assert len(ledger) == len(events)

    ledger_decisions = sorted(entry["decision"] for entry in ledger)
    event_decisions = sorted(event["payload"]["decision"] for event in events)
    assert ledger_decisions == event_decisions

    ledger_actions = sorted(entry["action"] for entry in ledger)
    event_actions = sorted(event["payload"]["action"] for event in events)
    assert ledger_actions == event_actions


def test_the_decision_names_its_enforcement_point(stack) -> None:
    """ADR-0004: the trail shows where a decision was made, not only that one was."""
    _decide(stack["policy"])

    ledger = stack["audit"].get("/v1/ledger").json()["entries"]
    assert ledger[0]["enforcementPoint"], "the ledger entry names no enforcement point"

    events = stack["fabric"].get("/v1/events", params={"types": "access.*"}).json()["events"]
    assert events[0]["payload"]["enforcementPoint"] == ledger[0]["enforcementPoint"]


def test_a_denied_decision_is_recorded_in_both_places(stack) -> None:
    """A trail containing only successes is not a trail."""
    response = stack["policy"].post(
        "/v1/decisions",
        json={
            "subject": {**SUBJECT, "citizenship": "FOREIGN"},
            "resource": RESOURCE,
            "action": "read",
        },
    )
    assert response.json()["decision"] == "DENY"

    ledger = stack["audit"].get("/v1/ledger").json()["entries"]
    events = stack["fabric"].get("/v1/events", params={"types": "access.*"}).json()["events"]

    assert ledger[0]["decision"] == "DENY"
    assert events[0]["payload"]["decision"] == "DENY"


def test_repeated_identical_requests_are_deduplicated(stack) -> None:
    """A retried decision must not accumulate as a second distinct decision."""
    _decide(stack["policy"])
    _decide(stack["policy"])

    events = stack["fabric"].get("/v1/events", params={"types": "access.*"}).json()["events"]
    assert len(events) == 1, "the idempotency key did not deduplicate the repeated decision"


def test_the_ledger_chain_still_verifies_after_decisions(stack) -> None:
    _decide(stack["policy"], "read")
    _decide(stack["policy"], "write")

    verification = stack["audit"].get("/v1/ledger/verify").json()
    assert verification["valid"] is True
    assert verification["checked"] == 2
