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

## Docker

Runs the API, the arq worker, PostgreSQL, Redis and Mailpit (catches outgoing email):

```bash
cp .env.example .env   # set JWT_SECRET_KEY (and S3 credentials if needed)
docker compose up --build
```

| Service  | Host port | URL / connection                                   |
|----------|-----------|----------------------------------------------------|
| API      | 8000      | http://localhost:8000 (Swagger at `/docs`)         |
| Postgres | 5432      | `postgresql://postgres:postgres@localhost:5432/fasticket_fastapi` |
| Redis    | 6379      | `redis://localhost:6379/0`                         |
| Mailpit  | 8025      | http://localhost:8025                              |

Migrations run automatically (`migrate` service) before the API and worker start.

Stop with `docker compose down` (add `-v` to also delete the database and Redis data).

Inside the containers, `DATABASE_URL`, `REDIS_URL` and the SMTP settings are pointed at the Compose services, so the values in `.env` for those are only used when running locally without Docker. The Postgres container uses `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` from `.env`.

Code changes need a rebuild (`docker compose up --build`). Create new migrations locally with `uv run alembic revision --autogenerate -m "..."`; they are applied on the next start.

## Tests

```bash
uv run pytest
```
