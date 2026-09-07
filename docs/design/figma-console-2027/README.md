# ConductAI console — Figma implementation handoff

Source: [ConductAI Figma file](https://www.figma.com/design/UktEyWiEqTWrkmJUaF2aco)

This directory contains implementation references for the authenticated console extension. The five screens share one shell and are intended as reusable templates for the remaining console routes.

## Contents

- `figma-variables.json` — complete local Figma variable collections, modes, aliases, scopes, and code syntax.
- `tokens.css` — resolved CSS custom properties for light and dark modes.
- `manifest.json` — Figma node, route, and PNG mapping.
- `mockups/*.png` — 2× visual references for the five representative screens.

## Implementation contract

Implement the five console frames faithfully while preserving existing product terminology, real route behavior, metrics sources, and actions from the repository. Use the Figma file for visual design, layout, components, color, density, and responsive behavior.

Build one shared authenticated shell and derive other routes from these templates:

| Template | Representative frame |
| --- | --- |
| Operational overview | Dashboard |
| Analytics workspace | Runtime Governance |
| Management table | Guard Policies |
| Event + inspector | Activity & Evidence |
| Catalog | Registry |

## Non-negotiable rules

- No emoji as interface icons. Use purpose-built SVG icons.
- Do not replace implemented product copy or positioning with speculative claims.
- Preserve semantic decision colors: Allow = green, Approve = amber, Block = red.
- Preserve the dark navigation / light operational-canvas relationship.
- Treat all numbers and activity entries shown in PNGs as mock data unless backed by an existing API.
- Responsive implementation must be derived from the shared components rather than five independent fixed pages.
