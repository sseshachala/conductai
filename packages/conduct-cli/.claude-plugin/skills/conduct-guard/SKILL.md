---
name: conduct-guard
description: ConductGuard MCP — enforces AI usage policies set by your team lead. Every file-write and sensitive tool call Claude makes is checked against Guard policies. Blocked calls are logged with who, what, and when.
---

## What ConductGuard does

ConductGuard runs as an MCP server (`conductguard-mcp`) that intercepts tool calls from Claude Code before they execute. It checks each call against the policies your team lead configured in the Conduct Guard dashboard.

- Blocked calls are rejected with an explanation
- All calls (allowed and blocked) are logged to Guard Insights
- Coverage dashboard shows which developers have Guard wired

## Setup

```bash
pip install conduct-cli
conduct whoami            # verify workspace is set
conductguard-mcp          # starts automatically via .mcp.json
```

## Key CLI commands

```bash
conduct switch <name>     # switch workspace + re-sync Guard policies
conduct guard status      # show hook wiring, policy count, last sync
conduct whoami            # workspace + Guard + Booster status at a glance
```

## Guard Insights

View the events feed and developer coverage at `/guard/insights` in the Conduct console.
