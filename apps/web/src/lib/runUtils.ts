// Shared run display utilities — used by /runs, /dashboard, project page, run detail

export type RunStatus = "pending" | "running" | "paused" | "succeeded" | "failed" | "cancelled" | "skipped"

export interface StatusStyle {
  label: string
  dot: string
  text: string
  bg: string
  border: string
}

export const STATUS: Record<string, StatusStyle> = {
  pending:   { label: "Queued",               dot: "bg-stone-300",              text: "text-stone-500",  bg: "bg-stone-100",  border: "border-stone-200" },
  running:   { label: "Running",              dot: "bg-blue-400 animate-pulse", text: "text-blue-700",  bg: "bg-blue-50",    border: "border-blue-200"  },
  paused:    { label: "Waiting for approval", dot: "bg-amber-400 animate-pulse",text: "text-amber-700", bg: "bg-amber-50",   border: "border-amber-200" },
  succeeded: { label: "Succeeded",            dot: "bg-green-400",              text: "text-green-700", bg: "bg-green-50",   border: "border-green-200" },
  failed:    { label: "Failed",               dot: "bg-red-400",                text: "text-red-600",   bg: "bg-red-50",     border: "border-red-200"   },
  cancelled: { label: "Cancelled",            dot: "bg-stone-300",              text: "text-stone-400", bg: "bg-stone-100",  border: "border-stone-200" },
  skipped:   { label: "Skipped",              dot: "bg-stone-300",              text: "text-stone-400", bg: "bg-stone-100",  border: "border-stone-200" },
}

export function statusStyle(status: string): StatusStyle {
  return STATUS[status] ?? STATUS.pending
}

export function needsAttention(status: string): boolean {
  return ["failed", "paused", "cancelled"].includes(status)
}

export function isActive(status: string): boolean {
  return ["pending", "running", "paused"].includes(status)
}

export function isTerminal(status: string): boolean {
  return ["succeeded", "failed", "cancelled", "skipped"].includes(status)
}

export function formatTrigger(triggeredBy: string | null): string {
  if (!triggeredBy) return "Manual"
  if (triggeredBy === "manual:test_trigger") return "Test run"
  if (triggeredBy.startsWith("github:pull_request")) return "GitHub PR"
  if (triggeredBy.startsWith("github:issues")) return "GitHub issue"
  if (triggeredBy.startsWith("github:push")) return "GitHub push"
  if (triggeredBy.startsWith("github:")) return "GitHub"
  if (triggeredBy === "webhook:inbound") return "Webhook"
  if (triggeredBy.startsWith("webhook:")) return "Webhook"
  if (triggeredBy.startsWith("schedule:")) return "Schedule"
  if (triggeredBy.startsWith("manual:")) return "Manual"
  return triggeredBy
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

export function duration(startedAt: string | null, completedAt: string | null): string {
  if (!startedAt || !completedAt) return "—"
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime()
  if (ms < 1000) return "< 1s"
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  const totalSecs = Math.floor(ms / 1000)
  return `${Math.floor(totalSecs / 60)}m ${totalSecs % 60}s`
}
