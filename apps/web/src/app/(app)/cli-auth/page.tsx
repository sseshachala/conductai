"use client"

import { useEffect, useRef, useState } from "react"
import { useAuth } from "@clerk/nextjs"
import { useSearchParams } from "next/navigation"
import { useWorkspace } from "@/lib/WorkspaceContext"

type State = "loading" | "success" | "error"

export default function CliAuthPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  const { activeWorkspace } = useWorkspace()
  const params = useSearchParams()
  const [state, setState] = useState<State>("loading")
  const [error, setError] = useState("")
  const exchanged = useRef(false)

  useEffect(() => {
    if (!isLoaded) return

    if (!isSignedIn) {
      const here = window.location.href
      window.location.href = `/sign-in?redirect_url=${encodeURIComponent(here)}`
      return
    }

    // Wait until workspace is resolved
    if (!activeWorkspace) return

    // Prevent double-fire (React Strict Mode / getToken ref change)
    if (exchanged.current) return
    exchanged.current = true

    const port        = params.get("port")
    const qstate      = params.get("state")

    if (!port || !qstate) {
      setState("error")
      setError("Missing port or state parameter. Re-run `conduct login`.")
      return
    }

    const workspaceId = activeWorkspace.id

    async function exchange() {
      try {
        const clerkToken = await getToken()
        if (!clerkToken) throw new Error("No Clerk session token")

        // RFC 8693: relay Clerk JWT to CLI; CLI calls POST /token to exchange it
        const callbackParams = new URLSearchParams({
          clerk_token:  clerkToken,
          workspace_id: workspaceId,
          state:        qstate!,
        })

        window.location.href = `http://127.0.0.1:${port}/callback?${callbackParams}`
        setState("success")
      } catch (e: unknown) {
        setState("error")
        setError(e instanceof Error ? e.message : "Unknown error")
      }
    }

    exchange()
  }, [isLoaded, isSignedIn, getToken, params, activeWorkspace])

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "60vh", gap: "16px", fontFamily: "sans-serif" }}>
      {state === "loading" && (
        <>
          <div style={{ fontSize: "24px" }}>⚡</div>
          <p style={{ color: "#555" }}>Authenticating CLI…</p>
        </>
      )}
      {state === "success" && (
        <>
          <div style={{ fontSize: "24px" }}>✓</div>
          <p style={{ fontWeight: 600 }}>CLI connected.</p>
          <p style={{ color: "#555" }}>You can close this tab.</p>
        </>
      )}
      {state === "error" && (
        <>
          <div style={{ fontSize: "24px" }}>✗</div>
          <p style={{ fontWeight: 600, color: "#c00" }}>Authentication failed</p>
          <p style={{ color: "#555", maxWidth: "400px", textAlign: "center" }}>{error}</p>
          <p style={{ color: "#888", fontSize: "13px" }}>Re-run <code>conduct login</code> to try again.</p>
        </>
      )}
    </div>
  )
}
