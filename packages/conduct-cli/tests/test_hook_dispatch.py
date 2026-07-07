"""Regression tests for hook dispatch and entrypoint wiring.

Catches the class of bug where a refactor silently breaks:
  - hook.py routing (post → posttooluse, else → pretooluse)
  - hook module importability
  - pyproject.toml entrypoint resolution
  - token backfill return types
  - journal payload structure
"""
from __future__ import annotations

import importlib
import json
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HOOKS_DIR = Path(__file__).parent.parent / "src" / "conduct_cli" / "hooks"
GUARD_DIR  = Path(__file__).parent.parent / "src" / "conduct_cli"


# ── 1. hook.py dispatch ───────────────────────────────────────────────────────

def _hook_py_content() -> str:
    """Read the thin-launcher template that gets written to ~/.conductguard/hook.py."""
    from conduct_cli.guard import _THIN_LAUNCHERS
    return _THIN_LAUNCHERS["pretooluse"]


def test_hook_py_dispatches_post_to_posttooluse():
    content = _hook_py_content()
    assert "post" in content, "hook.py must branch on 'post' arg"
    assert "posttooluse" in content, "hook.py must route 'post' to posttooluse"


def test_hook_py_dispatches_default_to_pretooluse():
    content = _hook_py_content()
    assert "pretooluse" in content, "hook.py must route default to pretooluse"


def test_hook_py_is_valid_python():
    import py_compile, tempfile, os
    content = _hook_py_content()
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(content)
        name = f.name
    try:
        py_compile.compile(name, doraise=True)
    finally:
        os.unlink(name)


# ── 2. All hook modules importable ───────────────────────────────────────────

@pytest.mark.parametrize("module", [
    "conduct_cli.hooks.pretooluse",
    "conduct_cli.hooks.posttooluse",
    "conduct_cli.hooks.stop",
    "conduct_cli.hooks.session_report_push",
    "conduct_cli.hooks.base",
])
def test_hook_module_importable(module):
    mod = importlib.import_module(module)
    assert mod is not None


@pytest.mark.parametrize("module,fn", [
    ("conduct_cli.hooks.pretooluse",        "main"),
    ("conduct_cli.hooks.posttooluse",       "main"),
    ("conduct_cli.hooks.stop",              "main"),
    ("conduct_cli.hooks.session_report_push", "run"),
])
def test_hook_entrypoint_callable(module, fn):
    mod = importlib.import_module(module)
    assert callable(getattr(mod, fn, None)), f"{module}:{fn} must be callable"


# ── 3. pyproject.toml entrypoints resolve ────────────────────────────────────

def _parse_entrypoints() -> dict[str, str]:
    """Read [project.scripts] from pyproject.toml."""
    import tomllib  # Python 3.11+; fall back to tomli
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    try:
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    except ImportError:
        try:
            import tomli
            with open(pyproject, "rb") as f:
                data = tomli.load(f)
        except ImportError:
            pytest.skip("tomllib/tomli not available — skipping entrypoint check")
    return data.get("project", {}).get("scripts", {})


def test_conductguard_post_entrypoint_resolves():
    eps = _parse_entrypoints()
    target = eps.get("conductguard-post", "")
    assert target, "conductguard-post must be in [project.scripts]"
    module_path, fn_name = target.rsplit(":", 1)
    mod = importlib.import_module(module_path)
    assert callable(getattr(mod, fn_name, None)), (
        f"conductguard-post points to {target} which is not callable. "
        "Did a refactor move the function without updating pyproject.toml?"
    )


def test_conduct_entrypoint_resolves():
    eps = _parse_entrypoints()
    target = eps.get("conduct", "")
    assert target, "conduct must be in [project.scripts]"
    module_path, fn_name = target.rsplit(":", 1)
    mod = importlib.import_module(module_path)
    assert callable(getattr(mod, fn_name, None))


def test_conductguard_mcp_entrypoint_resolves():
    eps = _parse_entrypoints()
    for name in ("conduct-mcp", "conductguard-mcp"):
        target = eps.get(name, "")
        if not target:
            continue
        module_path, fn_name = target.rsplit(":", 1)
        mod = importlib.import_module(module_path)
        assert callable(getattr(mod, fn_name, None)), f"{name} entrypoint broken"


# ── 4. Token backfill returns correct types ──────────────────────────────────

def test_read_tokens_returns_ints_on_missing_file():
    from conduct_cli.hooks.posttooluse import _read_tokens_from_transcript
    tin, tout = _read_tokens_from_transcript("/nonexistent/path.jsonl", "tool_use_abc123")
    assert isinstance(tin, int), "tokens_input must be int"
    assert isinstance(tout, int), "tokens_output must be int"


def test_read_tokens_returns_ints_on_no_match(tmp_path):
    from conduct_cli.hooks.posttooluse import _read_tokens_from_transcript
    f = tmp_path / "session.jsonl"
    f.write_text(json.dumps({"type": "text", "content": "hello"}) + "\n")
    tin, tout = _read_tokens_from_transcript(str(f), "tool_use_xyz")
    assert isinstance(tin, int)
    assert isinstance(tout, int)


def test_read_tokens_extracts_from_valid_transcript(tmp_path):
    from conduct_cli.hooks.posttooluse import _read_tokens_from_transcript
    tool_use_id = "toolu_01abc"
    entry = {
        "message": {
            "usage": {"input_tokens": 1500, "output_tokens": 200,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 100},
            "content": [{"type": "tool_use", "id": tool_use_id, "name": "read"}],
        }
    }
    f = tmp_path / "session.jsonl"
    f.write_text(json.dumps(entry) + "\n")
    tin, tout = _read_tokens_from_transcript(str(f), tool_use_id)
    assert tin == 1600  # input + cache_read
    assert tout == 200


# ── 5. Journal payload structure ─────────────────────────────────────────────

def test_post_event_tool_call_fits_db_column(tmp_path):
    """tool_call in journal payload must not exceed 255 chars (DB column limit)."""
    from conduct_cli.hooks import base

    journal_dir = tmp_path / "journal"
    cfg = {"workspace_id": "test-ws", "user_email": "x@x.com", "api_url": "https://api.conductai.ai"}
    long_name = "mcp__" + "x" * 260  # deliberately over 255

    with (
        patch.object(base, "JOURNAL_DIR", journal_dir),
        patch.object(base, "JOURNAL_PID_PATH", journal_dir / "drain.pid"),
        patch.object(base, "load_config", return_value=cfg),
        patch.object(base, "ensure_drain_daemon"),
    ):
        base.post_event(long_name, {}, "allowed", session_id="s")

    files = list(journal_dir.glob("*.json"))
    payload = json.loads(json.loads(files[0].read_text())["payload"])
    assert len(payload["tool_call"]) <= 255, "tool_call must be truncated to 255 chars"


def test_post_event_journal_payload_has_required_fields(tmp_path):
    """post_event must journal a payload with workspace_id and hook_session_id."""
    from conduct_cli.hooks import base

    journal_dir = tmp_path / "journal"
    cfg = {
        "workspace_id": "test-ws-id",
        "user_email": "test@example.com",
        "api_url": "https://api.conductai.ai",
    }
    with (
        patch.object(base, "JOURNAL_DIR", journal_dir),
        patch.object(base, "JOURNAL_PID_PATH", journal_dir / "drain.pid"),
        patch.object(base, "load_config", return_value=cfg),
        patch.object(base, "ensure_drain_daemon"),
    ):
        base.post_event("bash", {"command": "ls"}, "allowed", session_id="sess-123")

    files = list(journal_dir.glob("*.json"))
    assert files, "post_event must write to journal"
    entry = json.loads(files[0].read_text())
    payload = json.loads(entry["payload"])
    assert payload["workspace_id"] == "test-ws-id"
    assert payload["hook_session_id"] == "sess-123"
    assert payload["decision"] == "allowed"
    assert "user_email" in payload
