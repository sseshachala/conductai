"""
Smoke tests for the AI-SDLC cycle — three automation connections.

Connection 1: Guard block → Security Loop scan
Connection 2: Security Loop finding → Workflow run (severity threshold)
Connection 3: Workflow run → SecurityFinding status feedback
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ── Env + module stubs ────────────────────────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

for _mod in ["structlog", "redis", "sentry_sdk",
             "app.runtime.llm_client", "app.runtime.model_router",
             "app.core.crypto", "app.runtime.integrations.slack"]:
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["structlog"].get_logger = MagicMock(return_value=MagicMock())

from sqlalchemy import create_engine, types as _sa_types
from sqlalchemy.orm import declarative_base, sessionmaker
import sqlalchemy.dialects.postgresql as _pg_dialect

_pg_dialect.JSONB = _sa_types.JSON
_pg_dialect.ARRAY = _sa_types.JSON

class _SQLiteUUID(_sa_types.TypeDecorator):
    impl = _sa_types.String(36)
    cache_ok = True
    def process_bind_param(self, v, d): return str(v) if v is not None else None
    def process_result_value(self, v, d): return v

_pg_dialect.UUID = lambda *a, **kw: _SQLiteUUID()

_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Base = declarative_base()
_db_mod = MagicMock()
_db_mod.Base = _Base
_db_mod.SessionLocal = sessionmaker(bind=_engine)
_db_mod.engine = _engine
sys.modules["app.core.database"] = _db_mod

import app.models  # noqa
from app.models.environment import Environment  # noqa — registers environments table
from app.models.security_finding import SecurityFinding
from app.models.security_config import SecurityConfig
from app.models.workflow import Workflow, WorkflowVersion
from app.models.run import Run
from app.modules.guard.models import GuardConfig, GuardAuditEvent
from app.models.workspace import Workspace

_Base.metadata.create_all(_engine)

_Session = sessionmaker(bind=_engine)


@pytest.fixture
def db():
    conn = _engine.connect()
    tx = conn.begin()
    session = _Session(bind=conn)
    yield session
    session.close()
    tx.rollback()
    conn.close()


def _ws_id() -> str:
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


def _make_workspace(db, ws_id: str):
    ws = Workspace(id=uuid.UUID(ws_id), name="test-ws",
                   created_at=_now(), updated_at=_now())
    db.add(ws)
    db.flush()
    return ws


def _make_guard_config(db, ws_id: str, **kwargs) -> GuardConfig:
    cfg = GuardConfig(
        workspace_id=uuid.UUID(ws_id),
        invite_code="testcode",
        automation_security_scan=kwargs.get("automation_security_scan", False),
        automation_workflow_trigger=kwargs.get("automation_workflow_trigger", False),
    )
    db.add(cfg)
    db.flush()
    return cfg


def _make_security_config(db, ws_id: str, **kwargs) -> SecurityConfig:
    cfg = SecurityConfig(
        workspace_id=uuid.UUID(ws_id),
        installed=True,
        security_emit_enabled=True,
        automation_workflow_on_finding=kwargs.get("automation_workflow_on_finding", False),
        automation_finding_severity=kwargs.get("automation_finding_severity", "critical"),
    )
    db.add(cfg)
    db.flush()
    return cfg


def _make_finding(db, ws_id: str, severity="critical") -> SecurityFinding:
    f = SecurityFinding(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        tool="claude_code",
        severity=severity,
        type="secret_leak",
        description="test finding",
        status="open",
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(f)
    db.flush()
    return f


def _make_workflow(db, ws_id: str, slug: str) -> tuple[Workflow, WorkflowVersion]:
    wf = Workflow(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        name=slug,
        playbook_slug=slug,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(wf)
    db.flush()
    ver = WorkflowVersion(
        id=uuid.uuid4(),
        workflow_id=wf.id,
        created_at=_now(),
    )
    db.add(ver)
    db.flush()
    wf.current_version_id = ver.id
    db.flush()
    return wf, ver


# ─── Connection 2: _maybe_trigger_automation_workflow ────────────────────────

class TestConnection2:
    def test_skips_when_toggle_off(self, db):
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        _make_security_config(db, ws_id, automation_workflow_on_finding=False)
        finding = _make_finding(db, ws_id, severity="critical")

        from app.routers.security import _maybe_trigger_automation_workflow
        with patch("app.routers.security._enqueue_run") as mock_enqueue:
            _maybe_trigger_automation_workflow(finding, ws_id, db)
            mock_enqueue.assert_not_called()

    def test_skips_when_severity_below_threshold(self, db):
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        _make_security_config(db, ws_id, automation_workflow_on_finding=True,
                               automation_finding_severity="critical")
        finding = _make_finding(db, ws_id, severity="low")
        _make_workflow(db, ws_id, "incident-response")

        from app.routers.security import _maybe_trigger_automation_workflow
        with patch("app.routers.security._enqueue_run") as mock_enqueue:
            _maybe_trigger_automation_workflow(finding, ws_id, db)
            mock_enqueue.assert_not_called()

    def test_enqueues_run_when_threshold_met(self, db):
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        _make_security_config(db, ws_id, automation_workflow_on_finding=True,
                               automation_finding_severity="high")
        finding = _make_finding(db, ws_id, severity="critical")
        _make_workflow(db, ws_id, "incident-response")

        from app.routers.security import _maybe_trigger_automation_workflow
        with patch("app.routers.security._enqueue_run") as mock_enqueue:
            _maybe_trigger_automation_workflow(finding, ws_id, db)
            mock_enqueue.assert_called_once()

        run = db.query(Run).first()
        assert run is not None
        assert run.triggered_by == "security_finding_automation"
        assert run.state["_trigger"]["finding_id"] == str(finding.id)

    def test_skips_when_no_playbook_installed(self, db):
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        _make_security_config(db, ws_id, automation_workflow_on_finding=True,
                               automation_finding_severity="low")
        finding = _make_finding(db, ws_id, severity="critical")
        # no workflow created

        from app.routers.security import _maybe_trigger_automation_workflow
        with patch("app.routers.security._enqueue_run") as mock_enqueue:
            _maybe_trigger_automation_workflow(finding, ws_id, db)
            mock_enqueue.assert_not_called()

    def test_high_meets_high_threshold(self, db):
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        _make_security_config(db, ws_id, automation_workflow_on_finding=True,
                               automation_finding_severity="high")
        finding = _make_finding(db, ws_id, severity="high")
        _make_workflow(db, ws_id, "security-incident-response")

        from app.routers.security import _maybe_trigger_automation_workflow
        with patch("app.routers.security._enqueue_run") as mock_enqueue:
            _maybe_trigger_automation_workflow(finding, ws_id, db)
            mock_enqueue.assert_called_once()


# ─── Connection 3: _feedback_to_security_finding ─────────────────────────────

class TestConnection3:
    def _make_run(self, db, triggered_by: str, finding_id: str,
                  status: str = "succeeded", autopilot: bool = False) -> Run:
        run = Run(
            id=uuid.uuid4(),
            workflow_version_id=uuid.uuid4(),
            triggered_by=triggered_by,
            status=status,
            state={
                "_trigger": {
                    "finding_id": finding_id,
                    "event_type": triggered_by,
                    "autopilot_enabled": autopilot,
                }
            },
            created_at=_now(),
        )
        db.add(run)
        db.flush()
        return run

    def test_skips_unrelated_runs(self, db):
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        finding = _make_finding(db, ws_id)
        run = self._make_run(db, "manual", str(finding.id))

        from app.runtime.executor import _feedback_to_security_finding
        _feedback_to_security_finding(run, db)
        db.refresh(finding)
        assert finding.status == "open"  # untouched

    def test_triage_run_succeeded_without_autopilot_sets_triaging(self, db):
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        finding = _make_finding(db, ws_id)
        run = self._make_run(db, "security_finding", str(finding.id),
                              status="succeeded", autopilot=False)

        from app.runtime.executor import _feedback_to_security_finding
        _feedback_to_security_finding(run, db)
        db.refresh(finding)
        assert finding.status == "triaging"
        assert finding.source_run_id == str(run.id)

    def test_autopilot_run_succeeded_sets_fixed(self, db):
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        finding = _make_finding(db, ws_id)
        run = self._make_run(db, "security_finding", str(finding.id),
                              status="succeeded", autopilot=True)

        from app.runtime.executor import _feedback_to_security_finding
        _feedback_to_security_finding(run, db)
        db.refresh(finding)
        assert finding.status == "fixed"

    def test_automation_workflow_succeeded_sets_fixed(self, db):
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        finding = _make_finding(db, ws_id)
        run = self._make_run(db, "security_finding_automation", str(finding.id),
                              status="succeeded")

        from app.runtime.executor import _feedback_to_security_finding
        _feedback_to_security_finding(run, db)
        db.refresh(finding)
        assert finding.status == "fixed"

    def test_failed_triage_reopens_from_triaging(self, db):
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        finding = _make_finding(db, ws_id)
        finding.status = "triaging"
        db.flush()
        run = self._make_run(db, "security_finding", str(finding.id), status="failed")

        from app.runtime.executor import _feedback_to_security_finding
        _feedback_to_security_finding(run, db)
        db.refresh(finding)
        assert finding.status == "open"

    def test_missing_finding_id_is_noop(self, db):
        run = Run(
            id=uuid.uuid4(),
            workflow_version_id=uuid.uuid4(),
            triggered_by="security_finding",
            status="succeeded",
            state={"_trigger": {}},
            created_at=_now(),
        )
        db.add(run)
        db.flush()

        from app.runtime.executor import _feedback_to_security_finding
        _feedback_to_security_finding(run, db)  # must not raise
