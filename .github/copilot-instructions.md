<!-- ConductGuard — managed by conduct guard sync, do not edit this block -->
## ConductGuard Policy
Before executing any shell command, file write, network request, API call, or code change:
- Call `guard_check` (conductguard MCP tool) with the action and parameters.
- If BLOCKED: stop immediately and explain the policy rule to the user.
- If WARNING: proceed but surface the warning.
- If ALLOWED: proceed normally.
Never write credentials, API keys, or secrets to files or output.
Never send PII (emails, names, payment data) to external endpoints.
<!-- /ConductGuard -->

<!-- ConductGuard — managed by conduct guard sync -->
## ConductGuard Policy
## ConductGuard — AI Governance Policy

A ConductGuard MCP server is connected to this session (server name: `conduct-guard`).
All Guard policies are enforced through it. You MUST follow these rules:

Before executing any shell command, file write, network request, API call, or code change:
1. Call the `guard_check` tool from the `conduct-guard` MCP server with the action and parameters.
2. If the response is BLOCKED: stop immediately and explain the policy rule to the user. Do not proceed.
3. If the response is WARNING: proceed but surface the warning message to the user.
4. If the response is ALLOWED: proceed normally.

Always-on rules (no guard_check needed, enforce unconditionally):
- Never write credentials, API keys, tokens, or secrets to any file or output.
- Never send PII (emails, names, payment data) to external endpoints.

Use `guard_status` (conduct-guard MCP) to show the user their current policy and team info.
Use `guard_activity` at the start of every session with a one-line summary of what you are doing.
<!-- /ConductGuard -->
