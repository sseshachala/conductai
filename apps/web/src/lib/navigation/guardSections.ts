// Guard six-section IA. Single source of truth for:
// - AppShell palette + sidebar sub-nav + breadcrumbs
// - GuardShell vertical rail
//
// Pages not represented here (compliance, settings, team-memory, approvals)
// stay reachable via URL + ⌘K palette entries.

export type GuardSectionId =
  | "overview"
  | "inbox"
  | "agents"
  | "controls"
  | "activity"
  | "spend"
  | "connections"

export interface GuardSection {
  id: GuardSectionId
  label: string
  href: string
  activePrefixes: readonly string[]
}

export const GUARD_SECTIONS: readonly GuardSection[] = [
  // Order reflects the daily user loop: Inbox (finite triage queue) sits
  // above Activity (raw feed) because the queue converges on zero if you
  // work it — the feed never does. Same rationale every mature triage UI
  // (Slack, Linear, GitHub notifications) uses.
  { id: "overview",    label: "Overview",    href: "/theguard",                   activePrefixes: ["/theguard"] },
  { id: "inbox",       label: "Inbox",       href: "/theguard/inbox",             activePrefixes: ["/theguard/inbox"] },
  { id: "activity",    label: "Activity",    href: "/logs/guard",                 activePrefixes: ["/logs/guard", "/theguard/activity", "/theguard/blocks"] },
  { id: "agents",      label: "Agents",      href: "/theguard/discovery",         activePrefixes: ["/theguard/discovery", "/theguard/agents", "/agent-identity"] },
  { id: "controls",    label: "Controls",    href: "/theguard/policies",          activePrefixes: ["/theguard/policies", "/theguard/approvals"] },
  { id: "spend",       label: "Spend",       href: "/theguard/spend",             activePrefixes: ["/theguard/spend"] },
  { id: "connections", label: "Connections", href: "/theguard/connections/proxy", activePrefixes: ["/theguard/connections"] },
]

export function activeGuardSection(pathname: string): GuardSectionId | null {
  if (pathname === "/theguard") return "overview"
  for (const s of GUARD_SECTIONS) {
    if (s.id === "overview") continue
    if (s.activePrefixes.some(p => pathname === p || pathname.startsWith(p + "/"))) {
      return s.id
    }
  }
  return null
}
