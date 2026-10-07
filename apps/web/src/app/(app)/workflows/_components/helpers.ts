export interface Workflow {
  id: string
  name: string
  workspace_id: string
  updated_at: string
  last_run_status: string | null
  last_run_at: string | null
  project_name: string | null
  guard_enabled: boolean | null
}

export function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
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

export function statusKey(label: string): string {
  return ({ Running: "run", Awaiting: "wait", Succeeded: "ok", Failed: "err", "Never run": "idle" } as Record<string, string>)[label] ?? "idle"
}

// Explicit status sort order (#20)
export const STATUS_SORT_ORDER = ["run", "wait", "err", "idle", "ok"]
