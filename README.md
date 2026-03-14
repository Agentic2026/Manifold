# Manifold

**Manifold** is a futuristic DAG UI security monitoring and analysis platform for *vibe-coded* containerized systems — software rapidly assembled with AI tools that may harbor hidden security risks. It maps service dependencies from Docker Compose files into an interactive topology graph and uses an LLM security agent to reason about anomalies detected through live container metrics.

## Architecture Overview

Manifold is composed of three core layers:

1. **Container Runtime Monitoring** — [cAdvisor](https://github.com/google/cadvisor) is deployed alongside user systems to collect container metrics (CPU, memory, network, filesystem, lifecycle events). Metrics are streamed to the Manifold backend via the `POST /cadvisor/batch` ingestion endpoint for anomaly detection and baseline comparison.

2. **LLM Security Agent Pipeline** — A backend agent ingests cAdvisor telemetry, compares it against established baselines, reasons about anomalies, and generates human-readable threat explanations. It exposes security insights through the `/api/insights` endpoint and can stream analysis via SSE (`POST /llm/chat/stream`).

3. **Architecture Awareness** — Users supply a Docker Compose file so the system can map service relationships, dependencies, and exposed ports into a dependency graph. This enables the LLM to reason about how an incident in one service propagates to others, displayed as an interactive topology visualization at `/api/topology`.

### System Context

```
┌──────────────┐         ┌────────────────────────────────────────────────┐
│  User System │         │               Manifold Stack                  │
│              │         │                                                │
│  ┌────────┐  │  metrics│  ┌───────┐   ┌────────┐   ┌──────┐           │
│  │cAdvisor├──┼────────►│  │  API  ├──►│ Worker ├──►│Redis │           │
│  └────────┘  │  :8000  │  │:8000  │   └────────┘   │:6379 │           │
│              │         │  └───┬───┘                  └──────┘           │
│  docker      │         │      │                                        │
│  compose.yml─┼────────►│  ┌───▼────────────────────────┐               │
│              │         │  │  React Frontend (nginx)     │               │
└──────────────┘         │  │  :5173                      │               │
                         │  └─────────────────────────────┘               │
                         └────────────────────────────────────────────────┘
```

## Quick Start

### Local Development

```bash
# Start both API and web servers
cd api
uv run h4ckath0n dev
```

The API runs at http://localhost:8000 and the web UI at http://localhost:5173.

### Docker Compose

```bash
cp .env.example .env   # edit values as needed
docker compose up --build
```

| Service  | Port | Description                             |
|----------|------|-----------------------------------------|
| `api`    | 8000 | FastAPI backend (metrics ingestion, LLM agent, AEGIS API) |
| `worker` | —    | Background job processor                |
| `redis`  | 6379 | Job queue and pub/sub                   |
| `web`    | 5173 | React frontend served by nginx          |

## Repository Structure

```
manifold/
├── api/                    Python backend (FastAPI)
│   ├── app/
│   │   ├── main.py             FastAPI entry point, middleware, demo endpoints
│   │   ├── middleware.py       Content-Security-Policy and security headers
│   │   └── routers/
│   │       ├── aegis.py        AEGIS security API (topology, vulns, insights, RBAC)
│   │       ├── ingest.py       cAdvisor metrics ingestion endpoint
│   │       ├── dashboard.py    File uploads, jobs, LLM chat streaming
│   │       └── auth_ext.py     Auth session extensions
│   ├── pyproject.toml          Python dependencies and build config
│   └── openapi.json            Generated OpenAPI specification
├── web/                    React + TypeScript frontend
│   ├── src/
│   │   ├── App.tsx             Route definitions
│   │   ├── pages/
│   │   │   ├── SystemMap.tsx       Interactive topology graph (@xyflow/react)
│   │   │   ├── LLMInsights.tsx     AI-generated security insights
│   │   │   ├── Vulnerabilities.tsx  Vulnerability listing and triage
│   │   │   ├── RBACPolicies.tsx     RBAC policy viewer
│   │   │   └── AppSettings.tsx      Application configuration
│   │   ├── api/                Typed API clients (OpenAPI-generated)
│   │   ├── auth/               WebAuthn/passkey authentication
│   │   └── components/         Shared UI components
│   ├── package.json            Frontend dependencies
│   ├── Dockerfile              Multi-stage nginx build
│   └── nginx.conf              Reverse proxy configuration
├── docker-compose.yml      Multi-service orchestration
├── Dockerfile              Multi-stage API image
└── .env.example            Environment variable template
```

## Features

### Interactive Topology Map

The System Map page renders a real-time, interactive DAG of all services and their connections using [@xyflow/react](https://reactflow.dev/). Each node displays:

- **Service status** — healthy, warning, or compromised
- **Live telemetry** — ingress/egress throughput, latency, error rate
- **AI analysis** — summary findings and recommendations per node

Operators can **isolate compromised nodes** and **revoke RBAC permissions** directly from the graph.

### Container Metrics Ingestion

The `POST /cadvisor/batch` endpoint accepts telemetry batches from a cAdvisor instance running on the monitored system. Each batch includes:

- Container reference (name, aliases, namespace)
- Container spec (resource limits, image info)
- Stats snapshots (CPU, memory, network, filesystem)

Requests are authenticated with a Bearer token (`CADVISOR_METRICS_API_TOKEN`).

### LLM Security Insights

An LLM agent analyzes ingested metrics and topology data to produce security insights categorized as:

- **Threat** — confirmed malicious activity (e.g., prompt injection, data exfiltration)
- **Anomaly** — unusual behavior requiring investigation (e.g., latency spikes, bulk reads)
- **Info** — contextual observations (e.g., new ASN traffic patterns)

Each insight carries a confidence score and is tied to a specific node in the topology. The `POST /llm/chat/stream` endpoint streams LLM responses as Server-Sent Events (SSE) for the interactive chat panel.

### Vulnerability Management

Detected vulnerabilities are tracked with:

- Severity levels (critical, high, medium, low)
- CVE identifiers where applicable
- Affected node correlation
- Status workflow (open → in-progress → resolved)

### RBAC Policy Viewer

Role-based access control policies are visualized with risk-level indicators. Operators can review permissions, scopes, and last-modified timestamps, and revoke access for specific nodes.

### Authentication

- **Passkeys (WebAuthn)** for registration and login
- **Password auth** (enabled by default via `H4CKATH0N_PASSWORD_AUTH_ENABLED`)
- Each device gets a **P-256 keypair** (private key non-extractable, stored in IndexedDB)
- API requests use **short-lived JWTs** (15 min) signed by the device key
- Server verifies JWT signatures and enforces RBAC from the database

### Background Jobs

The worker process polls Redis for jobs and executes them. Start it with:

```bash
uv run python -m h4ckath0n jobs worker
```

Or use `docker compose up worker`.

### File Uploads

Upload files via `POST /uploads`. Files are stored in `H4CKATH0N_STORAGE_DIR` (default `.h4ckath0n_storage/`). Text files automatically create extraction jobs processed by the worker.

### Demo Mode

Set `H4CKATH0N_DEMO_MODE=true` to seed demo data on startup, including a sample topology with seven services, mock vulnerabilities, and pre-generated LLM insights.

## API Reference

### AEGIS Security Endpoints (`/api`)

| Method | Path                          | Description                    |
|--------|-------------------------------|--------------------------------|
| GET    | `/api/topology`               | Retrieve the full service topology (nodes + edges) |
| POST   | `/api/topology/scan`          | Trigger a deep network scan    |
| POST   | `/api/topology/{node_id}/isolate` | Isolate a compromised node |
| GET    | `/api/vulnerabilities`        | List detected vulnerabilities  |
| GET    | `/api/insights`               | Get LLM-generated security insights |
| GET    | `/api/rbac`                   | List RBAC policies             |
| POST   | `/api/rbac/{node_id}/revoke`  | Revoke node permissions        |

### Metrics Ingestion

| Method | Path               | Description                          |
|--------|--------------------|--------------------------------------|
| POST   | `/cadvisor/batch`  | Ingest a batch of cAdvisor container metrics (Bearer token required) |

### Dashboard & LLM

| Method | Path                  | Description                            |
|--------|-----------------------|----------------------------------------|
| GET    | `/uploads`            | List uploaded files                    |
| POST   | `/uploads`            | Upload a file                          |
| GET    | `/jobs`               | List background jobs                   |
| POST   | `/llm/chat/stream`    | Stream an LLM response (SSE)          |

### Auth

| Method | Path            | Description               |
|--------|-----------------|---------------------------|
| GET    | `/auth/session`  | Get current session info  |

The full OpenAPI specification is available at `api/openapi.json`.

## Security

### Application Security

- **Content-Security-Policy** headers enforced via middleware (strict in production, relaxed for local dev)
- **X-Content-Type-Options**: `nosniff`
- **X-Frame-Options**: `DENY`
- **Referrer-Policy**: `strict-origin-when-cross-origin`

### Authentication Security

- WebAuthn/passkey credentials with non-extractable private keys
- Short-lived JWTs (15 min) signed per-device
- Server-side JWT verification with RBAC enforcement

### Ingestion Security

- cAdvisor metric batches require a Bearer token (`CADVISOR_METRICS_API_TOKEN`)
- Token validated server-side before any data is processed

## OpenAPI Type Generation

Frontend TypeScript types are kept in sync with the backend OpenAPI spec:

```bash
cd web
npm run gen
```

This regenerates `api/openapi.json` and `web/src/api/openapi.ts`.

## Development

### API

```bash
cd api
uv sync
uv run uvicorn app.main:app --reload
```

### Web

```bash
cd web
npm install
npm run dev
```

### Testing

```bash
cd web
npm run lint          # ESLint
npm run typecheck     # TypeScript type checking
npm run test          # Vitest unit tests
npm run test:watch    # Watch mode
npm run test:e2e      # Playwright E2E tests
```

### Environment

Copy `.env.example` to `.env` and configure:

| Variable | Default | Description |
|----------|---------|-------------|
| `H4CKATH0N_DATABASE_URL` | sqlite | Database connection string |
| `H4CKATH0N_REDIS_URL` | — | Redis URL for job queue |
| `H4CKATH0N_STORAGE_DIR` | `.h4ckath0n_storage` | File upload directory |
| `H4CKATH0N_EMAIL_BACKEND` | `file` | Email backend (`file` or `smtp`) |
| `H4CKATH0N_PASSWORD_AUTH_ENABLED` | `true` | Enable password authentication |
| `H4CKATH0N_DEMO_MODE` | `false` | Seed demo data on startup |
| `OPENAI_API_KEY` | — | OpenAI API key for LLM features |
| `CADVISOR_METRICS_API_TOKEN` | `my-secret-token` | Bearer token for cAdvisor ingestion |
| `VITE_API_BASE_URL` | `/api` | Frontend API base URL |

## Tech Stack

### Backend

| Component      | Technology           |
|----------------|----------------------|
| Language       | Python 3.14          |
| Framework      | FastAPI              |
| Scaffold       | [h4ckath0n](https://github.com/BTreeMap/h4ckath0n) |
| Validation     | Pydantic v2          |
| Package Manager| uv                   |

### Frontend

| Component      | Technology           |
|----------------|----------------------|
| Framework      | React 19             |
| Language       | TypeScript 5.9       |
| Bundler        | Vite 7               |
| Styling        | Tailwind CSS v4      |
| Graph Rendering| @xyflow/react        |
| Data Fetching  | TanStack React Query |
| Auth           | WebAuthn / Passkeys  |

### Infrastructure

| Component      | Technology           |
|----------------|----------------------|
| Containers     | Docker (multi-stage, multi-arch) |
| Orchestration  | Docker Compose       |
| Reverse Proxy  | nginx                |
| Job Queue      | Redis 8              |
| CI/CD          | GitHub Actions       |
| Registry       | GitHub Container Registry (ghcr.io) |

## License

MIT
