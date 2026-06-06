---
name: booster-context
description: Use Agent Booster MCP tools for token-efficient code reading. Replaces Read/Grep with smart_read and search_context to reduce token usage 5-15x. Includes background daemon for instant search and auto-indexing on file save.
---

## When to use

Prefer Agent Booster tools over native Read/Grep whenever the project has been indexed:

- `mcp__agent-booster__search_context` — semantic search across all symbols (replaces Grep)
- `mcp__agent-booster__smart_read` — returns only the relevant slice of a file for a task (replaces Read)
- `mcp__agent-booster__get_symbols` — survey a file's structure before reading
- `mcp__agent-booster__route_model` — pick the right model tier (haiku/sonnet/opus) based on task complexity

## Setup

```bash
pip install 'agent-booster[full]'   # includes embeddings + file watcher
booster init claude                  # wire MCP, hooks, CLAUDE.md
booster start                        # background daemon — model warm + file watcher
```

## Daemon commands

```bash
booster start     # start daemon in background
booster stop      # stop daemon
booster status    # show pid, uptime, watcher state
```

With the daemon running:
- `search_context` responds in ~50ms instead of 2-3s (no model cold-start)
- File changes are automatically re-indexed within 2s (no manual `booster index`)

## Indexing

```bash
booster index           # incremental — only re-indexes changed files
booster index --force   # full re-index of everything
booster embed           # rebuild embeddings after manual index
```

## Gains

Run `booster gain` to see token savings statistics for the current session.
