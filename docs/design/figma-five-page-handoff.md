# ConductAI five-page Figma implementation handoff

## Source files

- Repository: `sseshachala/conductai`
- Figma: https://www.figma.com/design/UktEyWiEqTWrkmJUaF2aco
- Figma pages:
  1. `10 Website Port / Home`
  2. `11 Website Port / Guard`
  3. `12 Website Port / Registry`
  4. `13 Website Port / Evidence`
  5. `14 Website Port / MCP`

## Implementation instruction

> Implement the five `Website Port` frames faithfully. Preserve existing website copy and positioning; use the Figma file only for visual design, layout, components, color, and responsive behavior.

## Source-of-truth rules

1. The current website and repository remain the source of truth for product positioning, copy, capability status, claims, routes, and links.
2. Do not reinterpret or rewrite the positioning while implementing the visual design.
3. Preserve the existing core language, including:
   - “One policy across your AI agent stack.”
   - “Allow. Approve. Block. Prove.”
   - “Runtime policy for every AI agent.”
   - Agent Discovery as the primary conversion path.
   - Hash-chained evidence and explicit `SHIPPED`, `PREVIEW`, and `PLANNED` labels.
4. If Figma copy conflicts with current repository copy, use the repository copy.
5. Do not introduce customer logos, metrics, certifications, deployment claims, integrations, or product capabilities that are not supported by the repository.
6. Keep native platform controls in place; ConductAI adds a common runtime policy and evidence model across the agent stack.

## Visual implementation

- Reuse shared React components for navigation, buttons, cards, decision states, evidence receipts, deployment-status labels, CTA bands, and the footer.
- Map Figma colors and spacing to shared CSS variables or Tailwind theme tokens.
- Preserve the semantic color model:
  - Indigo: governance, authority, and primary actions.
  - Cyan: live runtime activity and evidence links.
  - Green: `ALLOW` and verified/shipped states.
  - Amber: `APPROVE` and preview states.
  - Red: `BLOCK`.
- Implement responsive desktop, tablet, and mobile layouts.
- Product interfaces shown in Figma should be implemented as structured HTML/CSS, not flattened screenshots.
- Retain accessibility, focus states, keyboard navigation, semantic headings, and reduced-motion support.

## Page mapping

| Figma page | Website route | Purpose |
|---|---|---|
| `10 Website Port / Home` | `/` | Primary platform narrative and Agent Discovery conversion |
| `11 Website Port / Guard` | `/guard` | Runtime enforcement, decisions, policies, evidence, deployment, and boundaries |
| `12 Website Port / Registry` | `/registry` | Compliance and automation pack catalog |
| `13 Website Port / Evidence` | `/evidence` | Decision receipts, replay, integrity, retention, compliance mapping, and Lens |
| `14 Website Port / MCP` | Existing MCP product route | Guarded MCP tool invocation and evidence flow |

## Acceptance criteria

- All five routes visually match their corresponding Figma frames.
- Existing copy and positioning remain unchanged unless the repository has a newer source-of-truth version.
- Shared elements are componentized rather than duplicated.
- Pages are responsive and usable at common mobile, tablet, and desktop widths.
- Decision states and capability-status labels retain their precise semantic meaning.
- No unsupported marketing claims are introduced.
