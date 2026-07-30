"""Database (PostgreSQL via SQLAlchemy) and Redis connection helpers."""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

Base = declarative_base()

_engine = None
_SessionLocal = None
_redis = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        if not settings.database_url:
            raise RuntimeError(
                "DATABASE_URL is not configured. Set it in the environment / .env."
            )
        # SQLite needs check_same_thread=False so sessions can be used across the
        # worker threads FastAPI runs sync DB dependencies in.
        connect_args = {}
        if settings.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(
            settings.database_url, pool_pre_ping=True, future=True,
            connect_args=connect_args,
        )
        _SessionLocal = sessionmaker(
            bind=_engine, autoflush=False, autocommit=False, future=True
        )
    return _engine


def get_session():
    if _SessionLocal is None:
        get_engine()
    return _SessionLocal()


def init_db() -> None:
    """Create all tables. Used for local bootstrap; production uses migrations."""
    from app import models  # noqa: F401  (register models on Base)

    Base.metadata.create_all(bind=get_engine())


def get_redis():
    global _redis
    if _redis is None:
        # Local-dev fallback: a `fakeredis://` URL runs an in-process Redis so the
        # service boots without a separate Redis server. Production uses a real
        # redis:// URL (see docker-compose.yml).
        if settings.redis_url.startswith("fakeredis://") or os.environ.get(
            "REDIS_FAKE"
        ):
            import fakeredis

            _redis = fakeredis.FakeStrictRedis(decode_responses=True)
        else:
            import redis

            _redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def get_db():
    """FastAPI dependency yielding a database session."""
    session = get_session()
    try:
        yield session
    finally:
        session.close()
