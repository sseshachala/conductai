"use client"

import { useState } from "react"
import { useAuth } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"

interface Props {
  resourceType: string
  resourceId: string
  /** Optional label override */
  label?: string
}

export default function ShareButton({ resourceType, resourceId, label = "Share" }: Props) {
  const { getToken } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const [state, setState] = useState<"idle" | "loading" | "copied" | "error">("idle")

  async function handleShare() {
    setState("loading")
    try {
      const token = await getToken()
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const res = await fetch(`${base}/share`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          "x-workspace-id": activeWorkspace?.id ?? "",
        },
        body: JSON.stringify({ resource_type: resourceType, resource_id: resourceId }),
      })
      if (!res.ok) throw new Error(await res.text())
      const { share_url } = await res.json()
      await navigator.clipboard.writeText(share_url)
      setState("copied")
      setTimeout(() => setState("idle"), 2500)
    } catch {
      setState("error")
      setTimeout(() => setState("idle"), 2500)
    }
  }

  const text = state === "loading" ? "…" : state === "copied" ? "Copied!" : state === "error" ? "Error" : label
  const color = state === "copied" ? "var(--ok)" : state === "error" ? "var(--err)" : "var(--text-3)"

  return (
    <button
      onClick={handleShare}
      disabled={state === "loading"}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        fontSize: 12,
        fontWeight: 500,
        color,
        background: "none",
        border: "1px solid var(--border)",
        borderRadius: 7,
        padding: "5px 11px",
        cursor: state === "loading" ? "wait" : "pointer",
        transition: "color .15s, border-color .15s",
      }}
    >
      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="13" cy="3" r="1.5" />
        <circle cx="3" cy="8" r="1.5" />
        <circle cx="13" cy="13" r="1.5" />
        <line x1="4.5" y1="7" x2="11.5" y2="4" />
        <line x1="4.5" y1="9" x2="11.5" y2="12" />
      </svg>
      {text}
    </button>
  )
}
