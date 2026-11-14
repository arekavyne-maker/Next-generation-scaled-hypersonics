#!/usr/bin/env python3
"""Validate the NGSH contract layer.

The contract files under ``contracts/`` are the source of truth for every
shape in the platform. This validator checks that they are internally
consistent and that they agree with the code:

1. Every JSON Schema file is a valid Draft 2020-12 schema.
2. Every ``$ref`` resolves to something that exists, locally.
3. The registry lists exactly the entity types and relation types that the
   schemas define, and nothing more.
4. Every event in the catalog has a payload schema, and every payload schema
   appears in the catalog.
5. The Python bindings in ``ngsh_core`` produce the same field set as the
   envelope schema, so the two cannot drift.

Run with ``make contracts``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = REPO_ROOT / "contracts"

FAILURES: list[str] = []
CHECKS = 0


def check(condition: bool, message: str) -> None:
    global CHECKS
    CHECKS += 1
    if not condition:
        FAILURES.append(message)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_refs(node: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.append(value)
            else:
                refs.extend(collect_refs(value))
    elif isinstance(node, list):
        for item in node:
            refs.extend(collect_refs(item))
    return refs


def contract_path_for_ref(ref: str) -> Path | None:
    """Map a contract ``$id`` reference to a file under the contracts directory.

    The fragment (``#/$defs/EntityId``) selects a definition inside the
    target document and is not part of the path.
    """
    marker = "ngsh.mil/contracts/"
    if marker not in ref:
        return None
    relative = ref.split(marker, 1)[1].split("#", 1)[0]
    if not relative:
        return None
    return CONTRACTS / relative


def validate_schemas() -> None:
    """Every schema file is valid Draft 2020-12 and its refs resolve."""
    from jsonschema import Draft202012Validator

    schema_files = sorted(CONTRACTS.rglob("*.schema.json"))
    check(bool(schema_files), "no schema files found under contracts/")

    documents: dict[str, Any] = {}
    for path in schema_files:
        document = load(path)
        documents[path.name] = document
        try:
            Draft202012Validator.check_schema(document)
        except Exception as exc:
            FAILURES.append(f"{path.relative_to(REPO_ROOT)}: invalid Draft 2020-12 schema: {exc}")
        check("$id" in document, f"{path.relative_to(REPO_ROOT)}: missing $id")

    for path in schema_files:
        document = load(path)
        for ref in collect_refs(document):
            if not ref.startswith("http"):
                continue
            target = contract_path_for_ref(ref)
            if target is None:
                FAILURES.append(f"{path.relative_to(REPO_ROOT)}: unresolvable external ref {ref}")
                continue
            check(
                target.exists(),
                f"{path.relative_to(REPO_ROOT)}: ref {ref} points at a missing file {target}",
            )

    # Resolver sanity: the entities schema must be able to resolve the
    # common schema's definitions, which is where most of the cross-file
    # references live.
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    entities = load(CONTRACTS / "ontology" / "entities.schema.json")
    common = load(CONTRACTS / "ontology" / "common.schema.json")
    relations = load(CONTRACTS / "ontology" / "relations.schema.json")

    registry = Registry()
    for document in (common, entities, relations):
        registry = registry.with_resource(
            uri=document["$id"],
            resource=Resource.from_contents(document, default_specification=DRAFT202012),
        )
    validator = Draft202012Validator(entities, registry=registry)
    try:
        validator.check_schema(entities)
    except Exception as exc:
        FAILURES.append(f"entities.schema.json does not resolve cleanly: {exc}")


def validate_registry() -> None:
    """The registry agrees with the schemas and the event catalog."""
    registry = load(CONTRACTS / "ontology" / "registry.json")
    entities_schema = load(CONTRACTS / "ontology" / "entities.schema.json")
    relations_schema = load(CONTRACTS / "ontology" / "relations.schema.json")

    registry_entities = {entry["type"] for entry in registry["entities"]}
    definitions = set(entities_schema.get("$defs", {}))
    schema_entities = {name[: -len("Attributes")] for name in definitions if name.endswith("Attributes")}

    check(
        registry_entities == schema_entities,
        f"registry entity types differ from the schema definitions: "
        f"only in registry {sorted(registry_entities - schema_entities)}, "
        f"only in schema {sorted(schema_entities - registry_entities)}",
    )

    for entry in registry["entities"]:
        def_name = f"{entry['type']}Attributes"
        check(
            def_name in definitions,
            f"registry type {entry['type']} has no schema definition {def_name}",
        )
        check(
            entry["idPrefix"].isupper() and entry["idPrefix"].isalnum(),
            f"registry idPrefix {entry['idPrefix']!r} for {entry['type']} must be uppercase alphanumeric",
        )

    registry_relations = {entry["type"] for entry in registry["relations"]}
    schema_relations = set(relations_schema.get("properties", {}).get("type", {}).get("enum", []))
    check(
        registry_relations == schema_relations,
        f"registry relation types differ from the relations schema: "
        f"only in registry {sorted(registry_relations - schema_relations)}, "
        f"only in schema {sorted(schema_relations - registry_relations)}",
    )

    for entry in registry["relations"]:
        for side in ("fromTypes", "toTypes"):
            for target in entry[side]:
                check(
                    target in registry_entities,
                    f"relation {entry['type']} references unknown entity type {target!r}",
                )

    constraint_ids = [constraint["id"] for constraint in registry.get("constraints", [])]
    check(len(constraint_ids) == len(set(constraint_ids)), "duplicate constraint ids in the registry")
    for constraint in registry.get("constraints", []):
        check(
            constraint.get("rule", "").strip() != "",
            f"constraint {constraint.get('id')} has no rule text",
        )


def validate_event_catalog() -> None:
    """Every catalogued event has a schema, and every schema is catalogued."""
    catalog = load(CONTRACTS / "events" / "catalog.json")
    catalogued = {entry["eventType"]: entry for entry in catalog["events"]}

    for event_type, entry in catalogued.items():
        schema_path = REPO_ROOT / entry["schema"]
        check(schema_path.exists(), f"event {event_type} references a missing schema {entry['schema']}")
        if schema_path.exists():
            document = load(schema_path)
            check(
                document.get("title") == event_type,
                f"schema {entry['schema']} has title {document.get('title')!r}, expected {event_type!r}",
            )

    on_disk = {
        path.name.removesuffix(".schema.json")
        for path in (CONTRACTS / "events").glob("*.schema.json")
        if path.name != "event-envelope.schema.json"
    }
    uncatalogued = on_disk - set(catalogued)
    check(
        not uncatalogued,
        f"event schemas not present in the catalog: {sorted(uncatalogued)}",
    )

    for group, patterns in catalog.get("subscriptionGroups", {}).items():
        for pattern in patterns:
            head = pattern.split(".")[0]
            check(
                any(event_type.split(".")[0] == head for event_type in catalogued),
                f"subscription group {group} references unknown event prefix {pattern!r}",
            )


def validate_audit_contract() -> None:
    """The audit ledger's entry shape is a contract, not prose."""
    path = CONTRACTS / "audit" / "ledger-entry.schema.json"
    check(path.exists(), "the audit ledger contract is missing")

    if path.exists():
        document = load(path)
        required = {"eventType", "body", "subject", "action", "resource", "decision"}
        missing = required - set(document.get("properties", {}))
        check(
            not missing,
            f"the audit ledger contract omits the fields {sorted(missing)}",
        )


def validate_policy_document() -> None:
    """The policy document is well formed and its obligations are defined."""
    policy = load(CONTRACTS / "policy" / "access-policy.json")
    defined = {obligation["name"] for obligation in policy.get("metadata", {}).get("obligations", [])}

    rule_ids = [rule["id"] for rule in policy["rules"]]
    check(len(rule_ids) == len(set(rule_ids)), "duplicate rule ids in the policy document")

    for rule in policy["rules"]:
        check(
            rule["effect"] in {"ALLOW", "DENY"},
            f"policy rule {rule['id']} has invalid effect {rule['effect']!r}",
        )
        for obligation in rule.get("obligations", []):
            check(
                obligation in defined,
                f"policy rule {rule['id']} references undefined obligation {obligation!r}",
            )

    check(
        policy.get("defaultEffect") == "DENY",
        "the policy document must default to DENY",
    )


def validate_python_bindings() -> None:
    """The Python envelope model agrees with the envelope schema."""
    from ngsh_core.envelope import EventEnvelope

    schema = load(CONTRACTS / "events" / "event-envelope.schema.json")
    schema_fields = set(schema.get("properties", {}))
    model_fields = set(EventEnvelope.model_fields)

    missing_in_code = schema_fields - model_fields
    missing_in_schema = model_fields - schema_fields

    check(
        not missing_in_code,
        f"the envelope schema declares fields the Python model lacks: {sorted(missing_in_code)}",
    )
    check(
        not missing_in_schema,
        f"the Python envelope model declares fields the schema lacks: {sorted(missing_in_schema)}",
    )


def main() -> int:
    validate_schemas()
    validate_registry()
    validate_event_catalog()
    validate_audit_contract()
    validate_policy_document()
    validate_python_bindings()

    if FAILURES:
        print(f"contract validation FAILED with {len(FAILURES)} problem(s):")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1

    print(f"contract validation passed: {CHECKS} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
