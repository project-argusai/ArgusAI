"""Session cookie SameSite default matches the same-site web topology."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

FERNET = "YhLHon9m3QOhb394b-Qa761Vgj9ij3oLlT-moS2oRcg="
JWT = "test-jwt-secret-for-testing-must-be-at-least-32-chars-long"


def _settings(monkeypatch, **overrides):
    monkeypatch.delenv("COOKIE_SAMESITE", raising=False)
    return Settings(
        _env_file=None,
        ENCRYPTION_KEY=FERNET,
        JWT_SECRET_KEY=JWT,
        SSL_CERT_FILE=None,
        SSL_KEY_FILE=None,
        **overrides,
    )


def test_default_samesite_is_lax(monkeypatch):
    settings = _settings(monkeypatch)
    assert settings.COOKIE_SAMESITE == "lax"
    assert settings.COOKIE_SECURE is True


@pytest.mark.parametrize("raw,expected", [("lax", "lax"), ("Lax", "lax"), ("NONE", "none"), ("strict", "strict")])
def test_samesite_values_are_normalized(monkeypatch, raw, expected):
    settings = _settings(monkeypatch, COOKIE_SAMESITE=raw)
    assert settings.COOKIE_SAMESITE == expected


def test_samesite_rejects_unknown_values(monkeypatch):
    with pytest.raises(ValidationError):
        _settings(monkeypatch, COOKIE_SAMESITE="cross-site")
