"""Unit tests for encryption utilities (Fernet AES-256)"""
import pytest
from app.utils.encryption import encrypt_password, decrypt_password, is_encrypted, mask_sensitive


class TestPasswordEncryption:
    """Test suite for password encryption/decryption"""

    def test_encrypt_password_returns_encrypted_prefix(self):
        """Encrypted password should start with 'encrypted:' marker"""
        password = "my_secret_password_123"
        encrypted = encrypt_password(password)

        assert encrypted.startswith("encrypted:")
        assert encrypted != password

    def test_encrypt_password_produces_different_output(self):
        """Encrypted password should be different from plain text"""
        password = "test_password"
        encrypted = encrypt_password(password)

        assert encrypted != password
        assert len(encrypted) > len(password)

    def test_encrypt_empty_password(self):
        """Empty password should return empty string"""
        encrypted = encrypt_password("")
        assert encrypted == ""

    def test_encrypt_none_password(self):
        """None password should return empty string"""
        encrypted = encrypt_password(None)
        assert encrypted == ""

    def test_encrypt_already_encrypted_password(self):
        """Already encrypted password should not be double-encrypted"""
        password = "test_password"
        encrypted_once = encrypt_password(password)
        encrypted_twice = encrypt_password(encrypted_once)

        assert encrypted_once == encrypted_twice

    def test_decrypt_password_returns_original(self):
        """Decrypted password should match original plain text"""
        original = "my_secret_password_123"
        encrypted = encrypt_password(original)
        decrypted = decrypt_password(encrypted)

        assert decrypted == original

    def test_decrypt_empty_password(self):
        """Empty encrypted password should return empty string"""
        decrypted = decrypt_password("")
        assert decrypted == ""

    def test_decrypt_non_encrypted_password(self):
        """Non-encrypted password should return as-is (backward compatibility)"""
        plain = "plain_text_password"
        decrypted = decrypt_password(plain)

        # Should log warning but return the plain text
        assert decrypted == plain

    def test_decrypt_invalid_encrypted_format(self):
        """Invalid encrypted format should raise ValueError"""
        invalid = "encrypted:invalid_base64_garbage!!!"

        with pytest.raises(ValueError, match="Failed to decrypt password"):
            decrypt_password(invalid)

    def test_roundtrip_encryption_decryption(self):
        """Encrypt then decrypt should return original password"""
        test_passwords = [
            "simple",
            "with spaces and symbols !@#$%",
            "unicode_test_éàü中文",
            "very_long_password_" * 10,
        ]

        for password in test_passwords:
            encrypted = encrypt_password(password)
            decrypted = decrypt_password(encrypted)
            assert decrypted == password, f"Roundtrip failed for: {password}"


class TestIsEncrypted:
    """Test suite for is_encrypted helper function"""

    def test_is_encrypted_returns_true_for_encrypted_values(self):
        """is_encrypted should return True for values with encrypted: prefix"""
        encrypted = encrypt_password("test_password")
        assert is_encrypted(encrypted) is True

    def test_is_encrypted_returns_false_for_plain_text(self):
        """is_encrypted should return False for plain text"""
        assert is_encrypted("plain_text") is False

    def test_is_encrypted_returns_false_for_empty_string(self):
        """is_encrypted should return False for empty string"""
        assert is_encrypted("") is False

    def test_is_encrypted_returns_false_for_none(self):
        """is_encrypted should return False for None"""
        assert is_encrypted(None) is False

    def test_is_encrypted_returns_true_for_prefix_only(self):
        """is_encrypted should return True for encrypted: prefix even without valid data"""
        assert is_encrypted("encrypted:invalid_but_has_prefix") is True


class TestMaskSensitive:
    """Test suite for mask_sensitive helper function"""

    def test_mask_sensitive_shows_last_4_chars(self):
        """mask_sensitive should show only last 4 characters by default"""
        result = mask_sensitive("sk-1234567890abcdef")
        assert result == "****cdef"

    def test_mask_sensitive_short_string(self):
        """mask_sensitive should return **** for strings <= show_chars"""
        assert mask_sensitive("abc") == "****"
        assert mask_sensitive("abcd") == "****"

    def test_mask_sensitive_empty_string(self):
        """mask_sensitive should return **** for empty string"""
        assert mask_sensitive("") == "****"

    def test_mask_sensitive_none(self):
        """mask_sensitive should return **** for None"""
        assert mask_sensitive(None) == "****"

    def test_mask_sensitive_encrypted_value(self):
        """mask_sensitive should hide encrypted values completely"""
        encrypted = encrypt_password("test_password")
        result = mask_sensitive(encrypted)
        assert result == "****[encrypted]"

    def test_mask_sensitive_custom_show_chars(self):
        """mask_sensitive should respect custom show_chars parameter"""
        result = mask_sensitive("sk-1234567890abcdef", show_chars=6)
        assert result == "****abcdef"

    def test_mask_sensitive_api_key_examples(self):
        """mask_sensitive should work with various API key formats"""
        # OpenAI
        assert mask_sensitive("sk-proj-123456789abcdef")[-4:] == "cdef"
        # Anthropic
        assert mask_sensitive("sk-ant-api03-123456789")[-4:] == "6789"
        # Google
        assert mask_sensitive("AIzaSyD-12345678901234")[-4:] == "1234"
