"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useAuth, useUser } from "@clerk/nextjs"

const SITE_KEY = process.env.NEXT_PUBLIC_RECAPTCHA_SITE_KEY ?? ""

declare global {
  interface Window {
    grecaptcha: {
      ready: (cb: () => void) => void
      execute: (siteKey: string, options: { action: string }) => Promise<string>
    }
  }
}

function useRecaptcha() {
  const loaded = useRef(false)
  const [captchaReady, setCaptchaReady] = useState(false)

  useEffect(() => {
    if (!SITE_KEY || loaded.current) {
      if (!SITE_KEY) setCaptchaReady(true) // no CAPTCHA needed — unblock immediately
      return
    }
    loaded.current = true
    const script = document.createElement("script")
    script.src = `https://www.google.com/recaptcha/api.js?render=${SITE_KEY}&onload=__conductRecaptchaReady`
    script.async = true
    ;(window as unknown as Record<string, unknown>)["__conductRecaptchaReady"] = () => setCaptchaReady(true)
    document.head.appendChild(script)
  }, [])

  const execute = useCallback(async (): Promise<string | null> => {
    if (!SITE_KEY) return null
    return new Promise(resolve => {
      window.grecaptcha.ready(async () => {
        try {
          const token = await window.grecaptcha.execute(SITE_KEY, { action: "submit_playbook" })
          resolve(token)
        } catch {
          resolve(null)
        }
      })
    })
  }, [])

  return { execute, captchaReady }
}

function validateYaml(content: string): string | null {
  const trimmed = content.trim()
  if (!trimmed) return "YAML content is required"
  const hasName = /^\s*name\s*:/m.test(trimmed)
  const hasStepsOrBlocks = /^\s*(steps|blocks)\s*:/m.test(trimmed)
  if (!hasName) return "Invalid YAML: missing required field 'name'"
  if (!hasStepsOrBlocks) return "Invalid YAML: missing required field 'steps' or 'blocks'"
  return null
}

export default function SubmitPlaybookPage() {
  const { getToken, isSignedIn, isLoaded } = useAuth()
  const { user } = useUser()
  const { execute: executeRecaptcha, captchaReady } = useRecaptcha()

  const [yaml, setYaml] = useState("")
  const [email, setEmail] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const userEmail = user?.primaryEmailAddress?.emailAddress ?? ""

  // Wait for Clerk to initialise before rendering auth-dependent UI
  if (!isLoaded) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-stone-300 border-t-stone-600 rounded-full animate-spin" />
      </div>
    )
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()

    // P1-10: validate YAML structure before submitting
    const validationError = validateYaml(yaml)
    if (validationError) { setError(validationError); return }

    setError(null)
    setSubmitting(true)

    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? ""
      const headers: Record<string, string> = { "Content-Type": "application/json" }

      let recaptchaToken: string | null = null

      if (isSignedIn) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      } else {
        // Anonymous — get reCAPTCHA token
        recaptchaToken = await executeRecaptcha()
        if (!recaptchaToken) {
          setError("Human verification failed — please try again")
          setSubmitting(false)
          return
        }
      }

      const res = await fetch(`${base}/playbooks/submit`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          yaml_content: yaml,
          recaptcha_token: recaptchaToken,
          submitter_email: isSignedIn ? userEmail : email || undefined,
        }),
      })

      const data = await res.json()
      if (res.ok) {
        setResult({ ok: true, message: data.message })
        setYaml("")
      } else {
        setError(data.detail ?? "Submission failed — please try again")
      }
    } catch {
      setError("Network error — please try again")
    } finally {
      setSubmitting(false)
    }
  }

  if (result?.ok) {
    return (
      <div className="min-h-screen bg-stone-50 flex items-center justify-center px-4">
        <div className="bg-white rounded-2xl border border-stone-200 shadow-sm p-10 max-w-md w-full text-center space-y-4">
          <div className="text-3xl">&#10003;</div>
          <h1 className="text-lg font-semibold text-stone-900">Submission received</h1>
          <p className="text-sm text-stone-500">{result.message}</p>
          <div className="flex gap-3 justify-center pt-2">
            <button
              onClick={() => setResult(null)}
              className="text-sm text-stone-600 border border-stone-200 rounded-lg px-4 py-2 hover:bg-stone-50 transition-colors"
            >
              Submit another
            </button>
            <Link href="/playbooks" className="text-sm text-stone-900 border border-stone-200 rounded-lg px-4 py-2 hover:bg-stone-50 transition-colors">
              Browse playbooks
            </Link>
          </div>
        </div>
      </div>
    )
  }

  // Submit button is disabled while reCAPTCHA is loading (anon users only)
  const submitBlocked = submitting || !yaml.trim() || (!isSignedIn && SITE_KEY !== "" && !captchaReady)
  const submitLabel = submitting
    ? "Submitting…"
    : !isSignedIn && SITE_KEY !== "" && !captchaReady
      ? "Verifying you're human…"
      : "Submit playbook"

  return (
    <div className="min-h-screen bg-stone-50 px-4 py-12">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <Link href="/playbooks" className="text-sm text-stone-400 hover:text-stone-600 transition-colors">
            ← Back to playbooks
          </Link>
          <h1 className="text-2xl font-semibold text-stone-900 mt-3">Submit a playbook</h1>
          <p className="text-sm text-stone-500 mt-1">
            Share a YAML playbook with the community. We review all submissions before publishing.
          </p>
        </div>

        {/* Auth status */}
        <div className={`rounded-lg px-4 py-3 text-sm flex items-center gap-2 ${isSignedIn ? "bg-green-50 border border-green-200 text-green-700" : "bg-amber-50 border border-amber-200 text-amber-700"}`}>
          {isSignedIn ? (
            <><span>&#10003;</span> Submitting as <strong>{userEmail}</strong></>
          ) : (
            <><span>&#9888;</span> You&apos;re not signed in — your submission will be verified with reCAPTCHA. <Link href="/sign-in" className="underline ml-1">Sign in</Link> for a faster review.</>
          )}
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Email for anon users */}
          {!isSignedIn && (
            <div>
              <label className="block text-sm font-medium text-stone-700 mb-1.5">
                Your email <span className="text-stone-400 font-normal">(optional — for review updates)</span>
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full text-sm border border-stone-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
              />
            </div>
          )}

          {/* YAML editor */}
          <div>
            <label className="block text-sm font-medium text-stone-700 mb-1.5">
              Playbook YAML <span className="text-red-500">*</span>
            </label>
            <textarea
              value={yaml}
              onChange={e => setYaml(e.target.value)}
              rows={20}
              placeholder={"name: my-playbook\ndescription: What this agent does\n\ntrigger:\n  type: github\n  events: [pull_request]\n\nsteps:\n  ..."}
              className="w-full text-sm font-mono border border-stone-200 rounded-lg px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white resize-y"
              spellCheck={false}
            />
          </div>

          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="flex items-center justify-between">
            <p className="text-xs text-stone-400">
              {!isSignedIn && SITE_KEY && "Protected by reCAPTCHA · "}
              <Link href="/docs/playbook-spec" className="hover:underline">
                Playbook spec
              </Link>
            </p>
            <button
              type="submit"
              disabled={submitBlocked}
              className="bg-stone-900 text-white text-sm font-medium px-5 py-2 rounded-lg hover:bg-stone-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
