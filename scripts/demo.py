#!/usr/bin/env python3
"""Exercise the NGSH foundation end to end against a running stack.

Run ``make dev`` in one terminal and ``make demo`` in another.

The script walks the path a pillar would walk: validate an entity against
the ontology, ingest a batch of test data, confirm the events landed in the
fabric, project them into the digital thread, trace a requirement to its
verification evidence, take a policy decision, and verify the audit chain.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

ONTO = "http://127.0.0.1:8081"
FABRIC = "http://127.0.0.1:8082"
POLICY = "http://127.0.0.1:8083"
AUDIT = "http://127.0.0.1:8084"
THREAD = "http://127.0.0.1:8085"
INGEST = "http://127.0.0.1:8086"

GREEN = "\033[32m"
CYAN = "\033[36m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


def call(method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise SystemExit(f"{RED}HTTP {exc.code} from {url}{RESET}\n{detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"{RED}cannot reach {url}{RESET}\n{DIM}Is the stack running? Start it with 'make dev'.{RESET}"
        ) from exc


def step(number: int, title: str) -> None:
    print(f"\n{CYAN}[{number}] {title}{RESET}")


def ok(message: str) -> None:
    print(f"    {GREEN}ok{RESET}  {message}")


def detail(message: str) -> None:
    print(f"    {DIM}{message}{RESET}")


def main() -> int:
    print(f"\n{CYAN}NGSH foundation — end-to-end demonstration{RESET}")

    step(1, "Ontology")
    registry = call("GET", f"{ONTO}/v1/ontology/registry")
    ok(
        f"ontology v{registry['ontologyVersion']}: {len(registry['entities'])} entity types, "
        f"{len(registry['relations'])} relation types, {len(registry['constraints'])} invariants"
    )

    step(2, "Validate a TestResult against the contract layer")
    entity = {
        "id": "TR:DEMO-0001",
        "type": "TestResult",
        "tenant": "ngsh",
        "version": 1,
        "createdAt": "2026-11-14T00:00:00Z",
        "updatedAt": "2026-11-14T00:00:00Z",
        "classification": {"level": "CUI"},
        "attributes": {
            "testMethod": "plasma-arc-heater",
            "outcome": "PASS",
            "measurements": [{"name": "peak_temperature", "value": 1840.0, "unit": "K"}],
        },
    }
    validation = call("POST", f"{ONTO}/v1/ontology/validate", {"kind": "entity", "entity": entity})
    if validation["valid"]:
        ok("entity conforms to the TestResult contract")
    else:
        for error in validation["errors"]:
            print(f"    {RED}error{RESET} {error}")
        return 1

    step(3, "Ingest a batch of test data")
    payload = "\n".join(
        [
            json.dumps({"id": "TR:DEMO-0002", "testMethod": "plasma-arc-heater", "outcome": "MARGINAL"}),
            json.dumps({"id": "TR:DEMO-0003", "testMethod": "tensile", "outcome": "PASS"}),
        ]
    )
    batch = call(
        "POST",
        f"{INGEST}/v1/ingest",
        {
            "source": "plasma-arc-heater.itc",
            "format": "NDJSON",
            "payload": payload,
            "entityType": "TestResult",
            "classification": {"level": "CUI"},
        },
    )
    ok(f"batch {batch['batchId']}: {batch['recordsAccepted']} accepted, {batch['recordsRejected']} rejected")
    detail(f"sha256 {batch['sha256']}")

    step(4, "Confirm the events reached the fabric")
    stats = call("GET", f"{FABRIC}/v1/stats")
    ok(f"{stats['total']} events in the log across {stats['aggregates']} aggregates")
    for event_type, count in sorted(stats["byType"].items()):
        detail(f"{event_type:<32} {count}")

    step(5, "Project into the digital thread")
    replay = call("POST", f"{THREAD}/v1/project/replay")
    ok(f"replayed {replay['replayed']} events; projection at cursor {replay['cursor']}")
    graph = replay["stats"]
    detail(f"{graph['totalEntities']} entities, {graph['totalRelations']} relations")

    step(6, "Trace a requirement to its verification evidence")
    call(
        "POST",
        f"{FABRIC}/v1/events",
        {
            "eventType": "entity.created",
            "aggregateType": "Requirement",
            "aggregateId": "REQ:DEMO-0001",
            "sequence": 1,
            "tenant": "ngsh",
            "program": "NGSH-SHY",
            "actor": {
                "subjectId": "usr:demo",
                "kind": "user",
                "clearance": "TOP SECRET",
                "citizenship": "US",
                "tenant": "ngsh",
                "programs": ["NGSH-SHY"],
                "needToKnow": ["NGSH-SHY"],
            },
            "classification": {"level": "CUI"},
            "payload": {
                "entity": {
                    "id": "REQ:DEMO-0001",
                    "type": "Requirement",
                    "tenant": "ngsh",
                    "program": "NGSH-SHY",
                    "version": 1,
                    "createdAt": "2026-11-14T00:00:00Z",
                    "updatedAt": "2026-11-14T00:00:00Z",
                    "classification": {"level": "CUI"},
                    "attributes": {
                        "statement": "The nosecap shall survive 1800 K for 30 minutes.",
                        "verificationMethod": "TEST",
                        "status": "BASELINED",
                    },
                }
            },
        },
    )
    call(
        "POST",
        f"{FABRIC}/v1/events",
        {
            "eventType": "entity.created",
            "aggregateType": "TestResult",
            "aggregateId": "TR:DEMO-0001",
            "sequence": 1,
            "tenant": "ngsh",
            "program": "NGSH-SHY",
            "actor": {
                "subjectId": "usr:demo",
                "kind": "user",
                "clearance": "TOP SECRET",
                "citizenship": "US",
                "tenant": "ngsh",
                "programs": ["NGSH-SHY"],
                "needToKnow": ["NGSH-SHY"],
            },
            "classification": {"level": "CUI"},
            "payload": {
                "entity": {
                    "id": "TR:DEMO-0001",
                    "type": "TestResult",
                    "tenant": "ngsh",
                    "program": "NGSH-SHY",
                    "version": 1,
                    "createdAt": "2026-11-14T00:05:00Z",
                    "updatedAt": "2026-11-14T00:05:00Z",
                    "classification": {"level": "CUI"},
                    "attributes": {
                        "testMethod": "plasma-arc-heater",
                        "outcome": "PASS",
                        "measurements": [
                            {"name": "peak_temperature", "value": 1838.0, "unit": "K", "uncertainty": 25.0}
                        ],
                        "reviewedBy": "usr:demo",
                    },
                }
            },
        },
    )
    call(
        "POST",
        f"{FABRIC}/v1/events",
        {
            "eventType": "entity.relation.asserted",
            "aggregateType": "Relation",
            "aggregateId": "REL:DEMO-0001",
            "sequence": 1,
            "tenant": "ngsh",
            "program": "NGSH-SHY",
            "actor": {
                "subjectId": "usr:demo",
                "kind": "user",
                "clearance": "TOP SECRET",
                "citizenship": "US",
                "tenant": "ngsh",
                "programs": ["NGSH-SHY"],
                "needToKnow": ["NGSH-SHY"],
            },
            "classification": {"level": "CUI"},
            "payload": {
                "relation": {
                    "id": "REL:DEMO-0001",
                    "type": "verifies",
                    "from": {"type": "TestResult", "id": "TR:DEMO-0001"},
                    "to": {"type": "Requirement", "id": "REQ:DEMO-0001"},
                    "tenant": "ngsh",
                    "classification": {"level": "CUI"},
                    "assertedAt": "2026-11-14T00:05:00Z",
                    "provenance": {"source": "demo"},
                    "confidence": 0.95,
                }
            },
        },
    )
    call("POST", f"{THREAD}/v1/project/replay")

    trace = call("GET", f"{THREAD}/v1/trace?root=Requirement:REQ:DEMO-0001&depth=3")
    ok(f"trace from REQ:DEMO-0001 reached {len(trace['nodes'])} nodes via {len(trace['edges'])} edges")
    for edge in trace["edges"]:
        detail(f"{edge['from']} --{edge['type']}--> {edge['to']}")

    coverage = call("POST", f"{THREAD}/v1/trace/requirements/REQ:DEMO-0001/coverage", {})
    ok(f"requirement verified={coverage['verified']} coverage={coverage['coverage']}")
    for gap in coverage["gaps"]:
        detail(f"gap: {gap}")

    step(7, "Evaluate an access decision")
    allowed = call(
        "POST",
        f"{POLICY}/v1/decisions",
        {
            "subject": {
                "subjectId": "usr:engineer",
                "kind": "user",
                "clearance": "TOP SECRET",
                "citizenship": "US",
                "tenant": "ngsh",
                "programs": ["NGSH-SHY"],
                "needToKnow": ["NGSH-SHY"],
            },
            "resource": {
                "type": "TestResult",
                "id": "TR:DEMO-0001",
                "classification": {"level": "CUI"},
                "tenant": "ngsh",
                "program": "NGSH-SHY",
            },
            "action": "read",
        },
    )
    ok(f"cleared engineer: {allowed['decision']} by {allowed['policyId']}")

    denied = call(
        "POST",
        f"{POLICY}/v1/decisions",
        {
            "subject": {
                "subjectId": "usr:foreign",
                "kind": "user",
                "clearance": "TOP SECRET",
                "citizenship": "FOREIGN",
                "tenant": "ngsh",
                "programs": ["NGSH-SHY"],
                "needToKnow": ["NGSH-SHY"],
            },
            "resource": {
                "type": "TestResult",
                "id": "TR:DEMO-0001",
                "classification": {"level": "CUI"},
                "tenant": "ngsh",
                "program": "NGSH-SHY",
            },
            "action": "read",
        },
    )
    ok(f"foreign subject: {denied['decision']} by {denied['policyId']}")

    step(8, "Verify the audit chain")
    verification = call("GET", f"{AUDIT}/v1/ledger/verify")
    if verification["valid"]:
        ok(f"chain verified across {verification['checked']} entries")
    else:
        print(f"    {RED}chain broken at seq {verification['brokenAt']}{RESET}")
        detail(verification.get("detail") or "")
        return 1
    detail(f"head {verification['head'][:32]}...")

    print(f"\n{GREEN}Foundation demonstration complete.{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
