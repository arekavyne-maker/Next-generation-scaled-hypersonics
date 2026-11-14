"""Ontology registry, validation and invariants."""

from __future__ import annotations

from pathlib import Path

import pytest
from ngsh_core.envelope import Entity, Relation
from ngsh_core.errors import ValidationError
from ngsh_core.ontology import OntologyLoader, assert_entity_valid, assert_relation_valid

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = REPO_ROOT / "contracts"


@pytest.fixture(scope="module")
def registry():
    return OntologyLoader(CONTRACTS).load()


def test_registry_carries_all_23_entity_types(registry) -> None:
    """The PSDD §6.1 ontology has 23 entity types."""
    assert len(registry.entities) == 23
    assert "TestResult" in registry.entities
    assert "ThreatSystem" in registry.entities
    assert "Credential" in registry.entities


def test_registry_carries_all_10_relation_types(registry) -> None:
    assert len(registry.relations) == 10
    for relation_type in (
        "satisfies",
        "verifies",
        "manufacturedBy",
        "characterizedBy",
        "derivedFrom",
        "threatens",
        "engages",
        "requiresSkill",
        "supplies",
        "reconstitutes",
    ):
        assert relation_type in registry.relations


def test_constraints_are_loaded(registry) -> None:
    ids = {constraint["id"] for constraint in registry.constraints}
    assert {"C-001", "C-002", "C-003", "C-008"} <= ids


def test_valid_entity_passes_validation(registry, entity_factory) -> None:
    entity = entity_factory(
        "TestResult",
        "TR:0001",
        {"testMethod": "tensile", "outcome": "PASS"},
    )
    assert registry.validate_entity(entity) == []


def test_unknown_type_is_rejected(registry) -> None:
    entity = Entity(id="X:1", type="NotAThing", tenant="ngsh")
    errors = registry.validate_entity(entity)
    assert any("unknown entity type" in error for error in errors)


def test_classification_floor_is_enforced(registry, entity_factory) -> None:
    """Constraint C-001: a type may never be written below its floor."""
    entity = entity_factory(
        "ThreatSystem",
        "THR:0001",
        {"designation": "X", "threatClass": "HGV"},
        classification="UNCLASSIFIED",
    )
    errors = registry.validate_entity(entity)
    assert any("C-001" in error for error in errors)


def test_id_prefix_must_match_the_type(registry, entity_factory) -> None:
    entity = entity_factory("TestResult", "PART:0001", {"testMethod": "x", "outcome": "PASS"})
    errors = registry.validate_entity(entity)
    assert any("declared prefix" in error for error in errors)


def test_missing_required_attribute_is_reported(registry, entity_factory) -> None:
    entity = entity_factory("TestResult", "TR:0002", {})
    errors = registry.validate_entity(entity)
    assert errors
    assert any("outcome" in error or "testMethod" in error for error in errors)


def test_relation_types_must_be_declared(registry, relation_factory) -> None:
    relation = relation_factory("verifies", ("TestResult", "TR:1"), ("Requirement", "REQ:1"))
    assert registry.validate_relation(relation) == []


def test_relation_source_and_target_types_are_constrained(registry, relation_factory) -> None:
    """A 'verifies' edge runs from a test to a requirement, not the reverse."""
    relation = relation_factory("verifies", ("Requirement", "REQ:1"), ("TestResult", "TR:1"))
    errors = registry.validate_relation(relation)
    assert any("may not originate" in error for error in errors)
    assert any("may not target" in error for error in errors)


def test_classification_boundary_is_enforced(registry, relation_factory) -> None:
    """Constraint C-002: an edge may not bridge a classification boundary."""
    relation = relation_factory("verifies", ("TestResult", "TR:1"), ("Requirement", "REQ:1"))
    errors = registry.validate_relation(relation, from_classification="CUI", to_classification="SECRET")
    assert any("C-002" in error for error in errors)


def test_cross_classification_capable_relations_are_allowed(registry, relation_factory) -> None:
    relation = relation_factory("derivedFrom", ("Model", "MDL:1"), ("TestResult", "TR:1"))
    errors = registry.validate_relation(relation, from_classification="CUI", to_classification="SECRET")
    assert errors == []


def test_provenance_is_required_where_the_registry_says_so(registry) -> None:
    relation = Relation(
        id="REL:1",
        type="verifies",
        fromRef={"type": "TestResult", "id": "TR:1"},
        toRef={"type": "Requirement", "id": "REQ:1"},
    )
    errors = registry.validate_relation(relation)
    assert any("requires provenance" in error for error in errors)


def test_assert_helpers_raise(registry, entity_factory) -> None:
    entity = entity_factory("TestResult", "TR:1", {"testMethod": "t", "outcome": "PASS"})
    assert_entity_valid(registry, entity)

    bad = entity_factory("TestResult", "TR:2", {})
    with pytest.raises(ValidationError):
        assert_entity_valid(registry, bad)

    bad_relation = Relation(
        id="REL:1",
        type="verifies",
        fromRef={"type": "Requirement", "id": "REQ:1"},
        toRef={"type": "TestResult", "id": "TR:1"},
        provenance={"source": "test"},
    )
    with pytest.raises(ValidationError):
        assert_relation_valid(registry, bad_relation)


def test_types_can_be_filtered_by_pillar(registry) -> None:
    """The registry drives modular deployment, so pillar filtering must work."""
    pillar_b = registry.types_for_pillar("B")
    assert {spec.type for spec in pillar_b} >= {"Material", "ProcessPlan", "ProcessRun"}
    assert "ThreatSystem" not in {spec.type for spec in pillar_b}


def test_registry_serialises_for_the_api(registry) -> None:
    document = registry.to_dict()
    assert document["ontologyVersion"] == registry.version
    assert len(document["entities"]) == 23
    assert len(document["relations"]) == 10
