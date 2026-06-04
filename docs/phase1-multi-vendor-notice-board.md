# Phase 1 Notice Board: Multi-Vendor Model Execution

Status: Completed
Owner: Engineering
Last updated: 2026-06-04

## Goal
Ship Phase 1 multi-vendor model execution support (Anthropic + OpenAI) for Brain and Memory paths with backward compatibility.

## Scope
- In scope:
  - Runtime provider-agnostic execution via existing LLM client abstraction
  - OpenAI LLM adapter implementation
  - Brain provider/model routing and executor wiring
  - Memory path provider/model alignment (embedding defaults/fallbacks)
  - Config/env defaults and smoke validation
- Out of scope:
  - Guard cross-tool governance unification (Phase 2)
  - Copilot deep local call interception

## Task Board
- [x] Task 1: Implement OpenAI LLM adapter in runtime client layer
- [x] Task 2: Add provider-aware selection for Brain blocks
- [x] Task 3: Wire Memory path provider/model defaults and fallback behavior
- [x] Task 4: Extend model router to return provider + model + reason
- [x] Task 5: Update executor to instantiate selected provider client (remove direct Anthropic construction)
- [x] Task 6: Add/verify config and env support for OpenAI defaults
- [x] Task 7: Run smoke tests and compile/type checks

## Checkpoint After Tasks 1-5
Pass criteria:
- Brain execution goes through provider-agnostic LLM client path.
- Anthropic remains default and behavior-compatible.
- OpenAI path is wired and selectable (not forced globally).
- No regressions in existing Brain flows.

Decision:
- Result: pass.
- Tasks 6-7 completed in the same session.

## One-Session Feasibility
Can this be done in one session? Yes, if scoped to Phase 1 only and executed with a checkpoint after Tasks 1-5.

Risk notes:
- Medium: tool-call format differences between Anthropic and OpenAI in agentic loops.
- Medium: subtle routing behavior drift if defaults are changed too early.

Mitigations:
- Keep Anthropic as default until post-checkpoint validation passes.
- Add focused smoke tests for Brain agentic + non-agentic and Memory embedding paths.

## Definition of Done (Phase 1)
- Anthropic and OpenAI both supported in execution layer.
- Brain can select provider/model deterministically.
- Memory path works with intended provider defaults and fallback behavior.
- Existing Anthropic workflows remain stable.
- Smoke checks pass and changes are documented.

## Notes
- Phase 2 (Guard governance/observability across tools) is tracked separately.
