"use client"

import { useEffect, useRef, useState } from "react"
import { useAuth } from "@clerk/nextjs"
import { useSearchParams } from "next/navigation"
import { useWorkspace } from "@/lib/WorkspaceContext"

type State = "loading" | "success" | "error"

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://api.conductai.ai"

export default function OauthAuthorizePage() {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const params = useSearchParams()
  const [state, setState] = useState<State>("loading")
  const [error, setError] = useState("")
  const done = useRef(false)

  useEffect(() => {
    if (!isLoaded) return

    if (!isSignedIn) {
      const here = window.location.href
      window.location.href = `/sign-in?redirect_url=${encodeURIComponent(here)}`
      return
    }

    if (!activeWorkspace) return

    if (done.current) return
    done.current = true

    const requestId = params.get("request_id")
    if (!requestId) {
      setState("error")
      setError("Missing request_id. Restart the OAuth flow from your MCP client.")
      return
    }

    ;(async () => {
      try {
        const clerkToken = await getToken()
        if (!clerkToken) throw new Error("No Clerk session token")

        const res = await fetch(`${API_BASE}/oauth/authorize/confirm`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            request_id: requestId,
            clerk_token: clerkToken,
            workspace_id: activeWorkspace.id,
          }),
        })
        if (!res.ok) {
          const j = await res.json().catch(() => ({}))
          throw new Error(j.detail || `HTTP ${res.status}`)
        }
        const { redirect_url } = await res.json()
        if (!redirect_url) throw new Error("Server returned no redirect_url")

        setState("success")
        window.location.href = redirect_url
      } catch (e: unknown) {
        setState("error")
        setError(e instanceof Error ? e.message : "Unknown error")
      }
    })()
  }, [isLoaded, isSignedIn, getToken, params, activeWorkspace])

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "60vh", gap: "16px", fontFamily: "sans-serif" }}>
      {state === "loading" && (
        <>
          <div style={{ fontSize: "24px" }}>⚡</div>
          <p style={{ color: "#555" }}>Authorizing MCP client…</p>
        </>
      )}
      {state === "success" && (
        <>
          <div style={{ fontSize: "24px" }}>✓</div>
          <p style={{ fontWeight: 600 }}>Authorized. Redirecting back to your app…</p>
        </>
      )}
      {state === "error" && (
        <>
          <div style={{ fontSize: "24px" }}>✗</div>
          <p style={{ fontWeight: 600, color: "#c00" }}>Authorization failed</p>
          <p style={{ color: "#555", maxWidth: "400px", textAlign: "center" }}>{error}</p>
        </>
      )}
    </div>
  )
}
