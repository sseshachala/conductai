// Shared time + count formatters for Guard event surfaces.
// Keeping them in one file guarantees Inbox "18× · 59m ago" reads the
// same as Activity "59m ago" as Discovery "59m ago" — no per-page
// drift. If we ever adopt a locale-aware format, this is the one place
// that changes.

export function timeAgo(iso: string | Date | null | undefined): string {
  if (!iso) return "—"
  const then = typeof iso === "string" ? new Date(iso).getTime() : iso.getTime()
  const sec = Math.floor((Date.now() - then) / 1000)
  if (sec < 5) return "just now"
  if (sec < 60) return `${sec}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  return `${Math.floor(hr / 24)}d ago`
}

export function countAndAge(count: number, iso: string | Date | null | undefined): string {
  return `${count.toLocaleString()}× · ${timeAgo(iso)}`
}

// Small pure-display component so JSX callers don't have to import both
// the fn and remember the format.
export function GuardTimeCount({
  count,
  ts,
  muted = true,
}: {
  count?: number
  ts: string | Date | null | undefined
  muted?: boolean
}) {
  const text = count == null ? timeAgo(ts) : countAndAge(count, ts)
  return (
    <span style={{ fontSize: 12, color: muted ? "var(--text-muted)" : "var(--text)" }}>
      {text}
    </span>
  )
}
