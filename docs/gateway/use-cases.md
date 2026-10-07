# Gateway v2 — supported use cases

Create separate profiles for each use case. Each published profile has its own
model identifier, ordered targets, credentials, timeout, and attempt limit.
Native HTTPS, LiteLLM SDK, and external Gateway targets support streaming.

---

## Prerequisites

1. **Conduct member token**: `guard-mt-...` from Settings → Team.
2. **V2 enabled for your workspace**:
   - `GUARD_GATEWAY_PROFILE_V2=true`
   - Your workspace UUID in `GUARD_GATEWAY_PROFILE_V2_ALLOWLIST`
3. **Vault credentials** for each provider you'll route to (Anthropic /
   OpenAI / OpenRouter). Settings → Vault → New credential.
4. **Base URLs** — pick the one matching your SDK:

   | SDK you're using | Base URL |
   |---|---|
   | Anthropic SDK | `https://gateway.conductai.ai/gateway/v1/anthropic` |
   | OpenAI SDK (incl. OpenRouter passthrough) | `https://gateway.conductai.ai/gateway/v1/openai/v1` |

5. **Model field** can use the profile's unambiguous cond-code identifier:
   ```
   cond-<8-char-code>-<alias>
   ```
   Grab it from the profile's "How to use" panel after publish.

### Client model selection

With Gateway v2 enabled, the canonical `/gateway/v1/...` endpoints also accept:

- A published profile alias, such as `coding`.
- An exact upstream model name, when every target in the matching profile uses
  that model. Mixed-model fallback profiles require their alias or full cond ID.
- `cheap`, `balanced`, or `smart`, resolved using LLM Model Primitives and the
  workspace's preferred provider. A provider-qualified tier, such as
  `openai/balanced`, uses that provider's primitives instead.

The selected model must match a compatible published profile in the caller's
workspace. Primitives do not publish or authorize profiles. Multiple matching
profiles return HTTP 409; choose the full cond ID. An unknown model returns 404.
An incompatible operation returns 400. No different model is silently selected.

Claude Code uses Anthropic Messages. Codex and Copilot use OpenAI Responses.
For Responses, publish an OpenAI profile accepting `openai_responses`; an
Anthropic Messages profile cannot serve that wire format. Streaming and tool
calls retain the existing transport capability checks.

Policy, budgets, credentials, rate limits, and audit still run through the same
Gateway path. Audit metadata records the original selection and pinned revision.
Existing full cond IDs and non-canonical proxy routes retain their behavior.

### Profile rate limits

Set RPM and TPM on each profile in **Gateways**. Blank means unlimited.
Limits remain editable after publishing, without creating a routing revision.

Requests from all clients and identities share the profile's quota. Optional
agent caps apply in addition to that quota. Other profiles have separate quotas;
changing revisions does not reset a profile's counters. Workspace spend budgets
remain separate.

TPM reserves estimated input plus the requested output allowance, then settles
against provider-reported input and output tokens, including cache usage and
paid fallback attempts. Missing or interrupted usage keeps the reservation.
For small smoke-test caps, send an explicit small `max_tokens` or
`max_output_tokens`. Caps return HTTP 429 with `Retry-After`; an unavailable
limit lookup or Redis service returns HTTP 503.

Migration 0163 copies existing workspace and agent limits onto each existing v2
profile. Legacy rows remain intact for older proxy routes; v2 requests use only
profile limits. New profiles start unlimited until configured.

---

## Capability matrix — what the catalog certifies

| Transport | Provider / Integration | Operation | Streaming |
|---|---|---|---|
| `native_http` | anthropic | anthropic_messages | ✅ |
| `native_http` | anthropic | anthropic_count_tokens | ❌ (sync only) |
| `native_http` | openai | openai_chat_completions | ✅ |
| `native_http` | openai | openai_responses | ✅ |
| `litellm_sdk` | anthropic | anthropic_messages, openai_chat_completions | Yes |
| `litellm_sdk` | anthropic | anthropic_count_tokens | No (non-streaming count) |
| `litellm_sdk` | openai | openai_chat_completions, openai_responses, anthropic_messages | Yes |
| `litellm_sdk` | perplexity, together | openai_chat_completions | Yes |
| `http_passthrough` | openrouter, portkey, helicone_openai, azure_openai | openai_chat_completions | Yes |
| `http_passthrough` | helicone_anthropic | anthropic_messages | Yes |
| `http_passthrough` | custom (OpenAI protocol) | openai_chat_completions, openai_responses | Yes |
| `http_passthrough` | custom (Anthropic protocol) | anthropic_messages | Yes |
| `http_passthrough` | custom (Anthropic protocol) | anthropic_count_tokens | No (non-streaming count) |

Absent from this table = not certified; publish rejects.

Tool arguments are validated before delivery in Chat, Messages, and Responses.
Messages and Responses tool streams are buffered for validation, up to 8 MiB.
Usage is captured before conversion or redaction, using the actual provider and
model for each attempt. Fallback is permitted on transient failures before
streaming starts, never after the stream is committed.

---

# Use cases

## UC1 — Claude Sonnet 4.6, single target, native HTTP

**Profile config:**
```json
{
  "name": "claude-sonnet",
  "accepts": ["anthropic_messages", "anthropic_count_tokens"],
  "model_alias": "claude-sonnet",
  "timeout_seconds": 60,
  "max_attempts": 1,
  "targets": [
    {
      "id": "primary",
      "transport": "native_http",
      "provider": "anthropic",
      "model": "claude-sonnet-4-6",
      "credential_ref": "vault://<env-uuid>/anthropic"
    }
  ]
}
```

**Python (Anthropic SDK):**
```python
from anthropic import Anthropic

client = Anthropic(
    api_key="guard-mt-YOUR_TOKEN",
    base_url="https://gateway.conductai.ai/gateway/v1/anthropic",
)
resp = client.messages.create(
    model="cond-abc12345-claude-sonnet",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
)
print(resp.content[0].text)
```

## UC2 — GPT-4o, single target, native HTTP

**Profile config:**
```json
{
  "name": "gpt-4o",
  "accepts": ["openai_chat_completions", "openai_responses"],
  "model_alias": "gpt-4o",
  "timeout_seconds": 60,
  "max_attempts": 1,
  "targets": [
    {
      "id": "primary",
      "transport": "native_http",
      "provider": "openai",
      "model": "gpt-4o",
      "credential_ref": "vault://<env-uuid>/openai"
    }
  ]
}
```

**Python (OpenAI SDK):**
```python
from openai import OpenAI

client = OpenAI(
    api_key="guard-mt-YOUR_TOKEN",
    base_url="https://gateway.conductai.ai/gateway/v1/openai/v1",
)
resp = client.chat.completions.create(
    model="cond-abc12345-gpt-4o",
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
)
print(resp.choices[0].message.content)
```

## UC3 — Same-vendor fallback: Claude Sonnet → Haiku

Sonnet primary; on 5xx / timeout / connection error, fall back to
Haiku. Both native_http, same protocol, so publish accepts the
shared operation set `{anthropic_messages, anthropic_count_tokens}`.

**Profile config:**
```json
{
  "name": "claude-with-fallback",
  "accepts": ["anthropic_messages", "anthropic_count_tokens"],
  "model_alias": "claude-with-fallback",
  "timeout_seconds": 60,
  "max_attempts": 2,
  "targets": [
    {
      "id": "primary",
      "transport": "native_http",
      "provider": "anthropic",
      "model": "claude-sonnet-4-6",
      "credential_ref": "vault://<env-uuid>/anthropic"
    },
    {
      "id": "fallback",
      "transport": "native_http",
      "provider": "anthropic",
      "model": "claude-haiku-4-5-20251001",
      "credential_ref": "vault://<env-uuid>/anthropic"
    }
  ]
}
```

**Python:** identical to UC1 — the SDK doesn't know a fallback exists.
Coordinator handles it. Check `audit_events.routing_meta->'attempts'`
after the request to confirm which target served.

## UC4 — Same-vendor fallback: GPT-4o → GPT-4o-mini

Symmetric to UC3, OpenAI side.

**Profile config:**
```json
{
  "name": "gpt-with-fallback",
  "accepts": ["openai_chat_completions", "openai_responses"],
  "model_alias": "gpt-with-fallback",
  "timeout_seconds": 60,
  "max_attempts": 2,
  "targets": [
    {
      "id": "primary",
      "transport": "native_http",
      "provider": "openai",
      "model": "gpt-4o",
      "credential_ref": "vault://<env-uuid>/openai"
    },
    {
      "id": "fallback",
      "transport": "native_http",
      "provider": "openai",
      "model": "gpt-4o-mini",
      "credential_ref": "vault://<env-uuid>/openai"
    }
  ]
}
```

## UC5 — Anthropic via LiteLLM SDK (translation opt-in)

Same effect as UC1 from the client's perspective, but the request
goes through the in-process LiteLLM SDK instead of a raw HTTP forward.
Use this for protocol translation or provider parameter normalization.
Both non-streaming and streaming requests are supported.

**Profile config:**
```json
{
  "name": "claude-via-litellm",
  "accepts": ["anthropic_messages", "openai_chat_completions"],
  "model_alias": "claude-via-litellm",
  "timeout_seconds": 60,
  "max_attempts": 1,
  "targets": [
    {
      "id": "primary",
      "transport": "litellm_sdk",
      "provider": "anthropic",
      "model": "claude-sonnet-4-6",
      "credential_ref": "vault://<env-uuid>/anthropic"
    }
  ]
}
```

**Python:** same as UC1.

## UC6 — OpenAI via LiteLLM SDK

Symmetric to UC5 for the OpenAI side.

**Profile config:**
```json
{
  "name": "gpt-via-litellm",
  "accepts": ["openai_chat_completions", "openai_responses", "anthropic_messages"],
  "model_alias": "gpt-via-litellm",
  "timeout_seconds": 60,
  "max_attempts": 1,
  "targets": [
    {
      "id": "primary",
      "transport": "litellm_sdk",
      "provider": "openai",
      "model": "gpt-4o",
      "credential_ref": "vault://<env-uuid>/openai"
    }
  ]
}
```

## UC7 — OpenRouter passthrough (chat completions only)

Client speaks OpenAI Chat Completions shape at
`/gateway/v1/openai/v1/chat/completions`. Transport POSTs to
OpenRouter with a Bearer key, and OpenRouter routes to whatever
model you ask for (`anthropic/claude-3.5-sonnet`,
`meta-llama/llama-3.1-70b-instruct`, etc.).

**Profile config:**
```json
{
  "name": "via-openrouter",
  "accepts": ["openai_chat_completions"],
  "model_alias": "via-openrouter",
  "timeout_seconds": 60,
  "max_attempts": 1,
  "targets": [
    {
      "id": "primary",
      "transport": "http_passthrough",
      "integration": "openrouter",
      "model": "anthropic/claude-3.5-sonnet",
      "credential_ref": "vault://<env-uuid>/openrouter"
    }
  ]
}
```

**Python (OpenAI SDK still — OpenRouter is OpenAI-compatible):**
```python
from openai import OpenAI

client = OpenAI(
    api_key="guard-mt-YOUR_TOKEN",
    base_url="https://gateway.conductai.ai/gateway/v1/openai/v1",
)
resp = client.chat.completions.create(
    model="cond-abc12345-via-openrouter",
    messages=[{"role": "user", "content": "Say hello."}],
)
```

## UC8 — Streaming Anthropic

Use Native HTTPS or LiteLLM SDK. Set `stream=True` on the request.
Anthropic event types are preserved; tool arguments are validated before delivery.

**Python:**
```python
from anthropic import Anthropic

client = Anthropic(
    api_key="guard-mt-YOUR_TOKEN",
    base_url="https://gateway.conductai.ai/gateway/v1/anthropic",
)
with client.messages.stream(
    model="cond-abc12345-claude-sonnet",
    max_tokens=200,
    messages=[{"role": "user", "content": "Count to 5 slowly."}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
print()
```

## UC9 — Streaming OpenAI

Use Native HTTPS, LiteLLM SDK, or an OpenAI-compatible external Gateway.
Use the matching published profile and set `stream=True`.

**Python:**
```python
from openai import OpenAI

client = OpenAI(
    api_key="guard-mt-YOUR_TOKEN",
    base_url="https://gateway.conductai.ai/gateway/v1/openai/v1",
)
stream = client.chat.completions.create(
    model="cond-abc12345-gpt-4o",
    messages=[{"role": "user", "content": "Count to 5 slowly."}],
    stream=True,
)
for chunk in stream:
    if not chunk.choices:
        continue  # Usage-only event.
    delta = chunk.choices[0].delta.content
    if delta:
        print(delta, end="", flush=True)
print()
```

## UC10 — Anthropic count_tokens (non-inference operation)

Cheap pre-flight to check payload size before firing a real request.

**Python:**
```python
from anthropic import Anthropic

client = Anthropic(
    api_key="guard-mt-YOUR_TOKEN",
    base_url="https://gateway.conductai.ai/gateway/v1/anthropic",
)
resp = client.messages.count_tokens(
    model="cond-abc12345-claude-sonnet",
    messages=[{"role": "user", "content": "How many tokens is this?"}],
)
print(resp.input_tokens)
```

Same profile as UC1. The endpoint (`/v1/messages/count_tokens`) is
part of the certified matrix.

## UC11 — OpenAI Responses API (`/v1/responses`)

The newer OpenAI Responses format (successor to Chat Completions
for many use cases).

**Python (OpenAI SDK ≥ 1.60):**
```python
from openai import OpenAI

client = OpenAI(
    api_key="guard-mt-YOUR_TOKEN",
    base_url="https://gateway.conductai.ai/gateway/v1/openai/v1",
)
resp = client.responses.create(
    model="cond-abc12345-gpt-4o",
    input="Say hello.",
)
print(resp.output_text)
```

Same profile as UC2 — the profile's `accepts` covers both operations
because native OpenAI is certified for both.

## Claude and OpenAI fallback in one profile

Choose **Claude + OpenAI fallback via LiteLLM** in Gateways, or import
[the example](examples/litellm-cross-provider-fallback.json). Pick both Vault
credentials and publish. Both targets accept Messages and Chat Completions.
For Responses, use a separate OpenAI profile.

## UC12 — Anthropic prompt-caching (via vendor headers)

`anthropic-beta` header for prompt caching passes through unchanged
(allowlisted for v2 — see PR #2041). No profile changes needed.

**Python:**
```python
from anthropic import Anthropic

client = Anthropic(
    api_key="guard-mt-YOUR_TOKEN",
    base_url="https://gateway.conductai.ai/gateway/v1/anthropic",
    default_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
)
resp = client.messages.create(
    model="cond-abc12345-claude-sonnet",
    max_tokens=200,
    system=[{
        "type": "text",
        "text": "You are a legal-review assistant.",
        "cache_control": {"type": "ephemeral"},
    }],
    messages=[{"role": "user", "content": "Analyse this clause..."}],
)
```

Header allowlist for v2 (from `gateway_handler._V2_HEADER_ALLOWLIST`):
`anthropic-beta`, `anthropic-version`, `openai-organization`,
`openai-project`, `openai-beta`, `openrouter-referer`.

---

# Verification

After every request, confirm the audit row landed:

```sql
SELECT
  ts,
  decision,
  execution_status,
  routing_meta->>'gateway_version' AS gw,
  routing_meta->>'cond_code' AS cond,
  routing_meta->'attempts' AS attempts,
  duration_ms,
  tokens_before, tokens_after
FROM guard_audit_events
WHERE workspace_id = '<your-workspace-uuid>'
ORDER BY ts DESC
LIMIT 5;
```

Look for:
- `gw = 'v2'`
- `cond` matches your profile
- `attempts[0].transport` matches the target you expected
- `attempts[0].succeeded = true`

---

# What's NOT supported

Profiles can only advertise operations supported by every target.

**Providers not in the catalog:**
- Groq, Cohere, Mistral, Bedrock, and Vertex need a tested catalog entry.

**Protocol constraints:**
- Native HTTPS does not translate between Anthropic and OpenAI. Use LiteLLM
  SDK targets for cross-provider Messages or Chat fallback.
- Anthropic targets do not accept OpenAI Responses in this catalog.
- Token counting is non-streaming and requires an Anthropic count endpoint.
- An external Gateway must implement the operation its profile advertises.

## Regression matrix

From `apps/api`, with its requirements installed:

```bash
python -m pytest tests/guard/test_gateway_transport_matrix.py tests/guard/test_gateway_native_tool_protocols.py -q
```

These tests run the real pinned LiteLLM SDK with mocked vendor HTTP, without
provider keys or inference charges. They cover certified transports, streaming,
token counting, fallback, tool validation, usage shapes, and response cleanup.

**Adding a new provider** is a two-step PR:
1. Add a row in `capability_catalog.py` (`_LITELLM_SDK_CERTIFIED`
   for LiteLLM route, `_HTTP_PASSTHROUGH_CERTIFIED` for passthrough).
2. If passthrough: add the `IntegrationConfig` in
   `http_passthrough_transport.py::_INTEGRATION_ENDPOINTS`.

Ship a test proving the (provider, operation) tuple works end-to-end
before merging.
