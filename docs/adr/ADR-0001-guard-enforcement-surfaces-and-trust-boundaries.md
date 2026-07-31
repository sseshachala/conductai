---
status: accepted
date: 2026-07-30
decision-makers:
  - Conduct engineering
---

# ADR-0001: Guard enforcement surfaces and trust boundaries

## Context

ConductGuard receives policy-relevant information at four different surfaces:
the LLM proxy, local pre-tool hooks, MCP `guard_check`, and the Conduct
workflow runtime. These surfaces do not observe the same inputs and do not
provide the same enforcement guarantees.

A single statement such as "this rule is enforced" hides deployment
dependencies and creates false security claims. MCP transport also cannot be
treated as an authentication or enforcement boundary.

## Decision

Conduct will model Proxy, Hook, MCP, and Runtime as distinct enforcement
surfaces with explicit trust boundaries.

### Proxy

- The proxy is the server-side boundary for LLM requests routed through
  Conduct.
- It authenticates the caller at the resource layer before forwarding.
- It can evaluate provider, model, and request-text matchers.
- It cannot infer local tool semantics that are absent from the LLM request.
- A hard proxy rule means the matching request is stopped once traffic reaches
  the proxy. It does not mean all LLM traffic is routed through Conduct.

### Hook

- The hook is the pre-execution boundary for supported AI tools that emit
  structured tool events.
- It can evaluate tool, path, surface, pattern, and token-context matchers.
- Enforcement is conditional on installation, policy sync, supported host
  behavior, and the hook running before the action.
- The hook is designed to prevent mistakes on governed machines; it is not an
  operating-system sandbox or adversarial containment boundary.

### MCP

- MCP is a transport for an authenticated `guard_check`, not a security
  boundary.
- The underlying Conduct API authenticates and evaluates every request.
- Enforcement is conditional on the agent submitting an accurate intent before
  acting and obeying a blocked result.
- Rules whose matcher semantics cannot be preserved by MCP are not advertised
  as MCP coverage.

### Runtime

- The Conduct runtime is the boundary for actions executed by Conduct
  playbooks.
- It evaluates workspace policy within the run context and preserves run,
  workspace, identity, and audit linkage.
- Arbitrary shell and file operations execute in configured sandboxes, not the
  API process.
- Runtime coverage does not imply control over actions performed outside the
  Conduct run.

Every Guard API endpoint continues to enforce authentication and workspace
scope at the resource layer. No upstream caller, MCP server, hook, or internal
service is trusted merely because of its transport.

Rule capability claims must use the versioned enforcement contract and name
each surface as `hard`, `conditional`, `advisory`, or `not_supported`.

## Alternatives considered

### Treat the proxy as the universal enforcement boundary

Rejected because raw LLM requests do not contain every local tool action, file
path, or host event.

### Treat hooks as universal enforcement

Rejected because hooks depend on installation and host support and cannot
contain actions outside their process boundary.

### Treat MCP as trusted internal transport

Rejected because MCP adds no authentication or authorization guarantee and a
cooperative agent can omit the call.

### Publish one global enforced/instructed label

Rejected because the same rule can be hard on one surface and unsupported on
another.

## Consequences

### Positive

- Product and compliance claims are tied to observable enforcement points.
- Unsupported matcher shapes are visible rather than silently overclaimed.
- New surfaces can be added without redefining existing guarantees.
- Security review can distinguish routing, installation, invocation, and
  sandbox dependencies.

### Negative

- Policy metadata and UI are more complex than one global status.
- Consumers must preserve surface-specific matcher semantics.
- Coverage gaps remain visible even when another surface enforces a similar
  rule.

## Implementation evidence

- `apps/api/app/modules/guard/enforcement.py`
- `apps/api/app/modules/guard/coverage.py`
- `apps/api/app/modules/guard/routers/proxy.py`
- `apps/api/app/modules/guard/routers/policies.py`
- `apps/api/app/modules/guard/routers/mcp.py`
- `packages/conduct-cli/src/conduct_cli/hooks/pretooluse.py`
- `docs/modules/conductguard/enforcement_coverage.generated.md`

## Follow-up triggers

Revisit this decision if Conduct introduces an operating-system enforcement
agent, mandatory network egress control, or a host platform that guarantees
non-bypassable tool interception.
