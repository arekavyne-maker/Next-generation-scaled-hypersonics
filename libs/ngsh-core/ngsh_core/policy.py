"""Attribute-Based Access Control engine (the Policy Decision Point).

Design decisions, expanded in ``docs/adr/ADR-0004-abac-with-pdp-pep-separation.md``:

* **ABAC, not RBAC.** Access is a function of attributes on the subject, the
  resource, the action and the environment. A clearance check alone is not
  sufficient: an SCI-cleared engineer without need-to-know on a program must
  still be denied.
* **Explicit deny wins.** If any matching rule denies, the request is denied
  regardless of the priority of an allowing rule. Failing closed is the
  correct default for CUI handling.
* **Obligations.** An allow may carry duties that the enforcement point must
  discharge, such as watermarking exports or forbidding onward transfer.
* **Data, not code.** Rules live in ``contracts/policy/access-policy.json`` so
  that a change to access control is a reviewed artefact rather than a
  deployment. The policy document is versioned and every decision records the
  policy id and version that produced it.

The engine evaluates a JSON condition tree::

    {"all": [<condition>, ...]}
    {"any": [<condition>, ...]}
    {"not": <condition>}
    {"attr": "subject.clearance", "op": "gte", "value": "SECRET"}

Attribute namespaces are ``subject``, ``resource``, ``context`` and ``env``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .classification import ClassificationLevel, parse_level
from .envelope import Actor, Classification
from .errors import ValidationError

# Clearance rank. 'SCI-CLEARED' is the highest because it subsumes TOP SECRET
# and additionally covers compartmented material.
_CLEARANCE_RANK: dict[str, int] = {
    "NONE": 0,
    "UNCLASSIFIED": 0,
    "SECRET": 1,
    "TOP SECRET": 2,
    "SCI-CLEARED": 3,
}


def clearance_rank(value: str | None) -> int:
    if not value:
        return 0
    return _CLEARANCE_RANK.get(value.strip().upper(), 0)


@dataclass(frozen=True)
class Obligation:
    """A duty the enforcement point must discharge for an allowed request."""

    name: str
    description: str = ""


@dataclass
class Rule:
    id: str
    description: str = ""
    effect: str = "ALLOW"
    priority: int = 0
    when: dict[str, Any] = field(default_factory=dict)
    obligations: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class Decision:
    decision: str
    policyId: str | None = None
    policyVersion: str | None = None
    obligations: list[str] = field(default_factory=list)
    reason: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision == "ALLOW"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "policyId": self.policyId,
            "policyVersion": self.policyVersion,
            "obligations": list(self.obligations),
            "reason": self.reason,
            "context": self.context,
        }


@dataclass
class Resource:
    """The resource being accessed.

    ``classification`` is a :class:`Classification` rather than a bare string
    so that policy rules can address ``resource.classification.level`` and
    ``resource.classification.caveats`` directly.
    """

    type: str
    id: str
    classification: Classification = field(default_factory=Classification)
    tenant: str | None = None
    program: str | None = None
    owner: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.classification, str):
            self.classification = Classification(level=self.classification)
        elif isinstance(self.classification, dict):
            self.classification = Classification.model_validate(self.classification)


class PolicySet:
    """A loaded, versioned collection of access rules."""

    def __init__(
        self,
        version: str,
        rules: list[Rule],
        *,
        classification_clearance_floor: Mapping[str, str] | None = None,
        default_effect: str = "DENY",
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.version = version
        self.rules = rules
        self.default_effect = default_effect
        self.metadata = dict(metadata or {})
        self.classification_clearance_floor = dict(classification_clearance_floor or {})
        self._obligations: dict[str, Obligation] = {
            obligation["name"]: Obligation(**obligation)
            for obligation in self.metadata.get("obligations", [])
        }

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> PolicySet:
        rules = [
            Rule(
                id=rule["id"],
                description=rule.get("description", ""),
                effect=rule.get("effect", "ALLOW"),
                priority=int(rule.get("priority", 0)),
                when=rule.get("when", {}) or {},
                obligations=list(rule.get("obligations", [])),
                reason=rule.get("reason", ""),
            )
            for rule in document.get("rules", [])
        ]
        return cls(
            version=document.get("policyVersion", "0.0.0"),
            rules=rules,
            classification_clearance_floor=document.get("classificationClearanceFloor", {}),
            default_effect=document.get("defaultEffect", "DENY"),
            metadata=document.get("metadata", {}),
        )

    @classmethod
    def load(cls, path: Path) -> PolicySet:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(document)

    def obligations_for(self, names: Iterable[str]) -> list[Obligation]:
        return [self._obligations[name] for name in names if name in self._obligations]

    @property
    def known_obligations(self) -> list[Obligation]:
        """Every obligation defined in the policy document."""
        return [self._obligations[name] for name in sorted(self._obligations)]

    # -- evaluation ------------------------------------------------------

    def evaluate(
        self,
        subject: Actor | Mapping[str, Any],
        resource: Resource | Mapping[str, Any],
        action: str,
        context: Mapping[str, Any] | None = None,
    ) -> Decision:
        subject_dict = subject.model_dump() if isinstance(subject, Actor) else dict(subject)
        resource_dict = asdict(resource) if isinstance(resource, Resource) else dict(resource)
        context_dict = dict(context or {})

        attributes: dict[str, Any] = {
            "subject": subject_dict,
            "resource": resource_dict,
            "context": context_dict,
            "action": action,
            "env": {
                "deploymentProfile": context_dict.get("deploymentProfile"),
                "networkZone": context_dict.get("networkZone"),
                "devicePosture": context_dict.get("devicePosture"),
            },
        }

        matched_allow: tuple[int, Rule] | None = None
        matched_deny: tuple[int, Rule] | None = None

        for rule in self.rules:
            if not self._matches(rule.when, attributes):
                continue
            if rule.effect.upper() == "DENY":
                if matched_deny is None or rule.priority > matched_deny[0]:
                    matched_deny = (rule.priority, rule)
            elif matched_allow is None or rule.priority > matched_allow[0]:
                matched_allow = (rule.priority, rule)

        # Explicit deny wins regardless of relative priority.
        if matched_deny is not None:
            rule = matched_deny[1]
            return Decision(
                decision="DENY",
                policyId=rule.id,
                policyVersion=self.version,
                reason=rule.reason or rule.description or f"denied by {rule.id}",
                context={"effect": "DENY", "matchedRule": rule.id},
            )

        if matched_allow is not None:
            rule = matched_allow[1]
            obligations = list(rule.obligations)
            obligations.extend(self._implied_obligations(subject_dict, resource_dict))
            return Decision(
                decision="ALLOW",
                policyId=rule.id,
                policyVersion=self.version,
                obligations=sorted(set(obligations)),
                reason=rule.reason or rule.description or f"allowed by {rule.id}",
                context={"effect": "ALLOW", "matchedRule": rule.id},
            )

        return Decision(
            decision=self.default_effect,
            policyId=None,
            policyVersion=self.version,
            reason="no rule matched; default deny",
            context={"effect": self.default_effect},
        )

    def _implied_obligations(self, subject: Mapping[str, Any], resource: Mapping[str, Any]) -> list[str]:
        """Obligations derived from the subject/resource pair rather than a rule."""
        implied: list[str] = []
        classification = resource.get("classification") or {}
        level = str(
            classification.get("level", "UNCLASSIFIED")
            if isinstance(classification, Mapping)
            else classification
        ).upper()
        citizenship = str(subject.get("citizenship") or "UNKNOWN").upper()
        if citizenship not in {"US", "ALLIED"} and parse_level(level) >= ClassificationLevel.CUI:
            implied.append("no-export")
        if level == "UNCLASSIFIED" and subject.get("kind") == "user":
            implied.append("watermark")
        return implied

    # -- condition evaluation -------------------------------------------

    def _matches(self, condition: Mapping[str, Any] | None, attributes: Mapping[str, Any]) -> bool:
        if not condition:
            return True
        if "all" in condition:
            return all(self._matches(sub, attributes) for sub in condition["all"])
        if "any" in condition:
            return any(self._matches(sub, attributes) for sub in condition["any"])
        if "not" in condition:
            return not self._matches(condition["not"], attributes)
        if "attr" in condition:
            return self._evaluate_atom(condition, attributes)
        raise ValidationError(f"unsupported condition fragment: {sorted(condition)}")

    def _evaluate_atom(self, condition: Mapping[str, Any], attributes: Mapping[str, Any]) -> bool:
        path = condition["attr"]
        operator = condition.get("op", "eq")
        expected = condition.get("value")
        actual = self._resolve(path, attributes)

        if operator == "eq":
            return actual == expected
        if operator == "ne":
            return actual != expected
        if operator == "in":
            return actual in (expected or [])
        if operator == "not_in":
            return actual not in (expected or [])
        if operator == "has":
            return (actual is not None) if expected else (actual is None)
        if operator == "contains":
            return isinstance(actual, (list, tuple, set)) and expected in actual
        if operator == "intersects":
            left = set(actual or [])
            right = set(expected or [])
            return bool(left & right)
        if operator == "starts_with":
            return isinstance(actual, str) and actual.startswith(str(expected))
        if operator == "ends_with":
            return isinstance(actual, str) and actual.endswith(str(expected))
        if operator == "matches":
            return isinstance(actual, str) and re.search(str(expected), actual) is not None
        if operator == "gte":
            return self._compare(actual, expected) >= 0
        if operator == "lte":
            return self._compare(actual, expected) <= 0
        if operator == "gt":
            return self._compare(actual, expected) > 0
        if operator == "lt":
            return self._compare(actual, expected) < 0
        if operator == "level_gte":
            return parse_level(str(actual)) >= parse_level(str(expected))
        if operator == "level_lt":
            return parse_level(str(actual)) < parse_level(str(expected))
        if operator == "clearance_gte":
            return clearance_rank(str(actual)) >= clearance_rank(str(expected))
        if operator == "clearance_lt":
            return clearance_rank(str(actual)) < clearance_rank(str(expected))
        # Subject-scoped operators. These exist so that access rules can be
        # expressed against the *requesting* subject without embedding any
        # subject-specific value in the policy document itself.
        if operator == "eq_subject_tenant":
            return actual == attributes["subject"].get("tenant")
        if operator == "in_subject_programs":
            programs = attributes["subject"].get("programs") or []
            return actual in programs
        if operator == "in_subject_need_to_know":
            need = attributes["subject"].get("needToKnow") or []
            return actual in need
        raise ValidationError(f"unsupported operator {operator!r}")

    @staticmethod
    def _compare(actual: Any, expected: Any) -> int:
        if actual is None:
            return -1
        try:
            if actual == expected:
                return 0
            return -1 if actual < expected else 1
        except TypeError:
            return 0

    @staticmethod
    def _resolve(path: str, attributes: Mapping[str, Any]) -> Any:
        current: Any = attributes
        for part in path.split("."):
            if current is None:
                return None
            current = current.get(part) if isinstance(current, Mapping) else getattr(current, part, None)
        return current


def required_clearance(policy_set: PolicySet, classification_level: str) -> str:
    """Minimum clearance a subject needs to reach a classification level."""
    floors = policy_set.classification_clearance_floor
    if classification_level in floors:
        return floors[classification_level]
    return "TOP SECRET" if parse_level(classification_level) >= ClassificationLevel.SECRET else "NONE"
