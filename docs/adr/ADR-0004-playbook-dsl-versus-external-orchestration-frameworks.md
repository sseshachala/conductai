---
status: accepted
date: 2026-07-30
decision-makers:
  - Conduct engineering
---

# ADR-0004: Playbook DSL versus external orchestration frameworks

## Context

Conduct needs reusable automations that combine deterministic integrations,
LLM reasoning, approvals, memory, policy checks, sandboxed execution, cleanup,
and durable run history. Playbooks must be installable, reviewable, versioned,
and observable across multiple tenants.

General-purpose agent frameworks such as LangGraph can execute graphs, but
adopting one as Conduct's source of truth would expose framework-specific
objects instead of a stable product contract and would not remove the need for
Conduct's authentication, credentials, policy, persistence, marketplace, and
run-observability layers.

## Decision

Conduct will own a declarative YAML playbook DSL, compiler, and runtime.

YAML is the canonical portable artifact. The canvas is an editor and
visualization of that artifact, not a separate execution definition.

The DSL defines product-level block types such as:

- brain;
- tool and API integration;
- logic;
- approval;
- memory;
- output;
- guard;
- MCP;
- trigger;
- cleanup.

The loader validates YAML, resolves base playbooks and `$use` inheritance, and
produces a graph. The compiler creates publish-time artifacts such as brain
block prompts. The runtime executes the persisted graph, resolves state
references, records events and traces, enforces budgets, and dispatches
arbitrary code to configured sandboxes.

External orchestration and agent frameworks may be invoked behind MCP, API,
tool, or custom block adapters. They are integrations, not Conduct's persisted
workflow contract.

## Alternatives considered

### Use LangGraph or another agent framework as the core workflow model

Rejected because it couples stored workflows and marketplace artifacts to an
external runtime API while leaving Conduct-specific governance and
multi-tenant concerns unsolved.

### Store only the visual canvas graph

Rejected because a UI-specific graph is harder to review, package, diff, and
maintain as a stable public artifact.

### Use arbitrary Python as the workflow definition

Rejected because unrestricted code weakens static validation, portability,
policy inspection, and safe marketplace distribution.

### Make YAML a generated export only

Rejected because generated artifacts become secondary, drift-prone
representations instead of the reviewable source of truth.

## Consequences

### Positive

- Playbooks are diffable, reviewable, packageable, and reversible.
- Conduct controls schema evolution and stable block semantics.
- Governance, identity, credentials, budgets, traces, and sandbox boundaries
  are integrated into execution.
- The same artifact supports built-in playbooks, customer workflows, and the
  marketplace.

### Negative

- Conduct owns compiler, runtime, schema migration, and debugging complexity.
- External framework features require adapters instead of being inherited
  automatically.
- The DSL is intentionally less general than arbitrary code.
- Backward compatibility becomes a Conduct responsibility.

## Implementation evidence

- `apps/api/app/dsl/schema.py`
- `apps/api/app/dsl/loader.py`
- `apps/api/app/compiler/compiler.py`
- `apps/api/app/runtime/dag_runner.py`
- `apps/api/app/runtime/executor.py`
- `apps/api/app/runtime/blocks/`
- `apps/api/playbooks/`
- `apps/api/tests/test_dsl_loader.py`
- `apps/api/tests/test_dsl_graph_to_workflow.py`

## Follow-up triggers

Revisit this decision if an external framework can preserve Conduct's stable
YAML contract, multi-tenant security model, durable run semantics, and block
portability while materially reducing runtime complexity.
