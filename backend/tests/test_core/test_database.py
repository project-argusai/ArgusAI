"""Tests for database session management.

Story P14-2.1: Standardize Database Session Management
"""
import pytest
from unittest.mock import MagicMock, patch


class TestGetDbSession:
    """Test the get_db_session context manager (Story P14-2.1)."""

    def test_session_is_created(self):
        """AC-1: get_db_session creates a valid database session."""
        with patch("app.core.database.SessionLocal") as mock_session_local:
            mock_session = MagicMock()
            mock_session_local.return_value = mock_session

            from app.core.database import get_db_session

            with get_db_session() as db:
                assert db is mock_session
                mock_session_local.assert_called_once()

    def test_session_is_closed_on_success(self):
        """AC-4: Session is closed after successful context exit."""
        with patch("app.core.database.SessionLocal") as mock_session_local:
            mock_session = MagicMock()
            mock_session_local.return_value = mock_session

            from app.core.database import get_db_session

            with get_db_session() as db:
                db.query("SELECT 1")

            mock_session.close.assert_called_once()

    def test_session_is_closed_on_exception(self):
        """AC-4: Session is closed even when exception occurs."""
        with patch("app.core.database.SessionLocal") as mock_session_local:
            mock_session = MagicMock()
            mock_session_local.return_value = mock_session

            from app.core.database import get_db_session

            with pytest.raises(ValueError):
                with get_db_session() as db:
                    raise ValueError("Test exception")

            mock_session.close.assert_called_once()

    def test_rollback_on_exception(self):
        """AC-3: Session is rolled back when exception occurs."""
        with patch("app.core.database.SessionLocal") as mock_session_local:
            mock_session = MagicMock()
            mock_session_local.return_value = mock_session

            from app.core.database import get_db_session

            with pytest.raises(ValueError):
                with get_db_session() as db:
                    db.add(MagicMock())  # Simulate adding something
                    raise ValueError("Test exception")

            mock_session.rollback.assert_called_once()

    def test_no_rollback_on_success(self):
        """Session should not be rolled back on successful exit."""
        with patch("app.core.database.SessionLocal") as mock_session_local:
            mock_session = MagicMock()
            mock_session_local.return_value = mock_session

            from app.core.database import get_db_session

            with get_db_session() as db:
                db.query("SELECT 1")

            mock_session.rollback.assert_not_called()

    def test_exception_is_propagated(self):
        """Exceptions from within the context should propagate."""
        with patch("app.core.database.SessionLocal") as mock_session_local:
            mock_session = MagicMock()
            mock_session_local.return_value = mock_session

            from app.core.database import get_db_session

            with pytest.raises(RuntimeError, match="Test error"):
                with get_db_session() as db:
                    raise RuntimeError("Test error")

    def test_commit_within_context(self):
        """Explicit commits within the context should work."""
        with patch("app.core.database.SessionLocal") as mock_session_local:
            mock_session = MagicMock()
            mock_session_local.return_value = mock_session

            from app.core.database import get_db_session

            with get_db_session() as db:
                db.add(MagicMock())
                db.commit()

            mock_session.commit.assert_called_once()
            mock_session.close.assert_called_once()
            mock_session.rollback.assert_not_called()

    def test_nested_context_managers(self):
        """Multiple get_db_session contexts should work independently."""
        with patch("app.core.database.SessionLocal") as mock_session_local:
            session1 = MagicMock()
            session2 = MagicMock()
            mock_session_local.side_effect = [session1, session2]

            from app.core.database import get_db_session

            with get_db_session() as db1:
                with get_db_session() as db2:
                    assert db1 is session1
                    assert db2 is session2

            session1.close.assert_called_once()
            session2.close.assert_called_once()
