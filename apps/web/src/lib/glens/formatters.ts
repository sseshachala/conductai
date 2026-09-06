// Shared formatters for Lens bubbles + dashboard. Consolidates fmtNumber /
// fmtCost / fmtDate / relativeTime previously duplicated across
// GLensPageBubble, GenericTableBubble, and GlensDashboard.

export function fmtNumber(n: number): string {
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M"
  if (Math.abs(n) >= 1_000)     return (n / 1_000).toFixed(1).replace(/\.0$/, "") + "K"
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

export function fmtCost(n: number): string {
  return `$${n.toFixed(2)}`
}

export function fmtDate(raw: string): string {
  const d = new Date(raw)
  if (isNaN(d.getTime())) return raw
  const datePart = d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })
  const timePart = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false })
  return `${datePart} ${timePart}`
}

export function relativeTime(ts: string): string {
  try {
    const diff = Date.now() - new Date(ts).getTime()
    const secs = Math.floor(diff / 1000)
    if (secs < 60) return "just now"
    const mins = Math.floor(secs / 60)
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs}h ago`
    const days = Math.floor(hrs / 24)
    return `${days}d ago`
  } catch {
    return ts
  }
}
