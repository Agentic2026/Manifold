# Manifold: Current State Assessment and Production-Readiness Plan

_Last updated: 2026-03-15_

This document is a practical readiness assessment of the **current repository state** and a roadmap to reach a production-grade platform.

## 1) Executive Summary

Manifold has a strong prototype foundation with recent hardening:
- A running FastAPI backend with telemetry ingestion, runtime topology discovery, and AEGIS-style endpoints.
- A modern React + TypeScript frontend with unit, lint, typecheck, and E2E tests all passing.
- Docker packaging uses pre-built GHCR images and a single-port Caddy reverse proxy.
- A real release workflow (multi-arch, SBOM, Trivy scanning) is in place.

The codebase is in **active transition toward production**. Key remaining work:
- Alembic migration lifecycle.
- Expanded secret management and environment profiles.
- Observability (structured logging, OpenTelemetry).
- Progressive delivery strategy.

## 2) Current State (Grounded in the Repository)

### Backend state
- Backend uses FastAPI via `h4ckath0n.create_app()` with CSP middleware plus routers.
- Healthcheck and demo endpoints (`/demo/ping`, `/demo/echo`, `/demo/ws`, `/demo/sse`) are active (demo/prototype, not production-hardened).
- Telemetry ingestion endpoint (`POST /cadvisor/batch`) validates bearer token and writes to PostgreSQL using bulk inserts/upserts.
- **Runtime topology auto-discovery** from live container metadata is the primary mode — topology nodes are created automatically from ingested cAdvisor data using `com.docker.compose.service` and `com.docker.compose.project` labels.
- **Topology node IDs are project-scoped** (`<project>__<service>`) to prevent collisions across different Compose stacks.
- **Import is non-destructive** — `POST /topology/import` merges/enriches existing topology (upsert) rather than replacing it. An optional `project_name` parameter scopes imported nodes to align with runtime-discovered containers.
- **Inferred edges are labeled honestly** — edges from runtime discovery are marked as `kind: "inferred"` with evidence labels (e.g., "inferred: same project (myapp)", "inferred: shared network (frontend)").
- **Isolate and revoke endpoints are honestly simulated** — they persist node status changes but do not perform real network isolation or credential revocation. Responses include `"simulated": true`.

### Frontend state
- React/Vite/TypeScript stack with component and page tests.
- API client uses `/api` base URL for all requests (proxied through Caddy in production, Vite dev server in development).
- System Map shows live/empty/offline state indicators and refreshes automatically.
- All lint, typecheck, and unit tests pass.

### Packaging state
- **Single-port deployment**: Only the Caddy web container exposes port 8080.
- **Image-based compose**: `docker-compose.yml` uses GHCR images by default (`ghcr.io/agentic2026/manifold`, `ghcr.io/agentic2026/manifold-web`).
- **Caddy reverse proxy**: Replaces nginx. Handles `/api/*` → backend, serves SPA, supports WebSocket and SSE.
- **Multi-stage Dockerfiles**: `api/Dockerfile` (builder/runtime stages, non-root user), `web/Dockerfile` (Caddy-based).
- **Release workflow**: Multi-arch builds, OCI labels, SBOM, provenance, Trivy scanning.

### Tests/checks state
- `api`: pytest suite passes (19 tests including runtime discovery, project-scoped IDs, import coexistence).
- `web`: vitest suite passes (37 tests), typecheck passes, eslint passes.
- `e2e`: Playwright suite passes (17 tests).

### Onboarding model
- **Primary flow:** Operator adds cAdvisor overlay to their Compose stack → cAdvisor pushes telemetry through `http://<manifold>:8080/api/cadvisor/batch` → Manifold auto-discovers topology.
- **Optional flow:** Manual Compose import (`POST /api/topology/import`) for enrichment/preview. Non-destructive merge.

## 3) Production-Readiness Gap Analysis

### A. Architecture & Service Boundaries
**Status:** Demo and production behaviors are coupled in one app.

**Remaining gaps:**
- No environment-gated feature separation for demo routes and seed endpoints.
- Isolate/revoke actions are simulated, not connected to real container runtime.

**Target state:**
- Explicit app modules with environment gating.
- Real container isolation via Docker API integration (future).

### B. Configuration, Secrets, and Environment Strategy
**Status:** `Settings` contains core environment variables. `.env.example` documents all variables.

**Remaining gaps:**
- No secret source strategy (vault/KMS/secrets manager) for production.
- No environment profiles (`local`, `staging`, `prod`).

### C. Data Layer and Migrations
**Status:** Table creation on startup; no Alembic migration lifecycle.

**Remaining gaps:**
- No schema drift policy or backward-compatible migration rules.

### D. API Security
**Status:** Ingestion token auth exists; WebAuthn auth exists.

**Remaining gaps:**
- No rate limiting on sensitive endpoints.
- No formal threat model documentation.

### E. Observability
**Status:** Basic health endpoint.

**Remaining gaps:**
- No structured logging, tracing, or metrics export.
- No dashboards or alerting.

### F. Delivery & Supply Chain
**Status:** Release workflow with SBOM, provenance, and Trivy scanning is in place.

**Completed:**
- [x] Multi-arch Docker image builds.
- [x] GHCR image publishing.
- [x] Trivy vulnerability scanning.
- [x] SBOM and provenance generation.
- [x] Release process documentation.

**Remaining gaps:**
- No signed artifacts (cosign).
- No progressive delivery (canary/blue-green).

## 4) Production Plan (Phased)

## Phase 0 — Stabilize Baseline ✅ (Completed)
1. ~~Fix frontend lint error and enforce lint as mandatory gate.~~ All quality gates pass.
2. ~~Runtime topology auto-discovery implemented.~~ Project-scoped IDs prevent collisions.
3. ~~Import is non-destructive.~~ Merges with runtime topology.
4. ~~Single-port Caddy deployment.~~ Image-based compose with GHCR defaults.

## Phase 1 — Secure Foundations (Next)
1. Expand `Settings` to include all runtime/security/ops knobs.
2. Add secret handling policy for staging/production.
3. Add rate limiting on sensitive endpoints.
4. Split demo routes behind `ENABLE_DEMO_ROUTES` setting.

## Phase 2 — Data & Platform Reliability
1. Introduce Alembic migrations and migration CI checks.
2. Add ingestion load tests and p95/p99 latency tracking.
3. Implement retention/partition strategy for telemetry tables.

## Phase 3 — Observability & Incident Readiness
1. Structured JSON logs with request correlation IDs.
2. OpenTelemetry traces + metrics.
3. Dashboards and alerts.

## Phase 4 — Delivery & Compliance Hardening
1. Artifact signing (cosign).
2. Progressive delivery strategy.
3. Chaos/fault-injection testing.

## 5) Immediate Next Actions
1. Add expanded `Settings` with explicit defaults and required secrets.
2. Add `ENABLE_DEMO_ROUTES` and `ENABLE_SEED_ENDPOINTS` flags.
3. Add Alembic and initial migration from current schema.
4. Add route-level auth tests for all privileged endpoints.
5. Add rate limiting to ingest + chat endpoints.
6. Add structured logging middleware with request IDs.
7. Add OpenTelemetry instrumentation for FastAPI + SQLAlchemy.
8. Implement real container isolation via Docker API (replace simulated isolate).
9. Add artifact signing to release workflow.
10. Create operational runbooks in `/docs/operations`.

---

Use this file as the canonical roadmap for production hardening and keep it updated every sprint.
