# Permissions and Authorization

Authentication answers "who are you?". Authorization answers "what can you do?". This page covers the boilerplate's authorization patterns: role permissions, superuser flags, and resource ownership.

## Authorization Patterns

The boilerplate ships three overlapping mechanisms. Pick the one(s) that fit your use case.

| Pattern | Where it lives | When to use |
|---------|----------------|-------------|
| **Role permissions** | `Role` + `RolePermission` + `UserRole` models, `require_permissions` | Granting a named capability to a group of users |
| **Superuser flag** | `User.is_superuser` boolean | Admin-only operations |
| **Resource ownership** | Service-layer permission checks | "Users can only edit their own X" |

These compose. A typical request goes through:

1. **Authentication** — session cookie identifies *who*
2. **Coarse access** — role permissions, or the superuser flag, for privileged endpoints
3. **Fine-grained access** — service-layer ownership checks
4. **Rate limiting** — one global limit from settings, applied to every route (separate concern)

## Role-Based Permissions

A permission is a flat `resource.action` string — `user.read`, `role.update`. Permissions are never granted to a user directly: a `Role` carries a set of them, and a user is assigned roles.

```text
User ──< UserRole >── Role ──< RolePermission
```

Three tables in `modules/role/models.py`:

| Table | Columns | Notes |
|-------|---------|-------|
| `roles` | `id`, `name` (unique), `description` | No soft delete — a deleted role is gone |
| `role_permissions` | `role_id`, `permission_name` (composite PK) | `ON DELETE CASCADE` from `roles` |
| `user_roles` | `user_id`, `role_id` (composite PK) | `ON DELETE CASCADE` from both sides |

### Declaring a Module's Permissions

Each module owns its permission names in its own `permissions.py`, as a `StrEnum` decorated with `@register_permissions("<resource>")`:

```python
# modules/user/permissions.py
from enum import StrEnum

from ..role.permission_registry import register_permissions


@register_permissions("user")
class UserPermission(StrEnum):
    READ = "user.read"
    CREATE = "user.create"
    UPDATE = "user.update"
    DELETE = "user.delete"
```

Registration is validated: the resource must match `^[a-z][a-z0-9_]*$`, every member must be `<resource>.<action>` with an action matching the same pattern, and the whole name must fit the 100-character `permission_name` column. A resource can only be registered once.

`discover_permissions()` walks `src.modules.*.permissions` and imports each one; `modules/__init__.py` calls it at import time, so a new `permissions.py` needs no registration elsewhere.

The registry in `modules/role/permission_registry.py` is what the rest of the app reads:

| Function | Returns |
|----------|---------|
| `all_permissions()` | Every registered name, as a `frozenset[str]` |
| `permission_groups()` | `{resource: (names, ...)}` — for a UI that offers permissions per resource |
| `is_known_permission(name)` | Whether a name is registered |

Unregistered names can't be stored: `RolePermission` validates `permission_name` against the registry and raises. In the other direction, a name that was stored and has since been removed from the code is ignored when permissions are loaded, so deleting a permission from a `StrEnum` can never grant anything.

### Protecting a Route

`require_permissions(*names)` returns a dependency that answers 403 unless the caller holds every name. It injects nothing into the handler, so it goes in the route's `dependencies`:

```python
# modules/user/routes.py
from ...infrastructure.auth.dependencies import require_permissions


@router.get(
    "/",
    response_model=PaginatedListResponse[UserRead],
    dependencies=[require_permissions("user.read")],
)
async def get_users(
    db: AsyncSessionDep,
    user_service: UserServiceDep,
    page: int = 1,
    items_per_page: int = 10,
) -> dict[str, Any]:
    ...
```

Unknown names are a programming error, not a runtime one: `require_permissions` raises when the route is declared, so a typo fails at import rather than on the first request.

**Superusers bypass every permission check.** `require_permissions` passes them without a lookup, and `get_current_permissions` reports them as holding every registered permission — so a superuser needs no roles.

### Reading the Caller's Permissions

When the handler itself has to decide, take the permission set instead of a guard. `CurrentPermissionsDep` (from `infrastructure/dependencies.py`) is `get_current_permissions` as an `Annotated` alias; FastAPI resolves it once per request, so several guards and parameters share one query:

```python
from ...infrastructure.dependencies import CurrentPermissionsDep


@router.patch("/{username}")
async def update_user_profile(
    username: str,
    values: UserUpdate,
    current_user: CurrentUserDep,
    permissions: CurrentPermissionsDep,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
) -> dict[str, str]:
    await user_service.verify_update_permission(current_user, username, permissions)
    ...
```

`load_permissions(db, user_id, is_superuser=...)` is the same lookup as a plain function, for code outside a request — or, as in the route above, for reading *another* user's permissions to compare against the caller's.

### Granting Permissions

A role is a row in `roles` plus one `role_permissions` row per permission; assigning it is a row in `user_roles`. Write them through the ORM (from a script, a migration, or your own admin tooling):

```python
from src.modules.role.models import Role, RolePermission, UserRole

role = Role(name="support", description="Read-only access to user records")
db.add(role)
await db.flush()

db.add(RolePermission(role_id=role.id, permission_name="user.read"))
db.add(UserRole(user_id=user_id, role_id=role.id))
await db.commit()
```

!!! info "Not shipped yet"
    Role and permission CRUD endpoints and admin-panel views for roles are follow-up work. This change ships the models, the registry, and the route guards.

## Superuser Authorization

The User model has an `is_superuser: bool` column. Endpoints that should only be accessible to admins use the `get_current_superuser` dependency:

```python
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from ...infrastructure.auth.dependencies import get_current_superuser

router = APIRouter()


@router.delete("/admin/users/{username}")
async def gdpr_anonymize(
    username: str,
    _: Annotated[dict[str, Any], Depends(get_current_superuser)],
) -> dict[str, str]:
    # Only superusers reach this code
    ...
```

The leading `_:` is the codebase convention for dependency-only parameters whose value isn't used.

`get_current_superuser` returns 401 if not authenticated and 403 if authenticated but not a superuser. See [Sessions](sessions.md) for the dependency reference.

### When to Use the Superuser Flag

- User management (create/delete other users)
- GDPR data anonymization
- System configuration changes

Anything a *subset* of staff should be able to do is better expressed as a permission on a role than as another superuser.

### Bootstrapping the First Superuser

The first superuser is created by `scripts/setup_initial_data.py` from `ADMIN_*` env vars on first run:

```bash
cd backend
uv run python -m scripts.setup_initial_data
```

To grant superuser to an existing user, flip the column directly via the admin UI (`/admin`) or a one-off SQL update.

## Resource Ownership

Most "users can only modify their own data" rules belong in the **service layer**, not the route. The service raises a `PermissionDeniedError`, which the global handler maps to HTTP 403.

Real example from `modules/user/service.py`:

```python
from ..common.exceptions import PermissionDeniedError


async def verify_user_permission(
    self,
    current_user: dict[str, Any],
    target_username: str,
    action: str,
) -> None:
    """Raise PermissionDeniedError if current_user can't act on target_username."""
    if current_user["username"] != target_username and not current_user["is_superuser"]:
        raise PermissionDeniedError(f"Cannot {action} for another user")
```

Routes call this before dispatching the operation.

Where ownership and a role permission both apply, the service takes the permission set too. `PATCH /api/v1/users/{username}` is the example that ships:

```python
# modules/user/routes.py
@router.patch("/{username}")
async def update_user_profile(
    username: str,
    values: UserUpdate,
    current_user: CurrentUserDep,
    permissions: CurrentPermissionsDep,
    db: AsyncSessionDep,
    user_service: UserServiceDep,
) -> dict[str, str]:
    await user_service.verify_update_permission(current_user, username, permissions)
    user = await user_service.get_by_username(username, db)

    if not user_service.is_self_or_superuser(current_user, user["username"]):
        target_permissions = await load_permissions(db, user["id"])
        user_service.verify_no_privilege_escalation(user, values, permissions, target_permissions)

    await user_service.update(user["id"], values, db)
    return {"message": "User updated successfully"}
```

The rules this enforces:

- A user may always edit their own profile.
- A superuser may edit anyone.
- A `user.update` holder may edit *another* user only when that user is not a superuser and holds no permission the requester lacks — editing an account is a way to take it over, so it can't reach a stronger one.
- Only a superuser may change another user's email address: a verified provider email is how an OAuth login is matched to an existing account.

The public `UserUpdate` schema accepts `name`, `username`, `email` and `profile_image_url` only. `google_id`, `github_id`, `oauth_provider`, `email_verified` and `oauth_updated_at` moved to `UserAdminUpdate`, which the admin panel uses — sending them to the API returns 422.

The exception flows up to the global handler (registered in `infrastructure/app_factory.py`) which translates it via the `EXCEPTION_MAPPING` table — `PermissionDeniedError` → `ForbiddenException` (403). See [Exceptions](../api/exceptions.md) for the full mapping pipeline.

### Generic Ownership Pattern

For your own modules:

```python
# modules/widgets/service.py
from ..common.exceptions import PermissionDeniedError, ResourceNotFoundError


class WidgetService:
    async def delete(
        self, widget_id: int, current_user: dict[str, Any], db: AsyncSession,
    ) -> None:
        widget = await crud_widgets.get(db=db, id=widget_id)
        if widget is None:
            raise ResourceNotFoundError("Widget not found")

        if widget["owner_id"] != current_user["id"] and not current_user["is_superuser"]:
            raise PermissionDeniedError("Cannot delete another user's widget")

        await crud_widgets.delete(db=db, id=widget_id)
```

Three rules to follow:

1. **Service raises domain exceptions, not HTTP exceptions.** Lets the same logic be reused outside routes (admin scripts, taskiq jobs).
2. **Superuser bypass is explicit.** `not current_user["is_superuser"]` makes the rule readable.
3. **Order: existence check first, then ownership.** A 404 is preferred to a 403 for resources the user shouldn't even know about — see the [Hide Resource Existence](../api/exceptions.md#hide-resource-existence) note.

## Combining Patterns

A real endpoint often uses several at once:

```python
@router.delete("/widgets/{widget_id}", status_code=204)
async def delete_widget(
    widget_id: int,
    current_user: Annotated[dict[str, Any], Depends(get_current_user)],   # 1. authn
    db: Annotated[AsyncSession, Depends(async_session)],
    widget_service: Annotated[WidgetService, Depends(get_widget_service)],
) -> None:
    try:
        # Service handles:
        #   2. Existence check
        #   3. Ownership check (superuser bypass)
        await widget_service.delete(widget_id, current_user, db)
    except Exception as e:
        http_exc = handle_exception(e)
        if http_exc:
            raise http_exc
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
```

The route stays trivial. Authorization rules accumulate in the service, where they're reusable.

## Best Practices

### Keep authorization in services

Routes do dependency injection and HTTP shaping; services hold rules. If a `PermissionDeniedError` raise feels out of place in your service, that's a sign your service is doing more than business logic.

### Order checks: authn → existence → ownership

```python
# 1. Authenticated? — done by the dependency
# 2. Resource exists?
if widget is None:
    raise ResourceNotFoundError(...)
# 3. User owns it?
if widget["owner_id"] != current_user["id"] and not current_user["is_superuser"]:
    raise PermissionDeniedError(...)
```

This order prevents leaking existence (404 before 403) and keeps the cheap checks first.

### Don't reinvent rate limits

The built-in global rate limiter is enforced by a router-level dependency on the `/api/v1` router. Do not roll your own per-feature counters unless you need a different budget; for that, attach `auth.rate_limit(...)` to the route. See [Rate Limiting](../rate-limiting/index.md).

### Audit superuser actions

Superuser endpoints touch sensitive data. Log the actor + action server-side — the boilerplate's logging infrastructure (with `correlation_id` + `support_id`) makes this straightforward. See [Logging](../../user-guide/configuration/index.md) for the setup.

## Next Steps

- **[Sessions](sessions.md)** — How session-based authentication works
- **[Rate Limiting](../rate-limiting/index.md)** — The global rate limit and how to tune or disable it
- **[Exceptions](../api/exceptions.md)** — How `PermissionDeniedError` becomes 403
- **[Production](../production.md)** — Hardening checklist
