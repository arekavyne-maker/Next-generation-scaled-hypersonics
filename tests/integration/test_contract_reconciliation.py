"""The contract reconciliation items.

Each test here covers a gap identified when the contract layer was reviewed
against the PSDD and the ADRs. They are the regression tests for the
reconciliation, so that a gap cannot reopen silently.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ngsh_core.envelope import Classification, Entity

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = REPO_ROOT / "contracts"

pytestmark = pytest.mark.contract


@pytest.fixture(scope="module")
def registry() -> dict:
    return json.loads((CONTRACTS / "ontology" / "registry.json").read_text())


# -- C-009: no in-place classification downgrade --------------------------


def test_c009_is_declared(registry) -> None:
    constraint = next(c for c in registry["constraints"] if c["id"] == "C-009")
    assert constraint["severity"] == "ERROR"
    assert constraint["scope"] == "write"


def test_a_downgrade_in_place_is_rejected(registry, entity_factory) -> None:
    """Constraint C-009: classification may not be lowered on an existing entity."""
    from ngsh_core.ontology import OntologyLoader

    reg = OntologyLoader(CONTRACTS).load()
    entity = entity_factory(
        "TestResult",
        "TR:0001",
        {"testMethod": "tensile", "outcome": "PASS"},
        classification="SECRET",
    )

    # The same entity written at a lower classification is refused.
    downgraded = entity.model_copy(update={"classification": Classification(level="CUI")})
    errors = reg.validate_entity_update(downgraded, "SECRET")
    assert any("C-009" in error for error in errors)

    # A write at the same or a higher classification is permitted.
    assert reg.validate_entity_update(entity, "SECRET") == []
    assert reg.validate_entity_update(entity, "CUI") == []


def test_a_downgraded_copy_must_carry_its_lineage(entity_factory) -> None:
    """A downgrade creates a new entity that points back at the original."""
    from ngsh_core.ontology import OntologyLoader

    reg = OntologyLoader(CONTRACTS).load()
    entity = entity_factory(
        "TestResult",
        "TR:0002",
        {"testMethod": "tensile", "outcome": "PASS"},
        classification="CUI",
    )

    errors = reg.validate_entity_update(entity, "SECRET")
    assert any("derivedFromClassified" in error for error in errors)
    assert any("parentRefs" in error for error in errors)


def test_the_ontology_service_applies_c009() -> None:
    """The service exposes the constraint through its validation endpoint."""
    from fastapi.testclient import TestClient
    from ngsh_core.config import Settings
    from ngsh_ontology.app import create_app

    settings = Settings(dsn="sqlite:///:memory:", deployment_profile="local")
    with TestClient(create_app(settings)) as client:
        entity = {
            "id": "TR:0003",
            "type": "TestResult",
            "tenant": "ngsh",
            "version": 1,
            "createdAt": "2026-11-14T00:00:00Z",
            "updatedAt": "2026-11-14T00:00:00Z",
            "classification": {"level": "CUI"},
            "attributes": {"testMethod": "tensile", "outcome": "PASS"},
        }
        response = client.post(
            "/v1/ontology/validate",
            json={"kind": "entity", "entity": entity, "currentClassification": "SECRET"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is False
        assert any("C-009" in error for error in body["errors"])


# -- The Interface id prefix must not collide with PSDD §7 ----------------


def test_the_interface_prefix_does_not_collide_with_psdd_interfaces(registry) -> None:
    """PSDD §7 uses IF-1..IF-7 for external interfaces."""
    interface = next(e for e in registry["entities"] if e["type"] == "Interface")
    assert interface["idPrefix"] == "IFC"
    assert interface["idPrefix"] != "IF"


def test_no_entity_uses_the_bare_if_prefix(registry) -> None:
    prefixes = {entry["idPrefix"] for entry in registry["entities"]}
    assert "IF" not in prefixes


# -- Person is consumed by more than one pillar ---------------------------


def test_person_is_consumed_by_the_manufacturing_pillar(registry) -> None:
    """C-006 requires a Person for a ProcessRun operator, which is Pillar B."""
    person = next(e for e in registry["entities"] if e["type"] == "Person")
    assert "B" in person["pillars"]
    assert "E" in person["pillars"]


# -- The audit ledger's entry shape is a contract -------------------------


def test_the_audit_ledger_has_a_contract() -> None:
    path = CONTRACTS / "audit" / "ledger-entry.schema.json"
    assert path.exists(), "the audit ledger entry shape must be a contract"

    document = json.loads(path.read_text())
    for field in ("eventType", "body", "subject", "action", "resource", "decision"):
        assert field in document["properties"], f"the audit contract omits {field!r}"


def test_the_access_decision_event_names_the_enforcement_point() -> None:
    document = json.loads((CONTRACTS / "events" / "access.decision.recorded.schema.json").read_text())
    assert "enforcementPoint" in document["properties"]


# -- The catalog's owner vocabulary ----------------------------------------


def test_the_catalog_explains_the_foundation_owner() -> None:
    """'FOUNDATION' in the catalog means the services, not the PSDD §4.1 layer."""
    catalog = json.loads((CONTRACTS / "events" / "catalog.json").read_text())
    assert "foundation layer" in catalog["description"].lower()


def test_pillar_e_can_observe_access_decisions() -> None:
    """Pillar E must be able to prove a sanitised extract held nothing classified."""
    catalog = json.loads((CONTRACTS / "events" / "catalog.json").read_text())
    assert "access.*" in catalog["subscriptionGroups"]["pillarE"]


# -- The conflict event is a first-class record ---------------------------


def test_reconcile_conflicts_are_catalogue_events() -> None:
    catalog = json.loads((CONTRACTS / "events" / "catalog.json").read_text())
    types = {entry["eventType"] for entry in catalog["events"]}
    assert "reconcile.conflict.recorded" in types

    document = json.loads((CONTRACTS / "events" / "reconcile.conflict.recorded.schema.json").read_text())
    for field in ("aggregateId", "conflictClass", "resolution"):
        assert field in document["properties"]


def test_the_edge_block_carries_the_branching_point() -> None:
    """Without these the fabric cannot tell a fast-forward from a duplicate."""
    envelope = json.loads((CONTRACTS / "events" / "event-envelope.schema.json").read_text())
    properties = envelope["properties"]["edge"]["properties"]
    assert "localSequence" in properties
    assert "branchedFromSeq" in properties


# -- An entity's floor and prefix are enforced ---------------------------


def test_entity_prefixes_are_unique(registry) -> None:
    prefixes = [entry["idPrefix"] for entry in registry["entities"]]
    assert len(prefixes) == len(set(prefixes)), "two entity types share an id prefix"


def test_an_entity_with_the_wrong_prefix_is_rejected() -> None:
    from ngsh_core.ontology import OntologyLoader

    reg = OntologyLoader(CONTRACTS).load()
    entity = Entity(
        id="TR:0001",
        type="TestResult",
        tenant="ngsh",
        classification=Classification(level="CUI"),
        attributes={"testMethod": "tensile", "outcome": "PASS"},
    )
    assert reg.validate_entity(entity) == []

    wrong = entity.model_copy(update={"id": "IF:0001"})
    errors = reg.validate_entity(wrong)
    assert any("declared prefix" in error for error in errors)
