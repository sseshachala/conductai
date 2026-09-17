# Gateway v2 — importable example profiles

Ready-to-import Gateway Profile v2 JSON files. Every credential_ref is
intentionally empty — the import endpoint strips them anyway, so the
admin picks a Vault + handle post-import via the editor's Save gate.

## Usage

**CLI:**
```bash
conduct import --gateway-config docs/gateway/examples/claude-sonnet.json
```

**UI:**
1. Open **Gateways** (`/proxy/gateway-profiles`) → **Import**.
2. Paste the JSON from any file below into the dialog.
3. Follow the returned link to the editor and pick credentials.

## Files

| File | Transport | Provider / Integration | Notes |
|---|---|---|---|
| `claude-sonnet.json` | `native_http` | anthropic / claude-sonnet-4-6 | single target |
| `claude-fallback.json` | `native_http` | anthropic (Sonnet → Haiku) | same-vendor fallback |
| `gpt-4o.json` | `native_http` | openai / gpt-4o | single target, both accepts |
| `litellm-anthropic.json` | `litellm_sdk` | anthropic | translation route (non-streaming) |
| `openrouter.json` | `http_passthrough` | openrouter | chat_completions only |

Cross-vendor fallback (e.g. Anthropic primary + OpenAI fallback) is
NOT supported today — publish rejects because no accepted operation
is served by both. See `../use-cases.md` for the full catalog.
