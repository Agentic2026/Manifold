##############################
# Builder
##############################
FROM python:3.14.3-slim-bookworm AS builder

# Copy uv binary only into the builder stage.
COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /usr/local/bin/uv

WORKDIR /build

# Put the project virtualenv in a fixed location so it can be copied
# directly into the runtime image.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy dependency manifests first for better layer caching.
COPY pyproject.toml uv.lock ./

# Create the virtualenv and install only production dependencies first.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv && \
    uv sync --frozen --no-dev --no-install-project

# Copy application source after dependency installation so normal code
# changes do not invalidate the dependency layer.
COPY app/ ./app/

# Install the project itself into the already-created venv.
# This keeps uv out of the final image while still giving us a complete
# self-contained Python environment in /opt/venv.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /opt/venv/bin/python --no-deps .

##############################
# Runtime
##############################
FROM python:3.14.3-slim-bookworm AS runtime

ARG BUILD_DATE
ARG VCS_REF
ARG SOURCE_URL="https://github.com/Agentic2026/Manifold"

LABEL org.opencontainers.image.title="manifold-api" \
      org.opencontainers.image.description="Manifold continuous cybersecurity monitoring backend" \
      org.opencontainers.image.url="${SOURCE_URL}" \
      org.opencontainers.image.source="${SOURCE_URL}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    H4CKATH0N_STORAGE_DIR="/app/.h4ckath0n_storage" \
    H4CKATH0N_EMAIL_OUTBOX_DIR="/app/.h4ckath0n_email_outbox"

# Create a non-root runtime user and runtime-writable directories.
RUN groupadd --system manifold && \
    useradd --system --gid manifold --home-dir /app --no-create-home manifold && \
    mkdir -p /app/.h4ckath0n_storage /app/.h4ckath0n_email_outbox && \
    chown -R manifold:manifold /app

WORKDIR /app

# Copy only the built virtualenv into the runtime image.
COPY --from=builder /opt/venv /opt/venv

USER manifold

EXPOSE 8000

CMD ["/opt/venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
