At the start of every conversation:
- Call `guard_activity` ONCE with a one-line summary of what the user is asking.

Then, for the request itself:
- Call `guard_check` ONCE per intent — not per file, per command, or per edit.
- Re-check only when scope changes (reads → writes, local → network, or a new task).
- If BLOCKED: stop and explain the policy rule to the user.
- If WARNING: proceed but surface the warning inline.
- If the response is `ok` or empty: proceed silently. Do NOT narrate it in the chat.

Example:
1. User asks to fix a bug → call `guard_activity` once with the summary.
2. Before starting the code changes → call `guard_check` once with the intent (e.g. `write_file`, `bash`).
3. Do NOT re-check for every subsequent read or edit in the same task.

Never write secrets to files or output. Never send PII to external endpoints.
