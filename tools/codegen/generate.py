#!/usr/bin/env python3
"""Generate typed models from the NGSH contract layer.

The contract files under ``contracts/`` are the source of truth. This
generator turns the entity, relation and common schemas into Python models
so that the platform's types are produced from the published contract rather
than transcribed from it by hand.

Two properties matter more than the code generation itself:

**Determinism.** Running the generator twice must produce byte-identical
output, so that the generated file can be committed and the staleness check
is meaningful.

**Contract authority.** When the contract changes, the generated models
change with it, and the codegen check fails until the new models are
regenerated. A shape that exists only in code is a shape nobody reviewed.

Usage::

    python tools/codegen/generate.py            # write the generated module
    python tools/codegen/generate.py --check    # fail if it is out of date
"""

from __future__ import annotations

import argparse
import json
import keyword
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = REPO_ROOT / "contracts"
OUTPUT = REPO_ROOT / "libs" / "ngsh-core" / "ngsh_core" / "generated" / "ontology_models.py"

#: Common-schema definitions that are plain strings rather than objects.
#: They become subclasses of ``str`` so that they remain usable as
#: annotations without dragging in a validation layer for a scalar.
COMMON_ALIASES = {
    "EntityId": ("EntityId", "An NGSH identifier: ``<TYPE_PREFIX>:<key>``."),
    "Timestamp": ("Timestamp", "An RFC 3339 / ISO 8601 UTC instant."),
}

#: Common-schema definitions that become reusable models.
COMMON_MODELS = {
    "Classification": "Classification",
    "Actor": "Actor",
    "Provenance": "Provenance",
    "Measurement": "Measurement",
    "Attachment": "Attachment",
    "Reference": "Reference",
    "FidelityScore": "FidelityScore",
    "CostEstimate": "CostEstimate",
}

#: JSON Schema type to Python type, for the simple cases.
PRIMITIVES = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "object": "dict[str, Any]",
}


class Generator:
    """Turns JSON Schema fragments into Python type annotations."""

    def __init__(self, common: dict[str, Any]) -> None:
        self.common = common
        self.defs = common.get("$defs", {})

    # -- type mapping ----------------------------------------------------

    def annotation(self, schema: dict[str, Any]) -> str:
        """The Python type annotation for a schema fragment."""
        if not isinstance(schema, dict):
            return "Any"

        if "$ref" in schema:
            return self._ref_annotation(schema["$ref"])

        if "const" in schema:
            return f"Literal[{json.dumps(schema['const'])}]"

        if "enum" in schema:
            values = ", ".join("None" if value is None else json.dumps(value) for value in schema["enum"])
            return f"Literal[{values}]"

        if "anyOf" in schema:
            options = [option for option in schema["anyOf"] if option.get("type") != "null"]
            nullable = len(options) != len(schema["anyOf"])
            if len(options) == 1:
                inner = self.annotation(options[0])
                return f"{inner} | None" if nullable else inner
            parts = [self.annotation(option) for option in options]
            if nullable:
                parts.append("None")
            return " | ".join(parts)

        declared = schema.get("type")
        if isinstance(declared, list):
            options = [item for item in declared if item != "null"]
            nullable = len(options) != len(declared)
            if len(options) == 1:
                carried = {
                    key: value
                    for key, value in schema.items()
                    if key in {"enum", "const", "items", "properties", "additionalProperties"}
                }
                inner = self.annotation({"type": options[0], **carried})
                return f"{inner} | None" if nullable else inner
            return " | ".join(self.annotation({"type": item}) for item in declared)

        if declared == "array":
            return f"list[{self.annotation(schema.get('items', {}))}]"

        if declared == "object":
            additional = schema.get("additionalProperties")
            if isinstance(additional, dict):
                return f"dict[str, {self.annotation(additional)}]"
            return "dict[str, Any]"

        return PRIMITIVES.get(declared or "", "Any")

    def _ref_annotation(self, ref: str) -> str:
        name = ref.rsplit("/", 1)[-1]
        if name in COMMON_ALIASES:
            return COMMON_ALIASES[name][0]
        if name in COMMON_MODELS:
            return COMMON_MODELS[name]
        if name.endswith("Attributes"):
            return name[: -len("Attributes")]
        return name

    # -- model emission --------------------------------------------------

    def model(self, name: str, schema: dict[str, Any]) -> str:
        """The source of one pydantic model."""
        properties: dict[str, Any] = schema.get("properties", {})
        required = set(schema.get("required", []))

        lines: list[str] = [f"class {name}(BaseModel):"]
        description = schema.get("description")
        if description:
            summary = description if len(description) <= 100 else description[:97] + "..."
            lines.append(f'    """{summary}"""')
            lines.append("")

        if not properties:
            lines.append("    pass")
            return "\n".join(lines) + "\n"

        aliased = False
        for field in sorted(properties):
            field_schema = properties[field]
            annotation = self.annotation(field_schema)

            # A contract field may use a word that is a Python keyword, such
            # as the relation's 'from'. The generated attribute is renamed and
            # keeps the contract name as its pydantic alias, so the wire
            # format stays exactly what the contract says.
            name = f"{field}_" if keyword.iskeyword(field) else field
            if name != field:
                aliased = True

            if name != field:
                # Aliased field: the default is carried by Field(), not by
                # an assignment, because the two would collide.
                default = "..." if field in required else "None"
                declaration = (
                    f"    {name}: {annotation} = Field(default={default}, alias={json.dumps(field)})"
                )
            elif field in required:
                declaration = f"    {name}: {annotation} = ..."
            else:
                # The annotation may already be nullable; do not say it twice.
                nullable = annotation if annotation.endswith("| None") else f"{annotation} | None"
                declaration = f"    {name}: {nullable} = None"

            note = field_schema.get("description", "")
            if note:
                summary = note if len(note) <= 100 else note[:97] + "..."
                declaration += f"  # {summary}"
            lines.append(declaration)

        if aliased:
            lines.insert(1, '    model_config = ConfigDict(populate_by_name=True, extra="forbid")')
            lines.insert(2, "")

        return "\n".join(lines) + "\n"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def generate() -> str:
    """Produce the generated module source."""
    common = _load(CONTRACTS / "ontology" / "common.schema.json")
    entities = _load(CONTRACTS / "ontology" / "entities.schema.json")
    registry = _load(CONTRACTS / "ontology" / "registry.json")
    relations = _load(CONTRACTS / "ontology" / "relations.schema.json")

    generator = Generator(common)

    entity_types = sorted(
        {name[: -len("Attributes")] for name in entities.get("$defs", {}) if name.endswith("Attributes")}
    )

    out: list[str] = []
    out.append('"""Entity and relation models generated from the NGSH contract layer.\n')
    out.append("DO NOT EDIT. This module is produced by ``tools/codegen/generate.py``\n")
    out.append("from the JSON Schema files in ``contracts/``. Edit the contract and\n")
    out.append("regenerate; ``make codegen-check`` fails the build when the committed\n")
    out.append("output no longer matches the contract.\n")
    out.append(f"\nContract version: ontology {registry.get('ontologyVersion', 'unknown')}.\n")
    out.append('"""\n')
    out.append("\n")
    out.append("from __future__ import annotations\n")
    out.append("\n")
    out.append("from typing import Annotated, Any, Literal\n")
    out.append("\n")
    out.append("from pydantic import BaseModel, ConfigDict, Field\n")
    out.append("\n")

    for def_name, (model_name, doc) in sorted(COMMON_ALIASES.items(), key=lambda item: item[1][0]):
        # A scalar contract type becomes an Annotated alias rather than a
        # subclass: pydantic cannot use a str subclass as a field type
        # without loosening validation, and the alias carries the contract's
        # own pattern into the generated models.
        pattern = (generator.defs.get(def_name) or {}).get("pattern")
        if pattern:
            out.append(f"{model_name} = Annotated[str, Field(pattern={json.dumps(pattern)})]\n")
        else:
            out.append(f"{model_name} = str\n")
        out.append(f"#: {doc}\n")
        out.append("\n")

    for def_name, model_name in sorted(COMMON_MODELS.items(), key=lambda item: item[1]):
        schema = generator.defs.get(def_name)
        if schema is None:
            continue
        out.append(generator.model(model_name, schema))
        out.append("\n")

    for entity_type in entity_types:
        schema = entities["$defs"][f"{entity_type}Attributes"]
        out.append(generator.model(entity_type, schema))
        out.append("\n")

    out.append(generator.model("RelationType", relations))
    out.append("\n")

    out.append("#: Every generated entity type, keyed by its ontology type name.\n")
    out.append("ENTITY_MODELS: dict[str, type[BaseModel]] = {\n")
    for entity_type in entity_types:
        out.append(f'    "{entity_type}": {entity_type},\n')
    out.append("}\n")
    out.append("\n")
    out.append("#: Every entity type in the ontology, in registry order.\n")
    out.append("ENTITY_TYPES: tuple[str, ...] = tuple(ENTITY_MODELS)\n")

    return "".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate models from the contract layer.")
    parser.add_argument("--check", action="store_true", help="fail if the output is stale")
    args = parser.parse_args()

    source = generate()

    if args.check:
        if not OUTPUT.exists():
            print(f"codegen check failed: {OUTPUT} does not exist", file=sys.stderr)
            return 1
        if OUTPUT.read_text(encoding="utf-8") != source:
            print(
                "codegen check failed: the generated models do not match the contract.\n"
                "Run 'make codegen' and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"codegen check passed: {OUTPUT.relative_to(REPO_ROOT)} is up to date")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(source, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)} ({len(source.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
