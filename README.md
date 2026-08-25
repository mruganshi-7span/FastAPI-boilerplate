# FastAPI Backend

A FastAPI service providing Auth and Users CRUD, using the standard FastAPI project layout (not a Laravel
folder-for-folder mirror). Managed with [uv](https://docs.astral.sh/uv/). Built for developers coming from a
Laravel background — the docs below call out the Laravel equivalent of each design decision.

## Structure

```
app/
├── main.py                # application factory, creates the FastAPI() instance
├── worker.py               # arq worker entry point (background jobs)
├── core/
│   ├── config.py          # settings (like .env + config/*.php combined)
│   ├── security.py        # JWT + password hashing + opaque-token helpers
│   ├── exceptions.py      # typed exceptions (carry a translation key) + JSON handlers
│   ├── localization.py    # LocaleMiddleware + translate() — see below
│   ├── templates.py       # Jinja2 renderer for email templates
│   └── queue.py           # lazy arq/Redis connection pool
├── lang/
│   ├── en/message.py       # MESSAGES dict — the source-of-truth English strings
│   └── ar/message.py       # same keys, Arabic strings
├── db/
│   ├── base.py             # declarative Base + SoftDeleteMixin + Queryable + QB (see below)
│   ├── pagination.py       # generic paginate() helper (see below)
│   └── session.py          # engine + session setup
├── models/                 # SQLAlchemy models (Eloquent equivalent)
│   ├── user.py, category.py, refresh_token.py, password_reset_token.py
│   └── media.py, mediable.py  # generic polymorphic file attachment (see below)
├── schemas/                 # Pydantic models — Form Request + API Resource combined
│   └── common.py            # PaginatedResponse[T] — shared list-response envelope
├── services/                 # business logic, queries the DB directly (no repository layer)
│   ├── auth_service.py
│   ├── user_service.py
│   ├── category_service.py
│   ├── email_service.py    # renders + sends email via SMTP (aiosmtplib)
│   └── storage_service.py  # S3 signed URLs (upload/download), via boto3
├── templates/emails/        # Jinja2 email views (password_reset.html / .txt)
└── api/
    ├── deps.py             # shared Depends() functions — get_db, get_current_user, get_qb
    └── routes/
        ├── auth.py         # routes + endpoint logic combined
        ├── users.py         # create/update accept an embedded `profile` descriptor — see below
        ├── categories.py    # same CRUD + filter/sort/include/pagination shape as users
        └── media.py         # POST /media/upload-url only — no separate confirm endpoint
alembic/                    # migrations (like database/migrations)
```

For a developer coming from Laravel: `schemas/` does double duty, the same Pydantic model validates an
incoming payload (Form Request) and can shape an outgoing response (API Resource). There's no separate
repository/CRUD layer — `services/` queries the database directly via SQLAlchemy's `Session`, which is
closer to how an Eloquent model queries itself than a repository class would be.

Auth uses stateless JWT access tokens plus DB-backed, rotating refresh tokens (similar in spirit to Laravel
Passport's token model) — see the `_issue_tokens` / `_resolve_refresh_token` helpers in
`app/services/auth_service.py`.

`Category` (`belongs to` a `User`, a `User` `has many` `Category`) is the second resource, built the same
way as `User` — model, schema, service, router, nothing shared by inheritance beyond the mixins described
below. It exists mainly to prove the generic pieces (`Queryable`, `paginate()`) actually generalize instead
of being `User`-specific in disguise.

### Password reset — queued email, the Laravel-job equivalent

`POST /auth/forgot-password` never sends email inline — it stores a hashed, single-use reset token and
enqueues a `send_password_reset_email` job onto Redis via [arq](https://arq-docs.helpmanual.io/), then
returns immediately. This is the same shape as a Laravel `ShouldQueue` Mailable dispatched onto
`queue:work` — the API process never blocks on SMTP, and a separate worker process does the actual sending:

```bash
uv run arq app.worker.WorkerSettings
```

Run this alongside `uvicorn` (two processes, same as running `php artisan queue:work` next to
`php artisan serve`). Both need `REDIS_URL` pointing at the same Redis instance. The email itself is
rendered from `app/templates/emails/password_reset.{html,txt}` via Jinja2 and sent over real SMTP
(`aiosmtplib`) using the `SMTP_*` settings — fill those in with a real provider (Mailtrap, SES, Postmark,
Mailgun's SMTP relay) before this will actually deliver. Mailgun specifically: use its SMTP credentials,
not your API key — they're different secrets, and Mailgun's `535 Authentication failed` gives no hint
which one you used by mistake.

The Redis connection itself is resolved lazily, inside `auth_service.request_password_reset`, *after*
every validation check has already passed — not as a route-level `Depends()`. FastAPI resolves route
dependencies before the handler body runs, so an eager `redis: ArqRedis = Depends(get_redis)` parameter
would attempt a Redis connection before the email-exists check below ever got a chance to run; a Redis
outage would then surface as a misleading 500 that masked whether validation happened at all.

`POST /auth/reset-password` verifies the email exists, verifies the token (id:secret, SHA-256 hashed,
checked in constant time — the same pattern refresh tokens use) belongs to *that* email's account, sets
the new password, marks the token used, and revokes every active refresh token for that user — a password
reset signs the account out everywhere.

Both endpoints validate the email up front and return a `422` with `errors.email: ["email.not_found"]`
when it isn't registered — the same shape as Laravel's stock `Password::sendResetLink`/`Password::reset()`,
which raise a `passwords.user` validation error in exactly this case. This is a deliberate UX-over-
anti-enumeration tradeoff: it does let a caller probe which emails are registered, but it matches Laravel's
actual behavior and gives a clear "no account with that email" message instead of a generic non-answer.

### Scheduled jobs — the Laravel `Schedule` facade equivalent

Laravel drives its scheduler off one crontab line (`* * * * * php artisan schedule:run`) and defines the
actual recurring tasks in code. `arq` can do the same thing without a second scheduling tool: `cron_jobs` on
`WorkerSettings` (`app/worker.py`) are recurring jobs the worker process times and runs itself — the worker
staying up *is* the "one cron entry," same role as `schedule:run`.

```python
class WorkerSettings:
    functions = [send_password_reset_email]
    cron_jobs = [
        cron(cleanup_expired_tokens, hour=3, minute=0),   # daily at 03:00
    ]
```

First job: `cleanup_expired_tokens` (`app/services/token_cleanup_service.py`) deletes `refresh_tokens` and
`password_reset_tokens` rows that are expired *or* already consumed (revoked/used) — those are dead the
moment auth_service's own checks reject them, no reason to wait for the natural expiry to remove them.
Nothing else in the app deletes these rows otherwise, so without this they'd accumulate forever.

To add another scheduled job: write the logic as a plain function taking a `db: Session` (or nothing, if it
doesn't touch the DB) in `app/services/`, wrap it in a `async def foo(ctx): ...` in `app/worker.py` the same
way `cleanup_expired_tokens` wraps `token_cleanup_service.cleanup_expired_tokens`, and add
`cron(foo, ...)` to `cron_jobs` — `hour=`/`minute=`/`weekday=`/`day=`/`month=` compose like crontab fields,
and omitting one means "every" value for it, same semantics as a `*`.

Cron jobs only run while `uv run arq app.worker.WorkerSettings` is running — same failure mode as Laravel's
scheduler needing its crontab entry to be live.

### File uploads — signed S3 URL, then embed the descriptor in the update

This follows a common Laravel pattern (e.g. `plank/laravel-mediable`'s `generate-signed-url` + embed-on-save
flow): signing a URL never persists anything, and the actual resource's own create/update call is what
confirms the upload and attaches it — there's no separate "confirm" or "attach" endpoint to call in between.

1. `POST /media/upload-url` `{content_type, tag}` → `{upload_url, key, expires_in}`. `content_type` is
   restricted to `image/jpeg`, `image/png`, `image/webp`, `image/gif`, `application/pdf`. `tag` picks which
   folder the key is generated under — `media_service._TAG_DIRECTORIES` is a tag → directory map, the same
   shape as a Laravel media-library config (`"profile"` → `users/profiles`), so a key for tag `"profile"`
   comes back as `users/profiles/<uuid>.png`. Add an entry to that dict for any future attachable resource.
   Nothing is written to the database at this step — it's pure signing, via
   `storage_service.generate_presigned_upload_url`.
2. The client `PUT`s the raw file bytes to `upload_url` directly — the file never passes through this API.
   Send the **same** `Content-Type` header used in step 1; the presigned URL's signature is bound to it, so
   a mismatched header fails with a 403 from S3, not from this API.
3. `POST /users` or `PUT /users/{id}` with `{"profile": {"key": "<the key from step 1>"}, ...other fields}`.
   The server checks the key sits under one of the known tag directories, then calls S3 `HeadObject` to
   confirm the file actually exists — trusting nothing the client claims about size or type, unlike some
   Laravel media libraries, which take `size`/`mime_type` from the client — and creates the `media` row
   and its `mediables` attachment (tagged `"profile"`) in that same request. Send `"profile": null` to remove
   the current one; omit the field entirely to leave it untouched.

`user_service._set_profile` is what does this: it calls `media_service.confirm_upload` (the same S3
verification logic that used to live behind its own `POST /media` route) and `mediable_service.create_mediable`
(the same sync-replace-on-conflict logic that used to live behind `POST /mediables`) back to back, inside
`create_user`/`update_user`. Both of those service functions are still exactly as generic and reusable as
before — `mediable_service.py` still checks `mediable_type` against a small registry (`"user"` → `User`
today; add an entry and a tag for any future attachable resource) — they're just no longer exposed as
separate HTTP endpoints for this flow.

Note there's no per-uploader ownership check on `confirm_upload` — any authenticated caller's key works for
any target user, which is what lets an admin create a new user and attach a profile picture they uploaded
themselves in the same call. The only gate is that the key must sit under one of the configured tag
directories.

`storage_service.py` supports two buckets (`AWS_BUCKET` for public objects, `AWS_BUCKET_PRIVATE` for
private ones — every function takes a `private: bool = False` to pick between them, mirroring Laravel's
public/private disk split) and an `AWS_ROOT` prefix applied to every key via `_full_key()` (Laravel's disk
`root` config equivalent) — set `AWS_ROOT=dev` and every object lands under `dev/...` regardless of tag.

`User.profile` (`app/models/user.py`) is a real, read-only SQLAlchemy `relationship` — a polymorphic
`secondary` join through `mediables`, filtered to `mediable_type="user"` and `tag="profile"` — the SQLAlchemy
equivalent of Eloquent's `morphToMany(...)->wherePivot('tag', 'profile')`. `UserRead.profile` is a nested
`Media` object (not a flat URL string), built from that relationship in `user_service.to_user_read`, with a
freshly-generated presigned download URL on every response — nothing about the URL is stored.

### Localization — every custom message, driven by a `locale` header

Every message this API writes itself — exception messages, validation errors, route success
messages, the password-reset email — goes through one `translate(key, locale)` function
(`app/core/localization.py`), using a custom `locale` header (not the standard `Accept-Language`)
to match how some Laravel APIs handle this. Send `locale: ar` on any request to any endpoint to get
every custom message back in Arabic; `en` is the default and anything unsupported falls back to it.

```
POST /api/v1/auth/login
locale: ar
{"email": "wrong@example.com", "password": "x"}

→ {"message": "بيانات الاعتماد هذه غير مطابقة لسجلاتنا."}
```

**Catalogs are plain Python dicts**, not gettext `.po`/`.mo` files — `app/lang/en/message.py` and
`app/lang/ar/message.py`, each a flat `MESSAGES: dict[str, str]` keyed by the same dotted names
(`"auth.invalid_credentials"`, `"email.already_taken"`, …). Adding a locale means adding a new
`app/lang/{locale}/message.py` with the same keys — no compile step, no binary files, just read and
edit the file.

**Translation is deferred to the point a `request` actually exists**, not done eagerly wherever a
message originates:

- `AppException` and its subclasses (`NotFoundException`, `UnauthorizedException`,
  `ValidationException`) carry a translation **key**, not translated text — services raise
  `UnauthorizedException("auth.invalid_credentials")` with no idea what locale is active.
  `register_exception_handlers`' `app_exception_handler` is the only place that calls
  `translate()`, using `request` (which it already receives) to resolve the locale. This sidesteps
  needing any request-scoped global/context-var machinery — the one thing every exception handler
  and every route already has is `request`.
- Route functions building a direct success message (`{"message": "..."}` for logout, forgot-password,
  reset-password) take `request: Request` and call `translate(key, locale=request_locale(request))`
  the same way.
- `ValidationException.errors` field messages can be a plain key (`"email.already_taken"`) or a
  `(key, params)` tuple when the message needs interpolation — e.g.
  `("mediable.target_not_found", {"type": "user"})` renders `"No {type} was found with this id."`
  as `"No user was found with this id."` (or the Arabic equivalent).

**`LocaleMiddleware`** (`app/core/localization.py`) reads the `locale` header, checks it against
the directory names under `app/lang/` (so an unsupported code like `fr` — no `app/lang/fr/` —
silently falls back to English rather than erroring), and sets `request.state.locale`. That's a
plain dict entry on the ASGI `scope` object shared by reference across the *entire* call chain —
which matters because it's what makes the trickiest case work correctly: an unhandled exception is
caught by `ServerErrorMiddleware`, the *outermost* layer, sitting outside `LocaleMiddleware`
entirely — yet `request.state.locale` is still visible there, since it was never contextvar/task-
scoped in the first place.

**The one channel that can't use `request` at all: the password-reset email.** It's rendered by the
`arq` worker, a separate process with no HTTP request of its own. The locale is captured once, at
the moment `POST /auth/forgot-password` is handled, and threaded explicitly through the job payload
— `auth_service.request_password_reset(..., locale)` → `redis.enqueue_job(..., locale=locale)` →
the worker's job function → `email_service.send_password_reset_email(..., locale=locale)` — which
also sets `dir="rtl"` on the HTML template when `locale == "ar"`.

**What's deliberately not localized**: Pydantic's own field-validation messages (`"field required"`,
`"value is not a valid email address"`) come from `pydantic-core` in a fixed language. Translating
those needs a much larger mapping keyed to Pydantic's internal error `type` codes — a real project,
not something bundled into this pass. Only the top-level `"The given data was invalid."` wrapper
around them is localized today.

### Soft deletes — a reusable `SoftDeleteMixin`, not copy-pasted filters

`DELETE /users/{id}` sets `users.deleted_at` instead of removing the row — Laravel's `SoftDeletes` trait.
SQLAlchemy has no global-scope feature built in, but it has the pieces to build one: `SoftDeleteMixin`
(`app/db/base.py`) adds the `deleted_at` column, and a `do_orm_execute` session event auto-injects
`deleted_at IS NULL` into *every* query that touches a model using the mixin — `select()`, `scalars()`,
and `Session.get()` alike. Nothing in `user_service.py` or `auth_service.py` filters `deleted_at` by hand
anymore; there's nothing to remember and nothing to forget.

```python
class Event(SoftDeleteMixin, Base):        # any future model
    __tablename__ = "events"
    ...                                    # run a migration for deleted_at — that's the whole cost
```

That's the entire integration cost for a new model: inherit the mixin, migrate the column. Every
`get_event`, `list_events`, whatever-you-write-later automatically excludes deleted rows — including code
that doesn't exist yet, since the filter lives at the `Session` level, not in each query.

Needed for `users` specifically:

- `user_service.get_user` / `list_users` — a soft-deleted user 404s and disappears from the paginated list.
- `auth_service.authenticate_user` — can't log in (fails the same way as a wrong password, not a distinct
  "deleted" message — unlike `is_active=False`, which does say "deactivated"; a deleted account should look
  like it never existed).
- `api/deps.get_current_user` and `auth_service.refresh_tokens` — an access or refresh token issued before
  the deletion stops working immediately, it isn't valid until it happens to expire.
- `auth_service.request_password_reset` — no reset email for a deleted account.

All four fell out of the mixin for free — none of those functions mention `deleted_at`. Deleting also calls
`auth_service.revoke_all_refresh_tokens` (the same "sign out everywhere" helper password reset uses), so
there's no lingering session left over from before the delete.

Need a trashed row anyway (an admin view, a future restore feature)? Opt out per-query, not per-model:

```python
db.scalar(select(User).where(...).execution_options(include_deleted=True))
```

`register_user` and `get_user_by_email` use exactly this — deliberately, with a comment — because
`users.email` has one unconditional unique constraint, not one scoped to `deleted_at IS NULL`. A
soft-deleted user's email stays physically taken, so the duplicate-email check has to see it too, or a
"the email is available" 200 would be immediately followed by a raw `IntegrityError` on insert. This matches
an unmodified Laravel app more than it might first appear: `SoftDeletes` alone doesn't free up unique
columns either, unless you deliberately add a partial/conditional unique index for it.

Restoring a soft-deleted row isn't implemented — there's no `withTrashed()`/`restore()` equivalent yet, just
the `is_deleted` property and `soft_delete()` method the mixin provides. `Category` uses the same mixin —
this is the second model proving it's genuinely reusable, not just written once for `User` and never
exercised again.

### Filtering, sorting, includes — the Laravel `getQB()` equivalent

Both `GET /users` and `GET /categories` support the same three query-string mechanics, driven entirely by
class attributes on the model — no per-resource query-builder code to write, matching a Laravel base-model
`getQB()` factory that inspects `$fillable`/`$relationship` instead of you hand-listing allowed fields per
controller.

```
GET /api/v1/categories?filter[name]=Groceries&sort=-created_at&include=user
```

- **`filter[field]=value`** — allow-listed to every real, non-`__hidden__` column, reflected straight off
  the SQLAlchemy model (`Queryable._queryable_columns()`, `app/db/base.py`) — no separate list to keep in
  sync. `User.__hidden__ = {"password"}` keeps it off the filterable surface entirely (an exact-match filter
  on a bcrypt hash is a hash-guessing surface, however small); the equivalent of Eloquent's `$hidden`, which
  SQLAlchemy has no built-in concept of. A bad value on a real column (`filter[is_active]=banana`) returns
  zero rows via `.where(false())`, not a 500 — int/bool columns are coerced, everything else compares as a
  plain string.
- **`sort=field`** / **`sort=-field`** — same allow-list, `-` prefix for descending. `__default_sort__`
  (`User` → `"id"`, `Category` → `"name"`) applies when `sort` is omitted. This is our own convention, not a
  native SQLAlchemy one — 2.0 actually removed the legacy `Mapper(order_by=...)` argument that used to do
  this, in favor of always sorting explicitly at the query site.
- **`include=relation`** (comma-separated) — allow-listed via `__includable__` (`User` → `{"categories"}`,
  `Category` → `{"user"}`), an allow-list rather than a deny-list like `__hidden__` since eager-loading an
  arbitrary relationship is a much bigger blast radius than filtering on one column. Every requested
  relation is loaded with `selectinload()` — one batched query for the whole page, not one per row — which
  is the actual N+1 prevention: `UserRead.categories`/`CategoryRead.user` only appear in the response when
  eager-loaded (checked via `sqlalchemy.inspect(row).unloaded`, which is also what lets a single-resource
  `GET` stay lazy-load-free while a list endpoint stays eager-load-or-nothing, using the same `to_user_read`
  either way), so a field a client never asked for never costs a query it didn't ask for either.

All three are exposed through **one dependency per resource**, built once by `get_qb(Model)`
(`app/api/deps.py`) and reused as `Depends(user_qb)` / `Depends(category_qb)`:

```python
# app/api/routes/users.py
user_qb = get_qb(User)

@router.get("", response_model=UserPage)
def list_users(request: Request, qb: QB = Depends(user_qb), db: Session = Depends(get_db)) -> UserPage:
    return user_service.list_users(db, qb, request)

# app/services/user_service.py
def list_users(db: Session, qb: QB, request: Request) -> UserPage:
    stmt = qb.apply(select(User)).options(selectinload(User.profile))
    return paginate(db, stmt, request, to_user_read)
```

`get_qb()` builds its `Query(...)` parameters (`filter[name]`, `filter[email]`, `sort`, `include`, …)
dynamically from the model's own allow-lists via a generated function signature — so unlike reading
`request.query_params` by hand, every one of these still shows up individually in `/docs`, fully typed and
described, exactly as if they'd been hand-written. Adding a filterable column or an includable relation to
a model is the entire change needed; no route or dependency code to touch.

`QB.apply(stmt)` (`app/db/base.py`) chains filters → sort → includes onto a `Select` in one call — the
direct equivalent of a configured Laravel query builder being handed back from `$model->getQB()`, ready for
the caller to run.

### Pagination — one generic helper, not reimplemented per resource

`paginate(db, base_stmt, request, qb, mapper)` (`app/db/pagination.py`) is the single place every listing
endpoint gets its pagination from — filters/includes/sort from `qb` are applied inside it, not by the
caller, and `page`/`per_page`/`cursor`/`direction` are all read straight off `request.query_params` rather
than threaded through every service function's own signature (the route's own `Query(...)` declarations
already validated `page`/`per_page`, so `/docs` still documents them and an out-of-range value already 422s
before this ever runs).

Two modes, chosen entirely by what the request sends — no separate endpoint per mode:

**Offset mode (`?page=`), the default:**

```json
{
  "data": [ ... ],
  "current_page": 2,
  "per_page": 15,
  "next_page_url": "http://.../categories?page=3&per_page=15",
  "prev_page_url": "http://.../categories?page=1&per_page=15"
}
```

- **No `total`/`last_page`, on purpose.** Computing an exact total means a `COUNT(*)` on every request,
  which has no index-only shortcut on Postgres and gets slower as a table grows — this is Laravel's
  `simplePaginate()` shape, not `paginate()`'s. "Is there a next page" is answered by fetching one row past
  `per_page` instead (trimmed before returning) — a fixed cost regardless of whether the table has 100 rows
  or 100 million.
- **`per_page=-1` ("give me everything") is clamped, not literally unbounded.** Capped at
  `settings.pagination_max_limit` (default 1000) rather than loading an entire table into memory, building
  a response object for every row, and running the mapper on all of them synchronously in one request.
  `settings.pagination_limit` (default 15) is the normal per-page default, applied the same way across
  every resource.
- **Deep pages still degrade.** `page=50000` means the DB scans and discards ~750K rows before it can
  return anything — inherent to `OFFSET`, unaffected by the `COUNT(*)` removal above. This is what cursor
  mode exists to fix.

**Cursor mode (`?cursor=`, opt-in) — send `direction=next` with no `cursor` to start:**

```json
{
  "data": [ ... ],
  "per_page": 15,
  "next_cursor": "WyJHcm9jZXJpZXMiLCA0Ml0=",
  "prev_cursor": null,
  "next_page_url": "http://.../categories?per_page=15&cursor=WyJHcm9jZXJpZXMiLCA0Ml0%3D&direction=next",
  "prev_page_url": null
}
```

`current_page` is `None` here — a cursor is "resume right after this row," not a page number, so there
isn't one. The cursor itself is `base64(json([sort_value, id]))` — opaque and not meant to be constructed
by hand, only round-tripped from a previous response. `id` rides along even when sorting by another column
(`Category`'s default `name`, say) because `name` usually isn't unique: without `id` breaking ties, rows
sharing a sort value could be skipped or duplicated across pages. `WHERE (sort_column, id) > (cursor_values)`
(SQLAlchemy's `tuple_(...)`) replaces `OFFSET` entirely — the database seeks straight to the right spot via
the index instead of scanning past everything before it, so page 50,000 costs exactly what page 1 does.
`direction=prev` is answered by reversing the comparison *and* the `ORDER BY`, fetching that way, then
reversing the result back to natural order before returning it — the standard trick that lets keyset
pagination go backwards at all, since there's no `OFFSET -n`. Verified directly, not just reasoned through:
walked forward and backward across page boundaries with duplicate sort values on purpose (nine rows all
named `"Same"`, differing only by `id`) to confirm no row is ever skipped or repeated, and confirmed the
query count for a "deep" cursor page is identical to a shallow one.

Both modes share `mapper` (e.g. `to_user_read`) as an explicit, required argument rather than something
`paginate()` derives on its own — the row → response conversion isn't a plain attribute passthrough Pydantic
could do automatically for either model: a profile picture's `url` is a presigned URL computed on the fly,
and the `unloaded`-checked include fields described above are real logic, not boilerplate.

`users.name` and `categories.name` are indexed — the former because it's filterable, the latter because
it's also `Category.__default_sort__`, meaning every plain `GET /categories` sorts by it by default.

## Setup

```bash
uv sync
cp .env.example .env   # then edit DATABASE_URL / JWT_SECRET_KEY / SMTP_* / REDIS_URL / AWS_*
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Run the worker in a second terminal if you want to actually test the password-reset email:

```bash
uv run arq app.worker.WorkerSettings
```

API reference is the auto-generated interactive docs at `http://127.0.0.1:8000/docs` (Swagger UI) or
`http://127.0.0.1:8000/redoc` once the server is running — generated straight from the route signatures
and Pydantic schemas, so it can't drift out of sync with the code the way a hand-maintained endpoint list
in this file would.

There's no automated test suite in this repo at the moment.
