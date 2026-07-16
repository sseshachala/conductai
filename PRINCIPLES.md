# ConductAI Architectural Principles

These are the invariants that define ConductAI's architecture. No change to the codebase should violate them. If a proposed change requires violating a principle — the principle must be explicitly reconsidered and this document updated before the change is made.

---

## P1 — Policy is evaluated before execution, never after

Every agent action is intercepted synchronously before it executes. The governance decision — allow, warn, or block — is returned before the tool call proceeds. There is no post-hoc review of actions that have already executed.

*Rationale: Post-hoc review is not governance. It is incident response. Governance must prevent harmful actions, not document them.*

---

## P2 — Provider-specific formats never enter the governance layer

Vendor adapters translate provider-specific callback formats into normalized tool call representations at the boundary. The policy engine, memory subsystem, and audit system only ever process normalized representations. No provider format leaks past the adapter layer.

*Rationale: Coupling governance logic to a specific provider's wire format creates a dependency that breaks whenever the provider changes their API. The governance layer must be provider-neutral.*

---

## P3 — Every action produces an audit event — no silent operations

Every governance decision, every tool call evaluation, every memory recall and record, every policy resync — all produce an audit event written to the hash-chained local journal. There are no silent operations in the enforcement path.

*Rationale: Governance without auditability is a policy document, not a control. Every decision must be traceable.*

---

## P4 — Tokens are short-lived and scoped — never persistent and broad

Workspace member tokens are issued per developer per workspace with a configured expiry. No persistent credentials. No broad-scope tokens. Token scope is the minimum required for the agent's assigned role and workflow.

*Rationale: Long-lived broad-scope credentials are the primary blast radius amplifier when an agent is compromised. Short-lived scoped tokens limit the damage window.*

---

## P5 — Guard decisions are synchronous — agents cannot proceed without a response

The pre-tool-use hook blocks execution until a governance decision is returned. There is no timeout-and-proceed fallback. If the governance layer is unreachable, the default decision is block.

*Rationale: A governance layer that fails open provides no governance. Fail-closed is the only safe default.*

---

## P6 — The audit log is append-only and hash-chained — decisions are never modified

Journal entries are written with a cryptographic hash linking each entry to its predecessor. No entry can be modified or deleted without breaking the chain. The chain is recomputable by a third party without access to ConductAI infrastructure.

*Rationale: An audit log that can be modified is not an audit log. Tamper-evidence must be cryptographic, not procedural.*

---

## P7 — Scope boundaries are enforced by policy, not by the memory store alone

Memory recall operations are subject to policy evaluation. An agent cannot recall entries from a scope it is not authorized to access, regardless of what the memory store contains. The memory store does not enforce access control — the policy engine does.

*Rationale: Delegating access control to the data store creates a single point of bypass. Policy enforcement must be in the governance layer.*

---

## P8 — One source of truth for policy — the central policy service

Policy rules live in one place. Policy changes are made in the central policy service and propagate to all governed agents within a bounded time window. No local overrides. No per-machine policy files. No agent-side policy definitions.

*Rationale: Distributed policy definitions create inconsistency. A policy that applies to some agents but not others is not a policy — it is a suggestion.*
