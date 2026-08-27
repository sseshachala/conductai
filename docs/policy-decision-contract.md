# Policy decision contract

## Purpose

This document defines the canonical decision contract for Conduct guard evaluations across proxy and MCP surfaces.

Canonical decision names in this document:

- `allow`
- `warn`
- `block`
- `require_approval`

Implementation note: persisted/event values may appear as `allowed`, `warned`, `blocked`, `audited`, plus approval request state records. Treat those as storage/transport variants of the canonical outcomes.

## Canonical outcomes and semantics

| Canonical outcome | Semantics | Expected caller behavior |
| --- | --- | --- |
| `allow` | No blocking condition matched (or prior approval already granted). | Proceed with requested action. |
| `warn` | A policy concern matched but action is not hard-blocked. | Proceed, but surface warning inline and record audit event. |
| `block` | Policy denies the action or fail-closed behavior denies on error. | Stop action and return policy reason. |
| `require_approval` | Action is gated pending approvals/HITL decision. | Pause/hold action; poll or resume only after approval outcome. |

## Minimum decision response schema

A decision response payload must include at least these fields (or equivalents in the transport shape):

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `decision_id` | string | yes | Stable identifier for this decision event. |
| `action` | enum | yes | One of `allow`, `warn`, `block`, `require_approval`. |
| `code` | string | yes | Machine-readable reason code (rule id or system code). |
| `reason` | string | yes | Human-readable summary. |
| `matched_rules` | array | yes | Ordered list of matched rule references (may be empty for allow). |
| `timestamp` | RFC3339 timestamp | yes | Decision time in UTC. |
| `workspace_id` | string | yes | Workspace context identifier. |
| `subject` | object | yes | Actor identity context (user/tool/session identifiers available at call time). |
| `context` | object | yes | Action context (surface, tool name, prompt/tool metadata as available). |

Recommended additional fields:

- `policy_hash` (policy version hash at decision time).
- `audit` (`prev_hash`, `entry_hash` once persisted).
- `approval` object (`approval_id`, `status`, `timeout_at`) when `require_approval` applies.

## Determinism and evaluation expectations

- Given the same policy set, normalized input, and config mode, evaluation should return the same canonical action.
- Rule evaluation uses explicit precedence (most restrictive wins).
- Restrictiveness order is:

`block` > `require_approval` > `warn` > `allow`

- When multiple rules match with same action, choose deterministic tie-breakers (for example stable rule ordering or canonical rule id ordering).
- If policy/version data is unavailable, behavior is controlled by fail mode configuration (see below).

## Conflict handling

- If one rule allows and another blocks, `block` wins.
- If no block exists but one rule requires approval, `require_approval` wins over warn/allow.
- `warn` is advisory and does not override `block` or `require_approval`.
- Explicit bypass/exception rules must be represented as policy logic, not ad-hoc runtime overrides.

## Failure behavior by surface

### MCP (`guard_check`)

- Decision engine errors default to fail-closed behavior (`block`) unless operator config explicitly enables fail-open behavior for that failure class.
- `require_approval` returns a pending marker/state and the caller must not execute until resolution.
- Timeout behavior for approval requests must resolve to a terminal deny/block unless explicitly configured otherwise.

### Proxy (`/proxy/{provider}/...`)

- Pre-call enforcement evaluates before forwarding upstream.
- Policy-eval or enforcement errors default fail-closed for protected actions unless operator-configured fail-open mode is enabled.
- Timeout handling must be explicit:
  - Guard decision timeout: apply configured fail behavior.
  - Upstream provider timeout after an `allow`: return transport/provider error without mutating decision action.

## Operator-configurable modes

Expected operator controls include:

- `fail_closed` (deny when enforcement is uncertain).
- `fail_open` (allow with audit/warn when configured to prioritize availability).
- `advisory`/warn-only modes for rollout.

Operators should document selected mode per environment and test both enforcement surfaces after any config change.
