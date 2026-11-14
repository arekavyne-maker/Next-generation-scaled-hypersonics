#!/usr/bin/env python3
"""Demonstrate the edge annex flow.

Runs against a local stack: ``make dev`` in one terminal, ``make demo-edge``
in another.

The demonstration walks the sequence that ADR-0006 exists to make possible:

1. A factory floor annex captures test results while the fabric is
   unreachable. The write path works; nothing is lost.
2. The link returns and the batch is reconciled.
3. The fabric allocates the global sequence and preserves the edge's local
   sequence, so the two can always be related.
4. A rival claim on the same physical test is escalated rather than resolved
   by software, because the platform does not adjudicate physics.
5. The audit chain verifies.
"""

from __future__ import annotations

import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ngsh_core.edge import EdgeAgent, EdgeQueue  # noqa: E402
from ngsh_core.envelope import Actor, Classification, EventEnvelope  # noqa: E402

FABRIC = "http://127.0.0.1:8082"

GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
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
        raise SystemExit(f"HTTP {exc.code} from {url}: {exc.read().decode('utf-8')}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"cannot reach {url}\n{DIM}Is the stack running? Start it with 'make dev'.{RESET}"
        ) from exc


def result_event(event_id: str, aggregate_id: str, article_id: str) -> EventEnvelope:
    return EventEnvelope(
        eventId=event_id,
        eventType="test.result.recorded",
        aggregateType="TestResult",
        aggregateId=aggregate_id,
        sequence=1,
        tenant="ngsh",
        program="NGSH-SHY",
        actor=Actor(subjectId="edge:factory-3", kind="edge-agent", clearance="SECRET", citizenship="US"),
        classification=Classification(level="CUI"),
        payload={
            "testResult": {
                "id": aggregate_id,
                "type": "TestResult",
                "tenant": "ngsh",
                "version": 1,
                "createdAt": "2026-11-14T09:00:00Z",
                "updatedAt": "2026-11-14T09:00:00Z",
                "classification": {"level": "CUI"},
                "attributes": {
                    "campaignId": "TC:EDGE-DEMO",
                    "testArticleId": article_id,
                    "testMethod": "plasma-arc-heater",
                    "outcome": "PASS",
                    "measurements": [{"name": "peak_temperature", "value": 1838.0, "unit": "K"}],
                },
            }
        },
    )


def transport(payload: dict[str, Any]) -> dict[str, Any]:
    return call("POST", f"{FABRIC}/v1/edge/reconcile", payload)


def main() -> int:
    print(f"\n{CYAN}NGSH edge annex — disconnected capture and reconciliation{RESET}")

    with tempfile.TemporaryDirectory() as tmp:
        queue = EdgeQueue(Path(tmp) / "edge.db", node_id="edge:factory-3")
        agent = EdgeAgent("edge:factory-3", queue, fabric_url=FABRIC)

        print(f"\n{CYAN}[1] Capture while disconnected{RESET}")
        agent.capture(result_event("01EDGEDEMO1", "TR:EDGE-DEMO-1", "TA:EDGE-DEMO-1"))
        agent.capture(result_event("01EDGEDEMO2", "TR:EDGE-DEMO-2", "TA:EDGE-DEMO-2"))
        print(f"    {GREEN}ok{RESET}  2 events captured locally")
        print(
            f"    {DIM}pending={agent.queue.pending_count()}  fabric events="
            f"{call('GET', f'{FABRIC}/v1/stats')['total']}{RESET}"
        )

        print(f"\n{CYAN}[2] The link returns{RESET}")
        report = agent.sync(lambda url, payload: transport(payload))
        if report.error:
            print(f"    {YELLOW}reconciliation failed: {report.error}{RESET}")
            return 1
        print(
            f"    {GREEN}ok{RESET}  accepted={len(report.accepted)} "
            f"duplicates={len(report.duplicates)} quarantined={len(report.quarantined)}"
        )
        print(f"    {DIM}pending={agent.queue.pending_count()}{RESET}")

        print(f"\n{CYAN}[3] The fabric allocated the global sequence{RESET}")
        events = call("GET", f"{FABRIC}/v1/events?types=test.result.recorded")["events"]
        for event in events:
            edge = event.get("edge") or {}
            print(
                f"    {DIM}{event['aggregateId']:<18} global seq {event['sequence']}  "
                f"edge local seq {edge.get('localSequence')}  node {edge.get('nodeId')}{RESET}"
            )

        print(f"\n{CYAN}[4] A rival claim on the same physical test{RESET}")
        # The fabric already holds a result for this article and campaign.
        call(
            "POST",
            f"{FABRIC}/v1/events",
            result_event("01FABRICRIVAL", "TR:EDGE-RIVAL", "TA:EDGE-RIVAL").to_logical_json(),
        )

        queue2 = EdgeQueue(Path(tmp) / "edge2.db", node_id="edge:factory-9")
        agent2 = EdgeAgent("edge:factory-9", queue2, fabric_url=FABRIC)
        agent2.capture(result_event("01RIVALEDGE", "TR:EDGE-RIVAL-2", "TA:EDGE-RIVAL"))

        rival = agent2.sync(lambda url, payload: transport(payload))
        if rival.quarantined:
            print(f"    {GREEN}ok{RESET}  escalated, not guessed: {rival.quarantined[0]['conflictClass']}")
            print(f"    {DIM}{rival.quarantined[0]['reason']}{RESET}")
        else:
            print(f"    {YELLOW}the rival claim was accepted; check the immutable keys{RESET}")

        conflicts = [
            e
            for e in call("GET", f"{FABRIC}/v1/events")["events"]
            if e["eventType"] == "reconcile.conflict.recorded"
        ]
        if conflicts:
            task = conflicts[-1]["payload"]["escalationTask"]
            print(f"    {DIM}escalated as a {task['taskType']} task to {task['assignedTo']}{RESET}")

        print(f"\n{CYAN}[5] Audit chain{RESET}")
        verification = call("GET", "http://127.0.0.1:8084/v1/ledger/verify")
        if verification["valid"]:
            print(f"    {GREEN}ok{RESET}  chain verified across {verification['checked']} entries")
        else:
            print(f"    {YELLOW}chain broken at seq {verification['brokenAt']}{RESET}")
            return 1

    print(f"\n{GREEN}Edge demonstration complete.{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
