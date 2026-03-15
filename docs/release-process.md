# Manifold – Release Process

## Image Names

| Image | Description |
|-------|-------------|
| `ghcr.io/agentic2026/manifold` | Backend API (also used as worker) |
| `ghcr.io/agentic2026/manifold-web` | Caddy frontend + reverse proxy |

## Tag Policy

| Tag pattern | When | Example |
|-------------|------|---------|
| `latest` | Every tagged release (`v*`) | `latest` |
| `X.Y.Z` | Semver from git tag | `0.3.0` |
| `X.Y` | Major.minor alias | `0.3` |
| `sha-<short>` | Every release build | `sha-abc1234` |

Dev tags (`sha-*`) are published on every `workflow_dispatch` and tag push.
`latest` is only updated on proper `v*` tag pushes.

## Release Workflow

The release is fully automated via `.github/workflows/release.yml`.

### Triggering a Release

1. **Tag push** (recommended):
   ```bash
   git tag v0.3.0
   git push origin v0.3.0
   ```

2. **Manual dispatch**: Go to Actions → Release → Run workflow.

### What the Workflow Does

1. **Version metadata** – `scripts/ci/compute_version.py` extracts version
   info from git tags.
2. **Frontend packaging** – `scripts/ci/package_frontend.sh` builds the Vite
   app and produces `frontend.tar.xz`.
3. **Backend image** – Multi-arch (`amd64`/`arm64`) Docker build from
   `api/Dockerfile`, pushed to GHCR with OCI labels, SBOM, and provenance.
4. **Web image** – Multi-arch build from `web/Dockerfile` using the
   pre-built frontend artifact, pushed to GHCR.
5. **Vulnerability scan** – Trivy scans both images for `CRITICAL`/`HIGH`
   CVEs; results uploaded as SARIF to GitHub Code Scanning.

## Building Local Images

For local testing without pulling from GHCR:

```bash
# Backend
docker build -t manifold-api:local -f api/Dockerfile api/

# Frontend (builds inline)
docker build -t manifold-web:local -f web/Dockerfile web/

# Run with local images
MANIFOLD_IMAGE=manifold-api:local \
MANIFOLD_WEB_IMAGE=manifold-web:local \
docker compose up -d
```

## How Compose Consumes Images

The primary `docker-compose.yml` defaults to GHCR images:

```yaml
api:
  image: ${MANIFOLD_IMAGE:-ghcr.io/agentic2026/manifold:latest}
web:
  image: ${MANIFOLD_WEB_IMAGE:-ghcr.io/agentic2026/manifold-web:latest}
```

Override with environment variables for local or pinned builds:

```bash
export MANIFOLD_IMAGE=ghcr.io/agentic2026/manifold:0.3.0
export MANIFOLD_WEB_IMAGE=ghcr.io/agentic2026/manifold-web:0.3.0
docker compose up -d
```

## Security & Supply Chain

- **SBOM generation**: Enabled via `docker/build-push-action` with `sbom: true`.
- **Provenance**: Enabled via `provenance: true` (SLSA Build L1).
- **Trivy scanning**: Runs post-publish and uploads SARIF results.
- **Non-root images**: Both backend and web images run as non-root users.
- **Pinned base images**: `python:3.14-slim` and `caddy:2-alpine`.

## CI Quality Gates

The CI workflow (`.github/workflows/ci.yml`) must pass before any release:

- Backend linting and tests (`pytest`)
- Frontend linting, type checking, and unit tests (`vitest`)
- E2E tests (`playwright`)
