"""Conduct MCP core — transport-agnostic JSON-RPC dispatcher.

See epic #1219 for design context. HTTP + stdio adapters compose this core
onto their transports; every registered tool from app.tools.registry becomes
available on every MCP client (Claude.ai, Claude Code, Cursor, VS Code
Copilot, Windsurf, Codex, custom agents) with zero per-transport wiring.
"""
