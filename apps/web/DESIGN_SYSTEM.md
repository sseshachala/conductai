# Delegator Design System

A minimal, developer-focused design language. Stone neutrals as the base, indigo as the accent, semantic color per block type. Every decision optimises for clarity and trust — engineers need to read this UI like they read code: precise, scannable, no ambiguity.

---

## Foundations

### Color Palette

#### Base (all pages)
| Token | Tailwind | Hex | Usage |
|-------|----------|-----|-------|
| Background | `bg-stone-50` | `#FAFAF9` | Page background |
| Surface | `bg-white` | `#FFFFFF` | Cards, panels, canvas |
| Border | `border-stone-200` | `#E7E5E4` | Cards, dividers |
| Border strong | `border-stone-300` | `#D6D3D1` | Hover states |
| Text primary | `text-stone-900` | `#1C1917` | Headings, labels |
| Text secondary | `text-stone-500` | `#78716C` | Descriptions, meta |
| Text muted | `text-stone-400` | `#A8A29E` | Timestamps, counts |

#### Accent (interactions, selection)
| Token | Tailwind | Hex | Usage |
|-------|----------|-----|-------|
| Accent | `text-indigo-700` | `#4338CA` | Link hover, selected node ring |
| Accent ring | `ring-indigo-400` | `#818CF8` | Selected canvas node |
| Accent edge | stroke `#6366F1` | `#6366F1` | Selected React Flow edge |

#### Primary CTA
| State | Tailwind | Notes |
|-------|----------|-------|
| Default | `bg-stone-900 text-white` | Near-black, not pure black |
| Hover | `hover:bg-stone-700` | Lightens on hover |
| Disabled | `opacity-50 cursor-not-allowed` | |

#### Status colors (semantic only — never decorative)
| Status | Color | Tailwind |
|--------|-------|----------|
| Success | Emerald | `text-emerald-600 bg-emerald-50` |
| Warning | Amber | `text-amber-600 bg-amber-50` |
| Error | Red | `text-red-600 bg-red-50` |
| Info | Blue | `text-blue-600 bg-blue-50` |

---

### Block Type Colors

Each block type has a fixed semantic color. Never reuse these colors for non-block UI.

| Block | Background | Border | Label text |
|-------|-----------|--------|-----------|
| TRIGGER | `bg-blue-50` | `border-blue-200` | `text-blue-700` |
| BRAIN | `bg-purple-50` | `border-purple-300` | `text-purple-700` |
| TOOL | `bg-green-50` | `border-green-200` | `text-green-700` |
| LOGIC | `bg-gray-50` | `border-gray-200` | `text-gray-600` |
| MEMORY | `bg-amber-50` | `border-amber-200` | `text-amber-700` |
| APPROVAL | `bg-orange-50` | `border-orange-200` | `text-orange-700` |
| OUTPUT | `bg-rose-50` | `border-rose-200` | `text-rose-700` |
| CLEANUP | `bg-yellow-50` | `border-yellow-200` | `text-yellow-700` |

Source of truth: `apps/web/src/lib/block-types.ts` → `BLOCK_STYLES`

---

### Typography

| Role | Font | Size | Weight | Color |
|------|------|------|--------|-------|
| Page heading | Inter | `text-xl` (20px) | `font-semibold` | `text-stone-900` |
| Section heading | Inter | `text-base` (16px) | `font-medium` | `text-stone-900` |
| Body | Inter | `text-sm` (14px) | `font-normal` | `text-stone-700` |
| Label / meta | Inter | `text-xs` (12px) | `font-normal` | `text-stone-400/500` |
| Block type badge | Inter | `text-[8px]` | `font-bold` | block type color |
| Monospace (code, commands) | JetBrains Mono | `text-xs` | `font-normal` | `text-stone-600` |
| Eyebrow | Inter | `text-[10px]` | `font-bold uppercase tracking-widest` | `text-stone-400` |

---

### Spacing & Layout

| Pattern | Value |
|---------|-------|
| Page max width | `max-w-3xl` (48rem) for content pages |
| Page padding | `px-6 py-10` |
| Card padding | `px-5 py-4` |
| Gap between cards | `gap-2` (list) / `gap-4` (grid) |
| Header height | `py-4` + border-b |
| Section gap | `mb-6` |

---

### Border Radius

| Element | Value |
|---------|-------|
| Cards, panels | `rounded-xl` (12px) |
| Buttons | `rounded-lg` (8px) |
| Badges / chips | `rounded` (4px) |
| Canvas nodes | `rounded-xl` (12px) |
| Input fields | `rounded-lg` (8px) |
| Canvas handles | circular (`rounded-full` implied) |

---

## Components

### Header (global)
```
bg-white border-b border-stone-200 px-6 py-4
Left:  font-semibold text-stone-900  →  "Delegator"
Right: nav links (text-sm text-stone-500) + CTA button + AuthButton
```

### CTA Button (primary)
```
bg-stone-900 text-white rounded-lg px-4 py-2 text-sm font-medium
hover: bg-stone-700
```

### Ghost / Secondary Button
```
border border-stone-200 text-stone-700 rounded-lg px-4 py-2 text-sm font-medium
hover: bg-stone-50
```

### List Card (workflow / run list items)
```
rounded-xl border border-stone-200 bg-white px-5 py-4
hover: border-stone-300 shadow-sm
group-hover on title: text-indigo-700
Right side: muted meta text + "→" arrow
```

### Empty State
```
rounded-xl border border-dashed border-stone-300 p-16 text-center
Message: text-stone-500 text-sm
CTA: primary button below message
```

### Canvas Node (BlockNode)
```
width: 200px fixed
rounded-xl border-2 px-3 py-2.5
Default:  block type bg + border (see BLOCK_STYLES)
Selected: ring-2 ring-indigo-400 ring-offset-2 shadow-md
Hover:    hover:shadow-md hover:ring-1 hover:ring-stone-300

Block type badge: text-[8px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded
Block label:      text-xs font-semibold text-stone-800 leading-tight truncate
Integration badge: colored pill (see INTEGRATION_COLORS in BlockNode.tsx)
Action label:     text-[9px] text-stone-400 truncate
```

### Canvas Handles
```
!w-2.5 !h-2.5 !border-2 !border-white !shadow-sm
hover: !scale-125
Pass handle: !bg-green-400
Fail handle: !bg-red-400
Default:     !bg-stone-400
```

### Status Badge (run status)
```
pending:   bg-stone-100   text-stone-600
running:   bg-blue-50     text-blue-700    (+ animate-pulse)
paused:    bg-orange-50   text-orange-700
succeeded: bg-emerald-50  text-emerald-700
failed:    bg-red-50      text-red-700
```

### Form Fields (block editor)
```
Input:    w-full rounded-lg border border-stone-200 px-3 py-2 text-sm
          focus: outline-none ring-2 ring-indigo-200 border-indigo-300
Textarea: same + resize-none
Select:   same styling as input
Label:    text-xs font-medium text-stone-600 mb-1
```

### Integration Color Badges (on canvas nodes)
```
github:       bg-stone-800 text-white
slack:        bg-purple-600 text-white
linear:       bg-indigo-600 text-white
vercel:       bg-stone-700 text-white
railway:      bg-violet-600 text-white
digitalocean: bg-blue-500 text-white
email:        bg-emerald-600 text-white
```

---

## Page Patterns

### Canvas Page layout
```
Header (fixed top): workflow name + Draft badge + Dry Run + Run buttons
Left sidebar (w-56): block library drag tiles
Main area: React Flow canvas (bg-stone-50 dotted grid)
Bottom panel (h-64): block editor for selected node
```

### Settings Page layout
```
Header + page title "Connect your tools"
Integration cards grid (2 col): colored badge + name + description + Connected dot
Inline expand on click — no modals
Footer CTA: "Create your first agent →" (disabled until 1 credential)
```

### Run Trace layout
```
Header: workflow name + run status badge + back link
Timeline: left-aligned event list, newest at bottom
Each event: block type indicator + block name + duration + output summary
Approval event: inline Approve / Reject buttons
```

---

## React Flow Canvas Specifics

```css
/* edges */
.react-flow__edge-path {
  stroke: #D1D5DB;      /* stone-300 */
  stroke-width: 1.5;
}
.react-flow__edge.selected .react-flow__edge-path {
  stroke: #6366F1;      /* indigo-500 */
}

/* background grid */
.react-flow__background {
  background-color: #FAFAF9;   /* stone-50 */
}
```

---

## What NOT to do

- Do not use `bg-gray-*` for page backgrounds — use `bg-stone-*`
- Do not use pure black (`#000`) — use `stone-900`
- Do not use block type colors outside of block nodes / sidebar tiles
- Do not add new accent colors — indigo is the only accent
- Do not use modals for inline actions that can expand in place (settings credentials)
- Do not truncate labels on canvas nodes with ellipsis beyond the node width — the 200px width is fixed for a reason
- Do not use `font-bold` for body text — `font-medium` or `font-semibold` max outside badges

---

## File Locations

| Asset | Path |
|-------|------|
| Block colors + types | `apps/web/src/lib/block-types.ts` |
| Tailwind config + color tokens | `apps/web/tailwind.config.ts` |
| Global CSS + React Flow overrides | `apps/web/src/app/globals.css` |
| Canvas node component | `apps/web/src/components/canvas/BlockNode.tsx` |
| Block editor panel | `apps/web/src/components/canvas/BlockEditor.tsx` |
| Integration color badges | `apps/web/src/components/canvas/BlockNode.tsx` → `INTEGRATION_COLORS` |
