"""
Tests for AI Rollout (epic #961) — CLI instruction file management.

Covers:
  - _patch_tool_instruction_files: new file, idempotent re-sync, dry_run, existing content preserved
  - _reset_tool_instruction_files: strips markers, preserves surrounding content
  - _check_instructions_staleness: stale version, up-to-date, no local version
"""
from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# ── ensure conduct_cli is importable ─────────────────────────────────────────
CONDUCT_CLI_SRC = Path(__file__).resolve().parent.parent / "src"
if str(CONDUCT_CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CONDUCT_CLI_SRC))

import conduct_cli.guard as guard_mod
from conduct_cli.guard import _patch_tool_instruction_files, _reset_tool_instruction_files

MARKER_START = "<!-- ConductGuard — managed by conduct guard sync -->"
MARKER_END   = "<!-- /ConductGuard -->"

# Five target filenames relative to repo root
_TARGET_NAMES = [
    "CLAUDE.md",
    ".github/copilot-instructions.md",
    "AGENTS.md",
    ".cursorrules",
    ".windsurfrules",
]


def _make_api_response(content: str = "# team rules\n", version: str = "v1") -> MagicMock:
    """Return a mock urllib response yielding the given JSON payload."""
    payload = json.dumps({"content": content, "version": version}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = payload
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _redirect_cwd_and_home(tmp_path: Path, monkeypatch) -> Path:
    """
    Point Path.cwd() and Path.home() at tmp_path sub-dirs.
    Also create a fake .git so _patch_tool_instruction_files finds a repo_root.
    Returns the repo root path.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    home = tmp_path / "home"
    home.mkdir()

    monkeypatch.chdir(repo)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return repo


# ─────────────────────────────────────────────────────────────────────────────
# 1. New file created — all 5 targets get marker block
# ─────────────────────────────────────────────────────────────────────────────

def test_patch_creates_new_files_with_marker_block(tmp_path, monkeypatch, capsys):
    repo = _redirect_cwd_and_home(tmp_path, monkeypatch)

    mock_resp = _make_api_response("# team rules\n", "v1")
    with patch("conduct_cli.guard.urllib.request.urlopen", return_value=mock_resp):
        _patch_tool_instruction_files(
            agent_token="tok-123",
            api_url="https://api.conductai.ai",
            dry_run=False,
        )

    for rel in _TARGET_NAMES:
        p = repo / rel
        assert p.exists(), f"Expected {rel} to be created"
        text = p.read_text()
        assert MARKER_START in text, f"{rel} missing marker start"
        assert MARKER_END in text, f"{rel} missing marker end"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Idempotent re-sync — marker block appears exactly once
# ─────────────────────────────────────────────────────────────────────────────

def test_patch_idempotent_resync(tmp_path, monkeypatch, capsys):
    repo = _redirect_cwd_and_home(tmp_path, monkeypatch)

    mock_resp = _make_api_response("# team rules\n", "v1")
    with patch("conduct_cli.guard.urllib.request.urlopen", return_value=mock_resp):
        _patch_tool_instruction_files("tok", "https://api.conductai.ai", dry_run=False)

    mock_resp2 = _make_api_response("# team rules\n", "v1")
    with patch("conduct_cli.guard.urllib.request.urlopen", return_value=mock_resp2):
        _patch_tool_instruction_files("tok", "https://api.conductai.ai", dry_run=False)

    for rel in _TARGET_NAMES:
        p = repo / rel
        text = p.read_text()
        assert text.count(MARKER_START) == 1, f"{rel} should have exactly one marker block after two syncs"
        assert text.count(MARKER_END) == 1, f"{rel} should have exactly one end marker"


# ─────────────────────────────────────────────────────────────────────────────
# 3. dry_run=True — no files written, something printed
# ─────────────────────────────────────────────────────────────────────────────

def test_patch_dry_run_does_not_write_files(tmp_path, monkeypatch, capsys):
    repo = _redirect_cwd_and_home(tmp_path, monkeypatch)

    mock_resp = _make_api_response("# team rules\n", "v1")
    with patch("conduct_cli.guard.urllib.request.urlopen", return_value=mock_resp):
        _patch_tool_instruction_files("tok", "https://api.conductai.ai", dry_run=True)

    for rel in _TARGET_NAMES:
        p = repo / rel
        assert not p.exists(), f"{rel} should NOT be created in dry_run mode"

    out = capsys.readouterr().out
    assert out.strip(), "Expected at least some output in dry_run mode"
    assert "[dry-run]" in out


# ─────────────────────────────────────────────────────────────────────────────
# 4. Existing developer content preserved
# ─────────────────────────────────────────────────────────────────────────────

def test_patch_preserves_existing_developer_content(tmp_path, monkeypatch, capsys):
    repo = _redirect_cwd_and_home(tmp_path, monkeypatch)

    claude_md = repo / "CLAUDE.md"
    claude_md.write_text("# My rules\nDo X\n")

    mock_resp = _make_api_response("# team rules\n", "v1")
    with patch("conduct_cli.guard.urllib.request.urlopen", return_value=mock_resp):
        _patch_tool_instruction_files("tok", "https://api.conductai.ai", dry_run=False)

    text = claude_md.read_text()
    assert "# My rules" in text, "Original developer content should be preserved"
    assert "Do X" in text, "Original developer content should be preserved"
    assert MARKER_START in text, "Marker block should be appended"
    assert MARKER_END in text, "Marker block end should be present"


# ─────────────────────────────────────────────────────────────────────────────
# 5. _reset_tool_instruction_files — strips markers, preserves surrounding content
# ─────────────────────────────────────────────────────────────────────────────

def test_reset_strips_marker_block_and_preserves_content(tmp_path, monkeypatch, capsys):
    repo = _redirect_cwd_and_home(tmp_path, monkeypatch)

    # _reset uses a slightly different marker format (without the long comment)
    # Match what _reset_tool_instruction_files actually searches for
    RESET_MARKER_START = "<!-- ConductGuard -->"
    RESET_MARKER_END   = "<!-- /ConductGuard -->"
    block = f"\n{RESET_MARKER_START}\n## Rules\nDo guard stuff.\n{RESET_MARKER_END}\n"

    claude_md = repo / "CLAUDE.md"
    claude_md.write_text(f"# Dev content\nKeep this.\n{block}\n# After block\n")

    # _reset uses Path.cwd() directly for repo targets and Path.home() for home
    _reset_tool_instruction_files()

    text = claude_md.read_text()
    assert RESET_MARKER_START not in text, "Marker start should be stripped"
    assert RESET_MARKER_END not in text, "Marker end should be stripped"
    assert "Keep this." in text, "Content before marker block must be preserved"


def test_reset_no_marker_prints_notice(tmp_path, monkeypatch, capsys):
    repo = _redirect_cwd_and_home(tmp_path, monkeypatch)

    claude_md = repo / "CLAUDE.md"
    claude_md.write_text("# No guard block here\n")

    _reset_tool_instruction_files()

    out = capsys.readouterr().out
    assert "No ConductGuard block" in out or "No ConductGuard blocks" in out


# ─────────────────────────────────────────────────────────────────────────────
# 6-8. _check_instructions_staleness
# ─────────────────────────────────────────────────────────────────────────────

# Re-import from session_start
SESSION_HOOK_SRC = CONDUCT_CLI_SRC
if str(SESSION_HOOK_SRC) not in sys.path:
    sys.path.insert(0, str(SESSION_HOOK_SRC))

from conduct_cli.hooks.session_start import _check_instructions_staleness


def _make_version_response(version: str) -> MagicMock:
    payload = json.dumps({"version": version}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = payload
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# 6. Stale: local v1, remote v2 → warning printed
def test_staleness_check_stale_prints_warning(capsys):
    cfg = {
        "api_url": "https://api.conductai.ai",
        "agent_token": "tok-abc",
        "instructions_version": "v1",
    }
    remote_resp = _make_version_response("v2")

    # urllib.request is imported inside the function body as a local alias (_req).
    # Patch the canonical module so the alias resolves to our mock.
    with patch("conduct_cli.hooks.session_start.load_config", return_value=cfg), \
         patch("urllib.request.urlopen", return_value=remote_resp):
        _check_instructions_staleness()

    out = capsys.readouterr().out
    assert "v1" in out and "v2" in out, "Warning should mention both versions"
    assert "conduct guard sync" in out, "Warning should suggest running sync"


# 7. Up to date: local v1, remote v1 → nothing printed
def test_staleness_check_up_to_date_no_output(capsys):
    cfg = {
        "api_url": "https://api.conductai.ai",
        "agent_token": "tok-abc",
        "instructions_version": "v1",
    }
    remote_resp = _make_version_response("v1")

    with patch("conduct_cli.hooks.session_start.load_config", return_value=cfg), \
         patch("urllib.request.urlopen", return_value=remote_resp):
        _check_instructions_staleness()

    out = capsys.readouterr().out
    assert out.strip() == "", f"Expected no output when up-to-date, got: {repr(out)}"


# 8. No local version → returns silently without making HTTP call
def test_staleness_check_no_local_version_silent(capsys):
    cfg = {
        "api_url": "https://api.conductai.ai",
        "agent_token": "tok-abc",
        # no instructions_version key
    }

    with patch("conduct_cli.hooks.session_start.load_config", return_value=cfg), \
         patch("urllib.request.urlopen") as mock_open:
        _check_instructions_staleness()

    mock_open.assert_not_called()
    out = capsys.readouterr().out
    assert out.strip() == "", "Expected no output when no local version"
