"""Ensure local src/ takes precedence over any installed conduct_cli package."""
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# Force-reload conduct_cli.guard from local src if installed version was cached
import importlib
for mod in list(sys.modules):
    if mod.startswith("conduct_cli"):
        del sys.modules[mod]

import pytest


@pytest.fixture(autouse=True)
def _no_real_claude_config(monkeypatch):
    # guard sync edits $CLAUDE_CONFIG_DIR/.claude.json; never let a developer's real one leak in.
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


@pytest.fixture(autouse=True)
def _no_real_token_propagation(monkeypatch):
    # Token rotation rewrites client configs under $HOME; tests opt in with their own paths.
    from conduct_cli import token_propagation
    monkeypatch.setattr(token_propagation, "_candidate_paths", lambda: [])
