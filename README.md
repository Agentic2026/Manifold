# manifold

Full-stack hackathon project scaffolded with [h4ckath0n](https://github.com/BTreeMap/h4ckath0n).

## Quick start

```bash
# Start both API and web servers
cd api
uv run h4ckath0n dev
```

API runs at http://localhost:8000, web at http://localhost:5173.

## Docker Compose

```bash
cp .env.example .env   # edit values as needed
docker compose up --build
```

Services:

| Service | Port | Description |
|---------|------|-------------|
| `api` | 8000 | FastAPI backend |
| `worker` | — | Background job processor |
| `redis` | 6379 | Job queue (optional) |
| `web` | 5173 | React frontend (nginx) |

## Structure

```
manifold/
  api/                Python (FastAPI + h4ckath0n library)
  web/                React + Vite + TypeScript + Tailwind v4
  docker-compose.yml  Multi-service setup
  Dockerfile          API image
  .env                Environment variables (gitignored)
```

## Features

### Auth

- Passkeys (WebAuthn) for registration and login
- Password auth (enabled by default via `H4CKATH0N_PASSWORD_AUTH_ENABLED`)
- Each device gets a P-256 keypair (private key non-extractable, stored in IndexedDB)
- API requests use short-lived JWTs (15 min) signed by the device key
- Server verifies JWT signature and enforces RBAC from the database

### File uploads

Upload files via `POST /uploads`. Files are stored in `H4CKATH0N_STORAGE_DIR` (default `.h4ckath0n_storage/`). Text files automatically create extraction jobs.

### Background jobs

The worker process polls for jobs and runs them. Start with:

```bash
uv run python -m h4ckath0n jobs worker
```

Or use `docker compose up worker`.

### AI streaming

`POST /llm/chat/stream` streams LLM responses as SSE. Set `OPENAI_API_KEY` in `.env`. The dashboard includes an interactive AI chat panel.

### Email

Set `H4CKATH0N_EMAIL_BACKEND=file` (default) to write emails to `H4CKATH0N_EMAIL_OUTBOX_DIR`. Switch to `smtp` for production.

### Demo mode

Set `H4CKATH0N_DEMO_MODE=true` to seed demo data on startup.

## OpenAPI types

The template keeps OpenAPI and frontend types in sync.

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

### Environment

Copy `.env.example` to `.env` and set values. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `H4CKATH0N_DATABASE_URL` | sqlite | DB connection string |
| `H4CKATH0N_REDIS_URL` | — | Redis for job queue |
| `H4CKATH0N_STORAGE_DIR` | `.h4ckath0n_storage` | File upload directory |
| `H4CKATH0N_EMAIL_BACKEND` | `file` | `file` or `smtp` |
| `H4CKATH0N_PASSWORD_AUTH_ENABLED` | `true` | Enable password auth |
| `H4CKATH0N_DEMO_MODE` | `false` | Seed demo data |
| `OPENAI_API_KEY` | — | For AI features |

## License

MIT
