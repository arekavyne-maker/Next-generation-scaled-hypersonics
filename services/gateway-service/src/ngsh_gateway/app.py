"""NGSH gateway: one address for the whole platform.

The gateway is not a business service. It is the operator's and the console's
single entry point, and it deliberately does very little:

* it reports the live state of every service and the capability matrix the
  platform claims;
* it proxies ``/api/<service>/...`` to the owning service without rewriting
  the domain;
* it issues a **local-only** signed identity assertion so the IF-6 path can be
  exercised end to end without pretending a PIV card exists.

The proxy is intentionally transparent. A request that fails at a service
returns that service's status and error envelope, not a gateway invention.
Masking a downstream failure would make the gateway look healthy while the
platform is not.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from fastapi import APIRouter, Body, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from ngsh_core.app import create_service
from ngsh_core.capabilities import capability_matrix
from ngsh_core.config import Settings, load_settings
from ngsh_core.errors import NotFoundError, ValidationError
from ngsh_core.identity import issue_assertion

SERVICE_NAME = "gateway"
DESCRIPTION = (
    "The single entry point: platform status, the capability matrix, a "
    "transparent service proxy and local identity assertion issuance."
)

#: The deployable services and their reference ports. A deployment overrides
#: any of these with ``NGSH_<NAME>_URL``; the map is the contract, the
#: environment is the placement.
SERVICE_PORTS: dict[str, int] = {
    "ontology": 8081,
    "fabric": 8082,
    "policy": 8083,
    "audit": 8084,
    "thread": 8085,
    "ingest": 8086,
    "edge": 8087,
    "architecture": 8088,
    "workforce": 8089,
    "manufacturing": 8090,
    "testlab": 8091,
    "supply": 8092,
    "engagement": 8093,
    "industrial": 8094,
    "analytics": 8095,
    "integration": 8096,
}

#: The services the gateway is expected to reach in a full stack. ``edge`` is
#: excluded because an edge annex may legitimately be disconnected.
CORE_SERVICES: tuple[str, ...] = tuple(name for name in SERVICE_PORTS if name != "edge")

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

router = APIRouter(tags=["gateway"])


def service_base(name: str) -> str:
    """Resolve a service base URL, preferring explicit deployment placement."""
    override = os.environ.get(f"NGSH_{name.upper()}_URL")
    if override:
        return override.rstrip("/")
    port = SERVICE_PORTS.get(name)
    if port is None:
        raise NotFoundError(f"no service named {name!r}")
    return f"http://127.0.0.1:{port}"


def _service_names() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "port": SERVICE_PORTS[name],
            "url": service_base(name),
            "core": name in CORE_SERVICES,
        }
        for name in SERVICE_PORTS
    ]


def _get_json(url: str, timeout: float = 3.0) -> tuple[int, Any]:
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {"error": type(exc).__name__, "detail": str(exc)}


def _proxy(
    method: str,
    url: str,
    body: bytes,
    headers: dict[str, str],
    timeout: float = 15.0,
) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(url, data=body or None, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        payload = json.dumps(
            {
                "error": {
                    "code": "service_unreachable",
                    "message": f"the gateway could not reach {url}",
                    "context": {"reason": type(exc).__name__},
                }
            }
        ).encode()
        return 503, {"content-type": "application/json"}, payload


@router.get("/v1/platform/services", summary="Every service and its resolved address")
async def services() -> dict[str, Any]:
    return {"services": _service_names(), "count": len(SERVICE_PORTS)}


@router.get("/v1/platform/status", summary="Live health of the whole platform")
async def platform_status() -> dict[str, Any]:
    """Probe every core service and report the platform, not a guess.

    ``status`` is ``ok`` only when every core service answers. A missing edge
    annex does not make the platform unhealthy, because disconnection is an
    expected edge posture.
    """
    probes = await asyncio.gather(
        *(asyncio.to_thread(_get_json, f"{service_base(name)}/healthz") for name in CORE_SERVICES)
    )
    rows = []
    for name, (code, payload) in zip(CORE_SERVICES, probes, strict=True):
        healthy = code == 200 and isinstance(payload, dict) and payload.get("status") == "ok"
        rows.append(
            {
                "name": name,
                "url": service_base(name),
                "reachable": code != 0,
                "statusCode": code,
                "status": "ok" if healthy else "down",
                "detail": payload if not healthy else payload.get("version"),
            }
        )
    reachable = sum(1 for row in rows if row["reachable"])
    healthy = sum(1 for row in rows if row["status"] == "ok")
    return {
        "status": "ok" if healthy == len(rows) else "degraded" if reachable else "down",
        "serviceCount": len(rows),
        "healthyCount": healthy,
        "reachableCount": reachable,
        "services": rows,
        "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@router.get("/v1/platform/capabilities", summary="Capability and interface matrix")
async def capabilities() -> dict[str, Any]:
    """The PSDD scope with the owning service and the runnable endpoints."""
    matrix = capability_matrix()
    by_service: dict[str, int] = {}
    for row in matrix["capabilities"]:
        by_service[row["service"]] = by_service.get(row["service"], 0) + 1
    return {
        **matrix,
        "services": [{"name": name, "capabilityCount": count} for name, count in sorted(by_service.items())],
        "note": (
            "IMPLEMENTED means a runnable, tested path exists. ADAPTER means the "
            "platform provides a validated simulated counterpart; the real "
            "counterpart is supplied and accredited by the programme."
        ),
    }


@router.post("/v1/identity/assert", summary="Issue a local PIV-style assertion", status_code=201)
async def issue_local_assertion(request: Request, body: dict[str, Any] = Body(default={})) -> JSONResponse:
    """Mint a signed local assertion for exercising IF-6.

    This is refused outside ``local`` and ``edge``. It is an adapter for tests
    and disconnected development, never a credential source for an accredited
    environment.
    """
    settings: Settings = request.app.state.settings
    if settings.deployment_profile not in {"local", "edge"}:
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "local_identity_refused",
                    "message": (
                        "local assertion issuance is only available in the 'local' and "
                        "'edge' profiles; use the government PIV/ICAM provider"
                    ),
                    "context": {"deploymentProfile": settings.deployment_profile},
                }
            },
        )
    if not isinstance(body, dict):
        raise ValidationError("the assertion request must be an object")
    attributes = dict(body.get("actor") or body)
    attributes.setdefault("tenant", settings.tenant)
    if settings.program:
        attributes.setdefault("programs", [settings.program])
        attributes.setdefault("needToKnow", [settings.program])
    if not attributes.get("subjectId"):
        raise ValidationError("'subjectId' is required")
    if not attributes.get("clearance"):
        raise ValidationError("'clearance' is required for an assertion")
    if not attributes.get("citizenship"):
        raise ValidationError("'citizenship' is required for an assertion")
    assertion = issue_assertion(attributes)
    token = (
        base64.urlsafe_b64encode(json.dumps(assertion, sort_keys=True, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    return JSONResponse(
        status_code=201,
        content={
            "assertion": assertion,
            "token": token,
            "authorization": f"Bearer {token}",
            "expiresAt": assertion["expiresAt"],
            "profile": settings.deployment_profile,
        },
    )


@router.get("/v1/platform/info", summary="Gateway metadata")
async def info(request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    return {
        "service": SERVICE_NAME,
        "proxyPrefix": "/api/<service>/",
        "identityIssuance": settings.deployment_profile in {"local", "edge"},
        "services": len(SERVICE_PORTS),
    }


@router.api_route(
    "/api/{service}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    summary="Transparent service proxy",
)
async def proxy(service: str, path: str, request: Request) -> Response:
    if service not in SERVICE_PORTS:
        raise NotFoundError(f"no service named {service!r}")
    base = service_base(service)
    url = f"{base}/{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    body = await request.body()
    headers = {key: value for key, value in request.headers.items() if key.lower() not in _HOP_BY_HOP}
    headers.setdefault("X-Forwarded-By", SERVICE_NAME)
    status, response_headers, payload = await asyncio.to_thread(_proxy, request.method, url, body, headers)
    forwarded = {key: value for key, value in response_headers.items() if key.lower() not in _HOP_BY_HOP}
    if "content-type" not in {key.lower() for key in forwarded}:
        forwarded["content-type"] = "application/json"
    return Response(content=payload, status_code=status, headers=forwarded)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()
    app = create_service(
        SERVICE_NAME,
        settings=resolved,
        description=DESCRIPTION,
        routers=[router],
        tags=[
            {"name": "gateway", "description": "One entry point for the platform."},
            {"name": "operations", "description": "Health and metadata."},
        ],
    )
    app.state.services = SERVICE_PORTS
    return app


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
