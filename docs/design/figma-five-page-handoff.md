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

## Exported assets

- Design tokens: [`docs/design/figma/tokens.json`](figma/tokens.json)
- Resolved CSS variables: [`docs/design/figma/tokens.css`](figma/tokens.css)
- Route and Figma-node manifest: [`docs/design/figma/manifest.json`](figma/manifest.json)
- PNG references:
  - [Home](figma/exports/home.png)
  - [Guard](figma/exports/guard.png)
  - [Registry](figma/exports/registry.png)
  - [Evidence](figma/exports/evidence.png)
  - [MCP](figma/exports/mcp.png)

The PNGs are compact full-page implementation references. Use the live Figma frames for precise inspection of typography, spacing, layers, and component details.

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
7. Any Figma panel or shared React component that depicts an in-product surface (Guard, Lens, Run, Registry, Evidence receipt, Slack approval, MCP flow) MUST be implemented from the matching screenshot in [`docs/design/figma/screenshots/`](figma/screenshots/), not redrawn from the mockup. Redrawing produces AI-looking mockups; real screenshots read as product. This rule applies site-wide, not only to the five Figma pages. See the Site-wide scope section for the four shared components and six consuming routes.
8. The MCP hero panel is a **diagram**, not a screenshot — no fake product-UI shell. Draw as SVG showing real client names (Claude Desktop, ChatGPT, Cursor) routing through ConductAI to an MCP server.

## Site-wide scope (beyond the five Figma pages)

The AI-slop problem is not limited to the five Figma frames. The same drawn "product UI" panels are used across the whole marketing site through four shared React components under `apps/web/src/components/marketing/facelift/`. Fixing those four components fixes every consuming route.

### Facelift components to swap

| Component | Path | Real-screenshot replacement |
|---|---|---|
| `DecisionCard` | `apps/web/src/components/marketing/facelift/DecisionCard.tsx` | Real Guard activity-feed row or decision-detail card |
| `PolicySnippet` | `apps/web/src/components/marketing/facelift/PolicySnippet.tsx` | Real policy from `/theguard/policies/{id}`, syntax-highlighted from disk |
| `EvidenceReceipt` | `apps/web/src/components/marketing/facelift/EvidenceReceipt.tsx` | Real receipt from `/theguard/decisions/{id}` |
| `AgentSurfaceStrip` | `apps/web/src/components/marketing/facelift/AgentSurfaceStrip.tsx` | Real integration-status row from `/settings/integrations` |
| `ActivityRow` | `apps/web/src/components/marketing/facelift/ActivityRow.tsx` | Real Guard activity-feed row (compact) from `/theguard/activity` |
| `CompliancePackCard` | `apps/web/src/components/marketing/facelift/CompliancePackCard.tsx` | Real Registry pack tile from `/registry` |
| `LensTranscript` | `apps/web/src/components/marketing/facelift/LensTranscript.tsx` | Real Lens query + result table from `/lens` |

All facelift components accept optional `imageSrc` and `imageAlt` props. When `imageSrc` is set, the drawn shell is bypassed and the screenshot is rendered inside the same border/rounded/shadow footprint. Consumers can adopt real screenshots per-route without any component-code change.

### Consuming routes (auto-updated when the components are fixed)

- `/guard` — hero + decisions row + policy + receipt + surfaces
- `/evidence` — hero receipt
- `/mcp-gateway` — decision cards in MCP flow
- `/solutions/action-governance` — decision cards for refund / deploy / secret-read stories
- `/solutions/engineering-leaders` — surface strip + decision cards
- `/solutions/security-compliance` — receipt

### Routes with no drawn product UI (skip)

`about`, `benchmark`, `blog`, `book-demo`, `compare`, `deployment`, `discovery`, `docs`, `eval`, `frameworks`, `open-source`, `partners`, `pricing`, `privacy`, `router`, `sdd`, `team-os`, `terms`, `token-guardrails`, `tools`, `use-cases`, `what-is-conduct-ai`, `security` (uses tabular threat-model rows, not drawn UI).

### Not drawn product UI — keep as-is

- `ThreatModelRow` — tabular teaching material, not a screen.
- `CapabilityStatus` — status legend, not a screen.
- `PlaybookTile` in `/registry` — architectural block-sequence tiles, not screens.

## Screenshot inventory (five Figma pages)

The mockup PNGs under `figma/exports/` depict several in-product surfaces as drawn UI. Those must be replaced during implementation with real screenshots captured from the running product. Marketing tiles (feature grids, deployment cards, compliance tag rows) stay as HTML/CSS components — only in-product surfaces need real captures.

Save all captures to `docs/design/figma/screenshots/` at 1440×900 desktop and 375×812 mobile, PNG, from the seeded demo workspace.

| Page | Drawn panel in mockup | Replace with real screenshot | Capture source |
|---|---|---|---|
| Home | Hero right-side dark card (fake actor / action / decision) | Lens `run_workflow` confirm card | `/lens` — send `run <workflow>`, capture the Confirm/Cancel bubble |
| Home | "Know exactly what happened" right card (fake run summary) | Run detail page, Summary tab | `/runs/{id}` |
| Guard | Three-card row (ALLOW / APPROVE / BLOCK) with fake action names | Guard activity feed row | `/theguard/activity` — feed with mixed decisions |
| Guard | YAML policy block | Real policy in editor | `/theguard/policies/{id}` |
| Guard | Consequential-actions column (three rows) | Slack Guard-approval card | Slack — real `Guard approval required` message with Approve/Reject |
| Registry | Four compliance-pack cards (OWASP LLM Top 10, SOC 2, HIPAA, PCI DSS) | Registry pack grid | `/registry` |
| Registry | "No automation packs found" | Keep as-is — honest empty state | — |
| Evidence | Hero right-side dark card (fake receipt) | Decision receipt page | `/theguard/decisions/{id}` — a full BLOCK receipt |
| Evidence | Bottom "Show me every block against payments…" quote card | Lens transcript answering that exact query | `/lens` — query = "show me every block against payments this month" |
| MCP | Hero right-side dark card (fake client router) | **Diagram (SVG)**, not a screenshot | draw client → ConductAI → MCP server |
| MCP | JSON tool-call block | MCP protocol trace | MCP inspector or Lens tool trace |

Marketing tiles that stay as HTML/CSS components (do not screenshot):

- Home: "Five agent tools shouldn't require five policy models" cards; "Allow. Approve. Block. Prove." decision quad; "Write the rule once" surface picker.
- Guard: "Deploy Guard where your controls need to live" (SaaS / Docker / Kubernetes / Air-gapped); "One policy where your stack isn't one vendor's" boundary cards.
- Registry: "Every pack runs under Guard enforcement" four-step row.
- Evidence: "What each receipt contains" six-card grid; "Compliance mapping" tag row.
- MCP: "One policy across MCP clients" client tiles; "Control before the tool executes" decision cards.

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
- Do not use emoji as interface icons (for example, 🔐, 🏥, or 💳). Use purpose-built SVG icons with consistent stroke, sizing, and accessible labels.
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

## Source implementation

The Figma visual system is implemented through the scoped `marketing-v2`
theme in `apps/web/src/app/globals.css`. The home page and every route in
the shared marketing layout inherit it automatically, including future
marketing pages. Authenticated console routes remain unaffected.
- Every in-product surface in the Screenshot inventory table is implemented from a real capture in `docs/design/figma/screenshots/`, not redrawn from the mockup.
- MCP hero is an SVG diagram, not a screenshot of a fake UI shell.
