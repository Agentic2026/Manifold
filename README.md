# Manifold

**Manifold** is a continuous cybersecurity monitoring platform for containerized systems — software assembled with AI tools that may harbor hidden security risks. It auto-discovers service topology from live Docker container metadata, renders an interactive DAG, and uses an LLM security agent to reason about anomalies detected through real-time container metrics.

## Project Status

Manifold is in a **prototype-to-production transition phase**.

- Core backend and frontend functionality are implemented and testable.
- Backend (19 tests), frontend unit (37 tests), and E2E (17 tests) all pass.
- Runtime topology auto-discovery from live cAdvisor data is the primary mode.
- Docker packaging uses pre-built GHCR images and a single-port Caddy frontend.

For a detailed assessment and phased production plan, see:

- [`docs/CURRENT_STATE_AND_PRODUCTION_PLAN.md`](docs/CURRENT_STATE_AND_PRODUCTION_PLAN.md)
- [`docs/release-process.md`](docs/release-process.md)

## How It Works — Onboarding

1. **You have an existing Docker Compose stack** you want to monitor.
2. **Add the Manifold cAdvisor overlay** to your stack (see [Drop-in Monitoring](#drop-in-monitoring-for-existing-stacks)).
3. **Redeploy** with `docker compose up`.
4. **Manifold auto-discovers services** from live runtime metadata (Docker Compose labels like `com.docker.compose.service` and `com.docker.compose.project`).
5. **The System Map updates continuously** with real telemetry — no manual import required.

> **Note:** A manual Docker Compose import endpoint (`POST /api/topology/import`) exists as an **optional enrichment** tool. It merges declared edges (depends_on, shared networks) into the live topology without destroying runtime-discovered data. Pass `project_name` to scope imported nodes so they align with runtime-discovered containers.

## Architecture Overview

Manifold is composed of three core layers:

1. **Container Runtime Monitoring** — [cAdvisor](https://github.com/google/cadvisor) collects container metrics (CPU, memory, network, filesystem). Metrics are pushed to the Manifold backend via `POST /api/cadvisor/batch` through the Caddy reverse proxy.

2. **LLM Security Agent Pipeline** — An LLM agent ingests telemetry, compares against baselines, reasons about anomalies, and generates human-readable threat explanations. Security insights are available via `/api/insights` and streaming analysis via SSE (`POST /api/llm/chat/stream`). LLM features are **optional** — live monitoring works without OpenAI credentials.

3. **Architecture Awareness** — Manifold auto-discovers service topology from live container runtime metadata. Topology node IDs are scoped by Compose project (`<project>__<service>`) to prevent collisions across different stacks. This enables the LLM to reason about incident propagation.

### Single-Origin Deployment

```
                        Public network
                            │
                    ┌───────▼───────┐
                    │  Caddy (web)  │ ← only exposed port (:8080)
                    │  serves SPA   │
                    │  proxies /api │
                    └───────┬───────┘
                            │ internal Docker network
              ┌─────────────┼─────────────┐
              │             │             │
        ┌─────▼─────┐ ┌────▼────┐ ┌──────▼──────┐
        │  FastAPI   │ │  Redis  │ │  PostgreSQL  │
        │  backend   │ │         │ │              │
        └─────┬─────┘ └─────────┘ └──────────────┘
              │
        ┌─────▼─────┐
        │  Worker    │ (same image as backend)
        └───────────┘
```

Only the Caddy web container publishes a host port. API, PostgreSQL, Redis, worker, and cAdvisor are internal-only by default.

## Quick Start

### Docker Compose (recommended)

```bash
cp .env.example .env   # edit values as needed
docker compose up -d
```

This pulls pre-built images from GHCR and starts all services. The API auto-creates database tables on startup.

| Service    | Port   | Description |
|------------|--------|-------------|
| `web`      | 8080   | Caddy frontend + reverse proxy (only public port) |
| `api`      | —      | FastAPI backend (internal) |
| `worker`   | —      | Background job processor (internal) |
| `db`       | —      | PostgreSQL 16 (internal) |
| `redis`    | —      | Job queue (internal) |
| `cadvisor` | —      | Container metrics collector (internal) |

### Using Local Images

```bash
# Build backend
docker build -t manifold-api:local -f api/Dockerfile api/

# Build frontend
docker build -t manifold-web:local -f web/Dockerfile web/

# Run with local images
MANIFOLD_IMAGE=manifold-api:local \
MANIFOLD_WEB_IMAGE=manifold-web:local \
docker compose up -d
```

### Verify Ingestion (Smoke Test)

```bash
# Health check
curl http://localhost:8080/api/healthz

# Ingest stats
curl http://localhost:8080/api/ingest/stats

# Topology (auto-discovered from running containers)
curl http://localhost:8080/api/topology | python3 -m json.tool
```

### (Optional) Import Topology from Docker Compose

> **Not required.** Manifold auto-discovers topology from live container metadata. Use this for enrichment (adding declared edges) or preview.

```bash
curl -X POST http://localhost:8080/api/topology/import \
  -H "Content-Type: application/json" \
  -d "{\"yaml_content\": $(python3 -c "import json; print(json.dumps(open('docker-compose.yml').read()))"), \"project_name\": \"manifold\"}"
```

### Drop-in Monitoring for Existing Stacks

To add Manifold monitoring to any existing Docker Compose stack:

```bash
# Set the public Manifold origin and API token
export MANIFOLD_URL=http://<manifold-host>:8080
export MANIFOLD_API_TOKEN=my-secret-token

# Add cAdvisor as an overlay to your stack
docker compose -f docker-compose.yml -f path/to/docker-compose.cadvisor.yml up -d
```

cAdvisor sends metrics through the Manifold web proxy at `/api/cadvisor/batch`. See `docker-compose.cadvisor.yml` for the reusable drop-in snippet.

> **Linux note:** The overlay includes `extra_hosts: host.docker.internal:host-gateway` so that `host.docker.internal` resolves correctly on Linux.

### Local Development (without Docker)

```bash
# Backend
cd api
uv sync
uv run uvicorn app.main:app --reload   # http://localhost:8000

# Frontend (separate terminal)
cd web
npm install
npm run dev                             # http://localhost:5173
```

The Vite dev server proxies `/api/*` requests to `http://localhost:8000`, stripping the `/api` prefix — matching the production Caddy behavior.

## Repository Structure

```
manifold/
├── api/                    Python backend (FastAPI)
│   ├── app/
│   │   ├── main.py             Entry point, middleware, demo endpoints
│   │   ├── services/
│   │   │   ├── discovery.py    Runtime topology auto-discovery
│   │   │   └── ingestion.py    cAdvisor metric processing
│   │   └── routers/
│   │       ├── aegis.py        AEGIS security API (topology, vulns, insights)
│   │       ├── ingest.py       cAdvisor metrics ingestion
│   │       ├── dashboard.py    File uploads, jobs, LLM chat streaming
│   │       └── auth_ext.py     Auth session extensions
│   ├── Dockerfile              Multi-stage production image
│   └── pyproject.toml          Python dependencies
├── web/                    React + TypeScript frontend
│   ├── src/
│   │   ├── pages/SystemMap.tsx     Interactive topology graph (@xyflow/react)
│   │   ├── api/aegis.ts           Typed AEGIS API client
│   │   └── auth/                  WebAuthn/passkey authentication
│   ├── Dockerfile              Caddy-based production image
│   ├── Caddyfile               Reverse proxy configuration
│   └── package.json            Frontend dependencies
├── docker-compose.yml      Image-based orchestration (GHCR defaults)
├── docker-compose.cadvisor.yml  Drop-in cAdvisor overlay
├── scripts/ci/             Release engineering scripts
├── docs/                   Documentation
│   ├── CURRENT_STATE_AND_PRODUCTION_PLAN.md
│   └── release-process.md
└── .env.example            Environment variable template
```

## Features

### Interactive Topology Map

The System Map renders a real-time, interactive DAG using [@xyflow/react](https://reactflow.dev/). Each node displays:

- **Service status** — healthy, warning, compromised, or isolated
- **Live telemetry** — ingress/egress throughput, latency, error rate
- **AI analysis** — summary findings and recommendations per node

Operators can **isolate compromised nodes** and **revoke RBAC permissions** directly from the graph. These actions are currently **simulated** — they persist status changes in the database but do not perform real network isolation or credential revocation.

### Runtime Topology Discovery

Manifold auto-discovers topology from live container metadata:

- Containers are grouped by `com.docker.compose.service` and `com.docker.compose.project` labels
- Node IDs are project-scoped (`<project>__<service>`) to prevent collisions across stacks
- Edges are inferred from shared Compose projects and shared Docker networks
- All inferred edges are labeled honestly (e.g., "inferred: same project (myapp)")

### Container Metrics Ingestion

The `POST /cadvisor/batch` endpoint accepts telemetry batches. Each batch includes:

- Container reference (name, aliases, namespace)
- Container spec (resource limits, image info, labels)
- Stats snapshots (CPU, memory, network, filesystem)

Requests are authenticated with a Bearer token (`CADVISOR_METRICS_API_TOKEN`).

### LLM Security Insights

An LLM agent analyzes metrics and topology to produce security insights:

- **Threat** — confirmed malicious activity
- **Anomaly** — unusual behavior requiring investigation
- **Info** — contextual observations

LLM features require `OPENAI_API_KEY`. Without it, live monitoring and topology work normally; only deep scan and insights are unavailable.

## API Reference

All API endpoints are accessed through the `/api` prefix on the public Caddy origin.

### AEGIS Security Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/topology` | Full service topology (nodes + edges) |
| POST | `/api/topology/import` | Import/enrich topology from Compose YAML |
| POST | `/api/topology/scan` | Trigger a deep LLM scan |
| POST | `/api/topology/{node_id}/isolate` | Soft-isolate a node (simulated) |
| GET | `/api/vulnerabilities` | List detected vulnerabilities |
| GET | `/api/insights` | LLM-generated security insights |
| GET | `/api/rbac` | List RBAC policies |
| POST | `/api/rbac/{node_id}/revoke` | Revoke node permissions (simulated) |
| GET | `/api/security-score` | Aggregate security posture score |

### Metrics Ingestion

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/cadvisor/batch` | Ingest cAdvisor container metrics (Bearer token) |
| GET | `/api/ingest/stats` | Ingest statistics |

### Other Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/healthz` | Health check |
| GET | `/api/auth/session` | Current session info |
| POST | `/api/llm/chat/stream` | Stream LLM response (SSE) |
| GET | `/api/demo/ws` | WebSocket demo endpoint |
| GET | `/api/demo/sse` | SSE demo endpoint |

## Security

### Application Security

- **Content-Security-Policy** headers enforced via middleware
- **X-Content-Type-Options**: `nosniff`
- **X-Frame-Options**: `DENY`
- **Referrer-Policy**: `strict-origin-when-cross-origin`

### Authentication

- WebAuthn/passkey credentials with non-extractable private keys
- Short-lived JWTs (15 min) signed per-device
- Server-side JWT verification with RBAC enforcement

### Ingestion Security

- cAdvisor metric batches require a Bearer token
- Token validated server-side before any data is processed

## Environment

Copy `.env.example` to `.env` and configure:

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_PORT` | `8080` | Public port for the Caddy web container |
| `H4CKATH0N_DATABASE_URL` | `postgresql+psycopg://…` | Canonical DB URL (psycopg). The async `asyncpg` URL is derived from this automatically. |
| `H4CKATH0N_ORIGIN` | `http://localhost:8080` | Public origin for CORS/auth |
| `OPENAI_API_KEY` | — | OpenAI key (optional, for LLM features) |
| `CADVISOR_METRICS_API_TOKEN` | `my-secret-token` | Bearer token for ingestion |
| `VITE_API_BASE_URL` | `/api` | Frontend API base URL |
| `MANIFOLD_IMAGE` | `ghcr.io/agentic2026/manifold:latest` | Backend image override |
| `MANIFOLD_WEB_IMAGE` | `ghcr.io/agentic2026/manifold-web:latest` | Web image override |

## Testing

```bash
# Backend tests
cd api && uv run pytest tests/ -v

# Frontend lint, typecheck, unit tests
cd web && npm run lint && npm run typecheck && npx vitest run

# E2E tests
cd web && npx playwright test
```

## Tech Stack

### Backend

| Component | Technology |
|-----------|------------|
| Language | Python 3.14 |
| Framework | FastAPI |
| ORM | SQLAlchemy 2.0 (asyncpg) |
| Package Manager | uv |

### Frontend

| Component | Technology |
|-----------|------------|
| Framework | React 19 |
| Language | TypeScript 5.9 |
| Bundler | Vite 7 |
| Graph Rendering | @xyflow/react |

### Infrastructure

| Component | Technology |
|-----------|------------|
| Containers | Docker (multi-stage, multi-arch) |
| Orchestration | Docker Compose |
| Reverse Proxy | Caddy 2 |
| Job Queue | Redis 8 |
| CI/CD | GitHub Actions |
| Registry | GHCR (ghcr.io/agentic2026/manifold) |

## License

MIT
