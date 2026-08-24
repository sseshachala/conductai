# conduct-litellm-guard

Conduct Guard as a LiteLLM guardrail. Every LLM call routed through
LiteLLM runs through your active Guard policy before the request leaves
your network — block, warn, audit, or trigger a HITL approval, with the
same signed configuration and hash-chained audit log as the rest of
Conduct.

## Install

```bash
pip install conduct-litellm-guard
```

## Wire it up

1. Mint an agent token in the [Conduct console](https://conductai.ai)
   (Settings → Agent identities). Copy the `cond_agt_…` value.
2. Export it in the environment where your LiteLLM proxy runs:
   ```bash
   export CONDUCT_AGENT_TOKEN=cond_agt_...
   ```
3. Add the guardrail to your LiteLLM proxy's `config.yaml`:
   ```yaml
   guardrails:
     - guardrail_name: conduct-guard
       litellm_params:
         guardrail: conduct_litellm_guard.ConductGuard
         mode: pre_call
         api_url: https://api.conductai.ai
         agent_token: os.environ/CONDUCT_AGENT_TOKEN
         fail_mode: fail_closed
   ```
4. Start the proxy:
   ```bash
   litellm --config config.yaml
   ```

A full example lives in [`examples/config.yaml`](./examples/config.yaml).

## What the guardrail does

For every incoming request the guardrail calls Conduct's `guard_check`
tool (JSON-RPC over the MCP endpoint) with a compact summary of the
LiteLLM request — model, call type, message count, temperature, stream
flag, plus the last user message so the audit trail carries context.

Guard returns one of five verdicts:

| Verdict            | LiteLLM behaviour                                   |
|--------------------|-----------------------------------------------------|
| `ok` / `allow`     | Request forwarded to the upstream model.            |
| `advisory`         | Forwarded, `metadata.conduct_guard` annotated.      |
| `WARNING`          | Forwarded, warning surfaced in metadata.            |
| `BLOCKED`          | LiteLLM returns an error to the caller. No upstream token spent. |
| `PENDING approval` | Blocked pending HITL. Caller receives an error citing the rule. |

## Configuration reference

| Field         | Required | Default                    | Notes                                                     |
|---------------|----------|----------------------------|-----------------------------------------------------------|
| `api_url`     | no       | `https://api.conductai.ai` | Point at a self-hosted Conduct API when needed.           |
| `agent_token` | yes      | `CONDUCT_AGENT_TOKEN` env  | `cond_agt_*` token minted in the Conduct console.         |
| `workspace_id`| no       | resolved from the token    | Usually unnecessary — the token owns its workspace.       |
| `fail_mode`   | no       | `fail_closed`              | `fail_closed` blocks when Guard is unreachable, `fail_open` allows. |
| `timeout`     | no       | `8.0`                      | Seconds. Guard checks return in <100ms in the healthy path. |

## Session tracking

Guard uses a session ID to correlate the pre-call check with any
resume-verdict / HITL approval that follows. The adapter picks the first
value it finds in this order:

1. `litellm_metadata.trace_id`
2. `metadata.X-Conduct-Session-Id` (explicit override — set this if you
   want deterministic control over the session boundary).
3. `metadata.conduct_session_id`.
4. A deterministic hash of the `user` field plus the first user message.

If none of the above are available and the caller sends no `user` or
`messages`, session tracking is skipped (single-shot mode). Approvals
still work — they just can't be resumed against a prior check.

## Fail modes

- `fail_closed` (default) — blocks the call if Guard is unreachable or
  the policy evaluator errors. Matches Conduct's default posture across
  every other enforcement surface.
- `fail_open` — allows the call and logs a warning. Use during rollout
  or if Guard is a soft dependency for your setup.

## License

`conduct-litellm-guard` is distributed under the same
[FSL-1.1-MIT](../../LICENSE) license as the rest of Conduct. On
2028-08-23 it converts to MIT.

## Links

- [Conduct Guard](https://conductai.ai/guard) — the policy engine.
- [Conduct Router](https://conductai.ai/router) — Conduct's own LLM proxy.
- [Source](https://github.com/sseshachala/conductai) — this package lives
  under `packages/conduct-litellm-guard/`.
- [Issues](https://github.com/sseshachala/conductai/issues) — file bugs
  and requests against the parent repo.
