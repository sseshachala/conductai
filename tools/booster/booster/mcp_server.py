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

_ROOT = Path.cwd()
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
            description="Keyword search across all indexed symbols. Returns top 10 matches.",
            inputSchema={
                "type": "object",
                "properties": {"task": {"type": "string", "description": "Task description or keywords"}},
                "required": ["task"],
            },
        ),
        Tool(
            name="smart_read",
            description="Return only the relevant slice of a file based on a task description.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Relative file path"},
                    "task": {"type": "string", "description": "Task description"},
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
        lines = [
            f"{s['file']}:{s['start_line']} {s['kind']} {s['name']} — {s['signature']}"
            for s in results
        ]
        text = "\n".join(lines) if lines else "No matches found."
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
        text = _smart_read(resolved, arguments["task"], indexer)
        text, orig, crushed = _crush(text)
        _get_tracker().record_crush("smart_read", orig, crushed)
        _get_tracker().record(arguments["file"], full_text, text, arguments.get("task", ""))
        return [TextContent(type="text", text=text)]

    if name == "route_model":
        import json as _json
        result = _route_model(indexer, arguments["task"], arguments.get("files") or [])
        return [TextContent(type="text", text=_json.dumps(result))]

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
    booster_dir = _ROOT / ".booster"
    booster_dir.mkdir(exist_ok=True)
    (booster_dir / "provider").write_text(_provider())

    secret_file = _ROOT / ".booster" / ".secret"
    if secret_file.exists():
        expected = secret_file.read_text().strip()
        if _SECRET and _SECRET != expected:
            import sys as _sys
            print("booster: BOOSTER_SECRET mismatch — refusing to start", file=_sys.stderr)
            _sys.exit(1)
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())
