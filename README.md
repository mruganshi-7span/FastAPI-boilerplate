# FasTicket FastAPI Backend

FastAPI service providing Auth and Users CRUD, backed by PostgreSQL, Redis (arq jobs), and S3-compatible storage.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL
- Redis

## Setup

```bash
cp .env.example .env   # fill in DB, Redis, SMTP, S3 credentials
uv sync
uv run alembic upgrade head
```

## Run

```bash
uv run uvicorn app.main:app --reload
```

Run the background worker (needed for queued emails, e.g. password reset) in a separate process:

```bash
uv run arq app.worker.WorkerSettings
```

## Tests

```bash
uv run pytest
```
