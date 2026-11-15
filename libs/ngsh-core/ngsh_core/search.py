"""Search projection: one query across the digital thread.

The search index is a *projection*, not a second source of truth. It is built
from the graph the thread service already materialises from the event log, and
it can be rebuilt at any time. That is why this module is a pure scoring
function over a list of entities rather than a service with its own store.

Scoring is deliberately explainable. Every result reports the fields that
matched and the score it earned, so an operator can see why a requirement
surfaced for a query. An unexplainable ranking is unacceptable on a system
whose results may be read into a review.
"""

from __future__ import annotations

import re
from typing import Any

#: Field weights. An exact identifier match outranks a free-text attribute
#: match, because a person searching for ``PART:NSN-4472`` wants that part.
WEIGHTS = {
    "idExact": 20,
    "idPrefix": 12,
    "idContains": 8,
    "type": 4,
    "label": 8,
    "attribute": 3,
    "annotation": 1,
}

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_.:/-]+")


def tokenise(text: str) -> list[str]:
    """Lower-case tokens, keeping identifiers such as ``PART:NSN-4472`` whole."""
    return [token.lower() for token in _TOKEN_PATTERN.findall(text or "")]


def _flatten(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for nested in value.values() for item in _flatten(nested)]
    if isinstance(value, list):
        return [item for nested in value for item in _flatten(nested)]
    return []


def _label(entity: dict[str, Any]) -> str:
    attributes = entity.get("attributes") or {}
    for key in ("name", "designation", "partNumber", "title", "variantId", "statement"):
        value = attributes.get(key)
        if isinstance(value, str) and value:
            return value
    return entity.get("id", "")


def score_entity(entity: dict[str, Any], terms: list[str]) -> tuple[int, list[str]]:
    """Score one entity against every query term.

    All terms must match somewhere: a two-word query narrows the result rather
    than broadening it, which is what a programme engineer expects.
    """
    if not terms:
        return 0, []

    entity_id = str(entity.get("id") or "")
    entity_type = str(entity.get("type") or "")
    lowered_id = entity_id.lower()
    lowered_type = entity_type.lower()
    label = _label(entity).lower()
    attributes = " ".join(_flatten(entity.get("attributes") or {})).lower()
    annotations = " ".join(_flatten(entity.get("annotations") or {})).lower()

    score = 0
    matched_fields: list[str] = []
    for term in terms:
        term_score = 0
        term_fields: list[str] = []
        if lowered_id == term:
            term_score += WEIGHTS["idExact"]
            term_fields.append("id")
        elif lowered_id.startswith(term):
            term_score += WEIGHTS["idPrefix"]
            term_fields.append("id")
        elif term in lowered_id:
            term_score += WEIGHTS["idContains"]
            term_fields.append("id")
        if term in lowered_type:
            term_score += WEIGHTS["type"]
            term_fields.append("type")
        if term in label:
            term_score += WEIGHTS["label"]
            term_fields.append("label")
        if term in attributes:
            term_score += WEIGHTS["attribute"]
            term_fields.append("attributes")
        if term in annotations:
            term_score += WEIGHTS["annotation"]
            term_fields.append("annotations")

        if not term_fields:
            return 0, []
        score += term_score
        for field in term_fields:
            if field not in matched_fields:
                matched_fields.append(field)

    return score, matched_fields


def search(
    entities: list[dict[str, Any]],
    query: str,
    *,
    entity_type: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Rank entities against a query, deterministically.

    Ties break on entity id, so two identical scores always appear in the same
    order. The caller supplies the candidate set; this module never reaches
    into a store.
    """
    terms = tokenise(query)
    if not terms:
        return {"query": query, "terms": [], "results": [], "count": 0, "totalConsidered": 0}

    considered = [entity for entity in entities if entity_type is None or entity.get("type") == entity_type]
    ranked: list[tuple[int, dict[str, Any], list[str]]] = []
    for entity in considered:
        score, fields = score_entity(entity, terms)
        if score:
            ranked.append((score, entity, fields))

    ranked.sort(key=lambda item: (-item[0], str(item[1].get("id"))))
    limited = ranked[: max(0, limit)]
    return {
        "query": query,
        "terms": terms,
        "results": [
            {
                "id": entity.get("id"),
                "type": entity.get("type"),
                "label": _label(entity),
                "classification": (entity.get("classification") or {}).get("level"),
                "score": score,
                "matchedFields": fields,
            }
            for score, entity, fields in limited
        ],
        "count": len(limited),
        "totalMatches": len(ranked),
        "totalConsidered": len(considered),
    }
