"""The shared ontology: registry, validation and constraint enforcement.

The JSON Schema contract files under ``contracts/`` are the source of truth.
This module loads them, resolves their cross-file references, validates
entities against them, and enforces the cross-entity invariants listed in
``contracts/ontology/registry.json`` (C-001 .. C-008).

The contract layer is deliberately external to the code: a governance board can
change the ontology without a code release, and the ontology service can
reload the registry at runtime.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .classification import at_least, join_levels, max_level, parse_level
from .envelope import Classification, Entity, Relation
from .errors import OntologyError, ValidationError


@dataclass(frozen=True)
class EntityTypeSpec:
    type: str
    idPrefix: str
    schemaDef: str
    description: str = ""
    pillars: tuple[str, ...] = ()
    classificationFloor: str = "UNCLASSIFIED"
    pii: bool = False


@dataclass(frozen=True)
class RelationTypeSpec:
    type: str
    fromTypes: tuple[str, ...]
    toTypes: tuple[str, ...]
    cardinality: str = "MANY_TO_MANY"
    description: str = ""
    mayCrossClassification: bool = False
    requiresProvenance: bool = True
    supportsRollup: bool = False


@dataclass
class OntologyRegistry:
    """Loaded ontology metadata plus the validators that enforce it."""

    version: str
    entities: dict[str, EntityTypeSpec] = field(default_factory=dict)
    relations: dict[str, RelationTypeSpec] = field(default_factory=dict)
    constraints: list[dict[str, Any]] = field(default_factory=list)
    _entity_validator: Draft202012Validator | None = None
    _attribute_validators: dict[str, Draft202012Validator] = field(default_factory=dict)
    _common: dict[str, Any] = field(default_factory=dict)

    # -- lookups ---------------------------------------------------------

    def entity_type(self, type_name: str) -> EntityTypeSpec | None:
        return self.entities.get(type_name)

    def relation_type(self, type_name: str) -> RelationTypeSpec | None:
        return self.relations.get(type_name)

    def types_for_pillar(self, pillar: str) -> list[EntityTypeSpec]:
        return sorted(
            (spec for spec in self.entities.values() if pillar in spec.pillars),
            key=lambda spec: spec.type,
        )

    def constraint(self, constraint_id: str) -> dict[str, Any] | None:
        for constraint in self.constraints:
            if constraint.get("id") == constraint_id:
                return constraint
        return None

    # -- validation ------------------------------------------------------

    def validate_entity(self, entity: Entity) -> list[str]:
        """Validate an entity against its type schema and the registry rules.

        Returns a list of human-readable error strings. An empty list means
        the entity is valid.

        The type-specific body is validated separately from the envelope so
        that an error names the offending attribute rather than reporting a
        generic schema-composition failure.
        """
        errors: list[str] = []

        spec = self.entities.get(entity.type)
        if spec is None:
            errors.append(f"unknown entity type {entity.type!r}")
            return errors

        if self._entity_validator is not None:
            for error in sorted(
                self._entity_validator.iter_errors(entity.model_dump(mode="json")),
                key=lambda e: list(e.path),
            ):
                # The top-level 'oneOf' composes the per-type attribute
                # schemas. Those are validated separately below, where the
                # error can name the attribute that is actually wrong.
                if error.validator == "oneOf" and not error.path:
                    continue
                location = ".".join(str(part) for part in error.path) or "<root>"
                errors.append(f"{location}: {error.message}")

        attribute_validator = self._attribute_validators.get(entity.type)
        if attribute_validator is not None:
            for error in sorted(
                attribute_validator.iter_errors(entity.attributes),
                key=lambda e: list(e.path),
            ):
                location = ".".join(str(part) for part in error.path) or "<root>"
                errors.append(f"attributes.{location}: {error.message}")

        floor = spec.classificationFloor
        if not at_least(entity.classification.level, floor):
            errors.append(
                f"constraint C-001: {entity.type} has classification floor {floor} "
                f"but was written at {entity.classification.level}"
            )

        if not entity.id.startswith(f"{spec.idPrefix}:"):
            errors.append(f"entity id {entity.id!r} does not use the declared prefix {spec.idPrefix!r}")

        return errors

    def validate_entity_update(self, entity: Entity, current_classification: str | None) -> list[str]:
        """Validate an update against the entity's current state.

        Constraint C-009: an entity's classification may not be lowered in
        place. A downgrade is a *new* entity in a lower partition, carrying
        ``derivedFromClassified`` and a ``parentRefs`` link to the original,
        so that the act of downgrading is itself auditable rather than a
        silent mutation of a record that was once classified.
        """
        errors = self.validate_entity(entity)
        if not current_classification:
            return errors

        if parse_level(entity.classification.level) < parse_level(current_classification):
            errors.append(
                f"constraint C-009: {entity.id} is currently {current_classification} and "
                f"cannot be lowered in place to {entity.classification.level}; a downgrade "
                "creates a new entity with derivedFromClassified=true and a parentRefs "
                "link to the original"
            )

        provenance = entity.provenance or {}
        if parse_level(entity.classification.level) < parse_level(current_classification):
            if not provenance.get("derivedFromClassified"):
                errors.append(
                    f"constraint C-009: a downgraded copy of {entity.id} must set "
                    "provenance.derivedFromClassified=true"
                )
            if not provenance.get("parentRefs"):
                errors.append(
                    f"constraint C-009: a downgraded copy of {entity.id} must record the "
                    "original in provenance.parentRefs"
                )

        return errors

    def validate_relation(
        self,
        relation: Relation,
        *,
        from_classification: str | None = None,
        to_classification: str | None = None,
    ) -> list[str]:
        """Validate a relation's types and its classification boundary rule."""
        errors: list[str] = []

        spec = self.relations.get(relation.type)
        if spec is None:
            errors.append(f"unknown relation type {relation.type!r}")
            return errors

        if relation.fromRef.get("type") not in spec.fromTypes:
            errors.append(
                f"relation {relation.type!r} may not originate from "
                f"{relation.fromRef.get('type')!r}; allowed: {sorted(spec.fromTypes)}"
            )
        if relation.toRef.get("type") not in spec.toTypes:
            errors.append(
                f"relation {relation.type!r} may not target "
                f"{relation.toRef.get('type')!r}; allowed: {sorted(spec.toTypes)}"
            )

        if from_classification and to_classification and not spec.mayCrossClassification:
            source = parse_level(from_classification)
            target = parse_level(to_classification)
            if source != target:
                errors.append(
                    f"constraint C-002: relation {relation.type!r} may not cross a "
                    f"classification boundary ({from_classification} -> {to_classification})"
                )

        if spec.requiresProvenance and not relation.provenance:
            errors.append(f"relation {relation.type!r} requires provenance")

        return errors

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "ontologyVersion": self.version,
            "entities": [
                {
                    "type": spec.type,
                    "idPrefix": spec.idPrefix,
                    "schemaDef": spec.schemaDef,
                    "description": spec.description,
                    "pillars": list(spec.pillars),
                    "classificationFloor": spec.classificationFloor,
                    "pii": spec.pii,
                }
                for spec in sorted(self.entities.values(), key=lambda s: s.type)
            ],
            "relations": [
                {
                    "type": spec.type,
                    "fromTypes": list(spec.fromTypes),
                    "toTypes": list(spec.toTypes),
                    "cardinality": spec.cardinality,
                    "description": spec.description,
                    "mayCrossClassification": spec.mayCrossClassification,
                    "requiresProvenance": spec.requiresProvenance,
                    "supportsRollup": spec.supportsRollup,
                }
                for spec in sorted(self.relations.values(), key=lambda s: s.type)
            ],
            "constraints": self.constraints,
        }


def _resolve_local(base: Path, url: str) -> Path | None:
    """Map a contract ``$id`` back to a file under the contracts directory."""
    marker = "ngsh.mil/contracts/"
    if marker not in url:
        return None
    relative = url.split(marker, 1)[1]
    candidate = base / relative
    if candidate.exists():
        return candidate
    return None


class OntologyLoader:
    """Loads the contract layer from disk and builds the registry."""

    def __init__(self, contracts_dir: Path) -> None:
        self._contracts_dir = Path(contracts_dir)
        self._lock = threading.RLock()
        self._registry: OntologyRegistry | None = None

    def load(self) -> OntologyRegistry:
        with self._lock:
            if self._registry is not None:
                return self._registry
            self._registry = self._load_uncached()
            return self._registry

    def reload(self) -> OntologyRegistry:
        with self._lock:
            self._registry = self._load_uncached()
            return self._registry

    def _read(self, relative: str) -> dict[str, Any]:
        path = self._contracts_dir / relative
        if not path.exists():
            raise OntologyError(f"contract file missing: {path}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise OntologyError(f"contract file is not valid JSON: {path}: {exc}") from exc

    def _load_uncached(self) -> OntologyRegistry:
        registry_doc = self._read("ontology/registry.json")
        common = self._read("ontology/common.schema.json")
        entities_doc = self._read("ontology/entities.schema.json")

        entities: dict[str, EntityTypeSpec] = {}
        for entry in registry_doc.get("entities", []):
            entities[entry["type"]] = EntityTypeSpec(
                type=entry["type"],
                idPrefix=entry["idPrefix"],
                schemaDef=entry["schemaDef"],
                description=entry.get("description", ""),
                pillars=tuple(entry.get("pillars", ())),
                classificationFloor=entry.get("classificationFloor", "UNCLASSIFIED"),
                pii=bool(entry.get("pii", False)),
            )

        relations: dict[str, RelationTypeSpec] = {}
        for entry in registry_doc.get("relations", []):
            relations[entry["type"]] = RelationTypeSpec(
                type=entry["type"],
                fromTypes=tuple(entry.get("fromTypes", ())),
                toTypes=tuple(entry.get("toTypes", ())),
                cardinality=entry.get("cardinality", "MANY_TO_MANY"),
                description=entry.get("description", ""),
                mayCrossClassification=bool(entry.get("mayCrossClassification", False)),
                requiresProvenance=bool(entry.get("requiresProvenance", True)),
                supportsRollup=bool(entry.get("supportsRollup", False)),
            )

        # Build a reference registry so that the `$ref`s pointing at ngsh.mil
        # resolve to the local contract files rather than the network. The
        # `referencing` library is used rather than the deprecated
        # `RefResolver`, because it implements the current specification.
        from referencing import Registry, Resource
        from referencing.jsonschema import DRAFT202012

        registry = Registry()
        for relative in (
            "ontology/common.schema.json",
            "ontology/entities.schema.json",
            "ontology/relations.schema.json",
        ):
            doc = self._read(relative)
            doc_id = doc.get("$id")
            if not doc_id:
                continue
            resource = Resource.from_contents(doc, default_specification=DRAFT202012)
            registry = registry.with_resource(uri=doc_id, resource=resource)

        validator = Draft202012Validator(
            entities_doc,
            registry=registry,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        )

        # A validator per entity type, so that attribute errors name the
        # attribute that is wrong instead of collapsing into a schema
        # composition failure.
        attribute_validators: dict[str, Draft202012Validator] = {}
        definitions = entities_doc.get("$defs", {})
        for entity_type in entities:
            def_name = f"{entity_type}Attributes"
            if def_name not in definitions:
                continue
            attribute_validators[entity_type] = Draft202012Validator(
                definitions[def_name],
                registry=registry,
                format_checker=Draft202012Validator.FORMAT_CHECKER,
            )

        return OntologyRegistry(
            version=registry_doc.get("ontologyVersion", "0.0.0"),
            entities=entities,
            relations=relations,
            constraints=list(registry_doc.get("constraints", [])),
            _entity_validator=validator,
            _attribute_validators=attribute_validators,
            _common=common,
        )


def load_registry(contracts_dir: Path) -> OntologyRegistry:
    return OntologyLoader(contracts_dir).load()


def relation_levels(relation: Relation) -> tuple[str, str]:
    """Classification levels of the two endpoints of a relation, as declared."""
    return (relation.classification.level, relation.classification.level)


def assert_entity_valid(registry: OntologyRegistry, entity: Entity) -> None:
    errors = registry.validate_entity(entity)
    if errors:
        raise ValidationError(f"entity {entity.id} failed validation", errors=errors)


def assert_relation_valid(
    registry: OntologyRegistry,
    relation: Relation,
    from_classification: str | None = None,
    to_classification: str | None = None,
) -> None:
    errors = registry.validate_relation(
        relation,
        from_classification=from_classification,
        to_classification=to_classification,
    )
    if errors:
        raise ValidationError(f"relation {relation.id} failed validation", errors=errors)


def effective_classification(entity: Entity) -> Classification:
    """Classification of an entity after applying its type floor.

    The floor is enforced at write time by ``validate_entity``; this helper
    reports what the effective level is for an entity that has already been
    admitted.
    """
    return entity.classification


def rollup_classification(levels: Iterable[str | None]) -> Classification:
    return Classification(level=join_levels(levels).label)


def strongest(*levels: str | Classification | None) -> Classification:
    return Classification(level=max_level(*levels).label)
