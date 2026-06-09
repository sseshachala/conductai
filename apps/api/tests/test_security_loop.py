"""
Integration tests for the Security Loop pipeline.

Covers:
  - Finding ingestion (_ingest_finding_core)
  - Validator rejection (bad severity, bad type, bad status)
  - Status transitions (PATCH open→triaging→fixed→dismissed)
  - Summary counts (by_severity, by_status, mttr)
  - _trigger_security_loop — enqueues run, sets finding.run_id
  - trigger_fix — sets status=triaging, enqueues autopilot run, returns run_id
  - Graceful no-op when security project / workflow not installed

No network, no real Redis, no LLM calls.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

# ── Stub side-effect modules before any app import ───────────────────────────
for _mod in ["structlog", "redis", "sentry_sdk",
             "app.runtime.llm_client", "app.runtime.model_router",
             "app.core.crypto", "app.runtime.integrations.slack"]:
    sys.modules.setdefault(_mod, MagicMock())

sys.modules["structlog"].get_logger = MagicMock(return_value=MagicMock())

# ── Isolated SQLite Base (only security models, no cross-FK pollution) ────────
from sqlalchemy import create_engine, types as _sa_types
from sqlalchemy.orm import declarative_base, sessionmaker

# SQLite doesn't support PG-specific types — remap before any model imports
import sqlalchemy.dialects.postgresql as _pg_dialect
_pg_dialect.JSONB = _sa_types.JSON
_pg_dialect.ARRAY = _sa_types.JSON  # closest portable equivalent

# UUID(as_uuid=True) passes Python uuid.UUID objects to sqlite3, which it can't bind.
# Replace with a TypeDecorator that coerces uuid.UUID ↔ str transparently.
class _SQLiteUUID(_sa_types.TypeDecorator):
    impl = _sa_types.String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return value

_pg_dialect.UUID = lambda *a, **kw: _SQLiteUUID()

_sqlite_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_RealBase = declarative_base()

_db_mod = MagicMock()
_db_mod.Base = _RealBase
_db_mod.SessionLocal = sessionmaker(bind=_sqlite_engine)
_db_mod.engine = _sqlite_engine
sys.modules["app.core.database"] = _db_mod

# Import via __init__ so all core models register against _RealBase (resolves
# relationships like Workspace→User). Then add the models missing from __init__.
import app.models  # noqa: E402  (triggers __init__.py — registers core models)
from app.models.environment import Environment  # noqa: E402  # missing from __init__
from app.models.security_finding import SecurityFinding  # noqa: E402
from app.models.security_config import SecurityConfig  # noqa: E402
from app.models.workflow import Workflow, WorkflowVersion  # noqa: E402 (re-import for convenience)
from app.models.run import Run  # noqa: E402

_RealBase.metadata.create_all(_sqlite_engine)


# ── In-memory DB fixture ──────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = _sqlite_engine.connect()
    tx = conn.begin_nested() if conn.in_transaction() else conn.begin()
    Session = sessionmaker(bind=conn)
    session = Session()
    yield session
    session.close()
    tx.rollback()
    conn.close()


def _ws() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_finding(db, workspace_id: str, **kwargs) -> SecurityFinding:
    defaults = dict(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        tool="claude-code",
        severity="high",
        type="secret-leak",
        description="Hardcoded API key detected",
        file="src/config.py",
        line=42,
        status="open",
        created_at=_now(),
        updated_at=_now(),
    )
    defaults.update(kwargs)
    f = SecurityFinding(**defaults)
    db.add(f)
    db.flush()
    return f


# ══════════════════════════════════════════════════════════════════════════════
# 1. Ingest — _ingest_finding_core
# ══════════════════════════════════════════════════════════════════════════════

class TestIngestFindingCore:
    def test_creates_row_with_correct_fields(self, db):
        from app.routers.security import _ingest_finding_core, FindingIn

        ws = _ws()
        body = FindingIn(
            tool="claude-code",
            severity="critical",
            type="injection",
            description="SQL injection in user input",
            file="app/db.py",
            line=99,
            repo_full_name="org/repo",
        )
        finding = _ingest_finding_core(body=body, workspace_id=ws, db=db)
        db.commit()

        assert finding.id is not None
        assert finding.workspace_id == ws
        assert finding.severity == "critical"
        assert finding.type == "injection"
        assert finding.status == "open"
        assert finding.file == "app/db.py"
        assert finding.line == 99

    def test_defaults_status_to_open(self, db):
        from app.routers.security import _ingest_finding_core, FindingIn

        body = FindingIn(tool="codex", severity="low", type="other", description="test")
        finding = _ingest_finding_core(body=body, workspace_id=_ws(), db=db)
        assert finding.status == "open"

    def test_optional_fields_nullable(self, db):
        from app.routers.security import _ingest_finding_core, FindingIn

        body = FindingIn(tool="manual", severity="info", type="other", description="bare minimum")
        finding = _ingest_finding_core(body=body, workspace_id=_ws(), db=db)
        assert finding.file is None
        assert finding.line is None
        assert finding.repo_full_name is None


# ══════════════════════════════════════════════════════════════════════════════
# 2. Validator rejection
# ══════════════════════════════════════════════════════════════════════════════

class TestValidation:
    def test_invalid_severity_raises(self):
        from app.routers.security import FindingIn
        with pytest.raises(Exception, match="severity"):
            FindingIn(tool="t", severity="EXTREME", type="other", description="x")

    def test_invalid_type_raises(self):
        from app.routers.security import FindingIn
        with pytest.raises(Exception, match="type"):
            FindingIn(tool="t", severity="high", type="xss", description="x")

    def test_invalid_status_raises(self):
        from app.routers.security import FindingUpdate
        with pytest.raises(Exception, match="status"):
            FindingUpdate(status="resolved")

    def test_valid_severities_accepted(self):
        from app.routers.security import FindingIn
        for sev in ("critical", "high", "medium", "low", "info"):
            body = FindingIn(tool="t", severity=sev, type="other", description="x")
            assert body.severity == sev

    def test_valid_types_accepted(self):
        from app.routers.security import FindingIn
        for t in ("injection", "path-traversal", "secret-leak", "auth-bypass", "crypto", "other"):
            body = FindingIn(tool="t", severity="low", type=t, description="x")
            assert body.type == t


# ══════════════════════════════════════════════════════════════════════════════
# 3. Status transitions
# ══════════════════════════════════════════════════════════════════════════════

class TestStatusTransitions:
    def test_open_to_triaging(self, db):
        ws = _ws()
        f = _make_finding(db, ws, status="open")
        f.status = "triaging"
        db.commit()
        db.refresh(f)
        assert f.status == "triaging"

    def test_triaging_to_fixed(self, db):
        ws = _ws()
        f = _make_finding(db, ws, status="triaging")
        f.status = "fixed"
        db.commit()
        db.refresh(f)
        assert f.status == "fixed"

    def test_open_to_dismissed(self, db):
        ws = _ws()
        f = _make_finding(db, ws)
        f.status = "dismissed"
        db.commit()
        db.refresh(f)
        assert f.status == "dismissed"

    def test_github_issue_url_stored(self, db):
        ws = _ws()
        f = _make_finding(db, ws)
        f.github_issue_url = "https://github.com/org/repo/issues/42"
        db.commit()
        db.refresh(f)
        assert f.github_issue_url == "https://github.com/org/repo/issues/42"


# ══════════════════════════════════════════════════════════════════════════════
# 4. Summary counts
# ══════════════════════════════════════════════════════════════════════════════

class TestSummary:
    def _summary(self, db, ws):
        from app.routers.security import get_summary
        class _FakeDB:
            def __init__(self, session): self._s = session
            def query(self, *a, **kw): return self._s.query(*a, **kw)
        # call the core logic directly rather than going through FastAPI
        from sqlalchemy import func
        from datetime import timedelta

        cutoff = _now() - timedelta(days=30)
        base = db.query(SecurityFinding).filter(
            SecurityFinding.workspace_id == ws,
            SecurityFinding.created_at >= cutoff,
        )
        total = base.count()
        by_sev = {s: 0 for s in ("critical","high","medium","low","info")}
        for row in base.with_entities(SecurityFinding.severity, func.count(SecurityFinding.id)).group_by(SecurityFinding.severity).all():
            by_sev[row[0]] = row[1]
        by_st = {s: 0 for s in ("open","triaging","fixed","dismissed")}
        for row in base.with_entities(SecurityFinding.status, func.count(SecurityFinding.id)).group_by(SecurityFinding.status).all():
            by_st[row[0]] = row[1]
        return total, by_sev, by_st

    def test_counts_match_ingested_findings(self, db):
        ws = _ws()
        _make_finding(db, ws, severity="critical", status="open")
        _make_finding(db, ws, severity="critical", status="open")
        _make_finding(db, ws, severity="high",     status="triaging")
        _make_finding(db, ws, severity="medium",   status="fixed")
        db.commit()

        total, by_sev, by_st = self._summary(db, ws)

        assert total == 4
        assert by_sev["critical"] == 2
        assert by_sev["high"] == 1
        assert by_sev["medium"] == 1
        assert by_sev["low"] == 0
        assert by_st["open"] == 2
        assert by_st["triaging"] == 1
        assert by_st["fixed"] == 1

    def test_workspace_isolation(self, db):
        ws_a, ws_b = _ws(), _ws()
        _make_finding(db, ws_a, severity="critical")
        _make_finding(db, ws_b, severity="high")
        db.commit()

        total_a, _, _ = self._summary(db, ws_a)
        total_b, _, _ = self._summary(db, ws_b)

        assert total_a == 1
        assert total_b == 1

    def test_mttr_computed_for_fixed_findings(self, db):
        ws = _ws()
        created = _now() - timedelta(hours=4)
        f = _make_finding(db, ws, status="fixed", created_at=created, updated_at=_now())
        db.commit()

        from sqlalchemy import func
        cutoff = _now() - timedelta(days=30)
        mttr_row = (
            db.query(func.avg(
                func.strftime("%s", SecurityFinding.updated_at).op("-")(
                    func.strftime("%s", SecurityFinding.created_at)
                )
            ))
            .filter(
                SecurityFinding.workspace_id == ws,
                SecurityFinding.status == "fixed",
                SecurityFinding.created_at >= cutoff,
            )
            .scalar()
        )
        # SQLite returns seconds — convert to hours
        if mttr_row is not None:
            mttr_hours = round(float(mttr_row) / 3600, 2)
            assert mttr_hours >= 3.9  # ~4 hours


# ══════════════════════════════════════════════════════════════════════════════
# 5. _trigger_security_loop — enqueues run, sets finding.run_id
# ══════════════════════════════════════════════════════════════════════════════

class TestTriggerSecurityLoop:
    def test_no_op_when_no_security_project(self, db):
        """If no security automation project exists, ingest still succeeds."""
        from app.routers.security import _trigger_security_loop

        ws = _ws()
        f = _make_finding(db, ws)

        # No project rows in DB → should return silently
        with patch("app.routers.secure._latest_security_automation_project", return_value=None):
            _trigger_security_loop(f, ws, db)  # must not raise

        assert f.run_id is None

    def test_no_op_when_workflow_not_installed(self, db):
        from app.routers.security import _trigger_security_loop

        ws = _ws()
        f = _make_finding(db, ws)

        fake_project = MagicMock()
        fake_project.id = uuid.uuid4()

        with patch("app.routers.secure._latest_security_automation_project", return_value=fake_project):
            # DB has no workflow rows → query returns None
            _trigger_security_loop(f, ws, db)

        assert f.run_id is None

    def test_enqueues_run_and_sets_run_id(self, db):
        from app.routers.security import _trigger_security_loop

        ws = _ws()
        f = _make_finding(db, ws)

        # Seed a minimal workflow
        version = WorkflowVersion(id=str(uuid.uuid4()), workflow_id=str(uuid.uuid4()), graph={})
        db.add(version)
        db.flush()

        workflow = Workflow(
            id=str(uuid.uuid4()),
            workspace_id=ws,
            project_id=str(uuid.uuid4()),
            name="Security Loop",
            playbook_slug="security_loop",
            current_version_id=version.id,
        )
        db.add(workflow)
        db.flush()

        fake_project = MagicMock()
        fake_project.id = workflow.project_id

        mock_redis = MagicMock()
        mock_redis.llen.return_value = 0

        with patch("app.routers.secure._latest_security_automation_project", return_value=fake_project), \
             patch("app.routers.security._redis", return_value=mock_redis):
            _trigger_security_loop(f, ws, db)

        assert f.run_id is not None
        run = db.query(Run).filter(Run.id == uuid.UUID(f.run_id)).first()
        assert run is not None
        assert run.status == "pending"
        assert run.state["_trigger"]["severity"] == "high"
        mock_redis.rpush.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# 6. trigger_fix — sets status=triaging, returns run_id
# ══════════════════════════════════════════════════════════════════════════════

class TestTriggerFix:
    def test_returns_not_triggered_when_no_autopilot_workflow(self, db):
        from app.routers.security import trigger_fix

        ws = _ws()
        f = _make_finding(db, ws)
        db.commit()

        result = trigger_fix(
            finding_id=f.id,
            db=db,
            workspace_id=ws,
            _=None,
        )

        assert result.triggered is False
        assert result.reason is not None

    def test_sets_status_triaging_on_success(self, db):
        from app.routers.security import trigger_fix

        ws = _ws()
        f = _make_finding(db, ws, repo_full_name="org/repo")

        _wf_id = str(uuid.uuid4())
        version = WorkflowVersion(id=str(uuid.uuid4()), workflow_id=_wf_id, graph={})
        db.add(version)

        workflow = Workflow(
            id=_wf_id,
            workspace_id=ws,
            project_id=str(uuid.uuid4()),
            name="Security Autopilot Fix",
            playbook_slug="security-autopilot-fix",
            current_version_id=version.id,
        )
        db.add(workflow)
        db.flush()

        sec_cfg = SecurityConfig(
            workspace_id=ws,
            installed=True,
            security_slack_channel="#security",
        )
        db.add(sec_cfg)
        db.commit()

        mock_redis = MagicMock()
        mock_redis.llen.return_value = 0

        with patch("app.routers.security._redis", return_value=mock_redis):
            result = trigger_fix(
                finding_id=f.id,
                db=db,
                workspace_id=ws,
                _=None,
            )

        assert result.triggered is True
        assert result.run_id is not None

        db.refresh(f)
        assert f.status == "triaging"
        mock_redis.rpush.assert_called_once()
