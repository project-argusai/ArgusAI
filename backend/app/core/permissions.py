"""Role-based access control for user sessions (Story P15-2.9, P16-1.3).

ADR-P15-003 defines three roles: admin, operator, and viewer. The comment that
used to live here granted operators camera CRUD and unrestricted event and
entity writes. Those grants were never enforced on routes. State-changing
routes now follow the matrix below. API keys are not roles: AuthMiddleware
still allowlists them by scope, and these dependencies do not narrow or widen
that table.

| Action | Admin | Operator | Viewer |
| --- | --- | --- | --- |
| Reads | Yes | Yes | Yes |
| Own account, devices, and push registration | Yes | Yes | Yes |
| Event feedback, reanalyze, manual camera analyze | Yes | Yes | No |
| Notification inbox (read, dismiss, delete) | Yes | Yes | No |
| Entity label, merge, assign (not deletion) | Yes | Yes | No |
| Voice query, summary generate, anomaly score | Yes | Yes | No |
| Camera, Protect, MQTT, SMTP, HomeKit, AI, alert, webhook config | Yes | No | No |
| Event, motion, media, face, and embedding deletes | Yes | No | No |
| Orphan reconcile, retention, cleanup, backup, restore, wipe | Yes | No | No |
| Users, API keys, tunnel control | Yes | No | No |

Story P16-1.3: permission denials include error_code INSUFFICIENT_PERMISSIONS.
"""
import logging
import os

from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.orm import Session

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


def get_mutation_principal(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    """Resolve the user for a role check.

    A request that AuthMiddleware already accepted with an API key returns
    None. The scope allowlist is the key's authorization; calling
    ``get_current_user`` here would reject that key with 401. Cookie and
    bearer sessions still resolve to a user. Test overrides of
    ``get_current_user`` are honored when no API key is present.
    """
    if getattr(request.state, "api_key", None) is not None:
        return None

    # Pytest-only. conftest sets this on the dependency function so legacy
    # route tests, including ones that mount a router on their own FastAPI
    # app, keep exercising handlers. It is ignored unless pytest is running.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        legacy = getattr(get_mutation_principal, "_legacy_test_principal", None)
        if legacy is not None:
            return legacy() if callable(legacy) else legacy

    from app.api.v1.auth import get_current_user

    override = request.app.dependency_overrides.get(get_current_user)
    if override is not None:
        return override()
    return get_current_user(request, db)


def require_role(*allowed_roles: UserRole):
    """
    Dependency factory that checks if the session user has one of the allowed roles.

    API keys that passed the middleware allowlist skip this check. A session
    user whose role is not listed receives 403.

    Usage:
        @router.get("/users")
        async def list_users(user: User = Depends(require_role(UserRole.ADMIN))):
            ...

        @router.post("/events/{event_id}/feedback")
        async def feedback(user: User = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
            ...

    Args:
        *allowed_roles: One or more UserRole values that are permitted

    Returns:
        A dependency function that validates the user's role
    """

    async def check_role(
        request: Request,
        principal: User | None = Depends(get_mutation_principal),
    ) -> User | None:
        if principal is None:
            if getattr(request.state, "api_key", None) is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return None

        if principal.role not in allowed_roles:
            role_value = principal.role.value if hasattr(principal.role, "value") else str(principal.role)
            logger.warning(
                "Permission denied",
                extra={
                    "event_type": "permission_denied",
                    "user_id": principal.id,
                    "username": principal.username,
                    "user_role": role_value,
                    "required_roles": [r.value for r in allowed_roles],
                    "path": request.url.path,
                    "method": request.method,
                }
            )
            raise PermissionDenied(
                detail=f"Role '{role_value}' "
                       f"is not authorized for this action. Required: {', '.join(r.value for r in allowed_roles)}"
            )

        return principal

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
    """Day-to-day event actions (feedback, reanalyze). Deletes are admin-only."""
    return user.role in (UserRole.ADMIN, UserRole.OPERATOR)


def check_can_manage_cameras(user: User) -> bool:
    """Camera configuration and CRUD. Admin only. Operators may analyze."""
    return user.role == UserRole.ADMIN


def check_can_analyze_cameras(user: User) -> bool:
    """Manual camera analysis. Admin and operator."""
    return user.role in (UserRole.ADMIN, UserRole.OPERATOR)


def check_can_manage_entities(user: User) -> bool:
    """Label, merge, and assign entities. Deleting entities is admin-only."""
    return user.role in (UserRole.ADMIN, UserRole.OPERATOR)


def check_can_manage_settings(user: User) -> bool:
    """Check if user can modify system settings (admin only)"""
    return user.role == UserRole.ADMIN


def check_can_view(user: User) -> bool:
    """Check if user can view data (all authenticated users)"""
    return user.role in (UserRole.ADMIN, UserRole.OPERATOR, UserRole.VIEWER)
