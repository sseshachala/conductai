"""Unit tests for _seed_starter_policies in app/routers/projects.py.

After #751 (drop guard_policies), _seed_starter_policies no longer writes
individual GuardPolicy rows — it installs the conduct-base skill pack by
registering a WorkspaceSkillPack row. The active rules then resolve via
compute_policy() against skill_packs.rules JSONB.

These tests verify the new contract.
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

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_marshal")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")

# Stub heavy ORM modules to avoid mapper resolution overhead on import.
for _mod in [
    "app.modules.guard.models",
]:
    if _mod in sys.modules:
        sys.modules.pop(_mod, None)
importlib.invalidate_caches()


def _run_seed():
    """Call _seed_starter_policies with a mock DB and capture db.add() calls."""
    class _WorkspaceSkillPack:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    _guard_models_stub = MagicMock()
    _guard_models_stub.WorkspaceSkillPack = _WorkspaceSkillPack
    original = sys.modules.get("app.modules.guard.models")
    sys.modules["app.modules.guard.models"] = _guard_models_stub

    db = MagicMock()
    db.get.return_value = None   # workspace not yet installed
    added: list = []
    db.add.side_effect = lambda obj: added.append(obj)

    try:
        from app.routers.projects import _seed_starter_policies
        _seed_starter_policies(db, uuid.uuid4(), datetime.now(timezone.utc))
    finally:
        if original is not None:
            sys.modules["app.modules.guard.models"] = original
        else:
            sys.modules.pop("app.modules.guard.models", None)
    return added


def test_seed_installs_conduct_base():
    """_seed_starter_policies installs exactly one pack: conduct-base."""
    added = _run_seed()
    assert len(added) == 1
    assert added[0].pack_slug == "conduct-base"


def test_seed_is_idempotent():
    """If conduct-base is already installed, _seed_starter_policies adds nothing."""
    class _WorkspaceSkillPack:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    _guard_models_stub = MagicMock()
    _guard_models_stub.WorkspaceSkillPack = _WorkspaceSkillPack
    original = sys.modules.get("app.modules.guard.models")
    sys.modules["app.modules.guard.models"] = _guard_models_stub

    db = MagicMock()
    db.get.return_value = object()   # already installed
    added: list = []
    db.add.side_effect = lambda obj: added.append(obj)

    try:
        from app.routers.projects import _seed_starter_policies
        _seed_starter_policies(db, uuid.uuid4(), datetime.now(timezone.utc))
    finally:
        if original is not None:
            sys.modules["app.modules.guard.models"] = original
        else:
            sys.modules.pop("app.modules.guard.models", None)

    assert added == []


def test_seed_sets_installed_by_system_create():
    """The installed_by audit field marks the source of the install."""
    added = _run_seed()
    assert added[0].installed_by == "system:workspace_create"
