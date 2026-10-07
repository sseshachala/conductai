"use client"

import { useState } from "react"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { workflows, credentials } from "@/lib/api"
import type { AuthFetch } from "@/lib/api"

// ── GitHub webhook status panel ───────────────────────────────────────────────

export function GitHubWebhookStatusPanel({
  workflowId, hookId, hookRepo, getToken, onWebhookChange, compact,
}: {
  workflowId: string
  hookId: string | null
  hookRepo: string | null
  getToken?: (() => Promise<string | null>) | null
  onWebhookChange?: (hookId: string | null, hookRepo: string | null) => void
  compact?: boolean
}) {
  const { activeWorkspace } = useWorkspace()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [sharedWith, setSharedWith] = useState<string | null>(null)

  async function authHeaders() {
    const h: Record<string, string> = { "Content-Type": "application/json" }
    if (getToken) { const t = await getToken(); if (t) h["Authorization"] = `Bearer ${t}` }
    const ws = activeWorkspace?.id ?? ""
    if (ws) h["X-Workspace-Id"] = ws
    return h
  }

  async function register() {
    setBusy(true); setErr(null); setSharedWith(null)
    try {
      const h = await authHeaders()
      const authFetch: AuthFetch = (url, opts) => fetch(url, { ...opts, headers: { ...h, ...(opts?.headers as Record<string, string> | undefined) } })
      const r = await workflows.webhook.create(authFetch, workflowId, {})
      const data = await r.json()
      if (!r.ok) { setErr(data.detail || `HTTP ${r.status}`); return }
      if (data.shared) setSharedWith(data.shared_with_name ?? "another agent")
      onWebhookChange?.(data.github_hook_id, data.github_hook_repo)
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Network error")
    } finally { setBusy(false) }
  }

  async function deregister() {
    setBusy(true); setErr(null)
    try {
      const h = await authHeaders()
      const authFetch: AuthFetch = (url, opts) => fetch(url, { ...opts, headers: { ...h, ...(opts?.headers as Record<string, string> | undefined) } })
      const r = await workflows.webhook.remove(authFetch, workflowId)
      if (!r.ok && r.status !== 204) {
        const data = await r.json().catch(() => ({}))
        setErr(data.detail || `HTTP ${r.status}`); return
      }
      onWebhookChange?.(null, hookRepo)
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Network error")
    } finally { setBusy(false) }
  }

  const registered = !!hookId

  if (compact) {
    return (
      <div className={`rounded-md border px-2.5 py-2 text-xs mt-1.5 flex items-center justify-between gap-3 ${registered ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
        <div>
          <p className={`font-semibold ${registered ? "text-emerald-700" : "text-amber-700"}`}>
            {registered ? `✓ Active on ${hookRepo}` : "Not active — click Activate to start receiving events"}
          </p>
          {sharedWith && <p className="text-stone-500 mt-0.5">Shared with &ldquo;{sharedWith}&rdquo;</p>}
          {err && <p className="text-red-600 mt-0.5">{err}</p>}
        </div>
        <div className="flex gap-1 shrink-0">
          {!registered && (
            <button onClick={register} disabled={busy}
              className="rounded bg-amber-600 text-white px-2.5 py-1 font-medium hover:bg-amber-700 disabled:opacity-50 transition-colors text-[10px]">
              {busy ? "Activating…" : "Activate"}
            </button>
          )}
          {registered && (
            <button onClick={register} disabled={busy}
              title="Re-registers the webhook and rotates the signing key with GitHub."
              className="rounded bg-emerald-600 text-white px-2.5 py-1 font-medium hover:bg-emerald-700 disabled:opacity-50 transition-colors text-[10px]">
              {busy ? "Updating…" : "Re-activate"}
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className={`rounded-lg border px-3 py-2.5 text-xs mt-2 ${registered ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className={`font-semibold ${registered ? "text-emerald-800" : "text-amber-800"}`}>
            {registered ? `✓ Active` : "Not active"}
          </p>
          <p className={`mt-0.5 ${registered ? "text-emerald-700" : "text-amber-700"}`}>
            {registered
              ? <span>on <span className="font-mono">{hookRepo}</span> — GitHub sends events here automatically</span>
              : hookRepo
              ? <span>Click Activate when ready — real GitHub events won't arrive until you do</span>
              : <span>Set a repository in the trigger config first</span>
            }
          </p>
          {sharedWith && <p className="text-stone-500 mt-1">Webhook shared with &ldquo;{sharedWith}&rdquo; — no duplicate hook created on GitHub.</p>}
          {err && <p className="text-red-600 mt-1">{err}</p>}
        </div>
        <div className="flex flex-col gap-1 shrink-0">
          {!registered && hookRepo && (
            <button onClick={register} disabled={busy}
              className="rounded-md bg-amber-600 text-white px-3 py-1.5 font-medium hover:bg-amber-700 disabled:opacity-50 transition-colors text-xs">
              {busy ? "Activating…" : "Activate"}
            </button>
          )}
          {registered && (
            <>
              <button onClick={register} disabled={busy}
                title="Re-registers the webhook and rotates the signing key with GitHub."
                className="rounded-md bg-emerald-600 text-white px-3 py-1.5 font-medium hover:bg-emerald-700 disabled:opacity-50 transition-colors text-xs">
                {busy ? "Updating…" : "Update"}
              </button>
              <button onClick={deregister} disabled={busy}
                className="rounded-md border border-stone-300 text-stone-600 px-3 py-1.5 font-medium hover:bg-stone-100 disabled:opacity-50 transition-colors text-xs">
                Unregister
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Webhook registration ──────────────────────────────────────────────────────

function WebhookRegisterButton({ owner, repo, getToken }: {
  owner: string; repo: string; getToken?: (() => Promise<string | null>) | null
}) {
  const { activeWorkspace } = useWorkspace()
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle")
  const [msg, setMsg] = useState("")

  async function register() {
    setStatus("loading")
    try {
      const wsId = activeWorkspace?.id ?? null
      const authFetch: AuthFetch = async (url, opts) => {
        const headers: Record<string, string> = { ...(opts?.headers as Record<string, string> | undefined) }
        if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
        if (wsId) headers["X-Workspace-ID"] = wsId
        return fetch(url, { ...opts, headers })
      }
      const r = await credentials.github.webhook(authFetch, owner, repo, {})
      const data = await r.json()
      if (!r.ok) { setStatus("error"); setMsg(data.detail || `HTTP ${r.status}`); return }
      setStatus("done")
      setMsg(data.existing ? "Already registered" : "Webhook registered!")
    } catch (e) {
      setStatus("error"); setMsg(e instanceof Error ? e.message : "Network error")
    }
  }

  return (
    <div className="rounded-lg border border-indigo-100 bg-indigo-50 px-3 py-2.5 text-xs">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-semibold text-indigo-800">GitHub webhook</p>
          <p className="text-indigo-600 mt-0.5">
            {status === "done" ? msg : `Auto-register on ${owner}/${repo} to receive issue events`}
            {status === "error" && <span className="text-red-600"> — {msg}</span>}
          </p>
        </div>
        {status !== "done" && (
          <button
            onClick={register}
            disabled={status === "loading"}
            className="shrink-0 rounded-md bg-indigo-600 text-white px-3 py-1.5 font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {status === "loading" ? "Registering…" : "Register"}
          </button>
        )}
        {status === "done" && <span className="text-emerald-600 font-semibold shrink-0">✓ Active</span>}
      </div>
    </div>
  )
}

// ── Vercel webhook registration ───────────────────────────────────────────────

export function VercelWebhookRegisterButton({ eventType, getToken }: {
  eventType: string; getToken?: (() => Promise<string | null>) | null
}) {
  const { activeWorkspace } = useWorkspace()
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle")
  const [msg, setMsg] = useState("")

  async function register() {
    setStatus("loading")
    try {
      const wsId = activeWorkspace?.id ?? null
      const authFetch: AuthFetch = async (url, opts) => {
        const headers: Record<string, string> = { ...(opts?.headers as Record<string, string> | undefined) }
        if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
        if (wsId) headers["X-Workspace-ID"] = wsId
        return fetch(url, { ...opts, headers })
      }
      const r = await credentials.vercel.webhook(authFetch, { event_type: eventType })
      const data = await r.json()
      if (!r.ok) { setStatus("error"); setMsg(data.detail || `HTTP ${r.status}`); return }
      setStatus("done")
      setMsg(data.existing ? "Already registered" : "Webhook registered!")
    } catch (e) {
      setStatus("error"); setMsg(e instanceof Error ? e.message : "Network error")
    }
  }

  return (
    <div className="rounded-lg border border-indigo-100 bg-indigo-50 px-3 py-2.5 text-xs">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-semibold text-indigo-800">Auto-register with Vercel</p>
          <p className="text-indigo-600 mt-0.5">
            {status === "done" ? msg : "Uses your saved Vercel token to register the workspace-scoped webhook"}
            {status === "error" && <span className="text-red-600"> — {msg}</span>}
          </p>
        </div>
        {status !== "done" && (
          <button
            onClick={register}
            disabled={status === "loading"}
            className="shrink-0 rounded-md bg-indigo-600 text-white px-3 py-1.5 font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {status === "loading" ? "Registering…" : "Register"}
          </button>
        )}
        {status === "done" && <span className="text-emerald-600 font-semibold shrink-0">✓ Active</span>}
      </div>
    </div>
  )
}
