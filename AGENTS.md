# Manifold - AI Agent Instructions

This document provides context for future AI agents interacting with the Manifold codebase.

## Architecture
Manifold is a continuous cybersecurity monitoring platform.
- **Backend (`/api`)**: Python, FastAPI, SQLAlchemy 2.0 (PostgreSQL via asyncpg), LangGraph.
- **Frontend (`/web`)**: TypeScript, React (Vite).

## Current Project Maturity
- The repository is in a **prototype-to-production hardening** stage.
- Before proposing major implementation work, review `docs/CURRENT_STATE_AND_PRODUCTION_PLAN.md`.
- Prefer incremental, test-backed changes aligned with that plan.

## Toolchain & Dependencies

### Backend
- **Package Management**: `uv`. All core dependencies are strictly defined in `api/pyproject.toml`.
- **Configuration**: Handled by `pydantic-settings`. All environment variables are unified under `api/app/core/config.py` in the `Settings` class. When modifying or adding new env vars, add them to `Settings`.
- **Testing**: `pytest` and `pytest-asyncio`. Tests reside in `api/tests`.
- **Run/Dev**: `uv run h4ckath0n run`

### Frontend
- **Package Management**: `npm` (lockfile is `package-lock.json`).
- **Build & Dev**: `vite`.
- **Unit Tests**: `vitest`.
- **E2E Tests**: `playwright` (setup in `web/playwright.config.ts`).

## Developer Guidelines
- **Telemetry Ingestion**: The backend ingests batched cAdvisor telemetry payloads via `POST /cadvisor/batch`. The router requires a `CADVISOR_METRICS_API_TOKEN` bearer token defined in the backend settings.
- **Database Modularity**: `SQLAlchemy` queries heavily lean into PostgreSQL-specific `JSONB` fields (`cpu_stats`, `memory_stats`) and `TIMESTAMP WITH TIME ZONE`. Use bulk inserts (`insert().values().on_conflict_...`) instead of the traditional ORM session approach for high-throughput metrics.
- **LangGraph Integration**: Time-series aggregations should be performed in PostgreSQL using CTEs or Window Functions (see `api/app/agents/tools/telemetry.py`) instead of passing raw row data to the LLM.

## Documentation & Planning Expectations
- Keep README status information and production-readiness docs in sync with code reality.
- If you discover a notable readiness gap (security, reliability, observability, delivery), record it in `docs/CURRENT_STATE_AND_PRODUCTION_PLAN.md`.
- Prefer adding concrete checklists and phased plans over vague TODO notes.
