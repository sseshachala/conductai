# ConductGuard — MCP

> **Retired binary — read this first.**
> The `conductguard-mcp` and `conduct-mcp` stdio binaries are retired as of
> #1219 Phase 3 M3. AI tools now bridge to the remote Conduct MCP endpoint
> via Cloudflare's `mcp-remote` — one binary, one endpoint, one policy
> source. Local policy evaluation is gone (was a governance hole — policy
> is now always server-side, always current).
>
> **Enterprise SBOM ask?** Native Python stdio bridge tracked in #1229.

---

## What replaces it

`conduct mcp install` now writes an `mcp-remote` entry pointing at
`https://api.conductai.ai/mcp` into every AI-tool config it detects
(Claude Code, Cursor, Windsurf, VS Code Copilot, Codex).

Example generated config (Cursor `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "conduct": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote", "https://api.conductai.ai/mcp",
        "--header", "Authorization: Bearer <your-token>"
      ]
    }
  }
}
```

The AI tool spawns `npx -y mcp-remote`, which relays JSON-RPC over HTTPS
to `/mcp`. Same tool catalogue (`guard_status`, `guard_check`,
`guard_activity`, `conduct_list_projects`, and every Lens Executor tool)
appears in every client automatically — adding a tool to the server
registry adds it everywhere.

## Install

```bash
conduct login        # if not already
conduct mcp install  # writes mcp-remote configs for every detected AI tool
```

Restart the AI tool to pick up the new server.

## Requirements

- **Node.js 18+** — `npx` bootstraps mcp-remote per launch. If Node isn't
  on your machine, the install command tells you so and points at #1229
  for a native Python bridge.

## MCP is not a security boundary

The transport is convenience. Auth is enforced at `/mcp` on every
request — a valid Bearer token resolves to a workspace + user. The
mcp-remote bridge only ferries bytes.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No Conduct token found` from `conduct mcp install` | Run `conduct login` first |
| `npx not on PATH` | Install Node.js 18+ |
| AI tool shows "connection error" | Confirm `~/.conduct/config.json` has a fresh `agent_token`; re-run `conduct login` if expired |
| Tool missing from AI tool's list | Restart the AI tool; the tool catalogue is fetched at handshake |
