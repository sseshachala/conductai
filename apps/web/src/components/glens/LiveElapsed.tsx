"use client"
import { useEffect, useState } from "react"
import { formatElapsed } from "@/components/glens/formatElapsed"

// Owns its own 1s tick so the elapsed badge updates without re-rendering
// RunBubble (and, more importantly, the embedded RunDetailPanel below it).
// Same pattern as <LiveDuration/> inside RunDetailPanel.
export function LiveElapsed({ startedAt, completedAt, status }: {
  startedAt: number; completedAt: number | null; status: string
}) {
  const [now, setNow] = useState<number>(() => Date.now())
  useEffect(() => {
    if (completedAt || (status !== "running" && status !== "pending")) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [completedAt, status])
  return (
    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
      {formatElapsed(startedAt, completedAt ?? now)}
    </span>
  )
}
