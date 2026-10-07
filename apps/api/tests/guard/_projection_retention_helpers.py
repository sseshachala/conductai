"""Shared fake ORM models, fixtures and row builders for the Guard
projection-retention tests (``test_projection_retention*.py``).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import DateTime, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.modules.guard import projection_retention as retention


class Base(DeclarativeBase):
    pass


class FakeKnowledge(Base):
    __tablename__ = "fake_projection_knowledge"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, nullable=False)
    source_kind: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FakeIntent(Base):
    __tablename__ = "fake_projection_intents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, nullable=False)
    source_kind: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FakeAuditEvent(Base):
    __tablename__ = 'fake_projection_audit_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FakeSummary(Base):
    __tablename__ = "fake_projection_summaries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FakeIntentWithoutSourceKind(Base):
    __tablename__ = "fake_projection_intents_without_source_kind"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FakeGuardAuditEvent(Base):
    __tablename__ = "fake_guard_audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


MODELS = {"knowledge": FakeKnowledge, "intent": FakeIntent, "summary": FakeSummary, "audit_event": FakeAuditEvent}
NOW = datetime(2026, 10, 3, 20, 38, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _disable_rls_sql(monkeypatch):
    monkeypatch.setattr(retention, "set_workspace_rls", lambda db, workspace_id: None)


def _session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)


def _session():
    _, factory = _session_factory()
    return factory()


def _knowledge(session, workspace, kind, expires_at, *, updated_at=None):
    row = FakeKnowledge(
        workspace_id=workspace,
        source_kind=kind,
        source_id=str(id(object())),
        source_timestamp=None,
        expires_at=expires_at,
        updated_at=updated_at,
    )
    session.add(row)
    return row


def _summary(session, workspace, expires_at):
    row = FakeSummary(
        workspace_id=workspace,
        window_end=expires_at - timedelta(days=30),
        source_timestamp=expires_at - timedelta(days=30),
        expires_at=expires_at,
    )
    session.add(row)
    session.flush()
    return row


def _intent(session, workspace, status, expires_at, *, source_kind="audit_event"):
    row = FakeIntent(
        workspace_id=workspace,
        source_kind=source_kind,
        source_id=f"source-{workspace}-{status}",
        status=status,
        expires_at=expires_at,
    )
    session.add(row)
    return row
