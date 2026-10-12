"""Initialize all modules and models to ensure SQLAlchemy registration."""

from .media.models import Media, Mediable
from .role.models import Role, RolePermission, UserRole
from .role.permission_registry import discover_permissions
from .user.models import User

discover_permissions()

__all__ = [
    "User",
    "Role",
    "RolePermission",
    "UserRole",
    "Media",
    "Mediable",
]
