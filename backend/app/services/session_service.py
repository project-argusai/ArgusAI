"""Session management service (Story P15-2.7, P15-2.8)

Provides session creation, tracking, expiration, and cleanup functionality.

ADR-P15-001: Session-based auth with JWT
- HTTP-only cookies prevent XSS
- Server-side tracking enables session management
- Token hash stored (not token itself) for security
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import desc
from fastapi import Request
import logging
import re
import uuid

from app.models.session import Session
from app.models.user import User
from app.core.config import settings
from app.utils.auth import generate_refresh_token, REFRESH_TOKEN_LENGTH
from app.utils.jwt import create_access_token

logger = logging.getLogger(__name__)

# Default settings - can be overridden in config
DEFAULT_SESSION_EXPIRY_HOURS = 24
DEFAULT_MAX_SESSIONS_PER_USER = 5


class SessionService:
    """
    Service for managing user sessions (Story P15-2.7, P15-2.8)

    Responsibilities:
    - Create new sessions with device/IP tracking
    - Enforce session limits per user
    - Track session activity
    - Revoke sessions
    - Clean up expired sessions
    """

    def __init__(self, db: DBSession):
        self.db = db
        self.session_expiry_hours = getattr(settings, 'SESSION_EXPIRY_HOURS', DEFAULT_SESSION_EXPIRY_HOURS)
        self.max_sessions = getattr(settings, 'MAX_SESSIONS_PER_USER', DEFAULT_MAX_SESSIONS_PER_USER)

    def create_session(
        self,
        user: User,
        token: str,
        request: Request
    ) -> Session:
        """
        Create a new session for a user.

        Enforces max sessions limit - if user has max sessions,
        the oldest one is deleted.

        Args:
            user: User to create session for
            token: JWT token for this session
            request: FastAPI request for extracting device info

        Returns:
            Created Session object
        """
        # Check and enforce session limit
        user_sessions = self._get_user_sessions(user.id)
        if len(user_sessions) >= self.max_sessions:
            # Delete oldest session(s) to make room
            sessions_to_delete = len(user_sessions) - self.max_sessions + 1
            for session in user_sessions[:sessions_to_delete]:
                logger.info(
                    "Deleting oldest session due to limit",
                    extra={
                        "event_type": "session_limit_enforced",
                        "user_id": user.id,
                        "deleted_session_id": session.id,
                    }
                )
                self.db.delete(session)

        # Extract device info from request
        device_info = self._parse_device_info(request)
        ip_address = self._get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "")[:512]

        # Calculate expiry
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self.session_expiry_hours)

        # Create session
        session = Session(
            user_id=user.id,
            token_hash=Session.hash_token(token),
            device_info=device_info,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )

        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        logger.info(
            "Session created",
            extra={
                "event_type": "session_created",
                "user_id": user.id,
                "session_id": session.id,
                "device_info": device_info,
                "ip_address": ip_address,
            }
        )

        return session

    def create_web_session_with_refresh(
        self,
        user: User,
        access_token: str,
        request: Request,
        refresh_token_expiry_days: int = 30
    ) -> tuple[Session, str]:
        """
        Create a new web session that also includes a refresh token.

        This is the new flow for Phase A web auth refresh support.
        Returns (session, plain_refresh_token) so the caller can return it to the client.
        """
        # First create the base session (access token part)
        session = self.create_session(user, access_token, request)

        # Generate refresh token + family
        plain_refresh_token = generate_refresh_token()
        token_family = str(uuid.uuid4())
        refresh_expires_at = datetime.now(timezone.utc) + timedelta(days=refresh_token_expiry_days)

        # Store on the session
        session.set_refresh_token(plain_refresh_token, token_family, refresh_expires_at)

        self.db.commit()
        self.db.refresh(session)

        logger.info(
            "Web session created with refresh token",
            extra={
                "event_type": "web_session_with_refresh_created",
                "user_id": user.id,
                "session_id": session.id,
                "refresh_token_family": token_family,
            }
        )

        return session, plain_refresh_token

    def refresh_tokens(
        self,
        plain_refresh_token: str,
        request: Request
    ) -> tuple[str, str, User]:
        """
        Validates a refresh token, rotates it (issues new refresh + new access token),
        and returns the new tokens along with the user.

        Security features:
        - Token rotation (single-use refresh tokens)
        - Family tracking
        - **Reuse detection**: If a previously used/revoked refresh token from an active
          family is presented, the *entire family* is immediately revoked.
        """
        refresh_hash = Session.hash_token(plain_refresh_token)

        # Find session by refresh token hash
        session = self.db.query(Session).filter(
            Session.refresh_token_hash == refresh_hash
        ).first()

        if not session:
            logger.warning(
                "Refresh attempt with unknown refresh token",
                extra={"event_type": "refresh_token_unknown"}
            )
            raise ValueError("Invalid refresh token")

        # === Critical: Reuse Detection ===
        if session.refresh_revoked_at is not None and session.refresh_token_family:
            # This refresh token has already been used/revoked.
            # Check if any *other* tokens in this family are still valid.
            active_in_family = self.db.query(Session).filter(
                Session.refresh_token_family == session.refresh_token_family,
                Session.refresh_revoked_at.is_(None),
                Session.refresh_expires_at > datetime.now(timezone.utc)
            ).count()

            if active_in_family > 0:
                # Reuse attack detected!
                self._revoke_refresh_family(
                    session.refresh_token_family,
                    reason="reuse_detected"
                )
                logger.warning(
                    "REFRESH TOKEN REUSE DETECTED — Entire family revoked",
                    extra={
                        "event_type": "refresh_token_reuse_detected",
                        "user_id": session.user_id,
                        "session_id": session.id,
                        "family": session.refresh_token_family,
                        "ip": request.client.host if request.client else "unknown",
                    }
                )
                # Specific error code so frontend can show a better message
                raise ValueError("refresh_token_reuse_detected")

        # Normal validation
        if not session.is_refresh_valid:
            logger.warning(
                "Refresh attempt with invalid/expired/revoked refresh token",
                extra={
                    "event_type": "refresh_token_invalid",
                    "session_id": session.id,
                    "user_id": session.user_id,
                }
            )
            raise ValueError("Refresh token expired or revoked")

        # Get the user
        user = self.db.query(User).filter(User.id == session.user_id).first()
        if not user or not user.is_active:
            logger.warning(
                "Refresh attempt for inactive or missing user",
                extra={"user_id": session.user_id}
            )
            raise ValueError("User account is disabled")

        # === Token Rotation ===
        old_family = session.refresh_token_family

        # Generate new refresh token (same family)
        new_plain_refresh = generate_refresh_token()
        new_refresh_expires = datetime.now(timezone.utc) + timedelta(days=30)

        # Revoke the old refresh token
        session.revoke_refresh("rotation")

        # Set the new refresh token on the same session
        session.set_refresh_token(new_plain_refresh, old_family, new_refresh_expires)

        # Create new short-lived access token
        new_access_token = create_access_token(user.id, user.username)

        # Update session activity + access token hash
        session.token_hash = Session.hash_token(new_access_token)
        session.update_activity()

        self.db.commit()
        self.db.refresh(session)

        logger.info(
            "Refresh token rotated successfully",
            extra={
                "event_type": "refresh_token_rotated",
                "user_id": user.id,
                "session_id": session.id,
                "family": old_family,
            }
        )

        return new_access_token, new_plain_refresh, user

    def _revoke_refresh_family(self, family: str, reason: str = "reuse_detected") -> int:
        """
        Revoke every refresh token belonging to a given family.
        This is the nuclear option used when reuse is detected.
        """
        sessions = self.db.query(Session).filter(
            Session.refresh_token_family == family,
            Session.refresh_revoked_at.is_(None)
        ).all()

        count = 0
        for sess in sessions:
            sess.revoke_refresh(reason)
            count += 1

        if count > 0:
            self.db.commit()
            logger.warning(
                f"Revoked entire refresh family ({count} sessions)",
                extra={
                    "event_type": "refresh_family_revoked",
                    "family": family,
                    "reason": reason,
                    "revoked_count": count,
                }
            )

        return count

    def revoke_session_by_refresh_token(self, plain_refresh_token: str, user_id: Optional[str] = None) -> bool:
        """
        Revoke a session (and its refresh token) using the refresh token value.
        Useful for logout when the access token cookie has already expired.
        """
        refresh_hash = Session.hash_token(plain_refresh_token)

        query = self.db.query(Session).filter(Session.refresh_token_hash == refresh_hash)

        if user_id:
            query = query.filter(Session.user_id == user_id)

        session = query.first()

        if not session:
            return False

        if session.has_refresh_token and not session.refresh_revoked_at:
            session.revoke_refresh("logout")

        self.db.delete(session)
        self.db.commit()

        logger.info(
            "Session revoked via refresh token",
            extra={
                "event_type": "session_revoked_via_refresh",
                "user_id": session.user_id,
                "session_id": session.id,
            }
        )

        return True

    def get_session_by_token(self, token: str) -> Optional[Session]:
        """
        Get session by JWT token.

        Args:
            token: JWT token

        Returns:
            Session if found and not expired, None otherwise
        """
        token_hash = Session.hash_token(token)
        session = self.db.query(Session).filter(
            Session.token_hash == token_hash
        ).first()

        if session and session.is_expired():
            # Auto-delete expired session
            self.db.delete(session)
            self.db.commit()
            return None

        return session

    def update_session_activity(self, session: Session) -> None:
        """Update session's last_active_at timestamp"""
        session.update_activity()
        self.db.commit()

    def revoke_session(self, session_id: str, user_id: str) -> bool:
        """
        Revoke a specific session.

        If the session has an active refresh token, it is explicitly revoked
        with reason "logout" before the session is deleted. This ensures
        proper audit trail for refresh token revocation.
        """
        session = self.db.query(Session).filter(
            Session.id == session_id,
            Session.user_id == user_id
        ).first()

        if not session:
            return False

        # Explicitly revoke refresh token if present (Phase A - Web Refresh)
        if session.has_refresh_token and not session.refresh_revoked_at:
            session.revoke_refresh("logout")
            self.db.commit()  # Commit the revocation before deleting

        self.db.delete(session)
        self.db.commit()

        logger.info(
            "Session revoked",
            extra={
                "event_type": "session_revoked",
                "user_id": user_id,
                "session_id": session_id,
                "refresh_revoked": session.has_refresh_token,
            }
        )

        return True

    def revoke_all_sessions(self, user_id: str, except_session_id: Optional[str] = None) -> int:
        """
        Revoke all sessions for a user, optionally keeping one.

        Args:
            user_id: User ID
            except_session_id: Session ID to keep (current session)

        Returns:
            Number of sessions revoked
        """
        query = self.db.query(Session).filter(Session.user_id == user_id)

        if except_session_id:
            query = query.filter(Session.id != except_session_id)

        sessions = query.all()
        count = len(sessions)

        for session in sessions:
            self.db.delete(session)

        self.db.commit()

        logger.info(
            "All sessions revoked",
            extra={
                "event_type": "all_sessions_revoked",
                "user_id": user_id,
                "revoked_count": count,
                "kept_session_id": except_session_id,
            }
        )

        return count

    def get_user_sessions(
        self,
        user_id: str,
        current_token: Optional[str] = None
    ) -> List[dict]:
        """
        Get all active sessions for a user.

        Args:
            user_id: User ID
            current_token: Current session's token (to mark is_current)

        Returns:
            List of session info dicts with is_current flag
        """
        sessions = self._get_user_sessions(user_id, valid_only=True)
        current_hash = Session.hash_token(current_token) if current_token else None

        result = []
        for session in sessions:
            result.append({
                "id": session.id,
                "device_info": session.device_info,
                "ip_address": session.ip_address,
                "created_at": session.created_at,
                "last_active_at": session.last_active_at,
                "is_current": session.token_hash == current_hash if current_hash else False,
            })

        return result

    def cleanup_expired_sessions(self) -> int:
        """
        Delete all expired sessions from database.

        Should be called by background task (hourly).

        Returns:
            Number of sessions cleaned up
        """
        now = datetime.now(timezone.utc)
        expired = self.db.query(Session).filter(
            Session.expires_at < now
        ).all()

        count = len(expired)
        for session in expired:
            self.db.delete(session)

        self.db.commit()

        if count > 0:
            logger.info(
                "Expired sessions cleaned up",
                extra={
                    "event_type": "sessions_cleanup",
                    "expired_count": count,
                }
            )

        return count

    def _get_user_sessions(self, user_id: str, valid_only: bool = False) -> List[Session]:
        """Get all sessions for a user, ordered by creation time (oldest first)"""
        query = self.db.query(Session).filter(Session.user_id == user_id)

        if valid_only:
            now = datetime.now(timezone.utc)
            query = query.filter(Session.expires_at > now)

        return query.order_by(Session.created_at.asc()).all()

    def _parse_device_info(self, request: Request) -> str:
        """
        Parse User-Agent into human-readable device info.

        Examples:
        - "Chrome on Windows"
        - "Safari on iPhone"
        - "Firefox on Linux"
        """
        user_agent = request.headers.get("User-Agent", "")
        if not user_agent:
            return "Unknown Device"

        # Browser detection
        browser = "Unknown Browser"
        if "Chrome" in user_agent and "Safari" in user_agent and "Edg" not in user_agent:
            browser = "Chrome"
        elif "Firefox" in user_agent:
            browser = "Firefox"
        elif "Safari" in user_agent and "Chrome" not in user_agent:
            browser = "Safari"
        elif "Edg" in user_agent:
            browser = "Edge"
        elif "MSIE" in user_agent or "Trident" in user_agent:
            browser = "Internet Explorer"

        # OS detection
        os = "Unknown OS"
        if "Windows" in user_agent:
            os = "Windows"
        elif "Macintosh" in user_agent or "Mac OS" in user_agent:
            os = "macOS"
        elif "iPhone" in user_agent:
            os = "iPhone"
        elif "iPad" in user_agent:
            os = "iPad"
        elif "Android" in user_agent:
            os = "Android"
        elif "Linux" in user_agent:
            os = "Linux"

        return f"{browser} on {os}"

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, checking forwarding headers"""
        # Check X-Forwarded-For header (for proxied requests)
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            # Take the first IP (original client)
            return forwarded.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP", "")
        if real_ip:
            return real_ip.strip()

        # Fall back to direct client
        if request.client:
            return request.client.host

        return "unknown"
