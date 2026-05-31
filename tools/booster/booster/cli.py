from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click

from booster.indexer import SymbolIndexer

_MCP_ENTRY = {"command": "booster", "args": ["serve"]}

_CURSOR_SNIPPET = {
    "mcpServers": {
        "agent-booster": _MCP_ENTRY,
    }
}

_CODEX_SNIPPET = {
    "mcp": {
        "servers": {
            "agent-booster": _MCP_ENTRY,
        }
    }
}

_CLAUDE_MD_BLOCK = """\
<!-- booster:start -->
## Agent Booster — Context-Efficient Reads

Prefer booster MCP tools over native Read/Grep:
- `mcp__agent-booster__search_context` instead of Grep — semantic search across all indexed symbols
- `mcp__agent-booster__smart_read` instead of Read — returns only relevant symbol slices for a task
- `mcp__agent-booster__get_symbols` to survey a file's structure before reading
- `mcp__agent-booster__route_model` at the start of any non-trivial task to pick the right model tier

Run `booster gain` to see token savings.
<!-- booster:end -->"""

_HOOK_COMMAND = "python3 .claude/hooks/booster-gate.py"

_GATE_SCRIPT = '''\
#!/usr/bin/env python3
"""Agent Booster gate hook — redirects Read to smart_read for indexed files."""
import json
import sqlite3
import sys
from pathlib import Path

data = json.load(sys.stdin)
tool_input = data.get("tool_input", {})
file_path = tool_input.get("file_path", "")
if not file_path:
    sys.exit(0)

cwd = Path.cwd()
db_path = cwd / ".booster" / "symbols.db"
if not db_path.exists():
    sys.exit(0)

try:
    rel = str(Path(file_path).relative_to(cwd))
except ValueError:
    sys.exit(0)

try:
    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM symbols WHERE file = ?", (rel,)).fetchone()[0]
    conn.close()
except Exception:
    sys.exit(0)

if count > 0:
    print(
        f"[booster] \'{rel}\' has {count} indexed symbols. "
        "Use mcp__agent-booster__smart_read with a task description "
        "to read only the relevant sections and save tokens."
    )
    sys.exit(1)

sys.exit(0)
'''


def _merge_mcp_json(root: Path) -> None:
    mcp_path = root / ".mcp.json"
    data: dict = {}
    if mcp_path.exists():
        data = json.loads(mcp_path.read_text())
    data.setdefault("mcpServers", {})["agent-booster"] = _MCP_ENTRY
    mcp_path.write_text(json.dumps(data, indent=2) + "\n")
    click.echo(f"  wrote {mcp_path.relative_to(root)}")


def _remove_mcp_json(root: Path) -> None:
    mcp_path = root / ".mcp.json"
    if not mcp_path.exists():
        return
    data = json.loads(mcp_path.read_text())
    data.get("mcpServers", {}).pop("agent-booster", None)
    if not data.get("mcpServers"):
        data.pop("mcpServers", None)
    if data:
        mcp_path.write_text(json.dumps(data, indent=2) + "\n")
    else:
        mcp_path.unlink()
    click.echo(f"  cleaned {mcp_path.relative_to(root)}")


def _append_claude_md(root: Path) -> None:
    claude_md = root / "CLAUDE.md"
    existing = claude_md.read_text() if claude_md.exists() else ""
    if "<!-- booster:start -->" in existing:
        click.echo("  CLAUDE.md already has booster block — skipped")
        return
    sep = "\n\n" if existing and not existing.endswith("\n\n") else ""
    claude_md.write_text(existing + sep + _CLAUDE_MD_BLOCK + "\n")
    click.echo(f"  appended booster block to {claude_md.relative_to(root)}")


def _remove_claude_md(root: Path) -> None:
    claude_md = root / "CLAUDE.md"
    if not claude_md.exists():
        return
    text = claude_md.read_text()
    start = text.find("<!-- booster:start -->")
    end = text.find("<!-- booster:end -->")
    if start == -1 or end == -1:
        return
    end += len("<!-- booster:end -->")
    cleaned = (text[:start].rstrip() + "\n" + text[end:].lstrip()).strip()
    if cleaned:
        claude_md.write_text(cleaned + "\n")
    else:
        claude_md.unlink()
    click.echo(f"  removed booster block from {claude_md.relative_to(root)}")


def _install_hook(root: Path) -> None:
    hooks_dir = root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    gate = hooks_dir / "booster-gate.py"
    gate.write_text(_GATE_SCRIPT)
    click.echo(f"  wrote {gate.relative_to(root)}")

    settings_path = root / ".claude" / "settings.json"
    settings: dict = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())

    hooks = settings.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])

    already = any(
        h.get("matcher") == "Read"
        and any(e.get("command") == _HOOK_COMMAND for e in h.get("hooks", []))
        for h in pre
    )
    if not already:
        pre.append({"matcher": "Read", "hooks": [{"type": "command", "command": _HOOK_COMMAND}]})

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    click.echo(f"  updated {settings_path.relative_to(root)}")


def _remove_hook(root: Path) -> None:
    gate = root / ".claude" / "hooks" / "booster-gate.py"
    if gate.exists():
        gate.unlink()
        click.echo(f"  removed {gate.relative_to(root)}")

    settings_path = root / ".claude" / "settings.json"
    if not settings_path.exists():
        return
    settings = json.loads(settings_path.read_text())
    pre = settings.get("hooks", {}).get("PreToolUse", [])
    filtered = [
        h for h in pre
        if not (
            h.get("matcher") == "Read"
            and any(e.get("command") == _HOOK_COMMAND for e in h.get("hooks", []))
        )
    ]
    settings["hooks"]["PreToolUse"] = filtered
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    click.echo(f"  updated {settings_path.relative_to(root)}")


@click.group()
def main() -> None:
    pass


@main.command("index")
@click.option("--embed", is_flag=True, default=False)
def cmd_index(embed: bool) -> None:
    root = Path.cwd()
    indexer = SymbolIndexer(root)
    files, symbols = indexer.index_all(embed=embed)
    click.echo(f"Indexed {files} files, {symbols} symbols.")


@main.command("embed")
def cmd_embed() -> None:
    root = Path.cwd()
    indexer = SymbolIndexer(root)
    n = indexer.build_embeddings()
    click.echo(f"Built embeddings for {n} symbols.")


@main.command("search")
@click.argument("query")
def cmd_search(query: str) -> None:
    root = Path.cwd()
    indexer = SymbolIndexer(root)
    results = indexer.search(query)
    if not results:
        click.echo("No matches.")
        return
    for r in results:
        click.echo(f"{r['file']}:{r['start_line']}  {r['kind']} {r['name']}  {r['signature']}")


@main.command("serve")
def cmd_serve() -> None:
    from booster.mcp_server import serve
    asyncio.run(serve())


@main.command("init")
@click.argument("platform", type=click.Choice(["claude", "cursor", "windsurf", "codex", "all"]))
def cmd_init(platform: str) -> None:
    root = Path.cwd()

    if platform in ("claude", "all"):
        click.echo("Installing booster for Claude Code:")
        _merge_mcp_json(root)
        _append_claude_md(root)
        _install_hook(root)
        click.echo("Done. Run: booster index && booster embed")

    if platform in ("cursor", "all"):
        mcp_path = root / ".cursor" / "mcp.json"
        mcp_path.parent.mkdir(exist_ok=True)
        existing: dict = json.loads(mcp_path.read_text()) if mcp_path.exists() else {}
        existing.setdefault("mcpServers", {})["agent-booster"] = _MCP_ENTRY
        mcp_path.write_text(json.dumps(existing, indent=2) + "\n")
        click.echo(f"  wrote {mcp_path}")

    if platform in ("windsurf", "all"):
        mcp_path = Path.home() / ".windsurf" / "mcp.json"
        mcp_path.parent.mkdir(parents=True, exist_ok=True)
        existing2: dict = json.loads(mcp_path.read_text()) if mcp_path.exists() else {}
        existing2.setdefault("mcpServers", {})["agent-booster"] = _MCP_ENTRY
        mcp_path.write_text(json.dumps(existing2, indent=2) + "\n")
        click.echo(f"  wrote {mcp_path}")

    if platform in ("codex", "all"):
        click.echo("Add to ~/.codex/config.json:")
        click.echo(json.dumps(_CODEX_SNIPPET, indent=2))


@main.command("remove")
@click.argument("platform", type=click.Choice(["claude", "cursor", "windsurf", "codex", "all"]))
def cmd_remove(platform: str) -> None:
    root = Path.cwd()

    if platform in ("claude", "all"):
        click.echo("Removing booster from Claude Code:")
        _remove_mcp_json(root)
        _remove_claude_md(root)
        _remove_hook(root)
        click.echo("Done.")

    if platform in ("cursor", "all"):
        mcp_path = root / ".cursor" / "mcp.json"
        if mcp_path.exists():
            data = json.loads(mcp_path.read_text())
            data.get("mcpServers", {}).pop("agent-booster", None)
            mcp_path.write_text(json.dumps(data, indent=2) + "\n")
            click.echo(f"  cleaned {mcp_path}")

    if platform in ("windsurf", "all"):
        mcp_path = Path.home() / ".windsurf" / "mcp.json"
        if mcp_path.exists():
            data = json.loads(mcp_path.read_text())
            data.get("mcpServers", {}).pop("agent-booster", None)
            mcp_path.write_text(json.dumps(data, indent=2) + "\n")
            click.echo(f"  cleaned {mcp_path}")


@main.command("route")
@click.argument("task")
def cmd_route(task: str) -> None:
    from booster.mcp_server import _route_model

    root = Path.cwd()
    indexer = SymbolIndexer(root)
    result = _route_model(indexer, task, [])
    click.echo(f"{result['model']}  ({result['reason']})")


@main.command("gain")
def cmd_gain() -> None:
    from booster.stats import StatsTracker

    tracker = StatsTracker(Path.cwd())
    s = tracker.summary()

    if s["total_reads"] == 0:
        click.echo("No data yet. Use booster serve and make some smart_read calls first.")
        return

    click.echo()
    click.echo("Agent Booster — Token Savings Report")
    click.echo("\u2500" * 37)
    click.echo(f"Active days:        {s['active_days']:,}")
    click.echo(f"Total reads:        {s['total_reads']:,}")
    click.echo(f"Tokens served:      {s['slice_tokens']:,}")
    click.echo(f"Tokens saved:       {s['saved_tokens']:,}")
    click.echo(f"Savings rate:       {s['savings_pct']:.0f}%")

    if s["top_files"]:
        click.echo()
        click.echo("Top files by savings:")
        for entry in s["top_files"]:
            name = Path(entry["file"]).name
            click.echo(f"  {name:<24} {entry['saved']:,} tokens saved  ({entry['reads']} reads)")
