# Rate Limiting

The boilerplate ships crudauth's rate limiter with a single global limit backed by Redis (or in-process memory). The
same limit, read from `DEFAULT_RATE_LIMIT_LIMIT` and `DEFAULT_RATE_LIMIT_PERIOD`, applies to every `/api/v1` route.
Authenticated requests key by user ID and anonymous requests by trusted-proxy-aware client IP.

!!! tip "Building a full SaaS?"
    Rate limiting is part of the free foundation. **[FastroAI](https://fastro.ai)** bundles it with Stripe payments, entitlements, transactional email, a frontend, and AI agents - all wired together and production-ready. [Ship your SaaS faster →](https://fastro.ai)

## What's Built In

```text
backend/src/infrastructure/auth/setup.py
└── resolve_api_rate_limit()  crudauth per-request resolver (one global limit)
    api_rate_limit_key()      names the counter (the caller)
    api_rate_limit_dependency  router-level dependency on the whole /api/v1 router
```

The configured crudauth backend is initialized with the auth singleton in the app's lifespan.

## How a Request Flows Through It

1. **The router-level crudauth dependency runs** for each API request.
2. **`resolve_api_rate_limit`** returns the global limit built from `DEFAULT_RATE_LIMIT_LIMIT` and `DEFAULT_RATE_LIMIT_PERIOD` (or `None` when `RATE_LIMITER_ENABLED=false`).
3. **`api_rate_limit_key`** names the budget: the caller (user ID when signed in, client IP otherwise). Every route shares that one counter.
4. **crudauth's limiter** atomically increments the counter for the current window and returns `(count, is_limited)`. Windows are `DEFAULT_RATE_LIMIT_PERIOD` seconds long and aligned to the clock, and each window's key expires on its own.
5. **If `is_limited`**, raises a 429 with `Retry-After`. Otherwise the limiter attaches `X-RateLimit-Limit` and `X-RateLimit-Remaining` to the response. A request refused afterwards (a 401, a 404, a 422) still counts, and its response carries the headers too.

The key shape in Redis, ending in the start of the current window:

```text
crudauth:rl:ratelimit:api:user:{user_id}:{window_start}
crudauth:rl:ratelimit:api:ip:{client_ip}:{window_start}
```

## Custom Enforcement

Shipped API routes already use a router-level dependency. For another router, reuse the same
crudauth API:

```python
from fastapi import APIRouter, Depends
from src.infrastructure.auth.setup import auth
from crudauth.ratelimit import KeyBy, RateLimit

router = APIRouter()


@router.post("/widgets", dependencies=[Depends(auth.rate_limit("widgets", RateLimit(10, 60), key=KeyBy.USER_OR_IP))])
async def create_widget(...): ...
```

Or apply it to every route in a router:

```python
router = APIRouter(dependencies=[Depends(auth.rate_limit("widgets", RateLimit(10, 60), key=KeyBy.USER_OR_IP))])
```

That's all that's required. The limiter is enabled with `RATE_LIMITER_ENABLED=true`.

## Configuration

```env
# Master toggle for the API limits (the login lockout runs either way)
RATE_LIMITER_ENABLED=true

# Where counters live: redis (default) or memory. Memory is per process, so it only
# holds for a single worker. The memcached limiter was removed; that value fails at startup.
RATE_LIMITER_BACKEND=redis

# The single global limit applied to every counted request
DEFAULT_RATE_LIMIT_LIMIT=100
DEFAULT_RATE_LIMIT_PERIOD=60          # seconds — 100/60s by default

# Redis backend
RATE_LIMITER_REDIS_HOST=redis         # use "localhost" without Docker
RATE_LIMITER_REDIS_PORT=6379
RATE_LIMITER_REDIS_DB=1               # rate-limiter DB (cache DB 0, sessions DB 2, taskiq DB 3)
RATE_LIMITER_REDIS_PASSWORD=
RATE_LIMITER_REDIS_CONNECT_TIMEOUT=5
RATE_LIMITER_REDIS_POOL_SIZE=10
```

When `RATE_LIMITER_ENABLED=false`, the router-level dependency is a no-op. This is useful for
isolating performance issues. The login lockout still counts on `RATE_LIMITER_BACKEND`, and
fails closed: with that backend unreachable, logins are refused rather than left unthrottled.

## User vs IP-Based Keys

`api_rate_limit_key` uses the request principal when authentication is present and falls back to
the client IP using `TRUSTED_PROXY_HOPS`. Every caller gets the same limit and one counter shared across all routes.

## One Limit Everywhere

There is no per-path or per-user configuration: the limit value is the same for every route and every caller, and
it comes only from `DEFAULT_RATE_LIMIT_LIMIT` and `DEFAULT_RATE_LIMIT_PERIOD`. Requests to any `/api/v1` route (including
`/auth`) count against the caller's single budget. To give a route a different budget, use `auth.rate_limit(...)`
directly (see Custom Enforcement).

## Response Headers

Every response to a counted request carries these, errors included:

| Header                  | Meaning                                          |
|-------------------------|--------------------------------------------------|
| `X-RateLimit-Limit`     | The configured limit for this caller           |
| `X-RateLimit-Remaining` | How many requests are left in the current window |

A 429 also carries `Retry-After`, the seconds until the window resets. A request refused after
the limiter counted it - a 401 from authentication, a 404, a 422 - still reports the budget it
spent, through crudauth's `RateLimitHeadersMiddleware`, which the app factory installs.

These are standard-ish (formatted like the GitHub / Stripe convention, not RFC 6585). Frontends can read them to surface graceful "you're approaching your limit" UI.

## Production Considerations

### Pool sizing

`RATE_LIMITER_REDIS_POOL_SIZE=10` is enough for typical workloads. If you're seeing `redis.exceptions.ConnectionError` under load, it usually means pool exhaustion — raise the pool size or check upstream connection-leak issues first.

### Backend errors

crudauth's window checks fail open on a Redis outage — requests pass through unrate-limited rather
than turning a cache blip into 429s for everyone. The login lockout is the exception: it fails
closed, so a locked-out account can't slip through while Redis is down.

### Window behavior

The implementation uses a fixed-window counter, with windows aligned to the clock. At the boundary between windows, a user can technically make `2 × limit` requests in a short span. For most use cases this is fine; if you need stricter sliding-window semantics, build that on top of the limiter yourself.

### Anonymous-user limits

IP-based rate limits are easy to bypass with NAT / proxies / IPv6 rotation. They're a speed bump, not security. If you're trying to prevent abuse rather than control fair use, you need authentication, captchas, or upstream firewall rules — not just rate limits.

## Troubleshooting

### "My limit is not being applied"

- Confirm `RATE_LIMITER_ENABLED=true`
- Confirm the auth singleton initialized cleanly at startup
- Confirm the route is under `/api/v1` (the limit is applied to that whole router)

### "All requests look anonymous even though users are logged in"

The limiter keys on the resolved principal for authenticated requests. If users appear anonymous,
the session cookie isn't reaching the app — check `SESSION_BACKEND`, `SESSION_REDIS_DB` and any
reverse proxy that strips cookies.

### "The limiter can't reach Redis"

Window checks fail open, so requests keep flowing while Redis is down (the login lockout fails
closed). Fix the Redis connection, or take the limiter out of the path entirely with
`RATE_LIMITER_ENABLED=false`.

## Key Files

| Component             | Location                                                  |
|-----------------------|-----------------------------------------------------------|
| Resolver + dependency | `backend/src/infrastructure/auth/setup.py`                |
| Settings              | `backend/src/infrastructure/config/settings.py` (`RateLimiterSettings`) |

## Next Steps

- **[Caching → Cache Strategies](../caching/cache-strategies.md)** — Patterns that share the same Redis-as-state mindset
