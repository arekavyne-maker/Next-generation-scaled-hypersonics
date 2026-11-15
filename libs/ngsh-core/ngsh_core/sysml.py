"""SysML v2 textual exchange for the architecture pillar (A-5, IF-5).

An accredited digital-engineering environment is a document authoring tool.
The platform does not try to replace it. What it must do is hand the same
model across the boundary in a form the tool can read, and accept the model
back without losing identity.

This module exports a deterministic SysML v2-style package and parses the
subset it emits. Scalars round-trip exactly; complex attributes are carried as
JSON strings with a ``_json`` suffix rather than guessed at.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .errors import ValidationError

_IDENTIFIER = re.compile(r"[^A-Za-z0-9_]")
_BLOCK_START = re.compile(r"(part def|interface def|requirement)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{")
_ATTRIBUTE_LINE = re.compile(r"^\s*attribute\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*);\s*$")


def identifier(value: str) -> str:
    cleaned = _IDENTIFIER.sub("_", value.strip())
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if value is None:
        return '""'
    if isinstance(value, str):
        return json.dumps(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _attributes(attributes: dict[str, Any]) -> str:
    lines: list[str] = []
    for key in sorted(attributes):
        value = attributes[key]
        if isinstance(value, str | int | float | bool) or value is None:
            lines.append(f"        attribute {identifier(key)} = {_literal(value)};")
        else:
            lines.append(
                f"        attribute {identifier(key)}_json = "
                f"{json.dumps(json.dumps(value, sort_keys=True, separators=(',', ':')))};"
            )
    return "\n".join(lines)


def export_sysml(
    *,
    systems: list[dict[str, Any]] | None = None,
    subsystems: list[dict[str, Any]] | None = None,
    interfaces: list[dict[str, Any]] | None = None,
    requirements: list[dict[str, Any]] | None = None,
    package_name: str = "NGSH",
) -> dict[str, Any]:
    """Render the architecture as a deterministic SysML v2-style package."""
    systems = systems or []
    subsystems = subsystems or []
    interfaces = interfaces or []
    requirements = requirements or []

    blocks: list[str] = []
    for row in systems:
        entity_id = row.get("id") or row.get("entityId")
        if not entity_id:
            raise ValidationError("every exported system needs an id")
        name = identifier(str(entity_id))
        attributes = {"entityId": str(entity_id), **(row.get("attributes") or {})}
        blocks.append(f"    part def {name} {{\n{_attributes(attributes)}\n    }}")
        blocks.append(f"    part {name.lower()} : {name};")
    for row in subsystems:
        entity_id = row.get("id") or row.get("entityId")
        if not entity_id:
            raise ValidationError("every exported subsystem needs an id")
        name = identifier(str(entity_id))
        attributes = {"entityId": str(entity_id), **(row.get("attributes") or {})}
        blocks.append(f"    part def {name} {{\n{_attributes(attributes)}\n    }}")
    for row in interfaces:
        interface_id = row.get("interfaceId") or row.get("id")
        if not interface_id:
            raise ValidationError("every exported interface needs an interfaceId")
        name = identifier(str(interface_id))
        attributes = {
            "entityId": str(interface_id),
            "fromSystemId": row.get("fromSystemId"),
            "toSystemId": row.get("toSystemId"),
            **(row.get("characteristics") or {}),
        }
        blocks.append(f"    interface def {name} {{\n{_attributes(attributes)}\n    }}")
    for row in requirements:
        entity_id = row.get("id") or row.get("entityId")
        if not entity_id:
            raise ValidationError("every exported requirement needs an id")
        name = identifier(str(entity_id))
        attributes = {"entityId": str(entity_id), **(row.get("attributes") or {})}
        blocks.append(f"    requirement {name} {{\n{_attributes(attributes)}\n    }}")

    model = f"package {identifier(package_name)} {{\n" + "\n\n".join(blocks) + "\n}\n"
    return {
        "package": package_name,
        "model": model,
        "digest": hashlib.sha256(model.encode()).hexdigest(),
        "counts": {
            "systems": len(systems),
            "subsystems": len(subsystems),
            "interfaces": len(interfaces),
            "requirements": len(requirements),
        },
        "format": "sysml-v2-text",
    }


def _parse_value(raw: str) -> Any:
    text = raw.strip()
    if text == "true":
        return True
    if text == "false":
        return False
    if text.startswith('"') and text.endswith('"'):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text[1:-1]
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def _parse_attributes(body: str) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    for line in body.splitlines():
        match = _ATTRIBUTE_LINE.match(line)
        if match is None:
            continue
        key = match.group(1)
        value = _parse_value(match.group(2))
        if key.endswith("_json") and isinstance(value, str):
            try:
                attributes[key[: -len("_json")]] = json.loads(value)
                continue
            except json.JSONDecodeError:
                pass
        attributes[key] = value
    return attributes


def _blocks(model: str) -> list[tuple[str, str, str]]:
    """Find top-level blocks, ignoring braces inside quoted JSON values.

    The exported model carries complex attributes as JSON strings. A naive
    regular expression stops at the first ``}`` inside such a string, so the
    scanner tracks string state and brace depth instead.
    """
    found: list[tuple[str, str, str]] = []
    for match in _BLOCK_START.finditer(model):
        kind, name = match.group(1), match.group(2)
        depth = 1
        index = match.end()
        in_string = False
        escaped = False
        while index < len(model) and depth:
            character = model[index]
            if in_string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
            elif character == '"':
                in_string = True
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
            index += 1
        if depth == 0:
            found.append((kind, name, model[match.end() : index - 1]))
    return found


def import_sysml(model: str) -> dict[str, Any]:
    """Parse the SysML subset emitted by :func:`export_sysml`."""
    if not isinstance(model, str) or "package" not in model:
        raise ValidationError("a SysML model must be a package")
    rows = {"systems": [], "interfaces": [], "requirements": []}
    for kind, name, body in _blocks(model):
        attributes = _parse_attributes(body)
        entity_id = attributes.pop("entityId", name)
        if kind == "part def":
            rows["systems"].append({"id": entity_id, "attributes": attributes})
        elif kind == "interface def":
            rows["interfaces"].append(
                {
                    "interfaceId": entity_id,
                    "fromSystemId": attributes.pop("fromSystemId", None),
                    "toSystemId": attributes.pop("toSystemId", None),
                    "characteristics": attributes,
                }
            )
        else:
            rows["requirements"].append({"id": entity_id, "attributes": attributes})
    return {
        **rows,
        "digest": hashlib.sha256(model.encode()).hexdigest(),
        "counts": {key: len(value) for key, value in rows.items()},
        "format": "sysml-v2-text",
    }
