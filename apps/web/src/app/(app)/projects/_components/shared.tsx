export interface Project {
  id: string
  name: string
  agent_count: number
  created_at: string
  workspace_id?: string
  project_type?: string
}

export interface Workflow {
  id: string
  name: string
  workspace_id: string
  project_id: string | null
  updated_at: string
  last_run_status: string | null
  last_run_at: string | null
  project_name: string | null
}

// P2-1: removed local timeAgo — imported from @/lib/runUtils

const AVATAR_COLORS = [
  "#4f46e5", "#059669", "#d97706", "#dc2626",
  "#7c3aed", "#0284c7", "#be185d", "#15803d",
]
export function avatarColor(name: string): string {
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffffffff
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length]
}

export function mapStatus(s: string | null): string {
  if (!s) return "idle"
  const l = s.toLowerCase()
  if (l === "running") return "run"
  if (l === "waiting" || l === "pending" || l === "awaiting") return "wait"
  if (l === "succeeded" || l === "success") return "ok"
  if (l === "failed" || l === "error") return "err"
  if (l === "warn" || l === "degraded") return "warn"
  return "idle"
}

export function PlusIcon({ size = 15 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 5v14M5 12h14" />
    </svg>
  )
}

export function ShieldIcon() {
  return (
    <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}
