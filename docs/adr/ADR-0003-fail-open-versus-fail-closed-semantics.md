---
status: accepted
date: 2026-07-30
decision-makers:
  - Conduct engineering
---

# ADR-0003: Fail-open versus fail-closed semantics

## Context

Guard participates in interactive developer workflows, LLM requests, MCP
checks, and automated playbook execution. A policy engine or network failure
creates a conflict between security and availability.

Applying one failure behavior everywhere is unsafe: silently forwarding an
unauthenticated LLM request is unacceptable, while some workspaces may
explicitly accept reduced enforcement during a temporary hook outage.

## Decision

Conduct is fail-closed by default for authentication failures and policy
evaluation uncertainty. Fail-open behavior is permitted only as an explicit,
workspace-controlled availability choice on supported surfaces.

### Authentication and workspace resolution

- Unknown, invalid, expired, or unscoped identity never reaches the protected
  resource.
- Authentication failures are always closed and cannot be changed by workspace
  configuration.

### Proxy

- The proxy never forwards when caller authentication fails.
- Policy computation errors follow `deny_on_error`, which defaults to `true`.
- If a workspace explicitly disables `deny_on_error`, the proxy may forward
  after recording the engine error.
- Vendor or configured-upstream failures are returned as errors; they are not
  converted into successful Guard decisions.

### Hook and daemon

- `fail_mode` controls behavior when the hook cannot obtain or evaluate policy.
- The default is `fail_closed`.
- `fail_open` is an explicit availability tradeoff and must remain visible in
  workspace settings and audit evidence.
- A valid policy decision still follows its configured action.

### MCP and runtime

- Policy evaluation errors follow the workspace `deny_on_error` setting.
- The default is closed.
- MCP remains cooperative even when policy evaluation succeeds; its transport
  does not make enforcement non-bypassable.
- Runtime policy bootstrap fails the run when closed mode cannot load policy.

### Advisory mode

`advisory_mode` is not a failure fallback. It is an explicit operating mode in
which matched actions are audited instead of blocked. Verification and evidence
must report advisory behavior honestly rather than counting it as prevention.

Failure-mode configuration must not alter authentication requirements,
workspace isolation, or tamper-evident audit behavior.

## Alternatives considered

### Always fail open

Rejected because Guard would create a success-shaped path during exactly the
conditions when policy state is unknown.

### Always fail closed with no override

Rejected because some developer workflows require an explicit business
continuity option and can accept the documented risk.

### Infer fail behavior from rule action

Rejected because a rule action describes a successful policy evaluation, not
what to do when policy cannot be evaluated.

### Treat advisory mode as fail-open

Rejected because advisory mode is intentional policy behavior and must not be
confused with an enforcement outage.

## Consequences

### Positive

- Secure defaults protect unknown identities and uncertain policy state.
- Availability exceptions are explicit and workspace-scoped.
- Verification can distinguish configured advisory behavior from bypass.
- Each surface exposes the operational dependency behind its guarantee.

### Negative

- Closed mode can interrupt development or automation during a Guard outage.
- Supporting both modes increases testing and operational complexity.
- A workspace that chooses fail-open accepts a measurable enforcement gap.

## Implementation evidence

- `apps/api/app/modules/guard/models.py` (`GuardConfig`)
- `apps/api/app/modules/guard/routers/proxy.py`
- `apps/api/app/modules/guard/routers/mcp.py`
- `apps/api/app/modules/guard/routers/policies.py`
- `apps/api/app/runtime/executor.py`
- `packages/conduct-cli/src/conduct_cli/hooks/pretooluse.py`
- `apps/api/app/modules/guard/test_battery.py`

## Follow-up triggers

Revisit this decision when Conduct can provide a highly available local policy
decision cache with signed expiry, or when a compliance profile requires
non-configurable closed behavior.
