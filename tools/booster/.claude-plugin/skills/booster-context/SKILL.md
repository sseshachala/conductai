---
name: booster-context
description: Use Agent Booster MCP tools for token-efficient code reading. Replaces Read/Grep with smart_read and search_context to reduce token usage 5-15x.
---

## When to use

Prefer Agent Booster tools over native Read/Grep whenever the project has been indexed:

- `mcp__agent-booster__search_context` — semantic keyword search across all symbols (replaces Grep)
- `mcp__agent-booster__smart_read` — returns only the relevant slice of a file for a task (replaces Read)
- `mcp__agent-booster__get_symbols` — survey a file's structure before reading
- `mcp__agent-booster__route_model` — pick the right model tier (haiku/sonnet/opus) based on task complexity

## Setup

```bash
pip install agent-booster
booster index .        # run once per repo
booster serve          # starts the MCP server (auto-started by .mcp.json)
```

## Gains

Run `booster gain` to see token savings statistics for the current session.
