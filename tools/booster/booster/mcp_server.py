from __future__ import annotations

import os as _os
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from booster.crusher import crush as _crush
from booster.indexer import SymbolIndexer
from booster.retriever import smart_read as _smart_read
from booster.stats import StatsTracker

_ROOT = Path.cwd() if Path.cwd() != Path("/") else Path.home()
_BOOSTER_HOME = Path.home() / ".booster"
_SECRET = _os.environ.get("BOOSTER_SECRET", "")


def _provider() -> str:
    explicit = _os.environ.get("BOOSTER_PROVIDER", "").lower()
    if explicit:
        return explicit
    if _os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if _os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "unknown"


def _sort_schema(obj: object) -> object:
    if isinstance(obj, dict):
        return dict(sorted((k, _sort_schema(val)) for k, val in obj.items()))
    if isinstance(obj, list):
        return [_sort_schema(i) for i in obj]
    return obj
_indexer: SymbolIndexer | None = None
_tracker: StatsTracker | None = None


def _get_indexer() -> SymbolIndexer:
    global _indexer
    if _indexer is None:
        _indexer = SymbolIndexer(_ROOT)
    return _indexer


def _get_tracker() -> StatsTracker:
    global _tracker
    if _tracker is None:
        _tracker = StatsTracker(_ROOT)
    return _tracker


app = Server("agent-booster")
app.version = "0.1.0"


@app.list_tools()
async def list_tools() -> list[Tool]:
    tools = [
        Tool(
            name="get_symbols",
            description="Return all indexed symbols for a given file path.",
            inputSchema={
                "type": "object",
                "properties": {"file": {"type": "string", "description": "Relative file path"}},
                "required": ["file"],
            },
        ),
        Tool(
            name="search_context",
            description="Keyword search across all indexed symbols. Returns top 10 matches. Pass 'since' (e.g. 'HEAD~5', 'main', SHA) to restrict to recently-changed symbols.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task description or keywords"},
                    "since": {"type": "string", "description": "Optional git ref. Restricts results to symbols whose lines changed since this ref."},
                },
                "required": ["task"],
            },
        ),
        Tool(
            name="smart_read",
            description="Return only the relevant slice of a file based on a task description. Pass 'since' to filter to symbols modified after a git ref.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Relative file path"},
                    "task": {"type": "string", "description": "Task description"},
                    "since": {"type": "string", "description": "Optional git ref (e.g. 'HEAD~5'). Restricts slice to symbols overlapping changes since this ref."},
                },
                "required": ["file", "task"],
            },
        ),
        Tool(
            name="route_model",
            description="Recommend the right model tier (haiku/sonnet/opus) for a task based on complexity signals.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task description"},
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Files the task will touch (optional — auto-detected via search if omitted)",
                    },
                },
                "required": ["task"],
            },
        ),
        Tool(
            name="expand_calls",
            description="Return immediate callers or callees of a symbol. Name-based resolution (~70% accuracy on Python).",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Symbol name to expand"},
                    "direction": {
                        "type": "string",
                        "enum": ["callers", "callees", "both"],
                        "description": "callers (who calls it) | callees (what it calls) | both. Default: callers",
                    },
                    "depth": {"type": "integer", "description": "Expansion depth, 1-3. Default: 1"},
                    "file": {"type": "string", "description": "Optional file to disambiguate when symbol exists in multiple files"},
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="test_coverage",
            description="Return test references for a symbol. Requires `booster index --tests` to populate the test index.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Symbol name to look up tests for"},
                    "file": {"type": "string", "description": "Optional source file to disambiguate"},
                },
                "required": ["symbol"],
            },
        ),
    ]
    # ponytail: sort alphabetically so Anthropic KV cache sees a stable prefix every request
    tools.sort(key=lambda t: t.name)
    for t in tools:
        t.inputSchema = _sort_schema(t.inputSchema)  # type: ignore[assignment]
    return tools


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    indexer = _get_indexer()

    if name == "get_symbols":
        symbols = indexer.get_symbols(arguments["file"])
        lines = [
            f"{s['kind']} {s['name']} (lines {s['start_line']}-{s['end_line']}): {s['signature']}"
            for s in symbols
        ]
        text = "\n".join(lines) if lines else "No symbols found."
        return [TextContent(type="text", text=text)]

    if name == "search_context":
        results = indexer.rrf_search(arguments["task"], limit=10)
        since = arguments.get("since")
        if since:
            from booster.indexer import _changed_lines_since, _filter_by_changed_lines
            changed = _changed_lines_since(indexer.root, since)
            if not changed:
                text = f"No matches found (no changes since {since})."
            else:
                results = _filter_by_changed_lines(results, changed)
        # v0.3.0 free-fold: nudge results toward files with high historical read counts.
        # ponytail: small boost from stats; falls back silently if stats empty.
        try:
            top = _get_tracker().summary().get("top_files", [])
            boost = {entry["file"]: entry.get("reads", 0) for entry in top}
            if boost:
                results = sorted(results, key=lambda s: -boost.get(s.get("file", ""), 0))
        except Exception:
            pass
        lines = [
            f"{s['file']}:{s['start_line']} {s['kind']} {s['name']} — {s['signature']}"
            for s in results
        ]
        text = "\n".join(lines) if lines else (f"No matches changed since {since}." if since else "No matches found.")
        text, orig, crushed = _crush(text)
        _get_tracker().record_crush("search_context", orig, crushed)
        return [TextContent(type="text", text=text)]

    if name == "smart_read":
        try:
            resolved = (_ROOT / arguments["file"]).resolve()
            resolved.relative_to(_ROOT.resolve())
        except (ValueError, Exception):
            return [TextContent(type="text", text=f"Error: path '{arguments['file']}' is outside the project root")]
        full_text = resolved.read_text(encoding="utf-8", errors="replace")
        text = _smart_read(resolved, arguments["task"], indexer, since=arguments.get("since"))
        text, orig, crushed = _crush(text)
        _get_tracker().record_crush("smart_read", orig, crushed)
        _get_tracker().record(arguments["file"], full_text, text, arguments.get("task", ""))
        return [TextContent(type="text", text=text)]

    if name == "route_model":
        import json as _json
        result = _route_model(indexer, arguments["task"], arguments.get("files") or [])
        return [TextContent(type="text", text=_json.dumps(result))]

    if name == "test_coverage":
        refs = indexer.test_coverage(arguments["symbol"], file=arguments.get("file"))
        if not refs:
            # Check whether tests index is even populated
            empty = indexer._conn.execute("SELECT COUNT(*) FROM symbol_tests").fetchone()[0] == 0
            if empty:
                return [TextContent(type="text", text="No test index yet. Run: booster index --tests")]
            return [TextContent(type="text", text=f"No tests reference '{arguments['symbol']}'.")]
        lines = [
            f"{r['symbol_file']}:{r['name']} <- {r['test_file']} ({r['source']})"
            for r in refs
        ]
        text = "\n".join(lines)
        text, orig, crushed = _crush(text)
        _get_tracker().record_crush("test_coverage", orig, crushed)
        return [TextContent(type="text", text=text)]

    if name == "expand_calls":
        results = indexer.expand_calls(
            arguments["symbol"],
            direction=arguments.get("direction", "callers"),
            depth=int(arguments.get("depth", 1)),
            file=arguments.get("file"),
        )
        if not results:
            return [TextContent(type="text", text=f"No edges found for '{arguments['symbol']}'.")]
        lines = []
        for r in results:
            d = r["direction"]
            if d == "callee":
                tgt = f"{r['to_file']}:{r['to_name']}" if r["to_file"] else f"?:{r['to_name']}"
                lines.append(f"[d{r['depth']}] callee: {r['from_file']}:{r['from_name']} -> {tgt} (call at line {r['call_line']})")
            else:
                lines.append(f"[d{r['depth']}] caller: {r['from_file']}:{r['from_name']} -> {r['to_name']} (call at line {r['call_line']})")
        text = "\n".join(lines)
        text, orig, crushed = _crush(text)
        _get_tracker().record_crush("expand_calls", orig, crushed)
        return [TextContent(type="text", text=text)]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


_OPUS_KEYWORDS = {"refactor", "architect", "design", "migrate", "migration", "security", "audit", "overhaul", "redesign"}


def _route_model(indexer: SymbolIndexer, task: str, files: list[str]) -> dict:
    task_lower = task.lower()
    words = set(task_lower.split())

    if words & _OPUS_KEYWORDS:
        matched = words & _OPUS_KEYWORDS
        return {"model": "opus", "reason": f"complexity keyword(s): {', '.join(sorted(matched))}"}

    if files:
        distinct_files = len(set(files))
    else:
        results = indexer.vector_search(task, limit=20)
        distinct_files = len({r["file"] for r in results})

    if distinct_files >= 5:
        return {"model": "opus", "reason": f"task spans {distinct_files} files"}
    if distinct_files >= 2:
        return {"model": "sonnet", "reason": f"task spans {distinct_files} files"}

    # 1 file — check symbol count
    if files:
        symbols = indexer.get_symbols(files[0]) if files else []
    else:
        results = indexer.vector_search(task, limit=10)
        symbols = results

    if len(symbols) < 3:
        return {"model": "haiku", "reason": f"narrow task — {len(symbols)} symbol(s) in 1 file"}

    return {"model": "sonnet", "reason": "moderate scope — default"}


async def serve() -> None:
    booster_dir = _BOOSTER_HOME
    booster_dir.mkdir(exist_ok=True)
    (booster_dir / "provider").write_text(_provider())

    secret_file = _BOOSTER_HOME / ".secret"
    if secret_file.exists():
        expected = secret_file.read_text().strip()
        if _SECRET and _SECRET != expected:
            import sys as _sys
            print("booster: BOOSTER_SECRET mismatch — refusing to start", file=_sys.stderr)
            _sys.exit(1)
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())
