# =============================================================================
# NGSH web console — nginx serving the static build of apps/web
# =============================================================================
# Owned by the deployment layer: the console is served as a static bundle by a
# plain nginx image. There is no Node runtime in the published image and no
# application server in front of the console.
#
# Build context is the repository root (../../ from deploy/compose) so that
# the frontend source at apps/web and this nginx configuration can be copied
# in one build.
#
# The frontend build is best-effort: if apps/web has no package manifest yet
# the builder stage produces an empty bundle and the console serves the
# placeholder page. That keeps `docker compose up` usable while the console
# is still being built out.
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1 — build the console bundle
# -----------------------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /src

# Manifest first so the dependency layer caches independently of source edits.
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund || true

COPY apps/web/ ./

# `npm run build` is expected to emit apps/web/dist. If the frontend is not
# present yet, fall back to an empty dist so the image still builds.
RUN npm run build || true
RUN mkdir -p /src/dist

# -----------------------------------------------------------------------------
# Stage 2 — runtime
# -----------------------------------------------------------------------------
FROM nginx:1.27-alpine

LABEL org.opencontainers.image.title="ngsh-web-console" \
      org.opencontainers.image.description="NGSH operator console (static build served by nginx)" \
      org.opencontainers.image.source="https://example.gov/ngsh" \
      org.opencontainers.image.licenses="Proprietary"

# Replace the stock config with one that serves the console and proxies the
# API surface to the platform services.
RUN rm -f /etc/nginx/conf.d/default.conf
COPY deploy/compose/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/compose/web/proxy_params_ngsh.conf /etc/nginx/proxy_params_ngsh.conf
COPY deploy/compose/web/placeholder.html /usr/share/nginx/html/placeholder.html

COPY --from=builder /src/dist/ /usr/share/nginx/html/

EXPOSE 8080

STOPSIGNAL SIGQUIT

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
