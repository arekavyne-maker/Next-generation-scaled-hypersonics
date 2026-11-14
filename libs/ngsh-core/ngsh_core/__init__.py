"""Shared foundation library for the NGSH platform.

The NGSH foundation is event-sourced: the event log is the system of record and
every other store (graph, time-series, document, lakehouse, vector index) is a
projection that can be rebuilt by replaying the log.

This package holds the domain primitives that all six foundation services and
all eight pillars share. It deliberately contains no cloud-provider SDK calls
and no framework-specific code so that it can be vendored into an accredited
enclave or an edge annex unchanged.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "audit",
    "classification",
    "config",
    "envelope",
    "errors",
    "eventlog",
    "graph",
    "identity",
    "ids",
    "ontology",
    "policy",
    "store",
]
