# ConductGuard — conductguard-mcp

`conductguard-mcp` is the ConductGuard MCP (Model Context Protocol) server. It enables AI tools that support MCP — such as Cursor and Gemini CLI — to participate in the same policy enforcement and telemetry pipeline as Claude Code.

---

## Entry Point

```bash
conductguard-mcp
```

Installed automatically with the `conduct-cli` package:

```bash
pip install conduct-cli
which conductguard-mcp   # /path/to/bin/conductguard-mcp
```

---

## What It Does

When an MCP-compatible AI tool calls a tool through `conductguard-mcp`, the server:

1. Receives the tool call request
2. Checks spend budget (same as the hook's PreToolUse check)
3. Evaluates the call against the cached policy set
4. If blocked: returns an error response with the block message
5. If allowed: forwards the call to the underlying tool, then logs the audit event

This mirrors the hook-based flow for Claude Code, but over the MCP transport instead of stdin/stdout.

---

## Registering with Cursor

Add `conductguard-mcp` to your Cursor MCP config:

```json
{
  "mcpServers": {
    "conductguard": {
      "command": "conductguard-mcp",
      "args": []
    }
  }
}
```

Once registered, Cursor will call ConductGuard's MCP server for each tool invocation. Policy enforcement and spend tracking work identically to Claude Code.

---

## MCP vs Hook — Same Enforcement

Both paths (hook and MCP) read from the same local config cache and call the same API endpoints. A policy set in the ConductGuard dashboard applies to both Claude Code (via hook) and Cursor (via MCP) without any additional configuration.

---

## MCP is Not a Security Boundary

The MCP transport is convenience — it is not auth. The `conductguard-mcp` server authenticates using the `member_token` from `~/.conductguard/config.json`, the same token the hook uses. The API endpoint enforces auth independently on every request.

---

## Telemetry

Events logged via `conductguard-mcp` appear in the ConductGuard dashboard alongside hook-sourced events. The `ai_tool` field distinguishes the source (e.g. `cursor` vs `claude-code`).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `conductguard-mcp: command not found` | Re-install `conduct-cli`; check PATH |
| Cursor shows MCP connection error | Verify `~/.conductguard/config.json` exists and `member_token` is set |
| Events not appearing in dashboard | Check `last_synced` in config; run `conduct guard sync` |
