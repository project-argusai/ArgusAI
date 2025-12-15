"""
Shared pytest fixtures for API tests.

This module provides database isolation for API tests to prevent cross-test pollution.
Each test module that imports `client` will get a fresh, isolated database.
"""
import os
import tempfile
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from main import app
from app.core.database import Base, get_db


# Store the original dependency to restore it after tests
_original_get_db = get_db


def _create_test_database(use_file=True):
    """
    Create a test database engine and session factory.

    Args:
        use_file: If True, use a temp file database. If False, use in-memory.
                  File-based is needed for some tests with threading issues.

    Returns:
        Tuple of (engine, SessionLocal, cleanup_func)
    """
    if use_file:
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db_url = f"sqlite:///{path}"
        cleanup = lambda: os.path.exists(path) and os.remove(path)
    else:
        db_url = "sqlite:///:memory:"
        cleanup = lambda: None
        path = None

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    return engine, SessionLocal, cleanup, path


@pytest.fixture(scope="module")
def test_db():
    """
    Create a test database for the module.

    This fixture creates tables at the start of the module and drops them at the end.
    Each module gets its own isolated database.
    """
    engine, SessionLocal, cleanup, db_path = _create_test_database(use_file=True)

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create FTS5 virtual table if needed (for events tests)
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE VIRTUAL TABLE IF NOT EXISTS events_fts
                USING fts5(
                    id UNINDEXED,
                    description,
                    content='events',
                    content_rowid='rowid'
                )
            """))
            conn.execute(text("""
                CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
                    INSERT INTO events_fts(rowid, id, description)
                    VALUES (new.rowid, new.id, new.description);
                END
            """))
            conn.execute(text("""
                CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
                    UPDATE events_fts
                    SET description = new.description
                    WHERE rowid = old.rowid;
                END
            """))
            conn.execute(text("""
                CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
                    DELETE FROM events_fts WHERE rowid = old.rowid;
                END
            """))
            conn.commit()
    except Exception:
        # FTS5 setup may fail in some environments - that's OK for non-event tests
        pass

    yield {
        "engine": engine,
        "SessionLocal": SessionLocal,
        "db_path": db_path,
    }

    # Cleanup
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    cleanup()


@pytest.fixture(scope="function")
def db_session(test_db):
    """
    Get a database session for a test.

    This provides a fresh session for each test function.
    """
    session = test_db["SessionLocal"]()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def api_client(test_db):
    """
    Create an API test client with proper database isolation.

    This fixture:
    1. Overrides get_db to use the test database
    2. Provides a TestClient
    3. Cleans up the database after the test
    4. Restores the original get_db
    """
    SessionLocal = test_db["SessionLocal"]

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # Apply the override
    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)

    yield client

    # Clean up all data after test (but keep tables)
    db = SessionLocal()
    try:
        # Delete from all tables
        for table in reversed(Base.metadata.sorted_tables):
            try:
                db.execute(table.delete())
            except Exception:
                pass
        db.commit()
    finally:
        db.close()

    # Note: We don't restore the original override here since
    # other tests in the same module may still need the override.
    # It will be properly cleaned up at module teardown.


@pytest.fixture(scope="session", autouse=True)
def ensure_test_database_setup():
    """
    Ensure a clean test database is available at session start.

    This runs once at the beginning of the test session and sets up a default
    test database for any tests that don't set up their own.
    """
    # Create a default test database for tests that don't set up their own
    engine, SessionLocal, cleanup, _ = _create_test_database(use_file=True)
    Base.metadata.create_all(bind=engine)

    def default_override_get_db():
        db = SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # Set a default override that tests can rely on
    app.dependency_overrides[get_db] = default_override_get_db

    yield

    # Cleanup at end of session
    if get_db in app.dependency_overrides:
        del app.dependency_overrides[get_db]
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    cleanup()


@pytest.fixture(scope="module", autouse=True)
def cleanup_overrides():
    """
    Ensure dependency overrides are properly cleaned up after module tests.
    """
    yield
    # Note: We don't delete the override here anymore since the session-level
    # fixture provides a default. Individual test modules can override get_db
    # and their override will be used until the module completes.
