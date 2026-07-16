# ACD-0005 — Scoped Discontinuous Agent Memory

**Status:** Accepted  
**Date:** July 11, 2026  
**Deciders:** Sudhendra Seshachala  
**Patent reference:** Claim 3 — Scoped Discontinuous Memory

---

## Context

Existing AI agent frameworks treat every session as stateless. An agent that investigated a security vulnerability in a repository on Monday starts from zero on Tuesday — no memory of what it found, what it tried, or what it concluded.

This creates three problems:

1. **Redundant work** — the agent re-investigates what it already investigated
2. **Lost context** — findings from prior sessions are not available to inform current decisions
3. **Persistence attack surface** — if memory is not governed, an attacker can plant instructions in a knowledge base that persist across sessions and activate in future agent invocations (RAG-dependent persistence in the Promptware Kill Chain)

The naive solution — a shared vector store with no scoping — solves problems 1 and 2 but makes problem 3 worse. An ungoverned shared memory is an attack surface.

---

## Decision

ConductAI implements a **scoped discontinuous agent memory** system:

**Three-level scope hierarchy:**
```
repository_id  (broadest — shared across all workflows in a repo)
    └── workflow_id  (mid-level — shared across sessions in a workflow)
            └── session_id  (narrowest — private to one session)
```

**Recall operation:**
- Issued before agent execution
- Retrieves semantically ranked prior agent outcome entries
- Scope key determines which entries are visible
- Cross-session recall is permitted within `repository_id` and `workflow_id` scopes
- Does not require session continuity — a new session can recall entries from a terminated prior session

**Record operation:**
- Issued after agent execution
- Persists a structured outcome entry under the specified scope
- Entry includes: outcome summary, tool calls made, files touched, policy decisions encountered, timestamp

**Governance invariant:** Recall operations are governed by policy. An agent running in a finance workflow cannot recall entries recorded by an agent running in a developer workflow — even within the same repository. Scope boundaries are enforced by the policy engine, not by the memory store alone.

**Promptware defense:** The scope boundary is the defense against RAG-dependent persistence attacks. An attacker who plants instructions in one memory scope cannot have them recalled by an agent operating in a different scope. Policy governs which scopes an agent can query.

---

## Consequences

**Positive:**
- Agents accumulate context across sessions without requiring session continuity
- Redundant investigation eliminated — agents recall prior findings
- Scope boundaries prevent cross-workflow contamination
- Governed recall closes the RAG-dependent persistence attack vector
- Session-scope memory provides private working space per invocation

**Negative:**
- Memory store grows over time — requires archival and pruning policy
- Scope key assignment requires workflow identity to be established at session start
- Semantic search quality depends on embedding model quality

**Mitigations:**
- Memory store pruned by configurable TTL per scope level
- Workflow identity established by `conduct init` and carried in the session record
- Embedding model is pluggable — defaults to a lightweight local model, can be upgraded

---

## Alternatives Considered

**Stateless sessions (status quo):** No memory between sessions. Rejected — redundant work, lost context, poor agent quality on multi-session tasks.

**Shared unscoped vector store:** All agents share a single memory namespace. Rejected — creates cross-workflow contamination and a RAG-dependent persistence attack surface.

**File-based context passing:** Agents write findings to files that subsequent agents read. Rejected — not governed, not semantic, no access control, creates a persistence attack surface at the filesystem layer.

**Session continuity requirement:** Memory only accessible within a continuous session. Rejected — defeats the purpose. Most valuable context (prior vulnerability findings, architectural decisions) comes from prior sessions that have terminated.
