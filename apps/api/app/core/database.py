import os
import threading
import time

from sqlalchemy import create_engine, event
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import settings
from app.modules.guard.observability.metrics import (
    SQLALCHEMY_POOL_CHECKINS,
    SQLALCHEMY_POOL_CHECKOUT_DURATION,
    SQLALCHEMY_POOL_CHECKOUTS,
    SQLALCHEMY_POOL_CONNECTIONS_CURRENT,
    SQLALCHEMY_POOL_INVALIDATIONS,
    SQLALCHEMY_POOL_TIMEOUTS,
)

_CHECKOUT_STARTED_KEY = "conduct_pool_checkout_started"
_POOL_METRICS_REGISTERED_ATTR = "_conduct_metrics_registered"
_POOL_METRICS_REGISTRATION_LOCK = threading.Lock()


class InstrumentedQueuePool(QueuePool):
    """QueuePool with timeout accounting and otherwise unchanged behavior."""

    def _do_get(self):
        try:
            return super()._do_get()
        except SQLAlchemyTimeoutError:
            SQLALCHEMY_POOL_TIMEOUTS.inc()
            raise


def _pool_checkout(_dbapi_connection, connection_record, _connection_proxy) -> None:
    connection_record.info[_CHECKOUT_STARTED_KEY] = time.monotonic()
    SQLALCHEMY_POOL_CHECKOUTS.inc()
    SQLALCHEMY_POOL_CONNECTIONS_CURRENT.inc()


def _pool_checkin(_dbapi_connection, connection_record) -> None:
    started = connection_record.info.pop(_CHECKOUT_STARTED_KEY, None)
    if started is not None:
        SQLALCHEMY_POOL_CHECKOUT_DURATION.observe(
            max(0.0, time.monotonic() - started)
        )
        SQLALCHEMY_POOL_CONNECTIONS_CURRENT.dec()
    SQLALCHEMY_POOL_CHECKINS.inc()


def _pool_invalidate(_dbapi_connection, _connection_record, _exception) -> None:
    SQLALCHEMY_POOL_INVALIDATIONS.inc()


def _pool_soft_invalidate(_dbapi_connection, _connection_record, _exception) -> None:
    SQLALCHEMY_POOL_INVALIDATIONS.inc()


def _register_pool_metrics(pool: QueuePool) -> None:
    """Attach listeners once even if initialization calls us repeatedly."""
    if getattr(pool, _POOL_METRICS_REGISTERED_ATTR, False):
        return
    with _POOL_METRICS_REGISTRATION_LOCK:
        if getattr(pool, _POOL_METRICS_REGISTERED_ATTR, False):
            return
        event.listen(pool, "checkout", _pool_checkout)
        event.listen(pool, "checkin", _pool_checkin)
        event.listen(pool, "invalidate", _pool_invalidate)
        event.listen(pool, "soft_invalidate", _pool_soft_invalidate)
        setattr(pool, _POOL_METRICS_REGISTERED_ATTR, True)


def _pool_int(name: str, default: int, *, minimum: int = 1) -> int:
    """Parse a pool-config env var with a configurable low-end clamp."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


# Pool sizing remains configurable so the shared Postgres instance is not
# oversubscribed. Instrumentation does not alter sizing or exception behavior.
engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 5},
    poolclass=InstrumentedQueuePool,
    pool_size=_pool_int("SQLALCHEMY_POOL_SIZE", 5),
    max_overflow=_pool_int("SQLALCHEMY_MAX_OVERFLOW", 10, minimum=0),
)
_register_pool_metrics(engine.pool)
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
