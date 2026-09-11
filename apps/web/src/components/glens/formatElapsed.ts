export function formatElapsed(startMs: number, endMs: number): string {
  const secs = Math.max(0, Math.round((endMs - startMs) / 1000))
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  const rem = secs % 60
  if (mins < 60) return rem ? `${mins}m ${rem}s` : `${mins}m`
  const hrs = Math.floor(mins / 60)
  const rmin = mins % 60
  return rmin ? `${hrs}h ${rmin}m` : `${hrs}h`
}
