# syntax=docker/dockerfile:1
#
# NGSH architecture-service — service image.
#
# Platform-agnostic by construction: this image contains the application and
# nothing cloud-specific. Where and how it runs is decided by the deployment
# layer, never by the image (ADR-0003).
#
# Build from the repository root:
#   docker build -f services/architecture-service/Dockerfile -t ngsh/architecture-service:dev .
#
# Runtime contract:
#   * listens on $PORT
#   * GET /healthz and GET /readyz return 200 application/json
#   * the contract layer is present at /app/contracts

ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.11.26

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ARG SERVICE_NAME=architecture-service
ARG SERVICE_PORT=8088

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    NGSH_SERVICE_NAME=${SERVICE_NAME} \
    NGSH_REPO_ROOT=/app \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:${UV_VERSION} /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY libs ./libs
COPY services ./services

RUN uv sync --frozen --no-dev

COPY contracts ./contracts

RUN useradd --uid 65532 --create-home --shell /usr/sbin/nologin ngsh \
 && chown -R 65532:65532 /app
USER 65532:65532

EXPOSE ${SERVICE_PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8088}/healthz" || exit 1

CMD ["ngsh_architecture.app:main"]
