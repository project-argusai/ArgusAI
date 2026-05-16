"""Fernet encryption utilities for sensitive data (camera passwords, API keys)"""
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Module-level ciphers and primary key
_primary_cipher: Fernet
_fallback_ciphers: list[Fernet] = []
_primary_key: str = ""  # Store raw primary key for rotation tooling


def _initialize_encryption_ciphers() -> None:
    """
    Initialize primary and fallback Fernet ciphers from settings.

    Supports key rotation by allowing multiple keys:
    - The first key is the primary (used for encryption)
    - Subsequent keys are fallbacks (used only for decryption)
    """
    global _primary_cipher, _fallback_ciphers

    keys: list[str] = []

    # Primary key (required)
    if settings.ENCRYPTION_KEY:
        keys.append(settings.ENCRYPTION_KEY.strip())

    # Support for previous key (simple rotation)
    previous_key = getattr(settings, 'ENCRYPTION_KEY_PREVIOUS', None)
    if previous_key and previous_key.strip():
        keys.append(previous_key.strip())

    if not keys:
        raise ValueError(
            "ENCRYPTION_KEY is required. "
            "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )

    try:
        _primary_key = keys[0]
        _primary_cipher = Fernet(_primary_key.encode())
        _fallback_ciphers = [Fernet(key.encode()) for key in keys[1:]]
    except Exception as e:
        logger.error(f"Failed to initialize encryption ciphers: {e}")
        raise ValueError(
            "Invalid ENCRYPTION_KEY. Generate a new key with: "
            "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )


# Initialize on import
_initialize_encryption_ciphers()


def encrypt_password(password: str) -> str:
    """
    Encrypt a password using Fernet (AES-256 symmetric encryption)
    
    Args:
        password: Plain text password to encrypt
        
    Returns:
        Encrypted password prefixed with 'encrypted:' marker
        
    Example:
        >>> encrypt_password("my_secret_123")
        'encrypted:gAAAAABh...'
    """
    if not password:
        return ""
    
    # Avoid double encryption
    if password.startswith("encrypted:"):
        return password
    
    try:
        encrypted_bytes = _primary_cipher.encrypt(password.encode())
        return f"encrypted:{encrypted_bytes.decode()}"
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise ValueError("Failed to encrypt password")


def is_encrypted(value: str) -> bool:
    """
    Check if a value is already encrypted (has 'encrypted:' prefix)

    Args:
        value: String to check

    Returns:
        True if value starts with 'encrypted:', False otherwise
    """
    if not value:
        return False
    return value.startswith("encrypted:")


def mask_sensitive(value: str, show_chars: int = 4) -> str:
    """
    Mask sensitive value for logging, showing only last N characters

    Args:
        value: Sensitive string to mask
        show_chars: Number of characters to show at the end (default: 4)

    Returns:
        Masked string like '****abcd' or '****' if too short

    Example:
        >>> mask_sensitive("sk-1234567890abcdef")
        '****cdef'
        >>> mask_sensitive("short")
        '****'
    """
    if not value:
        return "****"

    # Don't reveal encrypted values at all
    if value.startswith("encrypted:"):
        return "****[encrypted]"

    if len(value) <= show_chars:
        return "****"

    return "****" + value[-show_chars:]


def get_primary_encryption_key() -> str:
    """
    Returns the current primary encryption key (used for new encryptions).
    Useful for key rotation tooling.
    """
    return _primary_key


def decrypt_password(encrypted_password: str) -> str:
    """
    Decrypt a Fernet-encrypted password
    
    Args:
        encrypted_password: Encrypted password string with 'encrypted:' prefix
        
    Returns:
        Plain text password
        
    Raises:
        ValueError: If decryption fails or format is invalid
        
    Example:
        >>> decrypt_password("encrypted:gAAAAABh...")
        'my_secret_123'
    """
    if not encrypted_password:
        return ""
    
    # Return as-is if not encrypted (backward compatibility)
    if not encrypted_password.startswith("encrypted:"):
        logger.warning("Attempted to decrypt non-encrypted password")
        return encrypted_password
    
    # Remove prefix and decrypt
    encrypted_data = encrypted_password.replace("encrypted:", "", 1)

    # Try primary key first, then fallback keys (supports key rotation)
    all_ciphers = [_primary_cipher] + _fallback_ciphers

    for cipher in all_ciphers:
        try:
            decrypted_bytes = cipher.decrypt(encrypted_data.encode())
            return decrypted_bytes.decode()
        except InvalidToken:
            continue  # Try next key
        except Exception as e:
            logger.error(f"Decryption failed with one key: {e}")
            continue

    logger.error("Decryption failed: Invalid token or wrong encryption key (tried all keys)")
    raise ValueError("Failed to decrypt password - invalid token or wrong encryption key")
