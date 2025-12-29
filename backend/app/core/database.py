"""Database connection and session management"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

# Configure engine based on database type
# Story P10-2.5: Add PostgreSQL support
engine_kwargs = {
    "echo": settings.DEBUG,  # Log SQL queries in debug mode
}

# SQLite requires check_same_thread=False for multi-threaded access
# PostgreSQL doesn't need this and doesn't support it
if settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

# Create SQLAlchemy engine
engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()


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
