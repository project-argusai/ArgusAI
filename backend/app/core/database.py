"""Database connection and session management"""
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool, StaticPool
from app.core.config import settings
from app.core.logging_config import configure_sqlalchemy_query_logging

# Configure engine based on database type
# Story P10-2.5: Add PostgreSQL support
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine_kwargs = {
    # Statement logging is opt-in (SQL_ECHO / DB_ECHO). DEBUG and LOG_LEVEL
    # must not turn this on; per-query logs fill the rotated app log.
    "echo": settings.sql_echo_enabled,
    # pool_pre_ping issues a lightweight liveness check before handing out a
    # connection, transparently replacing ones dropped by the DB/network while
    # idle. Safe for both SQLite and PostgreSQL.
    "pool_pre_ping": settings.DB_POOL_PRE_PING,
    "pool_recycle": settings.DB_POOL_RECYCLE,
}

if _is_sqlite:
    # SQLite requires check_same_thread=False for multi-threaded access (camera
    # threads + asyncio workers). Do not use QueuePool here. SQLAlchemy's
    # default QueuePool is size 5, overflow 10, timeout 30s, and that checkout
    # waits on a threading lock. When the wait runs on the asyncio thread, the
    # whole process stops serving, including /health. File SQLite opens a
    # connection per checkout and closes it on return (NullPool). An in-memory
    # URL must share one connection (StaticPool) or each checkout is empty.
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    _memory = ":memory:" in settings.DATABASE_URL or "mode=memory" in settings.DATABASE_URL
    engine_kwargs["poolclass"] = StaticPool if _memory else NullPool
else:
    # PostgreSQL (prod): bound the connection pool explicitly so concurrent
    # workers/replicas cannot exhaust the server's max_connections. All values
    # are env-driven (12-Factor III) and default to SQLAlchemy's own defaults.
    engine_kwargs.update(
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
    )

# Create SQLAlchemy engine
engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
# echo=True installs an InstanceLogger that emits SQL at INFO regardless of
# the sqlalchemy logger level. Keep that logger at WARNING unless opted in,
# including when the process root logger is DEBUG.
configure_sqlalchemy_query_logging(settings.sql_echo_enabled)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """Turn on SQLite foreign-key enforcement for this connection.

    SQLite leaves foreign keys off unless every connection runs
    ``PRAGMA foreign_keys=ON``. Without it, ``ON DELETE CASCADE`` never runs
    and event child rows (entity_events, frames, embeddings, ...) are orphaned.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


if _is_sqlite:
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()


def release_db_connection(db: Optional[Session]) -> None:
    """Return a request session's connection before slow work.

    ``rollback()`` ends the read transaction and gives the connection back to
    the pool (or closes it, for SQLite's NullPool). Call this before file or
    network I/O on a ``Depends(get_db)`` session. A later ``close()`` from the
    dependency is safe. Do not use ORM objects loaded by ``db`` after this.
    """
    if db is None:
        return
    rollback = getattr(db, "rollback", None)
    if not callable(rollback):
        return
    rollback()


def get_db():
    """Dependency for FastAPI routes to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions in non-request contexts.

    Use this for background tasks, services, and middleware where
    FastAPI dependency injection is not available.

    Usage:
        with get_db_session() as db:
            result = db.query(Model).all()
            db.commit()  # If modifications made

    Automatically handles:
    - Session creation
    - Rollback on exception
    - Session cleanup (close)

    Story P14-2.1: Standardize database session management
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
