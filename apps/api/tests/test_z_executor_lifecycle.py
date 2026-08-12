"""
Unit tests for app/runtime/executor.py — lifecycle functions and execute_run state machine.

All external dependencies (DB, Redis, SSE, settings) are mocked.
No network, no real Postgres, no real Redis.

Module-level sys.modules patching is required because executor.py does a bare
`from app.core.config import settings` at import time, and pydantic-settings
tries to read the project .env which contains keys not in the Settings model.
"""
from __future__ import annotations

import hashlib
import sys
import types
import uuid
from unittest.mock import MagicMock, patch


# ── module-level pre-patch ────────────────────────────────────────────────────
# These stubs must be in sys.modules BEFORE any `from app.runtime.executor import ...`
# to prevent pydantic-settings from reading the project .env at import time.

def _stub_settings():
    s = MagicMock()
    s.redis_url = "redis://localhost:6379"
    s.api_base_url = "http://localhost:8000"
    s.default_max_cost_usd = 5.0
    s.sentry_dsn = ""
    s.environment = "development"
    s.encryption_key = "test-key-32-bytes-long-xxxxxxxx!"
    s.log_level = "INFO"
    s.database_url = "postgresql://test:test@localhost:5432/test_marshal"
    return s


_FAKE_SETTINGS = _stub_settings()

# Stub app.core.config so `from app.core.config import settings` resolves cleanly.
_config_mod = types.ModuleType("app.core.config")
_config_mod.settings = _FAKE_SETTINGS
sys.modules.setdefault("app.core.config", _config_mod)

# Stub structlog so executor's `log = structlog.get_logger(...)` works.
if "structlog" not in sys.modules:
    _structlog_mod = types.ModuleType("structlog")
    _structlog_mod.get_logger = lambda *a, **kw: MagicMock()
    _structlog_mod.contextvars = MagicMock()
    _structlog_mod.configure = MagicMock()
    _structlog_mod.stdlib = MagicMock()
    _structlog_mod.processors = MagicMock()
    _structlog_mod.dev = MagicMock()
    sys.modules["structlog"] = _structlog_mod
    sys.modules["structlog.contextvars"] = _structlog_mod.contextvars

# Stub redis — _enqueue_online_eval does `import redis as _redis` at call time.
if "redis" not in sys.modules:
    sys.modules["redis"] = MagicMock()

# Stub heavy runtime dependencies that executor re-exports at the bottom.
# Stub app.core.database with a real Base so model classes inherit from a proper
# SQLAlchemy declarative base (inheriting from MagicMock breaks column descriptors).
if "app.core.database" not in sys.modules:
    from sqlalchemy.orm import declarative_base as _decl_base
    _db_mod = types.ModuleType("app.core.database")
    _db_mod.Base = _decl_base()
    _db_mod.SessionLocal = MagicMock()
    _db_mod.get_db = MagicMock()
    sys.modules["app.core.database"] = _db_mod

for _mod_name in [
    "app.runtime.runtime",
    "app.runtime.dag_runner",
    "app.runtime.tool_engine",
    "app.runtime.blocks.guard_block",
    "app.runtime.run_contract",
    "app.core.credentials",
    "app.models.environment",
    "app.models.run",
    "app.models.workflow",
    "app.models.run_analytics_event",
    "app.modules.agent_identity.models",
    "app.modules.agent_identity.run_token_model",
    "app.core.crypto",
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

# Provide specific attributes expected by executor top-level imports.
sys.modules["app.runtime.runtime"]._now = MagicMock(return_value=None)
sys.modules["app.runtime.runtime"]._emit = MagicMock()
sys.modules["app.runtime.runtime"]._redact = MagicMock()
sys.modules["app.runtime.runtime"]._redact_payload = MagicMock()
sys.modules["app.runtime.runtime"]._write_trace = MagicMock()
sys.modules["app.runtime.runtime"]._agent_config = MagicMock()
sys.modules["app.runtime.dag_runner"].ApprovalRequired = type("ApprovalRequired", (Exception,), {})
sys.modules["app.runtime.dag_runner"].ClarificationRequired = type("ClarificationRequired", (Exception,), {})
sys.modules["app.runtime.dag_runner"]._classify_failure = MagicMock()
sys.modules.setdefault("app.models.run_analytics_event", MagicMock()).RunAnalyticsEvent = MagicMock()
sys.modules["app.core.credentials"].CredentialStore = MagicMock()
sys.modules["app.core.credentials"].get_all_credentials = MagicMock(return_value=MagicMock(_data={}, keys=lambda: []))
sys.modules["app.core.credentials"].mint_cred_token = MagicMock(return_value="")
sys.modules["app.core.credentials"].CredentialStore = MagicMock()


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_run(status="pending"):
    run = MagicMock()
    run.id = uuid.uuid4()
    run.status = status
    run.state = {}
    run.triggered_by = "manual"
    run.workflow_version_id = uuid.uuid4()
    run.attempt_count = 0
    run.started_at = None
    run.completed_at = None
    run.created_at = None
    run.agent_role_id = None
    run.locked_at = None
    run.locked_by = None
    return run


def _make_version(playbook_slug=None):
    wf = MagicMock()
    wf.workspace_id = str(uuid.uuid4())
    wf.guard_enabled = False
    wf.environment_id = None
    wf.name = "Test Workflow"
    wf.playbook_slug = playbook_slug
    version = MagicMock()
    version.workflow = wf
    version.graph = {"nodes": []}
    return version


def _make_db(run, version):
    """Build a db MagicMock wired for executor's two query patterns."""
    db = MagicMock()

    # Pattern 1: db.query(Run).filter(...).with_for_update().first() → run
    run_qchain = MagicMock()
    run_qchain.filter.return_value.with_for_update.return_value.first.return_value = run
    run_qchain.filter.return_value.first.return_value = run  # crash-handler re-query

    # Pattern 2: db.query(WorkflowVersion).options(...).filter(...).first() → version
    ver_qchain = MagicMock()
    ver_qchain.options.return_value.filter.return_value.first.return_value = version

    # Everything else (Environment, AgentRunToken, AgentIdentity) → returns None
    default_qchain = MagicMock()
    default_qchain.filter.return_value.first.return_value = None
    default_qchain.options.return_value.filter.return_value.first.return_value = None

    def _query_dispatch(model):
        name = getattr(model, "__name__", repr(model))
        if "Run" in name and "Version" not in name and "Analytics" not in name and "Token" not in name:
            return run_qchain
        if "WorkflowVersion" in name:
            return ver_qchain
        return default_qchain

    db.query.side_effect = _query_dispatch
    return db


# ── _find_artifact ────────────────────────────────────────────────────────────

def test_find_artifact_top_level_url():
    from app.runtime.executor import _find_artifact
    state = {"pr_url": "https://github.com/org/repo/pull/1", "other": "value"}
    assert _find_artifact(state, "pr_url") == "https://github.com/org/repo/pull/1"


def test_find_artifact_nested_block_output():
    from app.runtime.executor import _find_artifact
    state = {
        "brain_1": {"pr_url": "https://github.com/org/repo/pull/2", "status": "ok"},
    }
    assert _find_artifact(state, "pr_url") == "https://github.com/org/repo/pull/2"


def test_find_artifact_top_level_beats_nested():
    from app.runtime.executor import _find_artifact
    state = {
        "pr_url": "https://top-level.example.com/pr",
        "brain_1": {"pr_url": "https://nested.example.com/pr"},
    }
    assert _find_artifact(state, "pr_url") == "https://top-level.example.com/pr"


def test_find_artifact_returns_none_when_missing():
    from app.runtime.executor import _find_artifact
    state = {"other_key": "https://github.com/org/repo/pull/1"}
    assert _find_artifact(state, "pr_url") is None


def test_find_artifact_returns_none_when_not_url():
    from app.runtime.executor import _find_artifact
    state = {"pr_url": "not-a-url", "brain_1": {"pr_url": "also-not-a-url"}}
    assert _find_artifact(state, "pr_url") is None


# ── _detect_outcome ───────────────────────────────────────────────────────────

def test_detect_outcome_not_succeeded():
    from app.runtime.executor import _detect_outcome
    assert _detect_outcome("autopilot", {}, "failed") is None


def test_detect_outcome_no_slug():
    from app.runtime.executor import _detect_outcome
    assert _detect_outcome(None, {}, "succeeded") is None


def test_detect_outcome_unknown_slug():
    from app.runtime.executor import _detect_outcome
    assert _detect_outcome("unknown_playbook_xyz", {}, "succeeded") is None


def test_detect_outcome_known_slug_no_artifact_required():
    # smoke_test has requires_artifact=False — succeeds without any state content
    from app.runtime.executor import _detect_outcome
    result = _detect_outcome("smoke_test", {}, "succeeded")
    assert result is not None
    assert result["type"] == "pipeline_verified"


def test_detect_outcome_requires_artifact_missing():
    # autopilot requires pr_url to be present in state
    from app.runtime.executor import _detect_outcome
    result = _detect_outcome("autopilot", {}, "succeeded")
    assert result is None


def test_detect_outcome_includes_artifact_url_when_found():
    from app.runtime.executor import _detect_outcome
    state = {"pr_url": "https://github.com/org/repo/pull/99"}
    result = _detect_outcome("autopilot", state, "succeeded")
    assert result is not None
    assert result["type"] == "pr_opened"
    assert result["artifact_url"] == "https://github.com/org/repo/pull/99"


# ── _emit_run_analytics ───────────────────────────────────────────────────────

def test_emit_run_analytics_calls_db_add():
    from app.runtime.executor import _emit_run_analytics

    run = _make_run()
    version = _make_version()
    db = MagicMock()

    # _emit_run_analytics does `from app.models.run_analytics_event import RunAnalyticsEvent`
    # at call time. Set the attribute directly on the already-stubbed module.
    sys.modules.setdefault("app.models.run_analytics_event", MagicMock()).RunAnalyticsEvent = MagicMock()
    _emit_run_analytics(run, version, {}, db, outcome="succeeded")

    db.add.assert_called_once()
    db.commit.assert_called_once()


def _capturing_event_class():
    captured = {}

    class CapturingEvent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    return CapturingEvent, captured


def test_emit_run_analytics_aggregates_tokens():
    from app.runtime.executor import _emit_run_analytics

    run = _make_run()
    version = _make_version()
    db = MagicMock()
    state = {
        "brain_1": {"input_tokens": 100, "output_tokens": 50, "turns": 3},
        "brain_2": {"input_tokens": 200, "output_tokens": 75, "turns": 5},
    }

    CapturingEvent, captured = _capturing_event_class()
    sys.modules.setdefault("app.models.run_analytics_event", MagicMock()).RunAnalyticsEvent = CapturingEvent
    _emit_run_analytics(run, version, state, db, outcome="succeeded")

    assert captured["input_tokens"] == 300
    assert captured["output_tokens"] == 125
    assert captured["tool_calls"] == 8


def test_emit_run_analytics_trigger_type_webhook():
    from app.runtime.executor import _emit_run_analytics

    run = _make_run()
    run.triggered_by = "webhook:github"
    version = _make_version()
    db = MagicMock()

    CapturingEvent, captured = _capturing_event_class()
    sys.modules.setdefault("app.models.run_analytics_event", MagicMock()).RunAnalyticsEvent = CapturingEvent
    _emit_run_analytics(run, version, {}, db, outcome="succeeded")

    assert captured["trigger_type"] == "webhook"


def test_emit_run_analytics_trigger_type_cron():
    from app.runtime.executor import _emit_run_analytics

    run = _make_run()
    run.triggered_by = "schedule:daily"
    version = _make_version()
    db = MagicMock()

    CapturingEvent, captured = _capturing_event_class()
    sys.modules.setdefault("app.models.run_analytics_event", MagicMock()).RunAnalyticsEvent = CapturingEvent
    _emit_run_analytics(run, version, {}, db, outcome="succeeded")

    assert captured["trigger_type"] == "cron"


def test_emit_run_analytics_trigger_type_manual():
    from app.runtime.executor import _emit_run_analytics

    run = _make_run()
    run.triggered_by = "manual"
    version = _make_version()
    db = MagicMock()

    CapturingEvent, captured = _capturing_event_class()
    sys.modules.setdefault("app.models.run_analytics_event", MagicMock()).RunAnalyticsEvent = CapturingEvent
    _emit_run_analytics(run, version, {}, db, outcome="succeeded")

    assert captured["trigger_type"] == "manual"


def test_emit_run_analytics_hashes_workspace_id():
    from app.runtime.executor import _emit_run_analytics

    run = _make_run()
    version = _make_version()
    raw_ws = version.workflow.workspace_id
    db = MagicMock()

    CapturingEvent, captured = _capturing_event_class()
    sys.modules.setdefault("app.models.run_analytics_event", MagicMock()).RunAnalyticsEvent = CapturingEvent
    _emit_run_analytics(run, version, {}, db, outcome="succeeded")

    stored = captured["workspace_id"]
    expected = hashlib.sha256(raw_ws.encode()).hexdigest()[:16]
    assert stored == expected
    assert stored != raw_ws


def test_emit_run_analytics_does_not_raise_on_db_error():
    from app.runtime.executor import _emit_run_analytics

    run = _make_run()
    version = _make_version()
    db = MagicMock()
    db.add.side_effect = Exception("db exploded")

    # must not raise — fire-and-forget
    _emit_run_analytics(run, version, {}, db, outcome="succeeded")


def test_emit_run_analytics_records_outcome():
    from app.runtime.executor import _emit_run_analytics

    run = _make_run()
    version = _make_version()
    db = MagicMock()

    CapturingEvent, captured = _capturing_event_class()
    sys.modules.setdefault("app.models.run_analytics_event", MagicMock()).RunAnalyticsEvent = CapturingEvent
    _emit_run_analytics(run, version, {}, db, outcome="failed", error="boom")

    assert captured["outcome"] == "failed"


# ── _enqueue_online_eval ──────────────────────────────────────────────────────

def test_enqueue_online_eval_calls_pipeline():
    from app.runtime.executor import _enqueue_online_eval

    fake_pipe = MagicMock()
    fake_redis_instance = MagicMock()
    fake_redis_instance.pipeline.return_value = fake_pipe

    # _enqueue_online_eval does `import redis as _redis` then `_redis.from_url(...)`.
    # redis is already stubbed in sys.modules; patch the attribute on that stub.
    sys.modules["redis"].from_url = MagicMock(return_value=fake_redis_instance)

    _enqueue_online_eval("run-abc")

    fake_pipe.rpush.assert_called_once_with("marshal:eval:online:queue", "run-abc")
    fake_pipe.ltrim.assert_called_once()
    fake_pipe.execute.assert_called_once()


def test_enqueue_online_eval_does_not_raise_on_redis_error():
    from app.runtime.executor import _enqueue_online_eval

    sys.modules["redis"].from_url = MagicMock(side_effect=Exception("redis down"))
    _enqueue_online_eval("run-xyz")  # must not raise


# ── execute_run — state machine ───────────────────────────────────────────────

def _base_patches():
    """Return dict of patch targets + return values used across execute_run tests."""
    return {
        "app.runtime.executor.SessionLocal": MagicMock(),
        "app.runtime.executor._execute_dag": MagicMock(return_value={}),
        "app.runtime.executor._emit_run_analytics": MagicMock(),
        "app.runtime.executor._enqueue_online_eval": MagicMock(),
        "app.runtime.executor.get_all_credentials": MagicMock(
            return_value=MagicMock(_data={}, keys=lambda: [])
        ),
        "app.runtime.executor._emit": MagicMock(),
        "app.runtime.executor._now": MagicMock(return_value=None),
        "app.core.credentials.mint_cred_token": MagicMock(return_value=""),
        "app.runtime.run_contract.RunContext": MagicMock(),
    }


def test_execute_run_run_not_found():
    from app.runtime.executor import execute_run

    run = _make_run("pending")
    patches = _base_patches()

    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None
    patches["app.runtime.executor.SessionLocal"].return_value = db

    with patch.multiple("app.runtime.executor", **{
        k.replace("app.runtime.executor.", ""): v
        for k, v in patches.items()
        if k.startswith("app.runtime.executor.")
    }):
        execute_run(str(run.id))

    # run was never touched
    assert run.status == "pending"
    db.commit.assert_not_called()


def test_execute_run_already_claimed():
    from app.runtime.executor import execute_run

    run = _make_run("running")
    patches = _base_patches()

    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = run
    patches["app.runtime.executor.SessionLocal"].return_value = db

    with patch.multiple("app.runtime.executor", **{
        k.replace("app.runtime.executor.", ""): v
        for k, v in patches.items()
        if k.startswith("app.runtime.executor.")
    }):
        execute_run(str(run.id))

    assert run.status == "running"
    db.commit.assert_not_called()


def _run_execute_run(run, version, *, dag_mock=None, dag_raises=None):
    """
    Helper that wires all sys.modules stubs and calls execute_run.

    - dag_mock: callable to inject as _execute_dag (default: returns {})
    - dag_raises: exception instance to raise from _execute_dag
    Either dag_mock or dag_raises can be set (not both).
    Returns (mock_analytics, mock_eval).
    """
    from app.runtime.executor import execute_run

    # _execute_dag is imported locally inside execute_run via
    # `from app.runtime.dag_runner import _execute_dag`.
    # Set it directly on the already-stubbed module so the local import picks it up.
    if dag_raises is not None:
        sys.modules["app.runtime.dag_runner"]._execute_dag = MagicMock(side_effect=dag_raises)
    else:
        sys.modules["app.runtime.dag_runner"]._execute_dag = dag_mock or MagicMock(return_value={})

    # RunContext is imported locally: `from app.runtime.run_contract import RunContext as _RunContext`
    mock_ctx_cls = MagicMock()
    mock_ctx_cls.return_value = MagicMock()
    sys.modules["app.runtime.run_contract"].RunContext = mock_ctx_cls

    # mint_cred_token is imported locally: `from app.core.credentials import mint_cred_token`
    sys.modules["app.core.credentials"].mint_cred_token = MagicMock(return_value="")

    mock_analytics = MagicMock()
    mock_eval = MagicMock()

    db = _make_db(run, version)

    with patch("app.runtime.executor.SessionLocal", MagicMock(return_value=db)), \
         patch("app.runtime.executor._emit_run_analytics", mock_analytics), \
         patch("app.runtime.executor._enqueue_online_eval", mock_eval), \
         patch("app.runtime.executor.get_all_credentials",
               return_value=MagicMock(_data={}, keys=lambda: [])), \
         patch("app.runtime.executor._emit"), \
         patch("app.runtime.executor._now", return_value=None), \
         patch("app.runtime.executor.settings", _FAKE_SETTINGS), \
         patch("sqlalchemy.orm.joinedload", MagicMock(return_value=MagicMock())):
        execute_run(str(run.id))

    return mock_analytics, mock_eval


def test_execute_run_paused_is_resumable():
    run = _make_run("paused")
    version = _make_version()

    dag = MagicMock(return_value={})
    _run_execute_run(run, version, dag_mock=dag)

    assert run.status == "running"
    dag.assert_called_once()


def test_execute_run_happy_path_status_transitions():
    run = _make_run("pending")
    version = _make_version()

    dag = MagicMock(return_value={})
    mock_analytics, mock_eval = _run_execute_run(run, version, dag_mock=dag)

    assert run.status == "running"
    dag.assert_called_once()
    mock_analytics.assert_called()
    mock_eval.assert_called()


def test_execute_run_crash_sets_failed_status():
    run = _make_run("pending")
    version = _make_version()

    mock_analytics, _ = _run_execute_run(
        run, version, dag_raises=RuntimeError("dag exploded")
    )

    assert run.status == "failed"
    failed_calls = [c for c in mock_analytics.call_args_list if c.kwargs.get("outcome") == "failed"]
    assert len(failed_calls) >= 1


def test_execute_run_crash_still_emits_analytics_with_failed_outcome():
    run = _make_run("pending")
    version = _make_version()

    mock_analytics, _ = _run_execute_run(
        run, version, dag_raises=RuntimeError("oops")
    )

    mock_analytics.assert_called()
    failed_calls = [c for c in mock_analytics.call_args_list if c.kwargs.get("outcome") == "failed"]
    assert len(failed_calls) >= 1


def test_execute_run_enqueues_eval_on_success():
    run = _make_run("pending")
    version = _make_version()

    _, mock_eval = _run_execute_run(run, version, dag_mock=MagicMock(return_value={}))

    mock_eval.assert_called_once_with(str(run.id))


def test_execute_run_enqueues_eval_on_failure():
    run = _make_run("pending")
    version = _make_version()

    _, mock_eval = _run_execute_run(
        run, version, dag_raises=RuntimeError("crash")
    )

    mock_eval.assert_called()
