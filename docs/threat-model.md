# Threat model

## Purpose

This threat model documents how Conduct AI enforces policy across two surfaces using one policy engine:

1. LLM proxy requests (`/proxy/{provider}/v1/*` family, with provider-specific handlers).
2. MCP-fronted tool calls where `guard_check` is called before execution.

Conduct is an enforcement layer, not an LLM router.

## System context and protected assets

Primary assets:

- Policy definitions and active policy packs.
- Policy decision records and hash-chained audit log (`prev_hash`, `entry_hash`).
- Credentials/secrets used for provider access or tool/runtime access.
- Provider request/response content routed through proxy.
- MCP tool-call metadata (`tool_name`, `tool_input`, decision, rule ids).
- Approval/HITL state for gated actions.

## Trust boundaries and data flows

### Surface A: LLM proxy (`/proxy/{provider}/v1/*`)

1. Client/tool sends model request to Conduct proxy.
2. Conduct authenticates identity and resolves workspace context.
3. Proxy normalizes request context and evaluates policy.
4. Decision is applied (`allow`, `warn`, `block`, `require_approval` behavior mapped per surface).
5. Audit event is appended with hash-chain links.
6. If allowed, request is forwarded upstream to provider and response is returned.

Boundary notes:

- Boundary between caller and Conduct auth/policy decisioning.
- Boundary between Conduct and upstream model provider.
- Boundary between decision/audit persistence and read/reporting paths.

### Surface B: MCP fronting (`guard_check` before tool calls)

1. Agent calls Conduct MCP tool `guard_check` with intended action context.
2. Conduct authenticates caller and loads workspace policy set.
3. Policy engine evaluates intent and returns decision outcome.
4. For approval-gated rules, approvals/HITL workflow is created or resumed.
5. Caller either executes, waits for approval, or stops.
6. Conduct appends decision event to the hash-chained audit log.

Boundary notes:

- Boundary between agent runtime and Conduct MCP endpoint.
- Boundary between Conduct and downstream MCP tools/servers (tool outputs are untrusted input for future turns).
- Boundary between approval actors (human approver) and automated execution.

## Attacker goals and representative threats

### Prompt injection and tool-output injection

Goal: force unsafe behavior or policy evasion using crafted prompt/tool content.

### Policy bypass

Goal: execute tool/network actions without `guard_check`, or exploit mismatched enforcement paths.

### Audit tampering

Goal: delete, reorder, or alter decision records to hide actions.

### Approval spoofing/replay

Goal: fake an approval, reuse stale approval state, or race timeout transitions.

### Secret exfiltration

Goal: extract credentials or sensitive content via prompts, tool outputs, logs, or provider egress.

### Denial of service (DoS)

Goal: overload proxy/MCP endpoints or dependent components to degrade enforcement availability.

## Explicit non-goals

Conduct does **not** provide router responsibilities:

- Provider rotation.
- Model fallback selection.
- Cost-based model tier routing.
- API-key load balancing.

Conduct also does not claim to secure third-party providers or external MCP tools beyond Conduct’s own enforcement boundary.

## Mitigations

- Unified policy engine across proxy and MCP `guard_check` flows.
- Fail-closed defaults for decision errors on guarded paths, with operator-configurable fail behavior.
- Approvals/HITL flow for gated high-risk actions.
- Hash-chained audit log for tamper-evident decision history.
- Workspace-scoped identity and authorization checks at API/resource boundaries.
- Rule-based block/warn controls and advisory modes for phased rollout.

## Residual risks

- Bypass risk if clients/tools skip `guard_check` integration.
- Model/provider behavior remains outside Conduct’s direct control.
- Downstream tool output may still influence agent behavior after an allowed step.
- Operator misconfiguration (fail-open modes, overly broad allow rules) can reduce protection.
- Availability attacks against Conduct dependencies can still impact enforcement timeliness.

## Security review checklist (operator)

- [ ] Verify all agent/tool integrations call `guard_check` before sensitive actions.
- [ ] Keep policies and packs current for your threat model.
- [ ] Test approval/HITL timeout and rejection paths.
- [ ] Periodically verify hash-chain integrity from exported logs.
- [ ] Document chosen fail-open/fail-closed settings for proxy and MCP usage.
