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

_RULES_BLOCK = """\
<!-- booster:start -->
## Agent Booster — Context-Efficient Reads

Prefer booster MCP tools over native file reads:
- `search_context` instead of searching files — semantic search across all indexed symbols
- `smart_read` instead of reading full files — returns only the relevant symbol slices for a task
- `get_symbols` to survey a file's structure before reading it
- `route_model` at the start of any non-trivial task to pick the right model tier

Run `booster gain` to see token savings.
<!-- booster:end -->"""

def _hook_command(root: Path) -> str:
    return f"python3 {root / '.claude' / 'hooks' / 'booster-gate.py'}"

def _grep_hook_command(root: Path) -> str:
    return f"python3 {root / '.claude' / 'hooks' / 'booster-grep-nudge.py'}"

def _route_hook_command(root: Path) -> str:
    return f"python3 {root / '.claude' / 'hooks' / 'booster-route.py'}"

def _agent_inject_command(root: Path) -> str:
    return f"python3 {root / '.claude' / 'hooks' / 'booster-agent-inject.py'}"

_GATE_SCRIPT = '''\
#!/usr/bin/env python3
"""Agent Booster gate hook — runs smart-read for indexed files, blocking the raw Read."""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

data = json.load(sys.stdin)
file_path = data.get("tool_input", {}).get("file_path", "")
if not file_path:
    sys.exit(0)

# Derive project root from this hook\'s known location — .claude/hooks/ is 2 levels down
root = Path(__file__).resolve().parent.parent

db_path = root / ".booster" / "symbols.db"
if not db_path.exists():
    sys.exit(0)

try:
    rel = str(Path(file_path).relative_to(root))
except ValueError:
    sys.exit(0)

try:
    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM symbols WHERE file = ?", (rel,)).fetchone()[0]
    conn.close()
except Exception:
    sys.exit(0)

if count == 0:
    sys.exit(0)  # not indexed — let Read proceed normally

try:
    r = subprocess.run(
        ["booster", "smart-read", rel],
        capture_output=True, text=True, timeout=10, cwd=str(root),
    )
    output = r.stdout.strip()
    if output:
        print(output)
        sys.exit(2)  # block raw Read — smart-read result is the content
except Exception:
    pass

sys.exit(0)  # fallback — let Read proceed if smart-read fails
'''

_GREP_NUDGE_SCRIPT = '''\
#!/usr/bin/env python3
"""Booster grep nudge — runs booster search for semantic patterns, blocking raw Grep."""
import json
import subprocess
import sys
from pathlib import Path

data = json.load(sys.stdin)
pattern = data.get("tool_input", {}).get("pattern", "")
if not pattern:
    sys.exit(0)

REGEX_CHARS = set(r"^$*+?[](){}\\\\|.")
is_regex = any(c in REGEX_CHARS for c in pattern)
word_count = len(pattern.split())

if not is_regex and word_count >= 2:
    root = Path(__file__).resolve().parent.parent
    db_path = root / ".booster" / "symbols.db"
    if not db_path.exists():
        sys.exit(0)  # not indexed — let Grep proceed

    try:
        r = subprocess.run(
            ["booster", "search", pattern],
            capture_output=True, text=True, timeout=10, cwd=str(root),
        )
        output = r.stdout.strip()
        if output:
            print(f"[booster/search] results for {pattern!r}:\\n{output}")
            sys.exit(2)  # block Grep — search results are the answer
        else:
            print(f"[booster] No indexed symbols match {pattern!r} — falling through to Grep.")
    except Exception:
        pass

sys.exit(0)
'''

_ROUTE_SCRIPT = '''\
#!/usr/bin/env python3
"""Booster route hook — recommends model tier at the start of every user turn."""
import json
import re
import subprocess
import sys
from pathlib import Path

data = json.load(sys.stdin)
message = data.get("message", "")

if not message or len(message.strip()) < 10:
    sys.exit(0)

# Strip control characters and null bytes before passing to subprocess
safe_message = re.sub(r\'[\\x00-\\x1f\\x7f]\', \' \', message).strip()[:300]

# Derive project root from this hook\'s known location — never trust external cwd
safe_cwd = Path(__file__).resolve().parent.parent

try:
    result = subprocess.run(
        ["booster", "route", safe_message],
        capture_output=True,
        text=True,
        timeout=5,
        cwd=str(safe_cwd),
    )
    recommendation = result.stdout.strip()
    if recommendation:
        print(f"[booster/route] {recommendation}")
except Exception:
    pass

sys.exit(0)
'''


_AGENT_INJECT_SCRIPT = '''\
#!/usr/bin/env python3
"""Inject booster instructions into every subagent prompt so they use
mcp__agent-booster__search_context instead of Grep/Bash for searches."""
import json
import sys

data = json.load(sys.stdin)
prompt = data.get("tool_input", {}).get("prompt", "")

if not prompt:
    sys.exit(0)

BOOSTER_INSTRUCTION = (
    "\\n\\n[booster] IMPORTANT: This session has Agent Booster installed. "
    "For ANY search or code exploration task, use mcp__agent-booster__search_context "
    "instead of Grep or Bash grep/find. Use mcp__agent-booster__smart_read instead of "
    "Read for targeted file reads. Use mcp__agent-booster__get_symbols to survey a "
    "file\'s structure. These tools are faster, token-efficient, and already available."
)

if "mcp__agent-booster" not in prompt:
    new_prompt = prompt + BOOSTER_INSTRUCTION
    output = dict(data)
    output["tool_input"] = dict(data.get("tool_input", {}))
    output["tool_input"]["prompt"] = new_prompt
    print(json.dumps(output))

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
    _append_rules_block(root / "CLAUDE.md", _CLAUDE_MD_BLOCK, "CLAUDE.md")


def _remove_claude_md(root: Path) -> None:
    _remove_rules_block(root / "CLAUDE.md", "CLAUDE.md")


def _append_rules_block(path: Path, block: str, label: str) -> None:
    existing = path.read_text() if path.exists() else ""
    if "<!-- booster:start -->" in existing:
        click.echo(f"  {label} already has booster block — skipped")
        return
    sep = "\n\n" if existing and not existing.endswith("\n\n") else ""
    path.write_text(existing + sep + block + "\n")
    click.echo(f"  appended booster block to {label}")


def _remove_rules_block(path: Path, label: str) -> None:
    if not path.exists():
        return
    text = path.read_text()
    start = text.find("<!-- booster:start -->")
    end = text.find("<!-- booster:end -->")
    if start == -1 or end == -1:
        return
    end += len("<!-- booster:end -->")
    cleaned = (text[:start].rstrip() + "\n" + text[end:].lstrip()).strip()
    if cleaned:
        path.write_text(cleaned + "\n")
    else:
        path.unlink()
    click.echo(f"  removed booster block from {label}")


def _update_mcp_secret(root: Path, token: str) -> None:
    """Write BOOSTER_SECRET into the agent-booster MCP server env in .mcp.json."""
    mcp_path = root / ".mcp.json"
    if not mcp_path.exists():
        return
    data = json.loads(mcp_path.read_text())
    server = data.get("mcpServers", {}).get("agent-booster")
    if server is None:
        return
    server["env"] = {"BOOSTER_SECRET": token}
    mcp_path.write_text(json.dumps(data, indent=2) + "\n")


def _install_hook(root: Path) -> None:
    hooks_dir = root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    (hooks_dir / "booster-gate.py").write_text(_GATE_SCRIPT)
    (hooks_dir / "booster-grep-nudge.py").write_text(_GREP_NUDGE_SCRIPT)
    (hooks_dir / "booster-route.py").write_text(_ROUTE_SCRIPT)
    (hooks_dir / "booster-agent-inject.py").write_text(_AGENT_INJECT_SCRIPT)
    click.echo(f"  wrote .claude/hooks/booster-gate.py (Read gate)")
    click.echo(f"  wrote .claude/hooks/booster-grep-nudge.py (Grep nudge)")
    click.echo(f"  wrote .claude/hooks/booster-route.py (route_model on every turn)")
    click.echo(f"  wrote .claude/hooks/booster-agent-inject.py (Agent prompt injection)")

    settings_path = root / ".claude" / "settings.json"
    settings: dict = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())

    hooks = settings.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])

    def _has(matcher: str, cmd: str) -> bool:
        return any(
            h.get("matcher") == matcher
            and any(e.get("command") == cmd for e in h.get("hooks", []))
            for h in pre
        )

    hook_cmd = _hook_command(root)
    grep_cmd = _grep_hook_command(root)
    route_cmd = _route_hook_command(root)
    agent_cmd = _agent_inject_command(root)

    if not _has("Read", hook_cmd):
        pre.append({"matcher": "Read", "hooks": [{"type": "command", "command": hook_cmd}]})
    if not _has("Grep", grep_cmd):
        pre.append({"matcher": "Grep", "hooks": [{"type": "command", "command": grep_cmd}]})
    if not _has("Agent", agent_cmd):
        pre.append({"matcher": "Agent", "hooks": [{"type": "command", "command": agent_cmd}]})

    ups = hooks.setdefault("UserPromptSubmit", [])
    if not any(e.get("command") == route_cmd for h in ups for e in h.get("hooks", [])):
        ups.append({"hooks": [{"type": "command", "command": route_cmd}]})

    _BOOSTER_TOOLS = [
        "mcp__agent-booster__search_context",
        "mcp__agent-booster__smart_read",
        "mcp__agent-booster__get_symbols",
        "mcp__agent-booster__route_model",
    ]
    perms = settings.setdefault("permissions", {})
    allow = perms.setdefault("allow", [])
    for tool in _BOOSTER_TOOLS:
        if tool not in allow:
            allow.append(tool)

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    click.echo(f"  updated {settings_path.relative_to(root)}")

    # Generate BOOSTER_SECRET for the MCP server
    import secrets as _secrets
    booster_dir = root / ".booster"
    booster_dir.mkdir(exist_ok=True)
    secret_file = booster_dir / ".secret"
    if not secret_file.exists():
        token = _secrets.token_hex(32)
        secret_file.write_text(token)
        secret_file.chmod(0o600)
        click.echo(f"  generated .booster/.secret (BOOSTER_SECRET)")
    _update_mcp_secret(root, secret_file.read_text().strip())


def _remove_hook(root: Path) -> None:
    hooks_dir = root / ".claude" / "hooks"
    for name in ("booster-gate.py", "booster-grep-nudge.py", "booster-route.py", "booster-agent-inject.py"):
        f = hooks_dir / name
        if f.exists():
            f.unlink()
            click.echo(f"  removed .claude/hooks/{name}")

    settings_path = root / ".claude" / "settings.json"
    if not settings_path.exists():
        return
    settings = json.loads(settings_path.read_text())
    booster_cmds = {_hook_command(root), _grep_hook_command(root), _route_hook_command(root), _agent_inject_command(root)}

    pre = settings.get("hooks", {}).get("PreToolUse", [])
    settings["hooks"]["PreToolUse"] = [
        h for h in pre
        if not any(e.get("command") in booster_cmds for e in h.get("hooks", []))
    ]
    ups = settings.get("hooks", {}).get("UserPromptSubmit", [])
    settings["hooks"]["UserPromptSubmit"] = [
        h for h in ups
        if not any(e.get("command") in booster_cmds for e in h.get("hooks", []))
    ]

    _BOOSTER_TOOLS = [
        "mcp__agent-booster__search_context",
        "mcp__agent-booster__smart_read",
        "mcp__agent-booster__get_symbols",
        "mcp__agent-booster__route_model",
    ]
    allow = settings.get("permissions", {}).get("allow", [])
    settings.setdefault("permissions", {})["allow"] = [t for t in allow if t not in _BOOSTER_TOOLS]

    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    click.echo(f"  updated {settings_path.relative_to(root)}")


@click.group()
def main() -> None:
    pass


@main.command("index")
@click.option("--embed", is_flag=True, default=False)
@click.option("--force", is_flag=True, default=False, help="Re-index all files, ignoring cached hashes.")
def cmd_index(embed: bool, force: bool) -> None:
    root = Path.cwd()
    indexer = SymbolIndexer(root)
    files, symbols = indexer.index_all(embed=embed, force=force)
    if force:
        click.echo(f"Indexed {files} files, {symbols} symbols. (forced full re-index)")
    else:
        click.echo(f"Indexed {files} changed files, {symbols} symbols. (use --force to re-index all)")


@main.command("embed")
def cmd_embed() -> None:
    root = Path.cwd()
    indexer = SymbolIndexer(root)
    n = indexer.build_embeddings()
    click.echo(f"Built embeddings for {n} symbols.")


@main.command("search")
@click.argument("query")
def cmd_search(query: str) -> None:
    """Semantic (vector) search across indexed symbols. Falls back to keyword if no embeddings."""
    root = Path.cwd()
    indexer = SymbolIndexer(root)
    results = indexer.vector_search(query)
    if not results:
        click.echo("No matches.")
        return
    for r in results:
        click.echo(f"{r['file']}:{r['start_line']}  {r['kind']} {r['name']}  {r['signature']}")


@main.command("smart-read")
@click.argument("file_path")
@click.argument("task", default="")
def cmd_smart_read(file_path: str, task: str) -> None:
    """Return only the relevant symbol slices from a file. With no task, returns a symbol outline."""
    import sys
    from booster.retriever import smart_read
    from booster.stats import StatsTracker

    root = Path.cwd()
    indexer = SymbolIndexer(root)

    path = Path(file_path)
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        click.echo(f"File not found: {file_path}", err=True)
        sys.exit(1)

    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)

    full_text = path.read_text(encoding="utf-8", errors="replace")

    if not task:
        # No task — return full symbol outline so Claude can decide what to read
        symbols = indexer.get_symbols(rel)
        if not symbols:
            sys.exit(0)  # not indexed — let the hook fall through to Read
        lines = [
            f"# {s['kind']} {s['name']}  (lines {s['start_line']}–{s['end_line']})\n{s['signature']}"
            for s in symbols
        ]
        click.echo(f"# Symbol outline: {rel}  ({len(symbols)} symbols)\n")
        click.echo("\n\n".join(lines))
        return

    result = smart_read(path, task, indexer)

    tracker = StatsTracker(root)
    tracker.record(rel, full_text, result, task)

    click.echo(result)


@main.command("serve")
def cmd_serve() -> None:
    from booster.mcp_server import serve
    asyncio.run(serve())


@main.command("init")
@click.argument("platform", type=click.Choice(["claude", "cursor", "windsurf", "codex", "all"]))
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt.")
def cmd_init(platform: str, yes: bool) -> None:
    root = Path.cwd()

    if platform in ("claude", "all"):
        click.echo()
        click.echo("Agent Booster — Claude Code setup")
        click.echo("\u2500" * 34)
        click.echo("This will make the following changes:")
        click.echo(f"  + .mcp.json                        (add agent-booster MCP server)")
        click.echo(f"  + CLAUDE.md                        (append booster usage rules)")
        click.echo(f"  + .claude/settings.json            (add PreToolUse + UserPromptSubmit hooks)")
        click.echo(f"  + .claude/hooks/booster-gate.py        (blocks Read on indexed files)")
        click.echo(f"  + .claude/hooks/booster-grep-nudge.py  (nudges semantic Grep to search_context)")
        click.echo(f"  + .claude/hooks/booster-route.py       (recommends model tier each turn)")
        click.echo()
        click.echo("All changes are reversible: run 'booster remove claude' to undo.")
        click.echo()

        if not yes:
            click.confirm("Proceed?", default=True, abort=True)

        _merge_mcp_json(root)
        _append_claude_md(root)
        _install_hook(root)

        click.echo()
        click.echo("Indexing repo…")
        import subprocess as _sp
        r = _sp.run(["booster", "index"], cwd=str(root))
        if r.returncode == 0:
            click.echo("Building embeddings…")
            _sp.run(["booster", "embed"], cwd=str(root))

        click.echo()
        click.echo("Done. Hooks are active immediately — no restart needed.")
        click.echo("Optional: restart Claude Code to also activate the MCP server tools.")
        click.echo("To remove at any time: booster remove claude")

    if platform in ("cursor", "all"):
        mcp_path = root / ".cursor" / "mcp.json"
        rules_path = root / ".cursorrules"
        click.echo()
        click.echo("Agent Booster — Cursor setup")
        click.echo("\u2500" * 28)
        click.echo("This will make the following changes:")
        click.echo(f"  + .cursor/mcp.json   (add agent-booster MCP server)")
        click.echo(f"  + .cursorrules       (append booster usage rules)")
        click.echo()
        click.echo("Reversible: run 'booster remove cursor' to undo.")
        click.echo()

        if not yes:
            click.confirm("Proceed?", default=True, abort=True)

        mcp_path.parent.mkdir(exist_ok=True)
        existing: dict = json.loads(mcp_path.read_text()) if mcp_path.exists() else {}
        existing.setdefault("mcpServers", {})["agent-booster"] = _MCP_ENTRY
        mcp_path.write_text(json.dumps(existing, indent=2) + "\n")
        click.echo(f"  wrote .cursor/mcp.json")
        _append_rules_block(rules_path, _RULES_BLOCK, ".cursorrules")
        click.echo()
        click.echo("Done. Restart Cursor to activate the MCP server.")
        click.echo("To remove: booster remove cursor")

    if platform in ("windsurf", "all"):
        mcp_path = Path.home() / ".windsurf" / "mcp.json"
        rules_path = root / ".windsurfrules"
        click.echo()
        click.echo("Agent Booster — Windsurf setup")
        click.echo("\u2500" * 30)
        click.echo("This will make the following changes:")
        click.echo(f"  + ~/.windsurf/mcp.json  (add agent-booster MCP server)")
        click.echo(f"  + .windsurfrules        (append booster usage rules)")
        click.echo()
        click.echo("Reversible: run 'booster remove windsurf' to undo.")
        click.echo()

        if not yes:
            click.confirm("Proceed?", default=True, abort=True)

        mcp_path.parent.mkdir(parents=True, exist_ok=True)
        existing2: dict = json.loads(mcp_path.read_text()) if mcp_path.exists() else {}
        existing2.setdefault("mcpServers", {})["agent-booster"] = _MCP_ENTRY
        mcp_path.write_text(json.dumps(existing2, indent=2) + "\n")
        click.echo(f"  wrote ~/.windsurf/mcp.json")
        _append_rules_block(rules_path, _RULES_BLOCK, ".windsurfrules")
        click.echo()
        click.echo("Done. Restart Windsurf to activate the MCP server.")
        click.echo("To remove: booster remove windsurf")

    if platform in ("codex", "all"):
        agents_md = root / "AGENTS.md"
        codex_cfg = Path.home() / ".codex" / "config.json"
        click.echo()
        click.echo("Agent Booster — Codex setup")
        click.echo("\u2500" * 27)
        click.echo("This will make the following changes:")
        click.echo(f"  + ~/.codex/config.json  (add agent-booster MCP server)")
        click.echo(f"  + AGENTS.md             (append booster usage rules)")
        click.echo()
        click.echo("Reversible: run 'booster remove codex' to undo.")
        click.echo()

        if not yes:
            click.confirm("Proceed?", default=True, abort=True)

        codex_cfg.parent.mkdir(parents=True, exist_ok=True)
        existing3: dict = json.loads(codex_cfg.read_text()) if codex_cfg.exists() else {}
        existing3.setdefault("mcp", {}).setdefault("servers", {})["agent-booster"] = _MCP_ENTRY
        codex_cfg.write_text(json.dumps(existing3, indent=2) + "\n")
        click.echo(f"  wrote ~/.codex/config.json")
        _append_rules_block(agents_md, _RULES_BLOCK, "AGENTS.md")
        click.echo()
        click.echo("Done. Run: booster index && booster embed")
        click.echo("To remove: booster remove codex")


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
        click.echo("Removing booster from Cursor:")
        mcp_path = root / ".cursor" / "mcp.json"
        if mcp_path.exists():
            data = json.loads(mcp_path.read_text())
            data.get("mcpServers", {}).pop("agent-booster", None)
            mcp_path.write_text(json.dumps(data, indent=2) + "\n")
            click.echo("  cleaned .cursor/mcp.json")
        _remove_rules_block(root / ".cursorrules", ".cursorrules")
        click.echo("Done.")

    if platform in ("windsurf", "all"):
        click.echo("Removing booster from Windsurf:")
        mcp_path = Path.home() / ".windsurf" / "mcp.json"
        if mcp_path.exists():
            data = json.loads(mcp_path.read_text())
            data.get("mcpServers", {}).pop("agent-booster", None)
            mcp_path.write_text(json.dumps(data, indent=2) + "\n")
            click.echo("  cleaned ~/.windsurf/mcp.json")
        _remove_rules_block(root / ".windsurfrules", ".windsurfrules")
        click.echo("Done.")

    if platform in ("codex", "all"):
        click.echo("Removing booster from Codex:")
        codex_cfg = Path.home() / ".codex" / "config.json"
        if codex_cfg.exists():
            data = json.loads(codex_cfg.read_text())
            data.get("mcp", {}).get("servers", {}).pop("agent-booster", None)
            codex_cfg.write_text(json.dumps(data, indent=2) + "\n")
            click.echo("  cleaned ~/.codex/config.json")
        _remove_rules_block(root / "AGENTS.md", "AGENTS.md")
        click.echo("Done.")


@main.command("route")
@click.argument("task")
def cmd_route(task: str) -> None:
    from booster.mcp_server import _route_model

    root = Path.cwd()
    indexer = SymbolIndexer(root)
    result = _route_model(indexer, task, [])
    click.echo(f"{result['model']}  ({result['reason']})")


@main.command("gain")
@click.option("--format", "-f", "fmt", type=click.Choice(["text", "json"]), default="text")
def cmd_gain(fmt: str) -> None:
    from booster.stats import StatsTracker

    tracker = StatsTracker(Path.cwd())
    s = tracker.summary()

    if fmt == "json":
        click.echo(json.dumps(s))
        return

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
