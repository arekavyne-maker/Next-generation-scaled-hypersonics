# syntax=docker/dockerfile:1
#
# NGSH integration-service — service image.
#
# Platform-agnostic by construction: this image contains the application and
# nothing cloud-specific. Where and how it runs is decided by the deployment
# layer, never by the image (ADR-0003). The same image lands in an accredited
# cloud enclave, an on-prem IL6 node, or a disconnected edge annex.
#
# Build from the repository root:
#   docker build -f services/integration-service/Dockerfile -t ngsh/integration-service:dev .
#
# Runtime contract:
#   * listens on $PORT
#   * GET /healthz and GET /readyz return 200 application/json
#   * the contract layer is present at /app/contracts

ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.11.26

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ARG SERVICE_NAME=integration-service
ARG SERVICE_PORT=8096

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

# The Python tree and the lockfile. uv installs the whole workspace, so the
# service packages are present as editable installs and the contract layer is
# resolved relative to /app.
COPY pyproject.toml uv.lock ./
COPY libs ./libs
COPY services ./services

RUN uv sync --frozen --no-dev

# The contract layer is data, not code. It is copied after the dependency
# install so that a governance change to a schema does not invalidate the
# image's dependency layer.
COPY contracts ./contracts

RUN useradd --uid 65532 --create-home --shell /usr/sbin/nologin ngsh \
 && chown -R 65532:65532 /app
USER 65532:65532

EXPOSE ${SERVICE_PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8096}/healthz" || exit 1

CMD ["ngsh-integration-service"]
