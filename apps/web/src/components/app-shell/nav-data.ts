import { GUARD_SECTIONS } from "@/lib/navigation/guardSections"
import type { Project } from "./types"

// ── Breadcrumb logic ──────────────────────────────────────────────────────────

export function getBreadcrumbs(pathname: string, projects: Project[]): string[] {
  if (pathname.startsWith('/dashboard')) return ['Dashboard']
  if (pathname.startsWith('/theguard/inbox')) return ['Guard', 'Inbox']
  if (pathname.startsWith('/theguard/spend')) return ['Guard', 'Spend']
  if (pathname.startsWith('/theguard/policies')) return ['Guard', 'Controls', 'Policies']
  if (pathname.startsWith('/theguard/approvals')) return ['Guard', 'Approvals']
  if (pathname.startsWith('/theguard/discovery')) return ['Guard', 'Agents Discovered']
  if (pathname.startsWith('/theguard/session-reports')) return ['Guard', 'Activity', 'Session Reports']
  if (pathname.startsWith('/theguard/activity')) return ['Guard', 'Activity']
  if (pathname.startsWith('/proxy')) return ['Connect', 'Gateways']
  if (pathname.startsWith('/theguard/connections')) return ['Guard', 'Connections']
  if (pathname.startsWith('/theguard/settings')) return ['Guard', 'Settings']
  if (pathname.startsWith('/theguard/compliance')) return ['Guard', 'Compliance']
  if (pathname.startsWith('/governance')) return ['Governance']
  if (pathname.startsWith('/team-os/ai-rollout')) return ['Team OS', 'AI Rollout']
  if (pathname.startsWith('/theguard/team-os')) return ['Team OS']
  if (pathname.startsWith('/theguard')) return ['Guard', 'Overview']
  if (pathname.startsWith('/settings')) return ['Settings']
  if (pathname.startsWith('/packs')) return ['Registry']
  if (pathname.startsWith('/playbooks')) return ['Automations']
  if (pathname.startsWith('/logs/guard')) return ['Logs', 'Guard']
  if (pathname.startsWith('/logs/runs')) return ['Logs', 'Runs']
  if (pathname.startsWith('/logs/observability')) return ['Logs', 'Observability']
  if (pathname.startsWith('/logs')) return ['Logs']
  if (pathname.startsWith('/runs')) return ['Runs']
  if (pathname.startsWith('/observability')) return ['Observability']
  if (pathname === '/workflows') return ['Workflows']
  if (pathname.startsWith('/workflows/new')) return ['Canvas', 'New workflow']
  if (pathname.startsWith('/workflows/')) return ['Canvas']
  const projectMatch = pathname.match(/\/projects\/([^/]+)/)
  if (projectMatch) {
    const project = projects.find(p => p.id === projectMatch[1])
    const name = project?.name ?? 'Project'
    if (pathname.includes('/runs')) return ['Projects', name, 'Runs']
    return ['Projects', name]
  }
  if (pathname.startsWith('/projects')) return ['Projects']
  return ['Conduct']
}

// ── Command palette commands ──────────────────────────────────────────────────

export const PALETTE_COMMANDS = [
  { group: "BUILD", label: "Projects", href: "/projects", icon: "Grid" as const },
  { group: "BUILD", label: "Workflows", href: "/workflows", icon: "Flow" as const },
  { group: "BUILD", label: "Registry", href: "/packs", icon: "Store" as const },
  { group: "OBSERVE", label: "Dashboard", href: "/dashboard", icon: "Spark" as const },
  { group: "OBSERVE", label: "Runs", href: "/runs", icon: "Pulse" as const },
  { group: "GOVERN", label: "Runtime Governance", href: "/governance", icon: "Shield" as const },
  { group: "ASK", label: "Lens", href: "/lens", icon: "Spark" as const },
  ...GUARD_SECTIONS.map(s => ({ group: "GOVERN" as const, label: `Guard · ${s.label}`, href: s.href, icon: "Shield" as const })),
  { group: "GOVERN", label: "Guard · Compliance", href: "/theguard/compliance", icon: "Shield" as const },
  { group: "GOVERN", label: "Guard · Enforcement", href: "/theguard/policies/enforcement", icon: "Shield" as const },
  { group: "CONNECT", label: "Agent ID", href: "/agent-identity", icon: "Lock" as const },
  { group: "CONNECT", label: "MCP Registry", href: "/integrations", icon: "Plug" as const },
  { group: "CONNECT", label: "Gateways", href: "/proxy/gateway-profiles", icon: "Plug" as const },
  { group: "WORKSPACE", label: "Settings · Vault", href: "/settings", icon: "Gear" as const },
]
