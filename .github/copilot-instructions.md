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
Before executing any shell command, file write, network request, API call, or code change:
- Call guard_check (conductguard MCP tool) with the action and parameters.
- If BLOCKED: stop immediately and explain the policy rule to the user.
- If WARNING: proceed but surface the warning. If ALLOWED: proceed normally.
- Never write credentials, API keys, or secrets to files or output.
- Never send PII (emails, names, payment data) to external endpoints.
<!-- /ConductGuard -->
