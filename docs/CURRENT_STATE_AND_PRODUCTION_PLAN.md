# Manifold: Current State Assessment and Production-Readiness Plan

_Last updated: 2026-03-14_

This document is a practical readiness assessment of the **current repository state** and a roadmap to reach a production-grade platform.

## 1) Executive Summary

Manifold has a strong prototype foundation:
- A running FastAPI backend with telemetry ingestion and AEGIS-style endpoints.
- A modern React + TypeScript frontend with unit tests.
- Passing backend and frontend unit tests in local CI-like execution.

However, the codebase is **not production-ready yet**. Key blockers include:
- Minimal backend runtime configuration and secret management.
- Prototype/demo endpoints and seeding flows mixed with production routes.
- No explicit migration system, SLOs, or observability standards documented.
- Frontend lint currently failing on one React hook anti-pattern.
- Missing explicit release, rollback, and operational runbooks.

## 2) Current State (Grounded in the Repository)

### Backend state
- Backend uses FastAPI via `h4ckath0n.create_app()` and includes CSP middleware plus routers.
- Healthcheck and demo endpoints (`/demo/ping`, `/demo/echo`, `/demo/ws`, `/demo/sse`) are active in the same app surface.
- Telemetry ingestion endpoint (`POST /cadvisor/batch`) validates bearer token and writes to PostgreSQL using bulk inserts/upserts.
- **Runtime topology auto-discovery** from live container metadata is implemented — topology nodes are created automatically from ingested cAdvisor data using `com.docker.compose.service` and `com.docker.compose.project` labels.
- Configuration currently exposes a very small `Settings` surface (database URL + cAdvisor token).
- ORM models and services support machine/container/snapshot ingest, runtime discovery, and basic topology/vulnerability/insight access.

### Frontend state
- React/Vite/TypeScript stack is in place with component and page tests.
- API client scaffolding and auth modules exist.
- System Map shows live/empty/offline state indicators and refreshes automatically.
- Security score uses backend `/api/security-score` as the source of truth.
- All lint, typecheck, and unit tests pass.

### Tests/checks state
- `api`: pytest suite passes (18 tests including runtime discovery).
- `web`: vitest suite passes (37 tests), typecheck passes, eslint passes.

### Onboarding model
- **Primary flow:** User adds Manifold monitoring service to their existing Docker Compose stack → cAdvisor pushes telemetry → Manifold auto-discovers topology.
- **Optional flow:** Manual Docker Compose import (`POST /api/topology/import`) for enrichment/preview.

## 3) Production-Readiness Gap Analysis

### A. Architecture & Service Boundaries
**Observed:** Demo and production behaviors are coupled in one app.

**Gaps:**
- No environment-gated feature separation for demo routes and seed endpoints.
- No clear bounded contexts between ingestion, analysis, and control-plane actions.

**Target state:**
- Explicit app modules: `core_api`, `ingestion_api`, `analysis_api`, `demo_api` (disabled by default in production).

### B. Configuration, Secrets, and Environment Strategy
**Observed:** `Settings` only contains two environment variables.

**Gaps:**
- No standardized settings for auth, CORS origins, logging levels, rate limits, DB pool sizing, LLM/provider selection, Redis, storage, etc.
- No secret source strategy (vault/KMS/secrets manager).

**Target state:**
- Typed, validated settings with environment profiles (`local`, `staging`, `prod`) and secret-backed deployment.

### C. Data Layer and Migrations
**Observed:** Table creation happens in endpoint-level seed flow; no visible migration toolchain in repo docs.

**Gaps:**
- No Alembic migration lifecycle documented/enforced.
- No schema drift policy or backward-compatible migration rules.

**Target state:**
- Alembic migrations with CI checks for migration consistency and rollback safety.

### D. API Security and Zero-Trust Controls
**Observed:** Ingestion token auth exists; auth extensions and JWT flows exist.

**Gaps:**
- Missing documented threat model and token rotation policy.
- No explicit tenant isolation and per-endpoint authorization matrix.
- No formal API rate limiting and abuse controls documented.

**Target state:**
- Endpoint-by-endpoint authZ policy, key rotation SLAs, mandatory audit trails, and WAF/rate limits.

### E. Reliability, Scaling, and Performance
**Observed:** Bulk insert ingestion implementation is a good base.

**Gaps:**
- No declared SLOs/SLIs for ingest latency, query p95, API error rate.
- No queue/backpressure strategy documented for burst telemetry loads.
- No capacity planning or load test baselines.

**Target state:**
- Defined SLOs, autoscaling policy, and repeatable load test thresholds.

### F. Observability and Operations
**Observed:** Basic health endpoint exists.

**Gaps:**
- No standardized structured logging, tracing, metrics export, alerting docs.
- No on-call/runbook/incident management process.

**Target state:**
- OpenTelemetry-based traces/metrics, dashboard + alerts, incident playbooks.

### G. Frontend Production Hardening
**Observed:** Tests pass; lint passes.

**Gaps:**
- No explicit web performance budgets, error tracking, or accessibility budget.

**Target state:**
- Green quality gates, RUM + error telemetry, accessibility and bundle-size budgets.

### H. Delivery, Environments, and Governance
**Observed:** Docker + compose exists.

**Gaps:**
- No documented progressive delivery strategy (canary/blue-green).
- No signed artifacts / SBOM / supply-chain scanning workflow documented.
- No formal release checklist and rollback process.

**Target state:**
- CI/CD with security scans, artifact provenance, release gates, rollback automation.

## 4) Production Plan (Phased, Comprehensive)

## Phase 0 — Stabilize Baseline (Week 1)
1. Fix frontend lint error and enforce lint as mandatory gate.
2. Add a concise architecture decision record (ADR) index.
3. Split demo routes behind an explicit `ENABLE_DEMO_ROUTES` setting.
4. Freeze API contract versioning approach (OpenAPI + generated client policy).

**Exit criteria:** backend tests pass, frontend lint/type/test/build all pass, no demo endpoints exposed in prod profile.

## Phase 1 — Secure Foundations (Weeks 2–3)
1. Expand `Settings` to include all runtime/security/ops knobs.
2. Add secret handling policy (env for local, secret manager for staging/prod).
3. Document and enforce authN/authZ matrix per route.
4. Introduce rate limiting and request size guards on sensitive routes.
5. Add audit logging schema for security-sensitive actions.

**Exit criteria:** security review complete, config matrix documented, auth coverage tests added.

## Phase 2 — Data & Platform Reliability (Weeks 3–5)
1. Introduce Alembic migrations and migration CI checks.
2. Add ingestion load tests and p95/p99 latency tracking.
3. Implement DB index review + retention/partition strategy for telemetry tables.
4. Add idempotency/duplicate prevention strategy for telemetry snapshots.

**Exit criteria:** migrations required for schema changes, load benchmark baseline recorded, retention policy enabled.

## Phase 3 — Observability & Incident Readiness (Weeks 5–6)
1. Implement structured JSON logs with request correlation IDs.
2. Add OpenTelemetry traces + metrics for API/DB/LLM/tool calls.
3. Stand up dashboards and alerts aligned to SLOs.
4. Write runbooks: ingest degradation, DB saturation, auth outage, LLM provider failure.

**Exit criteria:** synthetic checks and alerts active in staging; runbooks tested in a game day.

## Phase 4 — Delivery & Compliance Hardening (Weeks 6–8)
1. Add CI/CD promotion flow: dev → staging → production with approval gates.
2. Add SAST, dependency scanning, container scanning, SBOM generation.
3. Add artifact signing/provenance and rollback automation.
4. Run pre-production chaos and fault-injection drills.

**Exit criteria:** signed deploy artifacts, green security scans, rehearsed rollback under SLA.

## Phase 5 — Production Launch Readiness (Weeks 8+)
1. Final launch review against checklist (below).
2. Execute staged rollout (internal → pilot tenants → GA).
3. Hold post-launch reliability and security retrospective.

**Exit criteria:** 2–4 weeks stable operation with SLO compliance.

## 5) Production Readiness Checklist (Go/No-Go)

### Security
- [ ] Threat model reviewed and approved.
- [ ] Secrets centrally managed and rotated.
- [ ] Endpoint authZ matrix tested.
- [ ] Audit logging enabled for privileged actions.

### Reliability
- [ ] SLOs and error budgets defined.
- [ ] Load tests at expected peak + surge.
- [ ] Runbooks exist for top incident classes.
- [ ] On-call ownership defined.

### Data
- [ ] Alembic migration workflow enforced.
- [ ] Backup + restore drill passed.
- [ ] Retention and PII policies implemented.

### Delivery
- [ ] CI gates green (lint/type/tests/build/security scans).
- [ ] Staging parity validated.
- [ ] Rollback tested.

### Product/UX
- [ ] Accessibility checks passed.
- [ ] Error boundaries and telemetry verified.
- [ ] Documentation up to date for operators and developers.

## 6) Suggested Ownership Model
- **Platform/Infra:** CI/CD, environments, observability, rollout safety.
- **Backend:** ingestion reliability, schema/migrations, authN/authZ enforcement.
- **Frontend:** UX reliability, accessibility, quality gates.
- **Security:** threat modeling, controls validation, incident readiness.
- **Product/Eng:** launch criteria and prioritization governance.

## 7) Immediate Next 10 Actions
1. Fix `SecurityGauge` lint violation and re-run `npm run check`.
2. Add expanded `Settings` with explicit defaults and required secrets.
3. Add `ENABLE_DEMO_ROUTES` and `ENABLE_SEED_ENDPOINTS` flags.
4. Add Alembic and initial migration from current schema.
5. Add route-level auth tests for all privileged endpoints.
6. Add rate limiting to ingest + chat endpoints.
7. Add structured logging middleware with request IDs.
8. Add OpenTelemetry instrumentation for FastAPI + SQLAlchemy.
9. Define SLOs and create baseline dashboards/alerts.
10. Create release checklist + rollback runbook in `/docs/operations`.

---

Use this file as the canonical roadmap for production hardening and keep it updated every sprint.
