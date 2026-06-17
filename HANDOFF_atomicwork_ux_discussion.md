# Handoff: Atomicwork vs Conduct UX Discussion
**Date:** 2026-06-17  
**Context:** Strategic product discussion — competitive UX analysis, YAML generation limits, and chat-first entry point opportunity

---

## What Was Discussed

### Atomicwork Observation
Atomicwork (ITSM platform) uses a **split-pane chat-first UX**:
- **Left panel:** "Ask Atom" — natural language workflow description
- **Right panel:** Visual step chain — read-only confirmation receipt before publishing
- No drag-and-drop. Atom generates the workflow, user approves it.
- Same ReactFlow framework as Conduct's canvas.
- Target: IT ops, non-technical buyers (laptop provisioning, onboarding, account setup).

### The Core Insight
The canvas is the **receipt**, not the workspace. The conversation is the UX. This pattern is becoming table stakes across all new AI tools.

---

## Conduct vs Atomicwork — Structural Comparison

| Dimension | Atomicwork | Conduct |
|---|---|---|
| Entry point | Chat → generate | Canvas → configure |
| Workflow primitives | Simple (assign, create, notify) | Complex (brain blocks, turn budgets, sandbox, guard) |
| LLM generation | Works reliably | Fails — hallucinates block names, bad chaining |
| Target buyer | IT manager, non-technical | Eng platform team, developer-adjacent |
| Governance depth | None | ConductGuard, MCP enforcement, policies |
| Distribution | Top-down (ITSM suite) | Bottom-up (CLI → developer → CISO) |

**Not a direct threat.** Different buyer, different depth.

---

## Why Conduct Doesn't Generate YAML (and shouldn't yet)

Previous attempt: NL prompt → YAML generation produced wrong block names, bad chaining, hallucinated credentials. Conduct's block surface is too rich for reliable generation today.

**Current answer:** Pre-canned playbooks (22 today). "Install and run in 60 seconds" beats "describe it and hope the AI got it right."

---

## Convergence Opportunity — Chat as Finder, Not Builder

Replace the blank canvas entry point with a **chat finder**:
- "Find me an incident response playbook" → semantic match → install
- Chat discovers, canvas configures
- Lower LLM risk than generation, same UX feel as Atomicwork's left panel
- When library hits 50+ playbooks, discovery becomes the real problem anyway

This is the right next UX step — not YAML generation.

---

## Broader Governance Framing (LinkedIn post)

Discussed audit trail vs feedback trail:
- **Audit trail** = backward-looking (what ran, who approved, what model)
- **Feedback trail** = forward-looking (did reality match assumption? who corrected it?)
- ConductGuard owns the audit layer. Scorecard + DORA = the feedback trail gap.
- Post angle: "Organizations that win with AI won't be the ones that automate fastest — they'll be the ones that learn fastest from what their agents actually did."

---

## Files Created This Session
- `AGENT_SCAN_SPEC.md` — `conduct scan` product spec, Phase 1 scoped to ~11d
- `HANDOFF_atomicwork_ux_discussion.md` — this file
