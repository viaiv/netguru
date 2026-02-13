"""
Role-Based Access Control (RBAC) definitions and helpers.
"""
from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    """
    System roles used for authorization.
    """

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Permission(str, Enum):
    """
    Fine-grained permissions mapped to roles.
    """

    USERS_READ_SELF = "users:read_self"
    USERS_UPDATE_SELF = "users:update_self"
    API_KEYS_READ_SELF = "api_keys:read_self"
    API_KEYS_UPDATE_SELF = "api_keys:update_self"
    USERS_LIST = "users:list"
    USERS_READ = "users:read"
    USERS_UPDATE_ROLE = "users:update_role"
    USERS_UPDATE_STATUS = "users:update_status"
    ADMIN_DASHBOARD = "admin:dashboard"
    ADMIN_USERS_MANAGE = "admin:users_manage"
    ADMIN_AUDIT_LOG = "admin:audit_log"
    ADMIN_PLANS_READ = "admin:plans_read"
    ADMIN_PLANS_MANAGE = "admin:plans_manage"
    ADMIN_SYSTEM_HEALTH = "admin:system_health"
    ADMIN_SETTINGS_MANAGE = "admin:settings_manage"


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.OWNER: frozenset(permission for permission in Permission),
    UserRole.ADMIN: frozenset(
        {
            Permission.USERS_READ_SELF,
            Permission.USERS_UPDATE_SELF,
            Permission.API_KEYS_READ_SELF,
            Permission.API_KEYS_UPDATE_SELF,
            Permission.USERS_LIST,
            Permission.USERS_READ,
            Permission.USERS_UPDATE_ROLE,
            Permission.USERS_UPDATE_STATUS,
            Permission.ADMIN_DASHBOARD,
            Permission.ADMIN_USERS_MANAGE,
            Permission.ADMIN_AUDIT_LOG,
            Permission.ADMIN_PLANS_READ,
            Permission.ADMIN_SYSTEM_HEALTH,
        }
    ),
    UserRole.MEMBER: frozenset(
        {
            Permission.USERS_READ_SELF,
            Permission.USERS_UPDATE_SELF,
            Permission.API_KEYS_READ_SELF,
            Permission.API_KEYS_UPDATE_SELF,
        }
    ),
    UserRole.VIEWER: frozenset(
        {
            Permission.USERS_READ_SELF,
            Permission.API_KEYS_READ_SELF,
        }
    ),
}

ADMIN_ASSIGNABLE_ROLES: frozenset[UserRole] = frozenset(
    {
        UserRole.ADMIN,
        UserRole.MEMBER,
        UserRole.VIEWER,
    }
)


def normalize_role(role: str | UserRole | None) -> UserRole:
    """
    Normalize string/enum role values to a valid ``UserRole``.

    Args:
        role: Raw role value from DB/token input.

    Returns:
        Normalized role. Falls back to ``UserRole.MEMBER`` for unknown values.
    """

    if isinstance(role, UserRole):
        return role

    if role is None:
        return UserRole.MEMBER

    try:
        return UserRole(str(role))
    except ValueError:
        return UserRole.MEMBER


def get_role_permissions(role: str | UserRole | None) -> frozenset[Permission]:
    """
    Resolve the permission set for a role.

    Args:
        role: Role value.

    Returns:
        Immutable set with granted permissions for the given role.
    """

    normalized_role = normalize_role(role)
    return ROLE_PERMISSIONS.get(normalized_role, frozenset())


def has_permission(role: str | UserRole | None, permission: Permission) -> bool:
    """
    Check if role grants the required permission.

    Args:
        role: Role value.
        permission: Required permission.

    Returns:
        ``True`` if role has the permission.
    """

    return permission in get_role_permissions(role)


def can_assign_role(actor_role: str | UserRole | None, target_role: UserRole) -> bool:
    """
    Check if actor role can assign target role.

    Args:
        actor_role: Role from acting user.
        target_role: Desired role for target user.

    Returns:
        ``True`` when assignment is authorized.
    """

    normalized_actor_role = normalize_role(actor_role)

    if normalized_actor_role == UserRole.OWNER:
        return True

    if normalized_actor_role == UserRole.ADMIN:
        return target_role in ADMIN_ASSIGNABLE_ROLES

    return False
