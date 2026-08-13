"""Unit tests for SessionService refresh-token reuse detection (Issue #520)."""
import os
import tempfile
import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-not-for-production")
os.environ.setdefault(
    "ENCRYPTION_KEY", "YhLHon9m3QOhb394b-Qa761Vgj9ij3oLlT-moS2oRcg="
)

from app.core.database import Base
from app.models.user import User
from app.models.session import Session
from app.models.consumed_refresh_token import ConsumedRefreshToken
from app.services.session_service import SessionService
from app.utils.auth import hash_password
from app.utils.jwt import create_access_token


def _mock_request(ip: str = "127.0.0.1"):
    request = MagicMock()
    request.headers = {"User-Agent": "pytest"}
    request.client.host = ip
    return request


class TestRefreshTokenReuseDetection:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )
        self.db = self.SessionLocal()

        self.user = User(
            id=str(uuid.uuid4()),
            username="reuseuser",
            password_hash=hash_password("TestPass123!"),
            is_active=True,
        )
        self.db.add(self.user)
        self.db.commit()

        yield

        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_replay_of_rotated_token_revokes_family(self):
        service = SessionService(self.db)
        request = _mock_request()
        access = create_access_token(self.user.id, self.user.username)

        session, original_refresh = service.create_web_session_with_refresh(
            self.user, access, request
        )
        family = session.refresh_token_family

        new_access, new_refresh, _ = service.refresh_tokens(original_refresh, request)
        assert new_refresh != original_refresh

        consumed = (
            self.db.query(ConsumedRefreshToken)
            .filter(ConsumedRefreshToken.token_family == family)
            .all()
        )
        assert len(consumed) == 1
        assert consumed[0].token_hash == Session.hash_token(original_refresh)

        with pytest.raises(ValueError, match="refresh_token_reuse_detected"):
            service.refresh_tokens(original_refresh, request)

        live = (
            self.db.query(Session)
            .filter(Session.refresh_token_family == family)
            .first()
        )
        assert live is not None
        assert live.refresh_revoked_at is not None
        assert live.refresh_revoked_reason == "reuse_detected"

        with pytest.raises(ValueError, match="Refresh token expired or revoked"):
            service.refresh_tokens(new_refresh, request)

    def test_unknown_token_is_not_reuse(self):
        service = SessionService(self.db)
        with pytest.raises(ValueError, match="Invalid refresh token"):
            service.refresh_tokens("not-a-real-refresh-token", _mock_request())
