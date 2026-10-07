"""Top-level `conduct` command implementations.

`conduct_cli.main` owns argument parsing and dispatch; implementations live here:

- shared: colors, config persistence, auth resolution, run streaming
- auth: login flows, agent-token refresh/rotation, `sync`
- mcp_setup: `mcp install` and MCP client config writers
- workspace: agents, environments, credentials, projects
- workspace_switch: `switch`, `whoami`
- playbooks: `playbooks`, `install`, `reset`, `install-all`
- run: `run`, `test`
- sessions: `sessions` table and TUI
- session_report: `session-report`
- config_io: Cedar / gateway-config import and export, `skill`
- diagnostics: `test-guard`, `memory`

Tests patch helpers at their owning module (or at the module that calls them).
"""
