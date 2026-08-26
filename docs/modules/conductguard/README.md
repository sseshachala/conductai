# ConductGuard Documentation

| Section | Description |
|---|---|
| [Overview](overview.md) | What ConductGuard is, the MDM analogy, core value prop, and how control flows |
| [Quickstart](QUICKSTART.md) | Dev-side 15-min path: verify Guard, send a proxy call, add your first custom rule |
| [Runbook](RUNBOOK.md) | On-call ops guide: health checks, failure modes, rollback, alert playbook |
| [Capability Inventory](CAPABILITY_INVENTORY.md) | Ground-truth reference for every shipped capability (file:line refs) |
| [Developer Setup](developer_setup.md) | Install CLI, join a team, sync policies, hook location, troubleshooting |
| [Hook & Tool Coverage](hook_coverage.md) | PreToolUse/PostToolUse mechanics, policy matching, AI tools covered |
| [MCP](conductguard_mcp.md) | How Cursor / Copilot / Codex bridge to `/mcp` via `npx mcp-remote`; supersedes retired `conductguard-mcp` binary |
| [Spend Controls](spend_controls.md) | Budget types, enforcement flow, Slack alerts, alert dedup, DB schema |
| [Roles & Permissions](roles_permissions.md) | 4-role matrix, role resolution priority, frontend + API enforcement |
| [Team Onboarding](team_onboarding.md) | Admin setup, developer sync flow, checklist |
| [Test Scenarios Runbook](../guard_scenarios.md) | End-to-end test scripts for all 4 Guard scenarios with Slack examples |
