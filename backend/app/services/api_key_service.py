"""
API Key Service for managing API keys.

Story P13-1.2: Implement API Key Generation Endpoint
Story P13-1.3: Implement API Key List and Revoke Endpoints

This service provides:
- Secure key generation with bcrypt hashing
- Key validation and authentication
- CRUD operations for API keys

Migrated to @singleton as part of #450 (Lightweight DI Container).
"""
import secrets
import bcrypt
import logging
from app.core.decorators import singleton
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.api_key import APIKey
from app.schemas.api_key import VALID_SCOPES

logger = logging.getLogger(__name__)


@singleton
class APIKeyService:
    """
    Service for API key management operations.

    Key format: argus_<32-char-random>
    Storage: Only bcrypt hash is stored, never the plaintext key
    """

    KEY_PREFIX = "argus_"
    KEY_LENGTH = 32  # Characters after prefix

    def generate_api_key(
        self,
        db: Session,
        name: str,
        scopes: list[str],
        created_by: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        rate_limit_per_minute: int = 100,
    ) -> tuple[APIKey, str]:
        """
        Generate a new API key.

        Args:
            db: Database session
            name: Descriptive name for the key
            scopes: List of permission scopes
            created_by: User ID of creator (optional)
            expires_at: Expiration timestamp (optional)
            rate_limit_per_minute: Max requests per minute

        Returns:
            Tuple of (APIKey model, plaintext_key)
            The plaintext_key is ONLY returned here and never stored.

        Raises:
            ValueError: If invalid scopes are provided
        """
        # Validate scopes
        invalid_scopes = set(scopes) - VALID_SCOPES
        if invalid_scopes:
            raise ValueError(f"Invalid scopes: {invalid_scopes}")

        # Generate cryptographically secure random key
        random_part = secrets.token_urlsafe(self.KEY_LENGTH)[:self.KEY_LENGTH]
        plaintext_key = f"{self.KEY_PREFIX}{random_part}"

        # Extract prefix for identification (first 8 chars of random part)
        prefix = random_part[:8]

        # Hash the full key with bcrypt (12 rounds)
        key_hash = bcrypt.hashpw(
            plaintext_key.encode('utf-8'),
            bcrypt.gensalt(rounds=12)
        ).decode('utf-8')

        api_key = APIKey(
            name=name,
            prefix=prefix,
            key_hash=key_hash,
            scopes=scopes,
            created_by=created_by,
            expires_at=expires_at,
            rate_limit_per_minute=rate_limit_per_minute,
        )

        db.add(api_key)
        db.commit()
        db.refresh(api_key)

        logger.info(
            f"API key created: {api_key.id}",
            extra={
                "event_type": "api_key_created",
                "api_key_id": api_key.id,
                "api_key_name": name,
                "prefix": f"argus_{prefix}...",
                "scopes": scopes,
                "created_by": created_by,
            }
        )

        return api_key, plaintext_key

    def verify_key(self, db: Session, plaintext_key: str) -> Optional[APIKey]:
        """
        Verify an API key and return the model if valid.

        Args:
            db: Database session
            plaintext_key: The full API key to verify

        Returns:
            APIKey model if valid, None otherwise
        """
        # Check key format
        if not plaintext_key.startswith(self.KEY_PREFIX):
            return None

        # Extract prefix for lookup
        random_part = plaintext_key[len(self.KEY_PREFIX):]
        if len(random_part) < 8:
            return None

        prefix = random_part[:8]

        # Find potential matches by prefix (active keys only)
        potential_keys = db.query(APIKey).filter(
            APIKey.prefix == prefix,
            APIKey.is_active == True,
        ).all()

        # Verify hash against each potential match
        for api_key in potential_keys:
            try:
                if bcrypt.checkpw(
                    plaintext_key.encode('utf-8'),
                    api_key.key_hash.encode('utf-8')
                ):
                    # Check expiration
                    if api_key.is_expired():
                        logger.warning(
                            f"API key expired: {api_key.id}",
                            extra={
                                "event_type": "api_key_expired",
                                "api_key_id": api_key.id,
                            }
                        )
                        return None

                    return api_key
            except Exception as e:
                logger.error(f"Error verifying API key: {e}")
                continue

        return None

    def list_keys(
        self,
        db: Session,
        include_revoked: bool = False,
    ) -> list[APIKey]:
        """
        List all API keys.

        Args:
            db: Database session
            include_revoked: Whether to include revoked keys

        Returns:
            List of APIKey models
        """
        query = db.query(APIKey)

        if not include_revoked:
            query = query.filter(APIKey.is_active == True)

        return query.order_by(desc(APIKey.created_at)).all()

    def get_key(self, db: Session, key_id: str) -> Optional[APIKey]:
        """
        Get a specific API key by ID.

        Args:
            db: Database session
            key_id: UUID of the API key

        Returns:
            APIKey model or None if not found
        """
        return db.query(APIKey).filter(APIKey.id == key_id).first()

    def revoke_key(
        self,
        db: Session,
        key_id: str,
        revoked_by: Optional[str] = None,
    ) -> Optional[APIKey]:
        """
        Revoke an API key.

        Args:
            db: Database session
            key_id: UUID of the API key to revoke
            revoked_by: User ID of the person revoking

        Returns:
            Updated APIKey model or None if not found
        """
        api_key = self.get_key(db, key_id)
        if not api_key:
            return None

        api_key.revoke(revoked_by)
        db.commit()
        db.refresh(api_key)

        logger.info(
            f"API key revoked: {api_key.id}",
            extra={
                "event_type": "api_key_revoked",
                "api_key_id": api_key.id,
                "api_key_name": api_key.name,
                "revoked_by": revoked_by,
            }
        )

        return api_key

    def record_usage(
        self,
        db: Session,
        api_key: APIKey,
        ip_address: Optional[str] = None,
    ) -> None:
        """
        Record API key usage.

        Args:
            db: Database session
            api_key: APIKey model to update
            ip_address: Client IP address
        """
        api_key.record_usage(ip_address)
        db.commit()


# Backward compatible thin getter (delegates to @singleton decorator)
def get_api_key_service() -> APIKeyService:
    """
    Get the global APIKeyService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer APIKeyService() directly.
    """
    return APIKeyService()


def reset_api_key_service() -> None:
    """Reset the global APIKeyService instance (for testing)."""
    APIKeyService._reset_instance()
