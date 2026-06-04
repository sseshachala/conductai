"""
Unit tests for _seed_starter_policies in app/routers/projects.py.

All tests use a mock DB that captures db.add() calls — no real Postgres needed.

Import strategy: stub out ORM-heavy modules that trigger SQLAlchemy mapper
configuration (which requires all related models to be registered) before
importing the function under test. This mirrors the pattern in test_guard.py.
"""
from __future__ import annotations

import os
import sys
import uuid
import importlib
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

# Minimal env so Settings() doesn't blow up on import
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_marshal")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

# Stub modules that have side-effects or heavy deps so that importing
# app.routers.projects doesn't trigger full SQLAlchemy mapper resolution.
_STUBS = [
    "structlog",
    "redis",
    "sentry_sdk",
    "app.core.email",
    "app.core.auth",
    "app.models.audit_log",
    "app.models.environment",
    "app.models.integration",
    "app.models.run",
    "app.models.workflow",
    "app.models.workspace",
    "app.core.crypto",
]
_ORIG_STUBS = {name: sys.modules.get(name) for name in _STUBS}
for _mod in _STUBS:
    sys.modules.setdefault(_mod, MagicMock())

# Stub app.core.config before any app import touches it
_cfg_stub = MagicMock()
_cfg_stub.settings = MagicMock(
    sentry_dsn=None,
    sqlalchemy_database_url="postgresql://test:test@localhost:5432/test_marshal",
    encryption_key="test-key-32-bytes-long-xxxxxxxx!",
    allowed_egress_hosts=[],
    admin_secret=None,
)
sys.modules.setdefault("app.core.config", _cfg_stub)

# Stub app.core.database so SQLAlchemy Base is never resolved against the
# real models (avoids "can't locate 'Environment'" mapper errors)
_db_stub = MagicMock()
sys.modules.setdefault("app.core.database", _db_stub)

# Finally import the function under test
from app.routers.projects import _seed_starter_policies  # noqa: E402

# Restore leaked module entries after import so later tests can import the real
# modules without seeing these collection-time stubs.
sys.modules.pop("app.core.config", None)
sys.modules.pop("app.core.database", None)
for _mod, _orig in _ORIG_STUBS.items():
    if _orig is not None:
        sys.modules[_mod] = _orig
    else:
        sys.modules.pop(_mod, None)
importlib.invalidate_caches()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_seed() -> list:
    """Call _seed_starter_policies with a mock DB and return added objects."""
    class _GuardPolicy:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    _guard_models_stub = MagicMock()
    _guard_models_stub.GuardPolicy = _GuardPolicy
    original_guard_models = sys.modules.get("app.modules.guard.models")
    sys.modules["app.modules.guard.models"] = _guard_models_stub

    db = MagicMock()
    added: list = []
    db.add.side_effect = lambda obj: added.append(obj)
    try:
        _seed_starter_policies(db, uuid.uuid4(), datetime.now(timezone.utc))
    finally:
        if original_guard_models is not None:
            sys.modules["app.modules.guard.models"] = original_guard_models
        else:
            sys.modules.pop("app.modules.guard.models", None)
    return added


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_seed_starter_policies_count():
    """_seed_starter_policies adds exactly 18 policies."""
    added = _run_seed()
    assert len(added) == 18


def test_seed_starter_policies_actions():
    """Seeded policies cover all 4 action types: BLOCK, WARN, APPROVAL, AUDIT."""
    added = _run_seed()
    actions = {obj.action for obj in added}
    assert actions == {"BLOCK", "WARN", "APPROVAL", "AUDIT"}


def test_seed_starter_policies_all_enabled():
    """Every seeded policy has enabled=True."""
    added = _run_seed()
    assert all(obj.enabled is True for obj in added)


def test_seed_starter_policies_builtin():
    """Every seeded policy has builtin=True."""
    added = _run_seed()
    assert all(obj.builtin is True for obj in added)


def test_seed_starter_policies_unique_rule_ids():
    """No duplicate rule_id values across the seeded policies."""
    added = _run_seed()
    rule_ids = [obj.rule_id for obj in added]
    assert len(rule_ids) == len(set(rule_ids))


def test_seed_starter_policies_all_have_patterns():
    """Every seeded policy has a non-empty match_pattern."""
    added = _run_seed()
    for obj in added:
        assert obj.match_pattern and obj.match_pattern.strip(), (
            f"Policy '{obj.rule_id}' has an empty match_pattern"
        )


def test_seed_starter_policies_destructive_ops():
    """The 6 destructive-operation rule_ids are present."""
    added = _run_seed()
    rule_ids = {obj.rule_id for obj in added}
    expected = {
        "no-rm-rf",
        "no-git-reset-hard",
        "no-force-push",
        "no-drop-table",
        "no-truncate-table",
        "no-delete-without-where",
    }
    assert expected <= rule_ids, f"Missing destructive-op rules: {expected - rule_ids}"


def test_seed_starter_policies_secrets():
    """The 4 secrets/credentials rule_ids are present."""
    added = _run_seed()
    rule_ids = {obj.rule_id for obj in added}
    expected = {
        "no-env-commits",
        "no-hardcoded-secrets",
        "no-aws-keys",
        "no-private-key-files",
    }
    assert expected <= rule_ids, f"Missing secrets rules: {expected - rule_ids}"


def test_seed_starter_policies_prod_gates():
    """The 5 production-gate rule_ids are present."""
    added = _run_seed()
    rule_ids = {obj.rule_id for obj in added}
    expected = {
        "approve-prod-deploy",
        "approve-db-migration-prod",
        "approve-terraform-destroy",
        "approve-kubectl-delete",
        "approve-prod-env-edit",
    }
    assert expected <= rule_ids, f"Missing prod-gate rules: {expected - rule_ids}"


def test_seed_starter_policies_audit():
    """The 3 audit rule_ids are present."""
    added = _run_seed()
    rule_ids = {obj.rule_id for obj in added}
    expected = {
        "audit-migrations",
        "audit-ci-config",
        "audit-dockerfile",
    }
    assert expected <= rule_ids, f"Missing audit rules: {expected - rule_ids}"
