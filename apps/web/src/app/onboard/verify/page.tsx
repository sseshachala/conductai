"use client"

import { useEffect, useRef, useState } from "react"

export default function VerifyTrialPage() {
  const challenge = useRef("")
  const busy = useRef(false)
  const [state, setState] = useState<"loading" | "ready" | "pending" | "new" | "existing" | "error">("loading")
  const [error, setError] = useState("")

  useEffect(() => {
    const token = new URL(window.location.href).searchParams.get("ct")
    if (token) challenge.current = token
    window.history.replaceState(null, "", window.location.pathname)
    setState(challenge.current ? "ready" : "error")
    if (!challenge.current) setError("This link is missing its verification code. Request a new trial email.")
  }, [])

  async function verify() {
    if (busy.current || !challenge.current) return
    busy.current = true
    setState("pending")
    try {
      const base = (process.env.NEXT_PUBLIC_API_URL || "https://api.conductai.ai").replace(/\/$/, "")
      const response = await fetch(`${base}/guard/trial/redeem`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ct: challenge.current }),
        cache: "no-store",
        referrerPolicy: "no-referrer",
      })
      if (!response.ok) {
        throw new Error(response.status === 410
          ? "This verification link has expired or was already used. Sign in if you already verified, or request a new email."
          : "Verification could not finish. Try signing in before requesting another trial email.")
      }
      const result = await response.json()
      if (result.status !== "new" && result.status !== "existing") throw new Error("Unexpected verification response. Please sign in to check your account.")
      // Credentials returned for CLI clients stay out of the DOM and storage.
      challenge.current = ""
      setState(result.status)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Verification could not finish.")
      setState("error")
    }
  }

  return (
    <main className="mx-auto max-w-lg px-6 py-20">
      <p className="mb-8 text-sm font-semibold">Conduct</p>
      <h1 className="mb-4 text-2xl font-semibold">{state === "new" ? "Your trial workspace is ready" : state === "existing" ? "Your account already exists" : "Verify your trial"}</h1>
      {(state === "ready" || state === "pending") && <>
        <p className="mb-6 text-sm text-gray-600">Confirm your email to create your trial workspace. If you started in the terminal, paste the original email link there instead.</p>
        <button type="button" disabled={state === "pending"} onClick={verify} className="rounded-md bg-black px-4 py-2 text-sm text-white disabled:opacity-50">
          {state === "pending" ? "Verifying..." : "Verify email"}
        </button>
      </>}
      {state === "loading" && <p role="status">Loading...</p>}
      {state === "error" && <p role="alert" className="mb-6 text-sm text-red-700">{error}</p>}
      {(state === "new" || state === "existing" || state === "error") && <a href="/sign-in" className="text-sm underline">Continue to sign in</a>}
    </main>
  )
}
