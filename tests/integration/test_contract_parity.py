"""Contract layer parity.

The contract files under ``contracts/`` are the source of truth and the
Python bindings are generated from them by hand. These tests are what stops
the two from drifting. They fail the build when a shape is changed in one
place and not the other.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from ngsh_core.envelope import Actor, Classification, EventEnvelope

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = REPO_ROOT / "contracts"

pytestmark = pytest.mark.contract


def test_contract_validator_passes() -> None:
    """The standalone validator must pass on a clean tree."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "validate_contracts.py")],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_envelope_fields_match_the_schema() -> None:
    schema = json.loads((CONTRACTS / "events" / "event-envelope.schema.json").read_text())
    schema_fields = set(schema["properties"])
    model_fields = set(EventEnvelope.model_fields)
    assert schema_fields == model_fields


def test_actor_fields_match_the_schema() -> None:
    schema = json.loads((CONTRACTS / "ontology" / "common.schema.json").read_text())
    schema_fields = set(schema["$defs"]["Actor"]["properties"])
    model_fields = set(Actor.model_fields)
    assert schema_fields == model_fields


def test_classification_fields_match_the_schema() -> None:
    schema = json.loads((CONTRACTS / "ontology" / "common.schema.json").read_text())
    schema_fields = set(schema["$defs"]["Classification"]["properties"])
    model_fields = set(Classification.model_fields)
    assert schema_fields == model_fields


def test_registry_matches_the_schemas() -> None:
    registry = json.loads((CONTRACTS / "ontology" / "registry.json").read_text())
    entities = json.loads((CONTRACTS / "ontology" / "entities.schema.json").read_text())
    relations = json.loads((CONTRACTS / "ontology" / "relations.schema.json").read_text())

    registry_types = {entry["type"] for entry in registry["entities"]}
    schema_types = {name.removesuffix("Attributes") for name in entities["$defs"]}
    assert registry_types == schema_types

    registry_relations = {entry["type"] for entry in registry["relations"]}
    schema_relations = set(relations["properties"]["type"]["enum"])
    assert registry_relations == schema_relations


def test_event_catalog_matches_the_payload_schemas() -> None:
    catalog = json.loads((CONTRACTS / "events" / "catalog.json").read_text())
    catalogued = {entry["eventType"] for entry in catalog["events"]}
    on_disk = {
        path.name.removesuffix(".schema.json")
        for path in (CONTRACTS / "events").glob("*.schema.json")
        if path.name != "event-envelope.schema.json"
    }
    assert catalogued == on_disk


def test_every_catalogue_event_has_a_matching_schema_title() -> None:
    catalog = json.loads((CONTRACTS / "events" / "catalog.json").read_text())
    for entry in catalog["events"]:
        schema = json.loads((REPO_ROOT / entry["schema"]).read_text())
        assert schema["title"] == entry["eventType"]


def test_envelope_example_validates_against_its_schema() -> None:
    """A representative envelope must satisfy the published contract."""
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    registry = Registry()
    for path in CONTRACTS.rglob("*.schema.json"):
        document = json.loads(path.read_text())
        registry = registry.with_resource(
            uri=document["$id"],
            resource=Resource.from_contents(document, default_specification=DRAFT202012),
        )

    envelope_schema = json.loads((CONTRACTS / "events" / "event-envelope.schema.json").read_text())
    validator = Draft202012Validator(envelope_schema, registry=registry)

    envelope = EventEnvelope(
        eventType="test.result.recorded",
        aggregateType="TestResult",
        aggregateId="TR:0001",
        sequence=1,
        tenant="ngsh",
        actor=Actor(subjectId="usr:operator", kind="user", clearance="TOP SECRET", citizenship="US"),
        classification=Classification(level="CUI"),
        payload={"testResult": {"id": "TR:0001"}},
    )
    errors = list(validator.iter_errors(envelope.to_logical_json()))
    assert errors == [], [error.message for error in errors]


def test_policy_document_default_is_deny() -> None:
    policy = json.loads((CONTRACTS / "policy" / "access-policy.json").read_text())
    assert policy["defaultEffect"] == "DENY"
