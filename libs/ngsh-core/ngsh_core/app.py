"""Shared HTTP service kit.

Every NGSH service is a FastAPI application built from this factory, so that
health semantics, error envelopes, identity resolution, request correlation
and access logging are identical across the platform. A difference in how two
services reject a request is a difference an operator has to learn twice, and
on an accredited system that difference is a liability.

The kit is intentionally thin. Domain logic belongs in ``ngsh_core`` and in
the individual services; this module only concerns itself with transport.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse

from .config import Settings, load_settings
from .envelope import Actor
from .errors import NGSHError
from .identity import IdentityContext, IdentityProvider, build_identity_provider

RequestIdMiddleware = Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]


def _request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response


def _timing_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def add_timing(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.2f}"
        return response


def create_service(
    name: str,
    *,
    settings: Settings | None = None,
    routers: Iterable[Any] = (),
    lifespan: Callable[[FastAPI], Any] | None = None,
    identity_provider: IdentityProvider | None = None,
    description: str = "",
    tags: list[dict[str, Any]] | None = None,
) -> FastAPI:
    """Build a FastAPI application with the shared NGSH service behaviour."""
    resolved = settings or load_settings()

    @asynccontextmanager
    async def _default_lifespan(app: FastAPI):
        yield

    app = FastAPI(
        title=f"NGSH {name}",
        description=description,
        version="0.1.0",
        openapi_tags=tags or [],
        lifespan=lifespan or _default_lifespan,
    )
    app.state.settings = resolved
    app.state.identity_provider = identity_provider or build_identity_provider(
        resolved.identity_provider, deployment_profile=resolved.deployment_profile
    )

    _request_id_middleware(app)
    _timing_middleware(app)

    @app.exception_handler(NGSHError)
    async def _domain_error(request: Request, exc: NGSHError) -> JSONResponse:  # type: ignore[no-untyped-def]
        payload = exc.to_dict()
        payload["error"]["requestId"] = getattr(request.state, "request_id", None)
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.get("/healthz", tags=["operations"], summary="Liveness probe")
    async def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": name,
            "version": app.version,
            "deploymentProfile": resolved.deployment_profile,
            "deploymentZone": resolved.deployment_zone,
        }

    @app.get("/readyz", tags=["operations"], summary="Readiness probe")
    async def readyz() -> dict[str, Any]:
        return {"status": "ready", "service": name}

    @app.get("/v1/service/info", tags=["operations"], summary="Service metadata")
    async def service_info() -> dict[str, Any]:
        return {
            "service": name,
            "version": app.version,
            "tenant": resolved.tenant,
            "program": resolved.program,
            "deploymentProfile": resolved.deployment_profile,
            "deploymentZone": resolved.deployment_zone,
            "identityProvider": resolved.identity_provider,
        }

    for router in routers:
        app.include_router(router)

    return app


def current_actor(request: Request) -> Actor:
    """Resolve the calling actor from the request's credential."""
    provider: IdentityProvider = request.app.state.identity_provider
    context: IdentityContext = provider.resolve(
        request.headers.get("Authorization"),
        client=request.client.host if request.client else None,
        path=request.url.path,
        method=request.method,
    )
    request.state.actor = context.actor
    request.state.identity = context
    return context.actor


async def actor_dependency(request: Request) -> Actor:
    """FastAPI dependency yielding the calling actor."""
    return current_actor(request)


def actor_of(request: Request) -> Actor:
    """Read the actor already resolved by the dependency, if any."""
    actor = getattr(request.state, "actor", None)
    if actor is None:
        return current_actor(request)
    return actor


def service_settings(request: Request) -> Settings:
    return request.app.state.settings


SettingsDependency = Depends(service_settings)
ActorDependency = Depends(actor_dependency)
