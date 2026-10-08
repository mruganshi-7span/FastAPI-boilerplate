"""Initialize all modules and models to ensure SQLAlchemy registration."""

from .role.models import Role, RolePermission, UserRole
from .role.permission_registry import discover_permissions
from .user.models import User

discover_permissions()

__all__ = [
    "User",
    "Role",
    "RolePermission",
    "UserRole",
]
