import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings


def _pool_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


# Pool sizing configurable via env so multiple web services on the same
# Postgres instance don't oversubscribe ``max_connections``. See the
# ``delegator-gateway`` block in ``render.yaml`` for the fleet-wide math.
engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 5},
    pool_size=_pool_int("SQLALCHEMY_POOL_SIZE", 5),
    max_overflow=_pool_int("SQLALCHEMY_MAX_OVERFLOW", 10),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
