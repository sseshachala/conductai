"use client"
/**
 * LensPanel — right-side chat drawer (#B1 + #B2 + #B4 from epic #1214).
 *
 * Copilot-style docked drawer: user asks Lens without leaving the current
 * page. This file owns only the docked shell (resize handle, header, Escape
 * key). The actual chat surface is `<LensChat>` — shared with `<LensEmbed>`.
 */

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { LensChat } from "@/components/glens/LensChat"

export function LensPanel({
  open,
  initialQuery,
  pathname,
  onClose,
}: {
  open: boolean
  initialQuery: string | null
  pathname: string | null
  onClose: () => void
}) {
  const router = useRouter()
  const [sessionId, setSessionId] = useState<string | null>(null)

  // Persisted, drag-to-resize width (min 320, max 720).
  const [width, setWidth] = useState(420)
  const widthRef = useRef(width)
  useEffect(() => { widthRef.current = width }, [width])
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem("lens:panelWidth")
      const n = raw ? parseInt(raw, 10) : NaN
      if (Number.isFinite(n) && n >= 320 && n <= 720) setWidth(n)
    } catch { /* ignore */ }
  }, [])
  const startDrag = (e: React.MouseEvent) => {
    e.preventDefault()
    const startX = e.clientX
    const startW = width
    const onMove = (ev: MouseEvent) => {
      setWidth(Math.min(720, Math.max(320, startW + (startX - ev.clientX))))
    }
    const onUp = () => {
      window.removeEventListener("mousemove", onMove)
      window.removeEventListener("mouseup", onUp)
      document.body.style.cursor = ""
      try { window.localStorage.setItem("lens:panelWidth", String(widthRef.current)) } catch { /* ignore */ }
    }
    document.body.style.cursor = "col-resize"
    window.addEventListener("mousemove", onMove)
    window.addEventListener("mouseup", onUp)
  }

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <aside
      style={{
        width, flexShrink: 0, height: "100vh",
        background: "var(--surface)", borderLeft: "1px solid var(--border)",
        display: "flex", flexDirection: "column",
        boxShadow: "-4px 0 20px rgba(0,0,0,.06)",
        position: "relative",
      }}
      role="complementary"
      aria-label="Ask Lens panel"
    >
      <div
        onMouseDown={startDrag}
        aria-hidden
        style={{
          position: "absolute", top: 0, bottom: 0, left: -3, width: 6,
          cursor: "col-resize", zIndex: 1,
        }}
      />
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 14px", borderBottom: "1px solid var(--border)",
        background: "var(--surface-1)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontWeight: 600, fontSize: 13, color: "var(--text)" }}>Lens</span>
          {pathname && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>· {pathname}</span>}
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          <button
            onClick={() => {
              router.push(sessionId ? `/lens/${sessionId}` : "/lens")
              onClose()
            }}
            title="Expand to full Lens"
            aria-label="Expand to full Lens"
            style={{
              border: "1px solid var(--border)", background: "var(--surface-2)",
              color: "var(--text-2)", padding: "3px 8px", borderRadius: 6,
              fontSize: 11, cursor: "pointer",
            }}
          >Expand →</button>
          <button
            onClick={onClose}
            title="Close"
            aria-label="Close Lens panel"
            style={{
              width: 26, height: 26, borderRadius: 6, border: "1px solid var(--border)",
              background: "var(--surface-2)", color: "var(--text-2)", cursor: "pointer",
              fontSize: 14, lineHeight: 1,
            }}
          >×</button>
        </div>
      </div>

      <LensChat
        pathname={pathname}
        initialQuery={initialQuery}
        onSessionId={setSessionId}
        onExpandMessage={(sid) => {
          router.push(sid ? `/lens/${sid}` : "/lens")
          onClose()
        }}
      />
    </aside>
  )
}
