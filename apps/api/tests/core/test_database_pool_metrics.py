from __future__ import annotations

import pytest
from app.core.database import InstrumentedQueuePool, _register_pool_metrics
from app.modules.guard.observability.metrics import (
    SQLALCHEMY_POOL_CHECKINS,
    SQLALCHEMY_POOL_CHECKOUT_DURATION,
    SQLALCHEMY_POOL_CHECKOUTS,
    SQLALCHEMY_POOL_CONNECTIONS_CURRENT,
    SQLALCHEMY_POOL_INVALIDATIONS,
    SQLALCHEMY_POOL_TIMEOUTS,
)
from sqlalchemy import create_engine
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError


def _value(metric) -> float:
    return metric._value.get()


def _count_sample(metric):
    for family in metric.collect():
        for sample in family.samples:
            if sample.name.endswith("_count"):
                return sample
    raise AssertionError("metric has no _count sample")


def test_pool_metrics_registration_is_duplicate_safe_and_tracks_lifecycle():
    engine = create_engine("sqlite://", poolclass=InstrumentedQueuePool)
    _register_pool_metrics(engine.pool)
    _register_pool_metrics(engine.pool)

    checkouts_before = _value(SQLALCHEMY_POOL_CHECKOUTS)
    checkins_before = _value(SQLALCHEMY_POOL_CHECKINS)
    checkout_durations_before = _count_sample(
        SQLALCHEMY_POOL_CHECKOUT_DURATION
    ).value
    current_before = _value(SQLALCHEMY_POOL_CONNECTIONS_CURRENT)
    invalidations_before = _value(SQLALCHEMY_POOL_INVALIDATIONS)

    connection = engine.connect()
    assert _value(SQLALCHEMY_POOL_CHECKOUTS) == checkouts_before + 1
    assert _value(SQLALCHEMY_POOL_CONNECTIONS_CURRENT) == current_before + 1
    connection.close()

    assert (
        _count_sample(SQLALCHEMY_POOL_CHECKOUT_DURATION).value
        == checkout_durations_before + 1
    )
    assert engine.pool.checkedout() == 0
    assert _value(SQLALCHEMY_POOL_CHECKINS) == checkins_before + 1
    assert _value(SQLALCHEMY_POOL_CONNECTIONS_CURRENT) == current_before

    connection = engine.connect()
    connection.invalidate()
    connection.close()

    assert _value(SQLALCHEMY_POOL_INVALIDATIONS) == invalidations_before + 1
    assert _value(SQLALCHEMY_POOL_CHECKINS) == checkins_before + 2
    assert _value(SQLALCHEMY_POOL_CONNECTIONS_CURRENT) == current_before
    assert engine.pool.checkedout() == 0
    engine.dispose()


def test_pool_timeout_metric_preserves_timeout_exception():
    engine = create_engine(
        "sqlite://",
        poolclass=InstrumentedQueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.01,
    )
    _register_pool_metrics(engine.pool)
    first = engine.connect()
    timeouts_before = _value(SQLALCHEMY_POOL_TIMEOUTS)

    with pytest.raises(SQLAlchemyTimeoutError):
        engine.connect()

    assert _value(SQLALCHEMY_POOL_TIMEOUTS) == timeouts_before + 1
    first.close()
    engine.dispose()
