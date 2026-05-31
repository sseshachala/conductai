from __future__ import annotations

from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from booster.indexer import SymbolIndexer
from booster.retriever import smart_read as _smart_read
from booster.stats import StatsTracker

_ROOT = Path.cwd()
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
    return [
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
    ]


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
        results = indexer.vector_search(arguments["task"], limit=10)
        lines = [
            f"{s['file']}:{s['start_line']} {s['kind']} {s['name']} — {s['signature']}"
            for s in results
        ]
        text = "\n".join(lines) if lines else "No matches found."
        return [TextContent(type="text", text=text)]

    if name == "smart_read":
        file_path = _ROOT / arguments["file"]
        full_text = file_path.read_text(encoding="utf-8", errors="replace")
        text = _smart_read(file_path, arguments["task"], indexer)
        _get_tracker().record(arguments["file"], full_text, text, arguments.get("task", ""))
        return [TextContent(type="text", text=text)]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def serve() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())
