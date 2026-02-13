"""
Synchronous database engine and session for Celery workers.

Mirrors database.py but uses psycopg2 (sync) instead of asyncpg.
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine_sync = create_engine(
    settings.database_url_sync,
    echo=settings.DEBUG,
    pool_size=5,
    max_overflow=0,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(
    bind=engine_sync,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@contextmanager
def get_sync_db() -> Generator[Session, None, None]:
    """
    Context manager para sessao sincrona do banco.

    Uso:
        with get_sync_db() as db:
            db.query(...)
    """
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
