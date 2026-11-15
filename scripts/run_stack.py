#!/usr/bin/env python3
"""Run the foundation and the pillar services locally.

Starts every service in a background thread and blocks until interrupted.
This is the local development topology: one process, one platform database,
all sixteen services.

For a multi-process deployment, run each service separately with the
``make dev-<name>`` targets and point the service-discovery environment
variables at each other.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from ngsh_core.config import load_settings  # noqa: E402

SERVICES: list[tuple[str, str, int]] = [
    ("ontology", "ngsh_ontology.app:create_app", 8081),
    ("fabric", "ngsh_fabric.app:create_app", 8082),
    ("policy", "ngsh_policy.app:create_app", 8083),
    ("audit", "ngsh_audit.app:create_app", 8084),
    ("thread", "ngsh_thread.app:create_app", 8085),
    ("ingest", "ngsh_ingest.app:create_app", 8086),
    ("architecture", "ngsh_architecture.app:create_app", 8088),
    ("workforce", "ngsh_workforce.app:create_app", 8089),
    ("manufacturing", "ngsh_manufacturing.app:create_app", 8090),
    ("testlab", "ngsh_testlab.app:create_app", 8091),
    ("supply", "ngsh_supply.app:create_app", 8092),
    ("engagement", "ngsh_engagement.app:create_app", 8093),
    ("industrial", "ngsh_industrial.app:create_app", 8094),
    ("analytics", "ngsh_analytics.app:create_app", 8095),
    ("integration", "ngsh_integration.app:create_app", 8096),
    ("gateway", "ngsh_gateway.app:create_app", 8080),
]


def main() -> int:
    import uvicorn

    settings = load_settings()
    if settings.sqlite_path is not None:
        settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    # Route the cross-service calls over HTTP so the topology behaves the
    # same way it will when the services run in separate containers.
    os.environ.setdefault("NGSH_FABRIC_URL", "http://127.0.0.1:8082")
    os.environ.setdefault("NGSH_AUDIT_URL", "http://127.0.0.1:8084")
    os.environ.setdefault("NGSH_THREAD_URL", "http://127.0.0.1:8085")

    servers: list[uvicorn.Server] = []
    for name, factory_path, port in SERVICES:
        module_name, _, attribute = factory_path.partition(":")
        module = __import__(module_name, fromlist=[attribute])
        factory = getattr(module, attribute)

        from dataclasses import replace

        service_settings = replace(settings, port=port, service_name=name)
        app = factory(service_settings)

        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                log_level="warning",
                access_log=False,
            )
        )
        servers.append(server)

        threading.Thread(target=server.run, name=f"ngsh-{name}", daemon=True).start()
        print(f"  {name:<9} http://127.0.0.1:{port}")

    print("\nNGSH platform running. Press Ctrl-C to stop.\n")

    stop = threading.Event()

    def _shutdown(signum, frame):  # noqa: ANN001, ARG001
        stop.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while not stop.is_set():
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        for server in servers:
            server.should_exit = True
        time.sleep(0.5)
        print("\nNGSH foundation stopped.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
