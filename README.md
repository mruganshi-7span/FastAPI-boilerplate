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

## Login with Google

Google login uses [Authlib](https://docs.authlib.org/en/stable/) as an OpenID Connect client. Google only proves who the user is; the API still issues its own access and refresh tokens, so `/auth/refresh`, `/auth/logout` and protected routes work the same as for password login.

### Google Cloud setup

1. In [Google Cloud Console](https://console.cloud.google.com/apis/credentials), configure the OAuth consent screen, then create an **OAuth client ID** of type **Web application**.
2. Under **Authorized redirect URIs**, add the API callback exactly as it appears in `GOOGLE_REDIRECT_URI`, e.g. `http://localhost:8000/api/v1/auth/google/callback` locally.
3. Put the client ID and secret in `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, and set `SESSION_SECRET_KEY` to a long random value.

### Flow and frontend contract

1. The frontend sends the browser (a full page navigation, not `fetch`) to `GET /api/v1/auth/google/login`.
2. After the user consents, Google redirects to the API callback, which finds or creates the user:
   - an existing Google link is reused;
   - otherwise, if Google reports the email as verified, it is linked to the existing user with that email;
   - otherwise a new user without a password is created.
3. The API redirects to `{FRONTEND_URL}/auth/callback` with one of:
   - `?code=<one-time code>`: POST `{"code": "<code>"}` to `/api/v1/auth/social/exchange` within `SOCIAL_LOGIN_CODE_EXPIRE_SECONDS` (default 60). The response is the same as `/auth/login`: `{access_token, refresh_token, token_type, expires_in}`. A code works only once.
   - `?error=<message key>`: login failed, e.g. `auth.social_login_failed`, `auth.social_email_unverified`, `auth.account_deactivated` or `auth.account_unavailable`.

Users created through Google have no password, so `/auth/login` rejects them with the normal invalid-credentials error. They can set a password with the forgot-password flow.

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
