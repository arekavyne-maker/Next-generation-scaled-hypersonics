"""Digital thread projection.

The graph is a materialised projection of the event log, not an independent
store. It exists because traversal queries over a graph are the single most
common access pattern in the platform: "show me every requirement this test
result satisfies", "show me the whole chain of custody for this part",
"which threat observations contributed to this engagement scenario".

Rebuilding the graph from the log is always possible. That is the property
that makes the thread trustworthy: the graph can be deleted and rebuilt
without loss, which in turn means the graph is never the place where
authoritative facts live.
"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .envelope import EventEnvelope
from .store import Executor, canonical_json


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class TraceNode:
    id: str
    type: str
    label: str
    classification: str = "UNCLASSIFIED"
    depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "classification": self.classification,
            "depth": self.depth,
        }


@dataclass
class TraceEdge:
    source: str
    target: str
    type: str
    confidence: float | None = None
    retracted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.source,
            "to": self.target,
            "type": self.type,
            "confidence": self.confidence,
            "retracted": self.retracted,
        }


@dataclass
class TraceResult:
    root: str
    nodes: list[TraceNode] = field(default_factory=list)
    edges: list[TraceEdge] = field(default_factory=list)
    paths: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "paths": self.paths,
        }


class GraphProjector:
    """Maintains the graph projection and answers traversal queries."""

    PROJECTION_NAME = "thread"

    def __init__(self, executor: Executor) -> None:
        self._db = executor

    # -- projection ------------------------------------------------------

    def cursor(self) -> int:
        row = self._db.fetchone("SELECT cursor_seq FROM projections WHERE name = ?", (self.PROJECTION_NAME,))
        return int(row["cursor_seq"]) if row else 0

    def apply(self, envelope: EventEnvelope) -> bool:
        """Apply one event to the projection.

        Returns True when the event changed the graph. Events are applied in
        log order; the projection tracks its own cursor so that a restart
        resumes where it left off.
        """
        handled = self._apply_event(envelope)
        self._db.execute(
            "INSERT INTO projections (name, cursor_seq, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET cursor_seq = excluded.cursor_seq, updated_at = excluded.updated_at",
            (self.PROJECTION_NAME, self._highest_seq(), envelope.recordedAt.isoformat()),
        )
        return handled

    def _highest_seq(self) -> int:
        row = self._db.fetchone("SELECT COALESCE(MAX(seq), 0) AS s FROM events")
        return int(row["s"]) if row else 0

    def _apply_event(self, envelope: EventEnvelope) -> bool:
        # A domain event may carry the entity it concerns under a
        # type-specific key. The projection is driven by the shape of the
        # payload, not by the name of the event, so that a new event type
        # carrying an entity does not require a change here.
        entity = self._entity_from(envelope)
        if entity:
            self._upsert_entity(entity)
            return True

        if envelope.eventType == "entity.relation.asserted":
            relation = envelope.payload.get("relation", {})
            if relation:
                self._upsert_relation(relation)
            return True

        if envelope.eventType == "entity.relation.retracted":
            relation_id = envelope.payload.get("relationId")
            if relation_id:
                self._retract_relation(relation_id, envelope.payload.get("reason", ""))
            return True

        return False

    #: Payload keys that carry the entity an event concerns.
    ENTITY_PAYLOAD_KEYS = ("entity", "testResult", "processRun", "campaign", "threatSystem")

    def _entity_from(self, envelope: EventEnvelope) -> dict[str, Any]:
        """The entity carried by an event, if it carries one."""
        for key in self.ENTITY_PAYLOAD_KEYS:
            candidate = envelope.payload.get(key)
            if isinstance(candidate, dict) and candidate.get("id") and candidate.get("type"):
                return candidate
        return {}

    def _upsert_entity(self, entity: dict[str, Any]) -> None:
        classification = (entity.get("classification") or {}).get("level", "UNCLASSIFIED")
        self._db.execute(
            "INSERT INTO entities (id, type, tenant, program, version, classification, body_json, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET type = excluded.type, tenant = excluded.tenant, "
            "program = excluded.program, version = excluded.version, "
            "classification = excluded.classification, body_json = excluded.body_json, "
            "updated_at = excluded.updated_at",
            (
                entity.get("id", ""),
                entity.get("type", ""),
                entity.get("tenant", ""),
                entity.get("program"),
                int(entity.get("version", 1)),
                classification,
                canonical_json(entity),
                entity.get("updatedAt", ""),
            ),
        )

    def _upsert_relation(self, relation: dict[str, Any]) -> None:
        source = relation.get("from", {})
        target = relation.get("to", {})
        classification = (relation.get("classification") or {}).get("level", "UNCLASSIFIED")
        self._db.execute(
            "INSERT INTO relations (id, type, from_type, from_id, to_type, to_id, tenant, "
            "classification, asserted_at, retracted_at, body_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET type = excluded.type, body_json = excluded.body_json, "
            "retracted_at = excluded.retracted_at",
            (
                relation.get("id", ""),
                relation.get("type", ""),
                source.get("type", ""),
                source.get("id", ""),
                target.get("type", ""),
                target.get("id", ""),
                relation.get("tenant"),
                classification,
                relation.get("assertedAt", ""),
                relation.get("retractedAt"),
                canonical_json(relation),
            ),
        )

    def _retract_relation(self, relation_id: str, reason: str) -> None:
        self._db.execute(
            "UPDATE relations SET retracted_at = ? WHERE id = ?",
            (_utc_now_iso(), relation_id),
        )
        body_row = self._db.fetchone("SELECT body_json FROM relations WHERE id = ?", (relation_id,))
        if body_row is not None:
            body = json.loads(body_row["body_json"])
            body["retractedAt"] = _utc_now_iso()
            body["retractionReason"] = reason
            self._db.execute(
                "UPDATE relations SET body_json = ? WHERE id = ?",
                (canonical_json(body), relation_id),
            )

    # -- reads -----------------------------------------------------------

    def entities(
        self,
        *,
        entity_type: str | None = None,
        tenant: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List projected entities, optionally filtered by type and tenant.

        The console uses this to populate entity pickers. It is a
        convenience over the projection, never an authoritative read: the
        projection can be rebuilt from the log.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if entity_type:
            clauses.append("type = ?")
            params.append(entity_type)
        if tenant:
            clauses.append("tenant = ?")
            params.append(tenant)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._db.fetchall(
            f"SELECT body_json FROM entities{where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return [json.loads(row["body_json"]) for row in rows]

    def entity(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        row = self._db.fetchone(
            "SELECT body_json FROM entities WHERE id = ? AND type = ?", (entity_id, entity_type)
        )
        if row is None:
            return None
        return json.loads(row["body_json"])

    def relations_for(self, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
        rows = self._db.fetchall(
            "SELECT body_json FROM relations WHERE (from_type = ? AND from_id = ?) "
            "OR (to_type = ? AND to_id = ?) ORDER BY asserted_at ASC",
            (entity_type, entity_id, entity_type, entity_id),
        )
        return [json.loads(row["body_json"]) for row in rows]

    def relations(
        self,
        *,
        from_id: str | None = None,
        to_id: str | None = None,
        relation_type: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """List projected relations, optionally filtered by endpoint or type."""
        clauses: list[str] = []
        params: list[Any] = []
        if from_id:
            clauses.append("(from_type = ? OR to_type = ?)")
            params.extend([from_id, from_id])
        if to_id:
            clauses.append("(from_type = ? OR to_type = ?)")
            params.extend([to_id, to_id])
        if relation_type:
            clauses.append("type = ?")
            params.append(relation_type)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._db.fetchall(
            f"SELECT body_json FROM relations{where} ORDER BY asserted_at ASC LIMIT ?",
            [*params, limit],
        )
        return [json.loads(row["body_json"]) for row in rows]

    def trace(
        self,
        root_type: str,
        root_id: str,
        *,
        depth: int = 3,
        relation_types: Sequence[str] | None = None,
        direction: str = "both",
        include_retracted: bool = False,
    ) -> TraceResult:
        """Walk the digital thread outward from a root entity.

        The walk is breadth-first with a visited set, so a cycle in the
        ontology (a part that satisfies two requirements which both allocate
        back to the part) terminates rather than looping.
        """
        result = TraceResult(root=f"{root_type}:{root_id}")

        root_entity = self.entity(root_type, root_id)
        root_node = TraceNode(
            id=root_id,
            type=root_type,
            label=_label_for(root_entity, root_type, root_id),
            classification=(root_entity or {}).get("classification", {}).get("level", "UNCLASSIFIED"),
            depth=0,
        )
        result.nodes.append(root_node)
        seen_nodes = {(root_type, root_id)}
        seen_edges: set[str] = set()

        # Build the adjacency list once so the walk does not re-query per node.
        adjacency = self._adjacency(relation_types, include_retracted)

        queue: deque[tuple[str, str, int, list[str]]] = deque(
            [(root_type, root_id, 0, [f"{root_type}:{root_id}"])]
        )
        while queue:
            node_type, node_id, current_depth, path = queue.popleft()
            if current_depth >= depth:
                continue
            for edge in adjacency.get((node_type, node_id), []):
                edge_key = f"{edge['source_type']}:{edge['source_id']}->{edge['target_type']}:{edge['target_id']}#{edge['type']}"
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    result.edges.append(
                        TraceEdge(
                            source=f"{edge['source_type']}:{edge['source_id']}",
                            target=f"{edge['target_type']}:{edge['target_id']}",
                            type=edge["type"],
                            confidence=edge.get("confidence"),
                            retracted=bool(edge.get("retracted_at")),
                        )
                    )

                # Resolve which endpoint of the edge is the next hop. The
                # adjacency list indexes each edge under both endpoints, so
                # the current node may be either end of it.
                if edge["source_type"] == node_type and edge["source_id"] == node_id:
                    next_type, next_id = edge["target_type"], edge["target_id"]
                    hop = "out"
                else:
                    next_type, next_id = edge["source_type"], edge["source_id"]
                    hop = "in"

                if direction == "out" and hop != "out":
                    continue
                if direction == "in" and hop != "in":
                    continue

                if (next_type, next_id) in seen_nodes:
                    continue
                seen_nodes.add((next_type, next_id))

                entity = self.entity(next_type, next_id)
                result.nodes.append(
                    TraceNode(
                        id=next_id,
                        type=next_type,
                        label=_label_for(entity, next_type, next_id),
                        classification=(entity or {}).get("classification", {}).get("level", "UNCLASSIFIED"),
                        depth=current_depth + 1,
                    )
                )
                new_path = path + [f"{next_type}:{next_id}"]
                result.paths.append(new_path)
                queue.append((next_type, next_id, current_depth + 1, new_path))

        return result

    def _adjacency(
        self, relation_types: Sequence[str] | None, include_retracted: bool
    ) -> dict[tuple[str, str], list[dict[str, Any]]]:
        clauses: list[str] = []
        params: list[Any] = []
        if relation_types:
            clauses.append("type IN (" + ",".join("?" for _ in relation_types) + ")")
            params.extend(relation_types)
        if not include_retracted:
            clauses.append("retracted_at IS NULL")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._db.fetchall(
            f"SELECT type, from_type, from_id, to_type, to_id, retracted_at, body_json FROM relations{where}",
            params,
        )
        adjacency: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in rows:
            body = json.loads(row["body_json"])
            edge = {
                "type": row["type"],
                "source_type": row["from_type"],
                "source_id": row["from_id"],
                "target_type": row["to_type"],
                "target_id": row["to_id"],
                "confidence": body.get("confidence"),
                "retracted_at": row["retracted_at"],
            }
            adjacency.setdefault((row["from_type"], row["from_id"]), []).append(edge)
            adjacency.setdefault((row["to_type"], row["to_id"]), []).append(edge)
        return adjacency

    def requirement_coverage(self, requirement_id: str) -> dict[str, Any]:
        """Verification status of a requirement.

        A requirement is verified when at least one test result that verifies
        it passed. Partial coverage - some requirements verified, others not -
        is the normal state of a programme in flight, so the response reports
        the ratio rather than a bare boolean.
        """
        requirement = self.entity("Requirement", requirement_id)
        verifying = self._db.fetchall(
            "SELECT r.body_json FROM relations r "
            "JOIN entities e ON e.id = r.to_id "
            "WHERE r.type = 'verifies' AND r.to_id = ? AND r.retracted_at IS NULL",
            (requirement_id,),
        )
        results: list[dict[str, Any]] = []
        dangling: list[str] = []
        for row in verifying:
            body = json.loads(row["body_json"])
            result_id = body.get("from", {}).get("id")
            entity = (
                self.entity(body.get("from", {}).get("type", "TestResult"), result_id) if result_id else None
            )
            if entity:
                results.append(entity)
            elif result_id:
                # The edge exists but the entity it points at does not. This
                # is a real integrity problem worth surfacing rather than
                # silently treating the requirement as unverified.
                dangling.append(result_id)

        outcomes = [r.get("attributes", {}).get("outcome") for r in results]
        passed = sum(1 for outcome in outcomes if outcome == "PASS")
        failed = sum(1 for outcome in outcomes if outcome == "FAIL")
        verified = passed > 0 and failed == 0

        allocated = self._db.fetchall(
            "SELECT r.body_json FROM relations r "
            "WHERE r.type = 'satisfies' AND r.to_id = ? AND r.retracted_at IS NULL",
            (requirement_id,),
        )
        allocated_to = []
        for row in allocated:
            body = json.loads(row["body_json"])
            allocated_to.append(
                {
                    "id": body.get("from", {}).get("id"),
                    "type": body.get("from", {}).get("type"),
                }
            )

        gaps: list[str] = []
        if dangling:
            gaps.append(
                "verification evidence references test results that are not in the thread: "
                + ", ".join(sorted(dangling))
            )
        if not results:
            gaps.append("no verification evidence has been recorded against this requirement")
        elif failed:
            gaps.append(f"{failed} verification result(s) failed")
        if not allocated_to:
            gaps.append("no design element has been allocated to this requirement")

        return {
            "requirement": requirement or {"id": requirement_id, "type": "Requirement"},
            "verified": verified,
            "verifyingResults": [
                {
                    "id": r.get("id"),
                    "outcome": r.get("attributes", {}).get("outcome"),
                    "testMethod": r.get("attributes", {}).get("testMethod"),
                    "reviewedBy": r.get("attributes", {}).get("reviewedBy"),
                }
                for r in results
            ],
            "coverage": round(passed / len(results), 4) if results else 0.0,
            "allocatedTo": allocated_to,
            "gaps": gaps,
        }

    def stats(self) -> dict[str, Any]:
        entity_rows = self._db.fetchall("SELECT type AS name, COUNT(*) AS n FROM entities GROUP BY type")
        relation_rows = self._db.fetchall("SELECT type AS name, COUNT(*) AS n FROM relations GROUP BY type")
        total_entities = sum(int(row["n"]) for row in entity_rows)
        total_relations = sum(int(row["n"]) for row in relation_rows)
        return {
            "entityCounts": {row["name"]: int(row["n"]) for row in entity_rows},
            "relationCounts": {row["name"]: int(row["n"]) for row in relation_rows},
            "totalEntities": total_entities,
            "totalRelations": total_relations,
            "cursor": self.cursor(),
        }


def _label_for(entity: dict[str, Any] | None, entity_type: str, entity_id: str) -> str:
    """A human-readable label for a graph node."""
    if not entity:
        return entity_id
    attributes = entity.get("attributes", {}) or {}
    for key in ("name", "designation", "partNumber", "serialNumber", "variantId", "skill"):
        value = attributes.get(key)
        if isinstance(value, str) and value:
            return value
    return entity_id


def merge_edges(edges: Iterable[TraceEdge]) -> list[TraceEdge]:
    """Deduplicate edges that appear from both endpoints of the same relation."""
    seen: set[tuple[str, str, str]] = set()
    merged: list[TraceEdge] = []
    for edge in edges:
        key = (edge.source, edge.target, edge.type)
        if key not in seen:
            seen.add(key)
            merged.append(edge)
    return merged
