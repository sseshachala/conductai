import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Conduct Guard

Use [Conduct Guard](https://conductai.ai/guard) to enforce runtime
policy on every LLM call routed through LiteLLM — block, warn, audit,
or trigger a human-in-the-loop approval, with signed configuration and
a hash-chained audit trail.

## 1. Set up Conduct

### Mint an agent token

Sign in at [conductai.ai](https://conductai.ai) → Settings → Agent
identities → **Mint agent token**. Copy the `cond_agt_…` value (shown
once).

### Enable a compliance pack (or write a rule)

At `/theguard/policies`, enable one of the shipped packs
(`conduct-owasp`, `conduct-soc2`, `conduct-hipaa`, `conduct-pci-dss`,
`conduct-eu-ai-act`, `conduct-nist-ai-rmf`, `conduct-iso-42001`, and
more), or author a custom rule with:

- **TOOL:** `llm_call` — matches every LLM call routed through the
  plugin.
- **PATTERN:** any regex that should trigger the rule (matched against
  the last user message in `tool_input.content`).
- **ACTION:** `block`, `warn`, `audit`, or `approval`.

## 2. Install the plugin

```shell
pip install conduct-litellm-guard
```

The native LiteLLM guardrail is a thin adapter — it imports the
runtime from the `conduct-litellm-guard` package on PyPI. Same install
model as Aporia and Lakera.

## 3. Define the guardrail on your LiteLLM `config.yaml`

```yaml
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY

guardrails:
  - guardrail_name: conduct-guard
    litellm_params:
      guardrail: conduct
      mode: pre_call
      api_key: os.environ/CONDUCT_AGENT_TOKEN
      api_base: https://api.conductai.ai         # optional, defaults to hosted
      fail_mode: fail_closed                      # or fail_open
      default_on: true
```

### Supported values for `mode`

- `pre_call` — run **before** the upstream LLM call. Blocks the request
  if a rule fires. Zero upstream tokens spent on blocked traffic.
- `during_call` — same as `pre_call` but runs in parallel to the LLM
  call. Response not returned until the guardrail check completes.

### Config reference

| Field           | Required | Default                    | Notes                                                                    |
|-----------------|----------|----------------------------|--------------------------------------------------------------------------|
| `api_key`       | yes      | `CONDUCT_AGENT_TOKEN` env  | `cond_agt_*` token minted in the Conduct console.                        |
| `api_base`      | no       | `https://api.conductai.ai` | Point at a self-hosted Conduct API when needed.                          |
| `workspace_id`  | no       | resolved from the token    | Usually unnecessary — the token owns its workspace.                      |
| `fail_mode`     | no       | `fail_closed`              | `fail_closed` blocks when Guard is unreachable; `fail_open` allows.      |
| `tool_name`     | no       | `llm_call`                 | Guard tool scope. Set to `workflow` to reuse existing non-LLM packs.     |
| `timeout`       | no       | `8.0`                      | Seconds. Guard responds in <100ms in the healthy path.                   |

## 4. Start LiteLLM Gateway

```shell
litellm --config config.yaml --detailed_debug
```

## 5. Test request

<Tabs>
<TabItem label="Allowed call" value="allowed">

```shell
curl http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello"}],
    "guardrails": ["conduct-guard"]
  }'
```

Standard OpenAI-compatible completion response. The audit chain records
the call in the Conduct console under **Guard → Activity**.

</TabItem>
<TabItem label="Blocked call" value="blocked">

If your active packs include a rule that matches AWS access-key
patterns (for example, `conduct-owasp` ships `no-aws-keys` scoped to
`filesystem-write,workflow`), a request containing that pattern is
blocked. Use a well-known-fake AWS access-key format (a string
starting with `AKIA` followed by 16 uppercase alphanumerics) as the
prompt:

```shell
curl http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "<paste-fake-aws-key-pattern-here>"}],
    "guardrails": ["conduct-guard"]
  }'
```

Expected response body:

```json
{
  "error": {
    "message": "BLOCKED — AWS access key detected in file. Blocked — use IAM roles or short-lived STS credentials. [rule: no-aws-keys]",
    "type": null,
    "code": "400"
  }
}
```

Zero upstream tokens spent. The audit chain records the block with
`RULE: no-aws-keys`, `DECISION: Blocked`.

</TabItem>
</Tabs>

## Session tracking

Conduct uses a session ID to correlate the pre-call check with any
resume-verdict or HITL approval that follows. The plugin picks the
first value it finds in this order:

1. `litellm_metadata.trace_id`
2. `metadata.X-Conduct-Session-Id` (explicit override)
3. `metadata.conduct_session_id`
4. A deterministic hash of the `user` field + first user message

## Human-in-the-loop approvals

Rules with `action: approval` pause the request. The plugin returns an
error to the caller citing the rule; the reviewer approves or rejects
at `/theguard/approvals` in the Conduct console (Slack Approve /
Reject buttons also supported). Once decided, the caller retries and
the resume-verdict short-circuits the check.

## Links

- **Conduct Guard:** [conductai.ai/guard](https://conductai.ai/guard)
- **Sign up:** [conductai.ai/sign-up](https://conductai.ai/sign-up)
- **Package on PyPI:** [conduct-litellm-guard](https://pypi.org/project/conduct-litellm-guard/)
- **Plugin source:** [github.com/sseshachala/conductai](https://github.com/sseshachala/conductai/tree/main/packages/conduct-litellm-guard)
- **Report issues:** [github.com/sseshachala/conductai/issues](https://github.com/sseshachala/conductai/issues)
