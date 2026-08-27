# API versioning

## Scope

This document defines versioning strategy for Conduct enforcement APIs:

- Proxy surface (`/proxy/{provider}/...`).
- MCP guard surface (`/guard/mcp`, including `guard_check`).

## Versioning strategy

## 1) Proxy endpoints

- Proxy uses path-based versioning aligned with provider-compatible endpoint families.
- Current examples include:
  - `/proxy/anthropic/v1/messages`
  - `/proxy/openai/v1/chat/completions`
  - `/proxy/perplexity/chat/completions`
- New breaking proxy contracts must introduce a new explicit versioned path segment (for example `/v2/...`) rather than in-place breaking changes.

## 2) MCP guard endpoint

- Transport endpoint remains `/guard/mcp`.
- Protocol compatibility is declared via MCP protocol metadata (current value in code: `2024-11-05`).
- Tool contract changes to `guard_check` should remain backward compatible within the same protocol window.

## Backward compatibility guarantees

- Non-breaking additive changes (new optional fields, new metadata fields, new optional tool arguments) may ship in minor releases.
- Breaking changes require:
  1. version bump (path and/or protocol-level),
  2. migration notes,
  3. overlap period where old version remains available.

## Deprecation policy

- Minimum deprecation notice: **90 days** for production-facing API contract breaks.
- Deprecation communications should include:
  - affected endpoint/tool fields,
  - replacement contract,
  - exact removal date,
  - migration examples.

## Error model and negotiation notes

- Clients must treat unknown response fields as forward-compatible.
- Clients should branch on explicit action/decision semantics (`allow`, `warn`, `block`, `require_approval`) rather than brittle string matching on prose.
- Proxy callers should expect standard HTTP status handling plus provider passthrough failures.
- MCP callers should treat protocol mismatch as non-retryable until client/server protocol versions are aligned.

## OpenAPI publication guidance

- Publish source OpenAPI schema from FastAPI app in `apps/api/`.
- Recommended artifact location for generated specs:
  - `docs/reference/openapi/` (JSON and/or YAML), versioned by release tag.
- Release process guidance:
  1. generate schema from the tagged API build,
  2. commit artifact under release-specific filename,
  3. link artifact in release notes.

`TODO: confirm exact schema generation command/path currently used in CI and codify it here.`
`TODO: confirm whether MCP tool schema snapshots should also be exported under docs/reference/.`
