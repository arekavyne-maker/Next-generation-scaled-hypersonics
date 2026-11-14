"""The contract-to-code generation pipeline.

The generated models must stay in step with the contract layer. A shape that
exists only in the contract, or only in the generated code, is a defect that
is invisible until something depends on it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = REPO_ROOT / "contracts"
GENERATOR = REPO_ROOT / "tools" / "codegen" / "generate.py"
GENERATED = REPO_ROOT / "libs" / "ngsh-core" / "ngsh_core" / "generated" / "ontology_models.py"

pytestmark = pytest.mark.contract


def test_the_generated_output_is_up_to_date() -> None:
    """The committed models must match a fresh generation from the contract."""
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_generation_is_deterministic() -> None:
    """Regenerating twice must produce byte-identical output."""
    outputs = []
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, str(GENERATOR)], capture_output=True, text=True, cwd=REPO_ROOT
        )
        assert result.returncode == 0, result.stderr
        outputs.append(GENERATED.read_bytes())
    assert outputs[0] == outputs[1]


def test_a_model_exists_for_every_entity_type() -> None:
    from ngsh_core.generated.ontology_models import ENTITY_MODELS

    registry = json.loads((CONTRACTS / "ontology" / "registry.json").read_text())
    declared = {entry["type"] for entry in registry["entities"]}
    assert set(ENTITY_MODELS) == declared


def test_generated_models_enforce_the_contract() -> None:
    """A model must refuse an invalid instance of its own type."""
    from ngsh_core.generated.ontology_models import TestResult
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TestResult()  # testMethod and outcome are required

    with pytest.raises(ValidationError):
        TestResult(testMethod="tensile", outcome="NOT-A-VALID-OUTCOME")

    valid = TestResult(testMethod="tensile", outcome="PASS")
    assert valid.outcome == "PASS"


def test_generated_models_validate_a_real_entity() -> None:
    """The model and the JSON Schema must accept the same entity."""
    from jsonschema import Draft202012Validator
    from ngsh_core.generated.ontology_models import TestResult
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    registry = Registry()
    for path in CONTRACTS.rglob("*.schema.json"):
        document = json.loads(path.read_text())
        registry = registry.with_resource(
            uri=document["$id"],
            resource=Resource.from_contents(document, default_specification=DRAFT202012),
        )
    entities = json.loads((CONTRACTS / "ontology" / "entities.schema.json").read_text())
    validator = Draft202012Validator(entities, registry=registry)

    model = TestResult(testMethod="tensile", outcome="PASS", campaignId="TC:1")
    body = {
        "id": "TR:1",
        "type": "TestResult",
        "tenant": "ngsh",
        "version": 1,
        "createdAt": "2026-11-14T00:00:00Z",
        "updatedAt": "2026-11-14T00:00:00Z",
        "classification": {"level": "CUI"},
        "attributes": model.model_dump(exclude_none=True),
    }

    errors = list(validator.iter_errors(body))
    assert errors == [], [error.message for error in errors]


def test_the_relation_model_keeps_the_contract_field_names() -> None:
    """'from' is a Python keyword; the wire name must survive anyway."""
    from ngsh_core.generated.ontology_models import RelationType

    relation = RelationType(
        id="REL:1",
        type="verifies",
        assertedAt="2026-11-14T00:00:00Z",
        **{"from": {"type": "TestResult", "id": "TR:1"}, "to": {"type": "Requirement", "id": "REQ:1"}},
    )
    dumped = relation.model_dump(by_alias=True)
    assert dumped["from"]["id"] == "TR:1"
    assert dumped["to"]["id"] == "REQ:1"
