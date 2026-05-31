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
    click.echo(f"Sessions tracked:   {s['sessions']:,}")
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
