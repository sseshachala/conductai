# support-bot — runnable NeMo × Conduct example

Minimal NeMo Guardrails app that wires the `conduct_guard_check` action
into an input rail. Every user turn hits Conduct's Guard policy before
the model runs. Blocked or pending-approval verdicts short-circuit the
conversation with a policy-safe response and never reach the LLM.

This is the demo path the HPE PCAI PM screencast walks through.

## Prereqs

```bash
pip install conduct-nemo-guard nemoguardrails
export CONDUCT_AGENT_TOKEN=cond_agt_...   # Conduct console → Settings → Agent identities
export OPENAI_API_KEY=sk-...
```

## Run

```bash
python run.py "delete my account"
python run.py "what are your support hours?"
```

Expected shape:

- The first message trips a matching Guard rule → the input rail returns
  `inform_policy_hold` or `inform_policy_block`. Model is never called.
- The second message passes → the flow continues to the model normally.

Every turn lands as a row on the [Guard Activity page](https://conductai.ai/theguard/activity),
source-tagged `nemo`. Blocked rows carry the rule ID that fired.

## What the flow does

1. Input rail (`check_policy`) runs first on every user turn.
2. The rail calls `conduct_guard_check(tool_name="support_bot_message", prompt=$last_user_message)`.
3. The Conduct API returns one of `allow`, `advisory`, `warning`, `block`,
   or `approval`. See `rails.co` for the branching.
4. On `block` / `approval` the flow ends with a policy-safe bot message
   and the model is never invoked.
5. On `warning` the user gets an advisory line but the model still runs.
6. On `allow` / `advisory` / `unknown` the flow continues normally.

## Files

- `config.yml` — NeMo Guardrails model binding + input-rail declaration.
- `rails.co` — Colang flow (`check_policy`) plus the bot response
  templates the rail can end with.
- `run.py` — CLI wrapper that constructs `LLMRails`, calls
  `register_actions` from the plugin, and runs one turn.

## Where this fits

- Track 1 (Plugin) of the parent epic:
  [#1620](https://github.com/sseshachala/conductai/issues/1620)
- Sub-issue for the plugin:
  [#1621](https://github.com/sseshachala/conductai/issues/1621)
- LiteLLM-plugin sibling that shares the client:
  [`packages/conduct-litellm-guard`](../../../conduct-litellm-guard)
