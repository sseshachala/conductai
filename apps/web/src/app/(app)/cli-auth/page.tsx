"use client"

import { useEffect, useState } from "react"
import { useAuth } from "@clerk/nextjs"
import { useSearchParams } from "next/navigation"

const DEFAULT_API = process.env.NEXT_PUBLIC_API_URL ?? "https://api.conductai.ai"

type State = "loading" | "success" | "error"

export default function CliAuthPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  const params = useSearchParams()
  const [state, setState] = useState<State>("loading")
  const [error, setError] = useState("")

  useEffect(() => {
    if (!isLoaded) return

    if (!isSignedIn) {
      // Redirect to sign-in, come back after
      const here = window.location.href
      window.location.href = `/sign-in?redirect_url=${encodeURIComponent(here)}`
      return
    }

    const port     = params.get("port")
    const qstate   = params.get("state")
    const apiOverride = params.get("api")

    if (!port || !qstate) {
      setState("error")
      setError("Missing port or state parameter. Re-run `conduct login`.")
      return
    }

    const apiUrl = (apiOverride ?? DEFAULT_API).replace(/\/$/, "")

    async function exchange() {
      try {
        const clerkToken = await getToken()
        if (!clerkToken) throw new Error("No Clerk session token")

        const res = await fetch(`${apiUrl}/auth/cli-token`, {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${clerkToken}`,
            "Content-Type": "application/json",
          },
        })

        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(body.detail ?? `Server error ${res.status}`)
        }

        const data = await res.json()
        const callbackParams = new URLSearchParams({
          agent_token:   data.agent_token,
          refresh_token: data.refresh_token,
          workspace_id:  data.workspace_id,
          state:         qstate!,
        })

        // Redirect to CLI's localhost callback server
        window.location.href = `http://127.0.0.1:${port}/callback?${callbackParams}`
        setState("success")
      } catch (e: unknown) {
        setState("error")
        setError(e instanceof Error ? e.message : "Unknown error")
      }
    }

    exchange()
  }, [isLoaded, isSignedIn, getToken, params])

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
