# conduct-nemo-guard

Conduct Guard as a NeMo Guardrails plugin. Every Colang flow and every
LLM call routed through NeMo runs through your active Guard policy —
block, warn, audit, or trigger a HITL approval, with the same signed
configuration and hash-chained audit log as the rest of Conduct.

Follows the same shape as
[`conduct-litellm-guard`](../conduct-litellm-guard). Different host,
same client, same policy contract.

## Install

```bash
pip install conduct-nemo-guard
```

## Wire it up

1. Mint an agent token in the [Conduct console](https://conductai.ai)
   (Settings → Agent identities). Copy the `cond_agt_…` value.
2. Export it where your NeMo app runs:
   ```bash
   export CONDUCT_AGENT_TOKEN=cond_agt_...
   ```
3. Register the `conduct_guard_check` action with your `LLMRails`
   instance and reference it from Colang:

   ```python
   from nemoguardrails import LLMRails, RailsConfig
   from conduct_nemo_guard.actions import register_actions

   config = RailsConfig.from_path("./rails")
   rails = LLMRails(config)
   register_actions(rails)
   ```

   ```colang
   define flow policy_gate
     $decision = execute conduct_guard_check(tool_name="ask_bot")
     if $decision.verdict == "block"
       bot inform_blocked_by_policy
       stop
   ```

4. (Optional, follow-up) Route NeMo's LLM traffic through Conduct's
   proxy with `engine: conduct` in `config.yml`. Placeholder lives in
   `llm_provider.py`; see the plugin epic for delivery timing.

## What the plugin does

For every `execute conduct_guard_check(...)` call inside a Colang flow
the plugin calls Conduct's `guard_check` tool (JSON-RPC over the MCP
endpoint) with the flow context. Guard returns one of five verdicts:

| Verdict            | Colang behaviour                                        |
|--------------------|---------------------------------------------------------|
| `ok` / `allow`     | Flow continues.                                         |
| `advisory`         | Flow continues; verdict + rule_id available on `$decision`. |
| `warning`          | Flow continues; verdict surfaced for the rail to render.|
| `block`            | Flow branches on `$decision.verdict == "block"`.        |
| `approval`         | Flow branches on `$decision.verdict == "approval"` — HITL pending. |

## Configuration reference

Same environment contract as the LiteLLM guardrail — a shared client
lives in `_client.py`.

| Env var                 | Required | Default                    | Notes                                                     |
|-------------------------|----------|----------------------------|-----------------------------------------------------------|
| `CONDUCT_AGENT_TOKEN`   | yes      | —                          | `cond_agt_*` token minted in the Conduct console.         |
| `CONDUCT_API_URL`       | no       | `https://api.conductai.ai` | Point at a self-hosted Conduct API when needed.           |
| `CONDUCT_WORKSPACE_ID`  | no       | resolved from the token    | Usually unnecessary — the token owns its workspace.       |

## License

`conduct-nemo-guard` is distributed under the
[Apache License 2.0](../../LICENSE), the same license as the rest of
Conduct and as
[`nemoguardrails`](https://github.com/NVIDIA-NeMo/Guardrails) upstream.

## Links

- [Conduct Guard](https://conductai.ai/guard) — the policy engine.
- [NeMo Guardrails upstream](https://github.com/NVIDIA-NeMo/Guardrails).
- [Source](https://github.com/sseshachala/conductai) — this package
  lives under `packages/conduct-nemo-guard/`.
- [Plugin epic](https://github.com/sseshachala/conductai/issues/1620)
  and [sub-issue](https://github.com/sseshachala/conductai/issues/1621).
