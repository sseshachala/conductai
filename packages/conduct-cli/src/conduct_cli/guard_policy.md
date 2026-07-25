At the start of every conversation:
- Call `guard_activity` once with a one-line summary of the user's request.

Before every shell command, file write, network request, API call, or code change:
- Call `guard_check` with the proposed action and parameters.
- If BLOCKED: stop and explain the policy rule.
- If WARNING: proceed and surface the warning.
- If ALLOWED: proceed normally.

Example:
1. User asks to fix a bug → call `guard_activity` once.
2. Before reading files or running tests → call `guard_check`.
3. Before editing code → call `guard_check` again.

Never write secrets to files or output.
Never send PII to external endpoints.
