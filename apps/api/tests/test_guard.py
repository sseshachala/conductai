"""
Unit tests for ConductGuard — no network, no LLM calls.

Uses a real SQLite in-memory engine for model introspection and a minimal
mock layer for the executor import chain (structlog, redis, sentry, etc.).

Covers:
  - Policy evaluation logic (_execute_guard)
  - enforcement_mode behaviour: block / warn / audit
  - Guard-not-installed path per enforcement_mode
  - match_tool, match_pattern, match_path_pattern, context_keys filtering
  - GuardAuditEvent, GuardSpendBudget model field validation
  - Output shape from _execute_guard
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

# ── Minimal env so Settings() doesn't blow up ────────────────────────────────
os.environ["DATABASE_URL"]      = "sqlite:///:memory:"
os.environ["REDIS_URL"]         = "redis://localhost:6379"
os.environ["ANTHROPIC_API_KEY"] = "sk-test"
os.environ["ENCRYPTION_KEY"]    = "test-key-32-bytes-long-xxxxxxxx!"

# ── Stub modules that have side-effects or binary deps ───────────────────────
for _mod in [
    "structlog", "redis", "sentry_sdk",
    "app.runtime.llm_client", "app.runtime.model_router",
    "app.routers.runs",
    "app.models.environment", "app.models.integration",
    "app.models.run", "app.models.workflow", "app.models.workspace",
    "app.core.crypto",
]:
    sys.modules.setdefault(_mod, MagicMock())

# publish_run_event is called inside _emit — stub it out
sys.modules["app.routers.runs"].publish_run_event = MagicMock()

# Stub app.core.config BEFORE executor imports it — avoids pydantic Settings()
# validation against the real .env which contains extra keys
_cfg_stub = MagicMock()
_cfg_stub.settings = MagicMock(
    sentry_dsn=None,
    sqlalchemy_database_url="sqlite:///:memory:",
    encryption_key="test-key-32-bytes-long-xxxxxxxx!",
    allowed_egress_hosts=[],
)
sys.modules["app.core.config"] = _cfg_stub

# ── Real SQLAlchemy Base + SQLite engine for guard models ────────────────────
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

_sqlite_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_RealBase = declarative_base()

# Patch app.core.database BEFORE importing guard models or executor
_db_mod = MagicMock()
_db_mod.Base = _RealBase
_db_mod.SessionLocal = sessionmaker(bind=_sqlite_engine)
_db_mod.engine = _sqlite_engine
sys.modules["app.core.database"] = _db_mod

# Now import guard models (they'll use the real SQLite Base)
from app.modules.guard.models import (   # noqa: E402
    GuardAuditEvent,
    GuardMember,
    GuardPolicy,
    GuardSession,
    GuardSpendBudget,
    GuardTeam,
)

# Import executor last — all its deps are already stubbed
from app.runtime.executor import _execute_guard   # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_team(**kw):
    t = MagicMock()
    t.id = kw.get("id", uuid.uuid4())
    t.name = kw.get("name", "Test Team")
    t.workspace_id = kw.get("workspace_id", uuid.uuid4())
    t.conductai_org_id = kw.get("conductai_org_id", "org_test")
    return t


def _make_policy(**kw):
    p = MagicMock()
    p.rule_id = kw.get("rule_id", "test-rule")
    p.match_tool = kw.get("match_tool", "*")
    p.match_pattern = kw.get("match_pattern", None)
    p.match_path_pattern = kw.get("match_path_pattern", None)
    p.action = kw.get("action", "block")
    p.message = kw.get("message", "Policy violation")
    p.enabled = kw.get("enabled", True)
    return p


def _make_db(team=None, policies=None, no_team=False):
    """Return a mock db session wired to return the given team and policies."""
    db = MagicMock()
    resolved_team = None if no_team else (team or _make_team())
    resolved_policies = policies or []

    q = MagicMock()
    q.filter.return_value = q
    q.first.return_value = resolved_team
    q.order_by.return_value = q
    q.all.return_value = resolved_policies
    db.query.return_value = q
    return db, resolved_team


def _run(config, state, db, workspace_id=None):
    block = {"id": "guard_test", "config": config}
    return _execute_guard(block, state, workspace_id or str(uuid.uuid4()), db)


# ── Guard not installed ───────────────────────────────────────────────────────

class TestGuardNotInstalled:
    def test_block_mode_raises(self):
        db, _ = _make_db(no_team=True)
        with pytest.raises(RuntimeError, match="ConductGuard is not installed"):
            _run({"enforcement_mode": "block"}, {}, db)

    def test_warn_mode_returns_skipped(self):
        db, _ = _make_db(no_team=True)
        result = _run({"enforcement_mode": "warn"}, {}, db)
        assert result["status"] == "skipped"
        assert result["reason"] == "guard_not_installed"

    def test_audit_mode_returns_skipped(self):
        db, _ = _make_db(no_team=True)
        result = _run({"enforcement_mode": "audit"}, {}, db)
        assert result["status"] == "skipped"


# ── No policies ───────────────────────────────────────────────────────────────

class TestNoPolicies:
    def test_passes_with_no_policies(self):
        db, _ = _make_db(policies=[])
        result = _run({}, {"key": "value"}, db)
        assert result["status"] == "passed"
        assert result["rules_checked"] == 0
        assert result["violations"] == 0
        assert result["warnings"] == []


# ── match_tool ────────────────────────────────────────────────────────────────

class TestMatchTool:
    def test_wildcard_matches_workflow(self):
        db, _ = _make_db(policies=[_make_policy(match_tool="*", action="warn")])
        assert _run({}, {"x": "data"}, db)["violations"] == 1

    def test_explicit_workflow_matches(self):
        db, _ = _make_db(policies=[_make_policy(match_tool="workflow", action="warn")])
        assert _run({}, {"x": "data"}, db)["violations"] == 1

    def test_claude_code_tool_skips_workflow(self):
        db, _ = _make_db(policies=[_make_policy(match_tool="claude-code", action="warn")])
        assert _run({}, {"x": "data"}, db)["violations"] == 0

    def test_comma_separated_including_workflow(self):
        db, _ = _make_db(policies=[_make_policy(match_tool="claude-code,workflow,cursor", action="warn")])
        assert _run({}, {"x": "data"}, db)["violations"] == 1


# ── match_pattern ─────────────────────────────────────────────────────────────

class TestMatchPattern:
    def test_pattern_matches_context_json(self):
        db, _ = _make_db(policies=[_make_policy(match_pattern=r"secret_key", action="warn")])
        assert _run({}, {"out": "the secret_key value"}, db)["violations"] == 1

    def test_pattern_no_match_passes(self):
        db, _ = _make_db(policies=[_make_policy(match_pattern=r"DROP TABLE", action="block")])
        assert _run({}, {"out": "opening a PR"}, db)["violations"] == 0

    def test_invalid_regex_skips_rule(self):
        db, _ = _make_db(policies=[_make_policy(match_pattern=r"[invalid(", action="block")])
        assert _run({}, {"x": "data"}, db)["violations"] == 0

    def test_case_insensitive_match(self):
        db, _ = _make_db(policies=[_make_policy(match_pattern=r"DROP TABLE", action="warn")])
        assert _run({}, {"sql": "drop table users"}, db)["violations"] == 1


# ── match_path_pattern ────────────────────────────────────────────────────────

class TestMatchPathPattern:
    def test_path_pattern_matches(self):
        db, _ = _make_db(policies=[_make_policy(match_path_pattern=r"\.env$", action="warn")])
        assert _run({}, {"file": "/project/.env"}, db)["violations"] == 1

    def test_path_pattern_no_match(self):
        db, _ = _make_db(policies=[_make_policy(match_path_pattern=r"\.env$", action="warn")])
        assert _run({}, {"file": "/project/main.py"}, db)["violations"] == 0


# ── context_keys ──────────────────────────────────────────────────────────────

class TestContextKeys:
    def test_excludes_unspecified_keys(self):
        db, _ = _make_db(policies=[_make_policy(match_pattern=r"secret", action="warn")])
        state = {"safe": {"out": "nothing"}, "leak": {"out": "secret value"}}
        assert _run({"context_keys": ["safe"]}, state, db)["violations"] == 0

    def test_includes_specified_key(self):
        db, _ = _make_db(policies=[_make_policy(match_pattern=r"secret", action="warn")])
        state = {"safe": {"out": "nothing"}, "leak": {"out": "secret value"}}
        assert _run({"context_keys": ["leak"]}, state, db)["violations"] == 1


# ── enforcement_mode ──────────────────────────────────────────────────────────

class TestEnforcementMode:
    def test_block_raises(self):
        db, _ = _make_db(policies=[_make_policy(action="block", message="blocked!")])
        with pytest.raises(RuntimeError, match="blocked!"):
            _run({"enforcement_mode": "block"}, {"x": "data"}, db)

    def test_warn_returns_passed_with_warnings(self):
        db, _ = _make_db(policies=[_make_policy(action="warn", rule_id="w1", message="careful")])
        result = _run({}, {"x": "data"}, db)
        assert result["status"] == "passed"
        assert result["warnings"][0]["rule_id"] == "w1"

    def test_audit_records_silently(self):
        db, _ = _make_db(policies=[_make_policy(action="audit")])
        result = _run({}, {"x": "data"}, db)
        assert result["status"] == "passed"
        assert result["warnings"] == []
        assert result["violations"] == 1
        db.add.assert_called()

    def test_block_writes_audit_event_before_raising(self):
        db, _ = _make_db(policies=[_make_policy(action="block")])
        with pytest.raises(RuntimeError):
            _run({}, {"x": "data"}, db)
        db.add.assert_called()
        db.commit.assert_called()

    def test_multiple_warn_violations(self):
        policies = [_make_policy(action="warn", rule_id=f"r{i}") for i in range(3)]
        db, _ = _make_db(policies=policies)
        result = _run({}, {"x": "data"}, db)
        assert len(result["warnings"]) == 3
        assert result["violations"] == 3


# ── output shape ──────────────────────────────────────────────────────────────

class TestOutputShape:
    def test_required_fields_present(self):
        db, team = _make_db(policies=[])
        result = _run({}, {}, db)
        for f in ("status", "team_id", "rules_checked", "violations", "warnings"):
            assert f in result
        assert result["team_id"] == str(team.id)


# ── GuardAuditEvent model ─────────────────────────────────────────────────────

class TestGuardAuditEventModel:
    def _cols(self):
        return {c.key for c in GuardAuditEvent.__table__.columns}

    def test_has_cost_fields(self):
        cols = self._cols()
        assert "cost_usd_before" in cols
        assert "cost_usd_after" in cols
        assert "tokens_before" in cols
        assert "tokens_after" in cols
        assert "tokens_saved" in cols

    def test_has_conductai_link_fields(self):
        cols = self._cols()
        assert "conductai_run_id" in cols
        assert "conductai_workflow" in cols

    def test_has_decision_field(self):
        assert "decision" in self._cols()

    def test_has_ai_tool_and_tool_call(self):
        cols = self._cols()
        assert "ai_tool" in cols
        assert "tool_call" in cols


# ── GuardSpendBudget model ────────────────────────────────────────────────────

class TestGuardSpendBudgetModel:
    def _cols(self):
        return {c.key for c in GuardSpendBudget.__table__.columns}

    def test_has_hard_limit(self):
        cols = self._cols()
        assert "hard_limit_usd" in cols
        assert "default_per_developer_usd" in cols
        assert "alert_threshold_pct" in cols

    def test_member_id_is_nullable(self):
        col = GuardSpendBudget.__table__.c["member_id"]
        assert col.nullable is True

    def test_monthly_limit_field_exists(self):
        assert "monthly_limit_usd" in self._cols()


# ── GuardTeam model ───────────────────────────────────────────────────────────

class TestGuardTeamModel:
    def _cols(self):
        return {c.key for c in GuardTeam.__table__.columns}

    def test_has_notification_prefs(self):
        cols = self._cols()
        assert "notify_on_block" in cols
        assert "notify_on_budget" in cols
        assert "alert_channel" in cols

    def test_has_workspace_link(self):
        assert "workspace_id" in self._cols()


# ── GuardPolicy model ─────────────────────────────────────────────────────────

class TestGuardPolicyModel:
    def _cols(self):
        return {c.key for c in GuardPolicy.__table__.columns}

    def test_has_match_fields(self):
        cols = self._cols()
        assert "match_tool" in cols
        assert "match_pattern" in cols
        assert "match_path_pattern" in cols

    def test_has_action_and_enabled(self):
        cols = self._cols()
        assert "action" in cols
        assert "enabled" in cols
        assert "builtin" in cols
