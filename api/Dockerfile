# ── Manifold API image ──────────────────────────────────────
# Multi-stage build: builder installs deps, runtime copies only
# what is needed.  Reused for the background worker service.
# ────────────────────────────────────────────────────────────

# --- builder ---
FROM python:3.14-slim AS builder

WORKDIR /app
COPY pyproject.toml uv.lock ./

RUN pip install --no-cache-dir uv && \
    uv sync --locked --all-extras --no-install-project

COPY . .

# --- runtime ---
FROM python:3.14-slim AS runtime

# OCI / opencontainers labels
ARG BUILD_DATE
ARG VCS_REF
ARG SOURCE_URL="https://github.com/Agentic2026/Manifold"
LABEL org.opencontainers.image.title="manifold" \
      org.opencontainers.image.description="Manifold – continuous cybersecurity monitoring backend" \
      org.opencontainers.image.url="${SOURCE_URL}" \
      org.opencontainers.image.source="${SOURCE_URL}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.licenses="MIT"

# Non-root user
RUN groupadd --gid 1000 manifold && \
    useradd --uid 1000 --gid manifold --create-home manifold

WORKDIR /app

# Copy the full virtualenv and source from builder
COPY --from=builder /app /app

# Writable dirs for runtime data
RUN mkdir -p /app/.h4ckath0n_storage /app/.h4ckath0n_email_outbox && \
    chown -R manifold:manifold /app

USER manifold

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
