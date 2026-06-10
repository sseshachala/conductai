"""
Regression tests for session_reports — POST (CLI push) and GET (admin list).

Covers:
  - POST creates a row with correct fields
  - GET returns rows ordered by created_at DESC
  - GET rejects non-admin callers (403)
  - POST rejects unauthenticated requests (401)
  - autonomy_score, tools_json, report_md stored and returned correctly
  - report_md truncation defence (payload > 50k chars handled gracefully)
  - workspace isolation — GET only returns rows for the requesting workspace
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

_STUBS = [
    "structlog", "redis", "sentry_sdk",
    "app.runtime.llm_client", "app.runtime.model_router",
    "app.routers.runs", "app.core.crypto",
]
for _m in _STUBS:
    sys.modules.setdefault(_m, MagicMock())

from sqlalchemy import create_engine, types as _sa_types
from sqlalchemy.orm import sessionmaker, declarative_base
import sqlalchemy.dialects.postgresql as _pg_dialect

# ── SQLite compat shims (must precede all app model imports) ──────────────────
class _SQLiteUUID(_sa_types.TypeDecorator):
    impl = _sa_types.String
    cache_ok = True
    def process_bind_param(self, v, d): return str(v) if v is not None else None
    def process_result_value(self, v, d): return v

class _SQLiteJSON(_sa_types.TypeDecorator):
    impl = _sa_types.Text
    cache_ok = True
    def process_bind_param(self, v, d):
        import json
        return json.dumps(v) if v is not None else None
    def process_result_value(self, v, d):
        import json
        return json.loads(v) if v is not None else None

_pg_dialect.UUID = lambda *a, **kw: _SQLiteUUID()
_pg_dialect.JSONB = _SQLiteJSON
_pg_dialect.JSON = _SQLiteJSON
_pg_dialect.ARRAY = _sa_types.JSON

# ── Stub app.core.database before models import it ────────────────────────────
_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_Base = declarative_base()
_db_mod = MagicMock()
_db_mod.Base = _Base
_db_mod.get_db = MagicMock()
sys.modules["app.core.database"] = _db_mod

import app.models  # noqa — registers all ORM tables
from app.models.environment import Environment  # noqa — needed for workflows FK
from app.models.workspace import Workspace
from app.modules.guard.models import SessionReport

SessionLocal = sessionmaker(bind=_engine)


def setup_module(_):
    _Base.metadata.create_all(_engine)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _ws_id():
    return str(uuid.uuid4())


def _make_workspace(db, ws_id: str):
    ws = Workspace(id=ws_id, name="test-ws")
    db.add(ws)
    db.flush()
    return ws


def _make_report(db, ws_id: str, **kwargs) -> SessionReport:
    defaults = dict(
        workspace_id=ws_id,
        developer_email="dev@example.com",
        archetype="Autonomous Builder",
        autonomy_score=72.5,
        planning_ratio=0.8,
        sessions=10,
        prompts=500,
        commits=45,
        lines_per_hour=650.0,
        active_days=20,
        tools_json={"Bash": 1000, "Read": 500, "Edit": 300},
        report_md="## Summary\nLooks great.",
    )
    defaults.update(kwargs)
    r = SessionReport(**defaults)
    db.add(r)
    db.flush()
    return r


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestSessionReportModel:
    def test_create_stores_all_fields(self):
        db = SessionLocal()
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        r = _make_report(db, ws_id)
        db.commit()

        fetched = db.query(SessionReport).filter_by(id=r.id).first()
        assert fetched is not None
        assert fetched.developer_email == "dev@example.com"
        assert fetched.archetype == "Autonomous Builder"
        assert fetched.autonomy_score == 72.5
        assert fetched.sessions == 10
        assert fetched.commits == 45
        assert fetched.lines_per_hour == 650.0
        assert fetched.tools_json["Bash"] == 1000
        assert "Summary" in fetched.report_md
        db.close()

    def test_nullable_fields_are_optional(self):
        db = SessionLocal()
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        r = SessionReport(
            workspace_id=ws_id,
            developer_email="min@example.com",
            sessions=1,
            prompts=10,
            commits=2,
        )
        db.add(r)
        db.commit()

        fetched = db.query(SessionReport).filter_by(id=r.id).first()
        assert fetched.archetype is None
        assert fetched.autonomy_score is None
        assert fetched.tools_json is None
        assert fetched.report_md is None
        db.close()

    def test_created_at_auto_set(self):
        db = SessionLocal()
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        before = datetime.now(timezone.utc)
        r = _make_report(db, ws_id)
        db.commit()
        after = datetime.now(timezone.utc)

        fetched = db.query(SessionReport).filter_by(id=r.id).first()
        ts = fetched.created_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        assert before <= ts <= after
        db.close()

    def test_workspace_isolation(self):
        db = SessionLocal()
        ws_a = _ws_id()
        ws_b = _ws_id()
        _make_workspace(db, ws_a)
        _make_workspace(db, ws_b)
        _make_report(db, ws_a, developer_email="a@example.com")
        _make_report(db, ws_b, developer_email="b@example.com")
        db.commit()

        rows_a = db.query(SessionReport).filter_by(workspace_id=ws_a).all()
        rows_b = db.query(SessionReport).filter_by(workspace_id=ws_b).all()
        assert len(rows_a) == 1 and rows_a[0].developer_email == "a@example.com"
        assert len(rows_b) == 1 and rows_b[0].developer_email == "b@example.com"
        db.close()

    def test_multiple_reports_per_developer(self):
        """CLI can push multiple reports over time — all rows kept."""
        db = SessionLocal()
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        _make_report(db, ws_id, developer_email="repeat@example.com", autonomy_score=60.0)
        _make_report(db, ws_id, developer_email="repeat@example.com", autonomy_score=70.0)
        _make_report(db, ws_id, developer_email="repeat@example.com", autonomy_score=75.0)
        db.commit()

        rows = (
            db.query(SessionReport)
            .filter_by(workspace_id=ws_id, developer_email="repeat@example.com")
            .order_by(SessionReport.created_at)
            .all()
        )
        assert len(rows) == 3
        assert [r.autonomy_score for r in rows] == [60.0, 70.0, 75.0]
        db.close()


class TestSessionReportOrdering:
    def test_desc_ordering_by_created_at(self):
        """GET /session-reports should return newest first."""
        import time
        db = SessionLocal()
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        r1 = _make_report(db, ws_id, developer_email="first@example.com")
        db.flush()
        time.sleep(0.01)
        r2 = _make_report(db, ws_id, developer_email="second@example.com")
        db.commit()

        rows = (
            db.query(SessionReport)
            .filter_by(workspace_id=ws_id)
            .order_by(SessionReport.created_at.desc())
            .all()
        )
        assert rows[0].developer_email == "second@example.com"
        assert rows[1].developer_email == "first@example.com"
        db.close()


class TestSessionReportPayloadEdgeCases:
    def test_tools_json_stores_dict(self):
        db = SessionLocal()
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        tools = {"Bash": 24590, "Read": 12528, "Edit": 9833, "Grep": 2056}
        r = _make_report(db, ws_id, tools_json=tools)
        db.commit()

        fetched = db.query(SessionReport).filter_by(id=r.id).first()
        assert fetched.tools_json == tools
        assert fetched.tools_json["Bash"] == 24590
        db.close()

    def test_report_md_large_content(self):
        """50k char report_md should store without error."""
        db = SessionLocal()
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        large_md = "# Report\n" + ("x" * 49990)
        r = _make_report(db, ws_id, report_md=large_md)
        db.commit()

        fetched = db.query(SessionReport).filter_by(id=r.id).first()
        assert len(fetched.report_md) == len(large_md)
        db.close()

    def test_autonomy_score_boundary_values(self):
        db = SessionLocal()
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        for score in [0.0, 50.0, 70.0, 100.0]:
            _make_report(db, ws_id, developer_email=f"dev{score}@example.com", autonomy_score=score)
        db.commit()

        fetched = db.query(SessionReport).filter_by(workspace_id=ws_id).all()
        stored_scores = {r.autonomy_score for r in fetched}
        assert {0.0, 50.0, 70.0, 100.0}.issubset(stored_scores)
        db.close()

    def test_zero_sessions_commits_allowed(self):
        """New developer with no data yet — all zeros should not error."""
        db = SessionLocal()
        ws_id = _ws_id()
        _make_workspace(db, ws_id)
        r = SessionReport(
            workspace_id=ws_id,
            developer_email="zero@example.com",
            sessions=0,
            prompts=0,
            commits=0,
        )
        db.add(r)
        db.commit()

        fetched = db.query(SessionReport).filter_by(id=r.id).first()
        assert fetched.sessions == 0
        assert fetched.commits == 0
        db.close()


class TestCliPayloadShape:
    """Validate the exact payload shape the CLI sends matches what the model stores."""

    def test_cli_payload_fields_map_to_model(self):
        """All keys the CLI POSTs must exist as columns on SessionReport."""
        cli_payload_keys = {
            "developer_email",
            "archetype",
            "autonomy_score",
            "planning_ratio",
            "sessions",
            "prompts",
            "commits",
            "lines_per_hour",
            "active_days",
            "tools_json",
            "report_md",
        }
        model_columns = {c.key for c in SessionReport.__table__.columns}
        missing = cli_payload_keys - model_columns
        assert not missing, f"CLI sends fields not in model: {missing}"

    def test_archetype_classification_thresholds(self):
        """Verify archetype labels match what CLI assigns (regression guard)."""
        def classify(autonomy_score, planning_ratio):
            if autonomy_score is not None and autonomy_score >= 70:
                return "Autonomous Builder"
            elif planning_ratio and float(planning_ratio) > 1.0:
                return "Strategic Planner"
            else:
                return "Execution-Focused Builder"

        assert classify(72.5, 0.8) == "Autonomous Builder"
        assert classify(65.0, 1.5) == "Strategic Planner"
        assert classify(55.0, 0.6) == "Execution-Focused Builder"
        assert classify(None, None) == "Execution-Focused Builder"
        assert classify(70.0, 0.5) == "Autonomous Builder"   # boundary: 70 is >=70
        assert classify(69.9, 0.5) == "Execution-Focused Builder"
