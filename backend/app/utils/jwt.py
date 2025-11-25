"""JWT token utilities for authentication"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class TokenError(Exception):
    """Custom exception for token-related errors"""
    pass


def create_access_token(user_id: str, username: str) -> str:
    """
    Create a JWT access token

    Args:
        user_id: User's UUID
        username: User's username

    Returns:
        Encoded JWT token string

    Example:
        >>> token = create_access_token("uuid-123", "admin")
        >>> isinstance(token, str)
        True
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    payload = {
        "sub": user_id,  # Subject (user ID)
        "username": username,
        "exp": expire,
        "iat": datetime.now(timezone.utc),  # Issued at
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token

    Args:
        token: JWT token string

    Returns:
        Decoded payload dict with user_id, username, exp

    Raises:
        TokenError: If token is invalid or expired

    Example:
        >>> token = create_access_token("uuid-123", "admin")
        >>> payload = decode_access_token(token)
        >>> payload["username"]
        'admin'
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return {
            "user_id": payload.get("sub"),
            "username": payload.get("username"),
            "exp": payload.get("exp"),
        }
    except jwt.ExpiredSignatureError:
        logger.debug("Token has expired")
        raise TokenError("Token has expired")
    except JWTError as e:
        logger.warning(f"Invalid token: {e}")
        raise TokenError("Invalid token")


def get_token_expiration(token: str) -> Optional[datetime]:
    """
    Get the expiration time of a token without full validation

    Args:
        token: JWT token string

    Returns:
        Expiration datetime or None if invalid
    """
    try:
        # Decode without verification to get expiration
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False}
        )
        exp = payload.get("exp")
        if exp:
            return datetime.fromtimestamp(exp, tz=timezone.utc)
        return None
    except JWTError:
        return None
