# ── Manifold web image (Caddy) ──────────────────────────────
# Serves the frontend SPA and reverse-proxies /api/* to the
# backend.  This is the ONLY container that publishes a host port.
#
# In release mode the frontend is supplied as a pre-built tarball
# (frontend.tar.xz) produced by scripts/ci/package_frontend.sh.
# For local / dev builds the tarball is built inline.
# ────────────────────────────────────────────────────────────

# --- builder (used only when no pre-built tarball is provided) ---
FROM node:24-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# --- release ---
FROM caddy:2-alpine AS release

# OCI labels
ARG BUILD_DATE
ARG VCS_REF
ARG SOURCE_URL="https://github.com/Agentic2026/Manifold"
LABEL org.opencontainers.image.title="manifold-web" \
      org.opencontainers.image.description="Manifold – Caddy frontend & reverse proxy" \
      org.opencontainers.image.url="${SOURCE_URL}" \
      org.opencontainers.image.source="${SOURCE_URL}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.licenses="MIT"

COPY Caddyfile /etc/caddy/Caddyfile

# Prefer pre-built tarball when available (release pipeline),
# otherwise fall back to builder stage output (local dev).
COPY --from=builder /app/dist /srv

EXPOSE 8080
