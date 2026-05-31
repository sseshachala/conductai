from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click

from booster.indexer import SymbolIndexer

_CLAUDE_SNIPPET = {
    "mcpServers": {
        "agent-booster": {
            "command": "booster",
            "args": ["serve"],
        }
    }
}

_CURSOR_SNIPPET = {
    "mcpServers": {
        "agent-booster": {
            "command": "booster",
            "args": ["serve"],
        }
    }
}

_CODEX_SNIPPET = {
    "mcp": {
        "servers": {
            "agent-booster": {
                "command": "booster",
                "args": ["serve"],
            }
        }
    }
}


@click.group()
def main() -> None:
    pass


@main.command("index")
def cmd_index() -> None:
    root = Path.cwd()
    indexer = SymbolIndexer(root)
    files, symbols = indexer.index_all()
    click.echo(f"Indexed {files} files, {symbols} symbols.")


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
@click.argument("platform", type=click.Choice(["claude", "cursor", "codex", "all"]))
def cmd_init(platform: str) -> None:
    def _print(label: str, snippet: dict) -> None:
        click.echo(f"# {label}")
        click.echo(json.dumps(snippet, indent=2))
        click.echo()

    if platform in ("claude", "all"):
        _print("Add to .mcp.json (project root)", _CLAUDE_SNIPPET)
    if platform in ("cursor", "all"):
        _print("Add to .cursor/mcp.json", _CURSOR_SNIPPET)
    if platform in ("codex", "all"):
        _print("Add to ~/.codex/config.json", _CODEX_SNIPPET)


@main.command("gain")
def cmd_gain() -> None:
    click.echo("No stats yet. Run some sessions first.")
