# Conduct Guard + Proliferate

Enforce Conduct policy on every LLM call from every coding agent
running inside a [Proliferate](https://github.com/proliferate-ai/proliferate)
install — Claude Code, Codex, OpenCode, Cursor, Grok, or any harness
Proliferate spawns.

Proliferate routes every agent's LLM traffic through its own LiteLLM
gateway (`server/litellm`). Conduct Guard ships as a LiteLLM plugin
([`conduct-litellm-guard`](https://pypi.org/project/conduct-litellm-guard/)).
Wire the plugin into that gateway and every agent in every worktree
gets the same policy, same audit chain, same signed configuration.

## What this integration gives you

- **One policy across every harness.** Add a rule once in Conduct.
  Every agent Proliferate spawns enforces it.
- **Fail-closed by default.** If Guard is unreachable, LiteLLM returns
  an error to the agent instead of silently passing.
- **Hash-chained audit.** Every LLM call (allowed / warned / audited /
  blocked / HITL-pending) lands as an entry in Guard's SHA-256 audit
  chain, with the Proliferate session ID plumbed through.
- **Signed configuration.** Guard verifies the workspace's active
  policy signature on every check.
- **No code changes to Proliferate.** One YAML addition to its
  `server/litellm` config.

## Prerequisites

- A Proliferate self-host (Docker Compose, AWS, GCP, Azure, Kubernetes,
  or air-gapped — the plugin is a Python package, not a service).
- A Conduct workspace with an agent token minted from Settings → Agent
  identities. Keep the `cond_agt_…` value handy.
- Python 3.10+ inside the Proliferate LiteLLM container.

## Step 1 — Install the plugin

Add `conduct-litellm-guard` to whatever image runs Proliferate's
LiteLLM service. If you deployed with their Docker Compose, extend
their `server/litellm` Dockerfile:

```dockerfile
RUN pip install conduct-litellm-guard
```

Or add `conduct-litellm-guard>=0.1` to your requirements file.

## Step 2 — Wire the guardrail into the LiteLLM config

Extend Proliferate's `server/litellm/config.yaml`:

```yaml
guardrails:
  - guardrail_name: conduct-guard
    litellm_params:
      guardrail: conduct_litellm_guard.ConductGuard
      mode: pre_call
      api_url: https://api.conductai.ai
      agent_token: os.environ/CONDUCT_AGENT_TOKEN
      fail_mode: fail_closed
      tool_name: workflow
```

`tool_name: workflow` makes plugin traffic register under the tool
scope existing Conduct packs already use. Rules like `no-aws-keys` in
`conduct-owasp` fire on LLM traffic without editing the pack.

Once packs ship the `llm_call` scope natively, drop this line — the
default (`llm_call`) will match.

## Step 3 — Provide the agent token

Set the environment variable where the LiteLLM container runs.

**Docker Compose:**
```yaml
services:
  litellm:
    environment:
      - CONDUCT_AGENT_TOKEN=cond_agt_...
```

**Kubernetes:** mount from a Secret.

## Step 4 — Restart and verify

```bash
docker compose restart litellm
```

Run any agent inside Proliferate. In the Conduct console:

1. Open **Guard → Activity** (`/theguard/activity`).
2. Look for entries with `TOOL: litellm` — audit attribution comes
   from the `X-Claude-Surface` header the plugin sets.
3. Each entry shows the Proliferate agent's model, the last user
   message, and the verdict (Allowed / Audited / Warned / Blocked /
   Pending).

## How Guard policies map to Proliferate runs

- **Per-agent scope.** Each Proliferate agent gets its own worktree
  and its own session. The plugin extracts session IDs from
  `litellm_metadata.trace_id` first, then falls back to
  `X-Conduct-Session-Id`, then a deterministic hash of the user
  identifier plus the first user message. Every Guard audit entry
  correlates back to a specific Proliferate task.
- **Cross-agent policy.** Because the plugin sits in `server/litellm`,
  every harness Proliferate supports goes through the same check. One
  policy update covers all of them.
- **HITL approvals.** A rule with `action: approval` produces a
  `PENDING approval` verdict. The plugin returns an error to the
  Proliferate agent (surfaced as a run failure with the rule name).
  Reviewer approves or rejects at `/theguard/approvals`. Once decided,
  the agent retries — same session ID, resumed verdict.

## Cloud sandbox path

Proliferate's execution plane runs agents in an
[E2B](https://e2b.dev) sandbox or on a personal target. Both paths
route LLM traffic through the same `server/litellm` control plane,
so the plugin covers sandboxed and local execution without further
configuration.

## Working example — block on secrets

Enable a rule scoped to `TOOL: workflow` (or install the
`conduct-owasp` pack, which ships `no-aws-keys` scoped to
`filesystem-write,workflow`).

Have a Proliferate agent generate a prompt containing an AWS access
key pattern (a well-known fake key format starting with the AKIA
prefix and 16 uppercase alphanumerics — the same pattern the rule
matches).

Expected:
- LiteLLM returns 400 with `BLOCKED — AWS access key detected in file.
  Blocked — use IAM roles or short-lived STS credentials.
  [rule: no-aws-keys]`
- Proliferate surfaces the run failure with the rule name.
- Zero upstream tokens spent — the plugin blocks before Anthropic /
  OpenAI is contacted.
- The audit chain lands a `Blocked` entry with `TOOL: litellm`,
  `CALL: workflow`, `RULE: no-aws-keys`.

## Troubleshooting — deterministic response → cause → fix

### Layer 1 — LiteLLM ↔ upstream provider

| Response body starts with… | HTTP | Cause | Fix |
|---|---|---|---|
| `{"detail":"Not Found"}` | 404 | Not hitting the real provider. An env variable is redirecting LiteLLM elsewhere. | `unset ANTHROPIC_BASE_URL OPENAI_BASE_URL`; restart LiteLLM. |
| `{"type":"error","error":{"type":"authentication_error"}}` | 401 | Real provider auth failed. Missing or wrong provider key. | Regenerate the provider key; export it in the LiteLLM environment. |
| `{"type":"error","error":{"type":"not_found_error","message":"model: X"}}` | 404 | Model `X` is not on your provider account. | Query the provider's model list and pick a real one. |
| `429` provider-throttling error | 429 | Provider quota reached for this window. | Slow down or upgrade the provider tier. |
| Real completion JSON with `choices[]` | 200 | LiteLLM ↔ provider is fine. Check Layer 2. | — |

### Layer 2 — Guard verdict

| Activity dashboard shows… | LiteLLM response | Cause | Fix |
|---|---|---|---|
| No entry at all | 200 completion | Plugin didn't call Guard. Config not loaded, `agent_token` empty, plugin not installed. | Check LiteLLM startup logs for `conduct_guard` init; verify `CONDUCT_AGENT_TOKEN`; run `pip show conduct-litellm-guard`. |
| Entry with `Allowed` | 200 completion | No rule matched. | Add a rule with a matching pattern, or install a compliance pack. |
| Entry with `Audited` | 200 completion | Rule matched, but action is `audit`. | Change rule action to `block` if you want blocking. |
| Entry with `Blocked` | 400 with `BLOCKED — … [rule: X]` | Correct block behaviour. | Success case. |
| Entry with `Pending Approval` | 400 with `PENDING approval — …` | HITL flow triggered. | Approve or reject at `/theguard/approvals`, then retry. |

### Layer 3 — Rule authoring for LLM traffic

The plugin sends:

- `tool_name` = whatever is configured (default `llm_call`, set to
  `workflow` to reuse existing packs).
- `tool_input` = `{model, call_type, message_count, temperature, max_tokens, stream, content}`.
  The `content` field is the last user message (truncated to 4 KB).
- `prompt` = the same last user message, top-level.

For a rule to fire on LLM traffic through the plugin, its `TOOL` scope
must include the configured `tool_name`, and its `PATTERN` must match
against `tool_input.content` (which carries the message body).

## Advanced — chaining plugin + Router

For maximum coverage you can put the plugin and Conduct Router both in
the path:

```
Agent → LiteLLM → conduct-litellm-guard (pre-call check)
              → Conduct Router (real proxy path)
              → Upstream provider
```

The plugin runs `guard_check` synchronously in the pre-call hook.
Router then re-checks proxy-time and writes the canonical audit-chain
entry.

## Links

- **Plugin:** https://pypi.org/project/conduct-litellm-guard/
- **Plugin source:** https://github.com/sseshachala/conductai/tree/main/packages/conduct-litellm-guard
- **Proliferate self-host guide:** https://github.com/proliferate-ai/proliferate/blob/main/guides/deploying/self-hosted-deploy.md
- **Conduct docs:** https://conductai.ai/docs
- **Report issues:** https://github.com/sseshachala/conductai/issues
