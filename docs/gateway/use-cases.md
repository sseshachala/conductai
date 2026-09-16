# Gateway v2 — supported use cases

Reference doc grounded in the actual capability catalog + transport
registrations (as of merge of #2043, #2044). Every use case here
publishes cleanly and can be exercised end-to-end with the Python
snippets below.

> **Anything not in this doc is not supported by the platform today.**
> See [What's NOT supported](#whats-not-supported) at the bottom.

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
   | Anthropic SDK | `https://api.conductai.ai/gateway/v1/anthropic` |
   | OpenAI SDK (incl. OpenRouter passthrough) | `https://api.conductai.ai/gateway/v1/openai` |

5. **Model field** is always the profile's cond-code identifier:
   ```
   cond-<8-char-code>-<alias>
   ```
   Grab it from the profile's "How to use" panel after publish.

---

## Capability matrix — what the catalog certifies

| Transport | Provider / Integration | Operation | Streaming |
|---|---|---|---|
| `native_http` | anthropic | anthropic_messages | ✅ |
| `native_http` | anthropic | anthropic_count_tokens | ❌ (sync only) |
| `native_http` | openai | openai_chat_completions | ✅ |
| `native_http` | openai | openai_responses | ✅ |
| `litellm_sdk` | anthropic | anthropic_messages | ❌ (returns 501) |
| `litellm_sdk` | anthropic | anthropic_count_tokens | ❌ |
| `litellm_sdk` | openai | openai_chat_completions | ❌ (returns 501) |
| `litellm_sdk` | openai | openai_responses | ❌ |
| `http_passthrough` | openrouter | openai_chat_completions | ❌ (returns 501) |

Absent from this table = not certified; publish rejects.

---

# Use cases

## UC1 — Claude Sonnet 4.6, single target, native HTTP

**Profile config:**
```json
{
  "name": "claude-sonnet",
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
    base_url="https://api.conductai.ai/gateway/v1/anthropic",
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
    base_url="https://api.conductai.ai/gateway/v1/openai",
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
Useful when you want LiteLLM's cost tracking or param normalization.
Streaming through this path returns 501 today — use UC1 if you need
streaming.

**Profile config:**
```json
{
  "name": "claude-via-litellm",
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
    base_url="https://api.conductai.ai/gateway/v1/openai",
)
resp = client.chat.completions.create(
    model="cond-abc12345-via-openrouter",
    messages=[{"role": "user", "content": "Say hello."}],
)
```

## UC8 — Streaming Anthropic

Uses `native_http`. Same profile as UC1; set `stream=True` on the
request. Anthropic's SSE format is preserved byte-for-byte.

**Python:**
```python
from anthropic import Anthropic

client = Anthropic(
    api_key="guard-mt-YOUR_TOKEN",
    base_url="https://api.conductai.ai/gateway/v1/anthropic",
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

Uses `native_http`. Same profile as UC2 with `stream=True`.

**Python:**
```python
from openai import OpenAI

client = OpenAI(
    api_key="guard-mt-YOUR_TOKEN",
    base_url="https://api.conductai.ai/gateway/v1/openai",
)
stream = client.chat.completions.create(
    model="cond-abc12345-gpt-4o",
    messages=[{"role": "user", "content": "Count to 5 slowly."}],
    stream=True,
)
for chunk in stream:
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
    base_url="https://api.conductai.ai/gateway/v1/anthropic",
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
    base_url="https://api.conductai.ai/gateway/v1/openai",
)
resp = client.responses.create(
    model="cond-abc12345-gpt-4o",
    input="Say hello.",
)
print(resp.output_text)
```

Same profile as UC2 — the profile's `accepts` covers both operations
because native OpenAI is certified for both.

## UC12 — Anthropic prompt-caching (via vendor headers)

`anthropic-beta` header for prompt caching passes through unchanged
(allowlisted for v2 — see PR #2041). No profile changes needed.

**Python:**
```python
from anthropic import Anthropic

client = Anthropic(
    api_key="guard-mt-YOUR_TOKEN",
    base_url="https://api.conductai.ai/gateway/v1/anthropic",
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

The following will publish-fail or hit `501 Not Implemented`. Filing
issues / PRs adds them.

**Providers not in the catalog:**
- Groq, Cohere, Mistral, Bedrock, Vertex, Perplexity — LiteLLM the
  library supports them, but `_LITELLM_SDK_CERTIFIED` only lists
  `anthropic` + `openai`. Extending the catalog is a code change.

**Passthrough integrations not yet certified:**
- Portkey, Helicone (anthropic + openai), Azure OpenAI, Custom.
  Each needs its per-integration auth-header semantics wired in
  `_INTEGRATION_ENDPOINTS` + `_HTTP_PASSTHROUGH_CERTIFIED`.

**Streaming through non-native transports:**
- `litellm_sdk` streaming → 501 (needs SDK-response-to-SSE bridging).
- `http_passthrough` streaming → 501 (needs per-integration
  streaming wire).

**Cross-vendor fallback in one profile:**
- Claude → GPT fallback: the accepts intersection would be empty
  (Anthropic ops ∩ OpenAI ops = ∅), so publish rejects with a
  "no shared operations" error. Would need a translation layer
  (LiteLLM's cross-provider mode) or two separate profiles + client-
  side routing.

**Adding a new provider** is a two-step PR:
1. Add a row in `capability_catalog.py` (`_LITELLM_SDK_CERTIFIED`
   for LiteLLM route, `_HTTP_PASSTHROUGH_CERTIFIED` for passthrough).
2. If passthrough: add the `IntegrationConfig` in
   `http_passthrough_transport.py::_INTEGRATION_ENDPOINTS`.

Ship a test proving the (provider, operation) tuple works end-to-end
before merging.
