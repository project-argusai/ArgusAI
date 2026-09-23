"""Role-based access control permissions (Story P15-2.9, P16-1.3)

Provides FastAPI dependencies for enforcing role-based permissions on API endpoints.

ADR-P15-003: Three-role RBAC (admin, operator, viewer)
- Admin: Full system access including user management
- Operator: Manage events, entities, cameras but not users
- Viewer: Read-only access to dashboard and events

Permission Matrix:
| Endpoint Pattern          | Admin | Operator | Viewer |
|---------------------------|-------|----------|--------|
| GET /events/*             | Yes   | Yes      | Yes    |
| POST/PUT/DELETE /events/* | Yes   | Yes      | No     |
| */users/*                 | Yes   | No       | No     |
| PUT /system/*             | Yes   | No       | No     |
| GET /cameras/*            | Yes   | Yes      | Yes    |
| POST/PUT/DELETE /cameras/*| Yes   | Yes      | No     |
| GET /entities/*           | Yes   | Yes      | Yes    |
| POST/PUT/DELETE /entities/*| Yes  | Yes      | No     |

Story P16-1.3: Added error_code to permission denied responses.
"""
from functools import wraps
from typing import List, Callable
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.orm import Session
import logging

from app.core.database import get_db
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


class PermissionDenied(HTTPException):
    """Exception raised when user lacks required permissions (Story P16-1.3)

    Returns 403 with body: {"detail": "...", "error_code": "INSUFFICIENT_PERMISSIONS"}
    """

    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "detail": detail,
                "error_code": "INSUFFICIENT_PERMISSIONS"
            }
        )


def require_role(*allowed_roles: UserRole):
    """
    Dependency factory that checks if user has one of the allowed roles.

    Usage:
        @router.get("/users")
        async def list_users(user: User = Depends(require_role(UserRole.ADMIN))):
            ...

        @router.post("/events")
        async def create_event(user: User = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
            ...

    Args:
        *allowed_roles: One or more UserRole values that are permitted

    Returns:
        A dependency function that validates the user's role
    """
    from app.api.v1.auth import get_current_user  # Import here to avoid circular import

    async def check_role(
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> User:

        # Check if user's role is in allowed roles
        if current_user.role not in allowed_roles:
            logger.warning(
                "Permission denied",
                extra={
                    "event_type": "permission_denied",
                    "user_id": current_user.id,
                    "username": current_user.username,
                    "user_role": current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role),
                    "required_roles": [r.value for r in allowed_roles],
                    "path": request.url.path,
                    "method": request.method,
                }
            )
            raise PermissionDenied(
                detail=f"Role '{current_user.role.value if hasattr(current_user.role, 'value') else current_user.role}' "
                       f"is not authorized for this action. Required: {', '.join(r.value for r in allowed_roles)}"
            )

        return current_user

    return check_role


def require_admin():
    """Shorthand for require_role(UserRole.ADMIN)"""
    return require_role(UserRole.ADMIN)


def require_operator_or_admin():
    """Shorthand for require_role(UserRole.ADMIN, UserRole.OPERATOR)"""
    return require_role(UserRole.ADMIN, UserRole.OPERATOR)


def require_authenticated():
    """
    Dependency that just requires any authenticated user.
    All roles (admin, operator, viewer) are allowed.
    """
    return require_role(UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER)


# Role checking utilities for use in business logic
def check_can_manage_users(user: User) -> bool:
    """Check if user can manage other users (admin only)"""
    return user.role == UserRole.ADMIN


def check_can_manage_events(user: User) -> bool:
    """Check if user can create/edit/delete events (admin, operator)"""
    return user.role in (UserRole.ADMIN, UserRole.OPERATOR)


def check_can_manage_cameras(user: User) -> bool:
    """Check if user can create/edit/delete cameras (admin, operator)"""
    return user.role in (UserRole.ADMIN, UserRole.OPERATOR)


def check_can_manage_entities(user: User) -> bool:
    """Check if user can create/edit/delete entities (admin, operator)"""
    return user.role in (UserRole.ADMIN, UserRole.OPERATOR)


def check_can_manage_settings(user: User) -> bool:
    """Check if user can modify system settings (admin only)"""
    return user.role == UserRole.ADMIN


def check_can_view(user: User) -> bool:
    """Check if user can view data (all authenticated users)"""
    return user.role in (UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER)
