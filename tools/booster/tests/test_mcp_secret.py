from __future__ import annotations

import json
from pathlib import Path

from booster.cli import _scrub_mcp_secret


def _mcp(root: Path, env: dict) -> Path:
    p = root / ".mcp.json"
    p.write_text(json.dumps({"mcpServers": {
        "agent-booster": {"command": "booster", "args": ["serve"], "env": env},
        "other": {"env": {"BOOSTER_SECRET": "untouched"}},
    }}))
    return p


def test_scrub_removes_literal_secret(tmp_path):
    p = _mcp(tmp_path, {"BOOSTER_SECRET": "abc123", "KEEP": "1"})
    _scrub_mcp_secret(tmp_path)
    data = json.loads(p.read_text())["mcpServers"]
    assert data["agent-booster"]["env"] == {"KEEP": "1"}
    assert data["other"]["env"] == {"BOOSTER_SECRET": "untouched"}


def test_scrub_leaves_clean_file_byte_identical(tmp_path):
    p = _mcp(tmp_path, {})
    before = p.read_text()
    _scrub_mcp_secret(tmp_path)
    assert p.read_text() == before
