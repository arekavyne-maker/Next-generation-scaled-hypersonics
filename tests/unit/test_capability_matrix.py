"""The capability matrix must describe endpoints that actually exist.

A capability matrix is only useful if the runnable path it advertises is the
path the service exposes. This test imports each service router and checks the
declared endpoints against it, so the console, the gateway and the demo cannot
drift away from the code.
"""

from __future__ import annotations

import importlib
import re

from ngsh_core.capabilities import CAPABILITIES, capability_matrix
from ngsh_core.integration import INTERFACE_REGISTER

SERVICE_MODULES = {
    "architecture": "ngsh_architecture.app",
    "workforce": "ngsh_workforce.app",
    "manufacturing": "ngsh_manufacturing.app",
    "testlab": "ngsh_testlab.app",
    "supply": "ngsh_supply.app",
    "engagement": "ngsh_engagement.app",
    "industrial": "ngsh_industrial.app",
    "analytics": "ngsh_analytics.app",
    "integration": "ngsh_integration.app",
    "ingest": "ngsh_ingest.app",
    "thread": "ngsh_thread.app",
    "gateway": "ngsh_gateway.app",
}

_PARAMETER = re.compile(r"\{[^}]+\}")


def _routes(service: str) -> set[str]:
    module = importlib.import_module(SERVICE_MODULES[service])
    return {_PARAMETER.sub("{id}", route.path) for route in module.router.routes}


def test_matrix_declares_the_full_psdd_scope():
    matrix = capability_matrix()
    assert matrix["count"] == 34
    assert matrix["pillarCount"] == 8
    assert matrix["interfaceCount"] == len(INTERFACE_REGISTER) == 7
    assert {row["id"] for row in matrix["capabilities"]} == {
        f"{pillar}-{index}"
        for pillar, count in {"A": 5, "B": 4, "C": 4, "D": 3, "E": 5, "F": 6, "G": 4, "H": 3}.items()
        for index in range(1, count + 1)
    }


def test_every_capability_endpoint_exists_in_the_owning_service():
    routes = {service: _routes(service) for service in SERVICE_MODULES}
    missing = []
    for capability in CAPABILITIES:
        service = capability["service"]
        for endpoint in capability["endpoints"]:
            if _PARAMETER.sub("{id}", endpoint) not in routes[service]:
                missing.append(f"{capability['id']} {service} {endpoint}")
    assert missing == []


def test_every_capability_names_an_owning_service():
    for capability in CAPABILITIES:
        assert capability["service"] in SERVICE_MODULES, capability["id"]
        assert capability["limitations"] is not None
