# ACD-0004: Provider-Neutral Governance Layer

**Status:** Accepted  
**Date:** 2026-07-01  
**Patent claim:** Vendor adapter registry with normalized internal representation

---

## Decision

The governance layer (policy engine, audit log, spend tracking) operates on a provider-neutral internal representation. Provider-specific wire formats (Anthropic `input_tokens`, OpenAI `prompt_tokens`, Gemini `usageMetadata`) are translated at the proxy boundary and never reach the policy engine or audit schema.

```
Anthropic response  →  _extract_token_counts()  →  (in_tokens, out_tokens)
OpenAI response     →  _extract_token_counts()  →  (in_tokens, out_tokens)
Gemini response     →  _extract_token_counts()  →  (in_tokens, out_tokens)
                                                          │
                                                          ▼
                                              guard_audit_events
                                              (provider-neutral schema)
                                                          │
                                                          ▼
                                              Policy engine, spend dashboard,
                                              hash chain — all provider-agnostic
```

---

## Context

The temptation when building an LLM gateway is to normalize everything to OpenAI format — it's the most common and most SDKs speak it. This couples your internal representation to a single provider's design decisions.

OpenAI uses `prompt_tokens` / `completion_tokens`. Anthropic uses `input_tokens` / `output_tokens` and adds `cache_read_input_tokens` / `cache_creation_input_tokens`. Gemini uses `usageMetadata.promptTokenCount`. These names reflect each provider's internal model, not a stable abstraction.

If the governance layer consumes OpenAI field names directly, adding Anthropic support requires changing audit schema, spend calculations, and policy evaluation — not just the adapter.

---

## Alternatives Rejected

**Normalize to OpenAI format internally**: Couples governance logic to OpenAI's field naming. Anthropic cache tokens have no OpenAI equivalent — they would need to be dropped or shoehorned into non-matching fields. Breaks when OpenAI changes their schema (as they have multiple times).

**Store raw provider responses**: Audit rows would contain provider-specific JSON blobs. Spend queries, policy evaluation, and compliance exports would require provider-specific parsing logic at query time. Governance becomes a reporting problem.

**One adapter per query**: Each governance query handles provider differences inline. Governance logic becomes entangled with provider normalization. Adding a new provider requires modifying every governance query.

---

## Consequences

- `_extract_token_counts()` is the single translation point — all provider differences are handled here
- `_compute_cost()` takes normalized `(in_tokens, out_tokens)` — cost calculation is provider-aware via the pricing registry but field extraction is not
- Adding a new provider requires: one new extraction branch in `_extract_token_counts()`, one pricing entry — nothing else changes
- Provider-specific fields (Anthropic cache tokens) are captured as additional normalized fields (`cache_read_tokens`, `cache_creation_tokens`) in the audit schema — not as raw provider payloads
- The proxy exposes an OpenAI-compatible API surface to callers — this is a deliberate compatibility choice for the external API, not an internal representation choice. The two are independent.
