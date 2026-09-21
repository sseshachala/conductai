# Tool-call correlation IDs

**Issue:** [#2158](https://github.com/sseshachala/conductai/issues/2158)

## What this is

When the Gateway returns a response containing `tool_calls[]`, each call is
tagged with a stable **correlation ID**. Callers use it to join the Gateway
audit row (`tool_call.generated`) with their own execution log
(`tool_call.completed`).

## Wire format

The Gateway sets one header on every response that returned at least one
`tool_call`:

```
X-Conduct-Tool-Correlation-Ids: <tool_call_id>=<correlation_id>[,<tool_call_id>=<correlation_id>]...
```

Example:

```
X-Conduct-Tool-Correlation-Ids: call_abc=9c4f3e21a7b0d8e1,call_def=1f8b3c22e5a06d94
```

- `<tool_call_id>` — the id set by the LLM in `choices[].message.tool_calls[].id`.
- `<correlation_id>` — 16 hex characters. Fresh per generation; retries of the
  same logical tool_call get distinct correlations by design.

The header is omitted (not set to an empty string) when the response has no
`tool_calls[]` or none passed the header-safety filter.

## Reading the header

Any HTTP client works. Two examples:

**Python (using the helper in this repo):**

```python
from app.modules.guard.tools_validator import parse_correlation_header

correlations = parse_correlation_header(
    response.headers.get("X-Conduct-Tool-Correlation-Ids")
)
# {"call_abc": "9c4f3e21a7b0d8e1", "call_def": "1f8b3c22e5a06d94"}
```

**Anywhere else:** split on `,`, split each pair on `=`, keep the two halves.
Drop pairs that don't have exactly one `=`.

## What the caller does with it

For each `tool_call` the caller dispatches to a tool executor, attach the
matching `correlation_id` to the executor's log entry. The Flight Recorder /
audit UI can then join both sides:

```
Gateway audit row
  request_id: req_xyz
  tool_calls_generated: [{name: send_email, id: call_abc}]
  tool_call_correlation_ids: {call_abc: 9c4f3e21a7b0d8e1}

Caller execution log
  correlation_id: 9c4f3e21a7b0d8e1
  tool: send_email
  duration_ms: 340
  outcome: succeeded
```

## Guarantees

- **Server-controlled.** Correlation IDs are UUID4 slices assigned server-side —
  never model-controlled, never derived from `tool_call.id`.
- **Best-effort header.** If reading it fails, the audit row still carries the
  full mapping in `routing_meta.tool_call_correlation_ids` (queryable server
  side). The header is a caller-side convenience, not the source of truth.
- **Stable across retries at the Gateway.** A single response gate assigns
  correlations once. Coordinator-level retries (different attempt) generate
  fresh correlations by design — each attempt is its own audit event.

## Out of scope

- Executor-side wire-in for specific callers (`conduct-cli`,
  `conduct-litellm-guard`) — separate follow-up.
- Audit UI join view — separate follow-up.
- Routing brain_block through the Gateway (today it calls providers directly) —
  separate story.
