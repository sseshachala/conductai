"use client"

/**
 * /runs/<run_id> resolver.
 *
 * The real run detail page lives at /workflows/<wf>/runs/<run_id>. Callers
 * that only have a run id (Guard activity log, deep links, MCP surfaces) can
 * link `/runs/<id>` and this page fetches the run's workflow_id via the
 * workspace-scoped GET /runs/{run_id} endpoint and redirects.
 */
import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { API } from "@/lib/api"
import AppShell from "@/components/AppShell"

export default function RunResolverPage() {
  return <AppShell><Resolver /></AppShell>
}

function Resolver() {
  const params = useParams<{ run_id: string }>()
  const runId = params?.run_id
  const router = useRouter()
  const { authFetch } = useAuthFetch()
  const { activeWorkspace } = useWorkspace()
  const wsId = activeWorkspace?.id
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!runId || !wsId) return
    let cancelled = false
    ;(async () => {
      try {
        const res = await authFetch(`${API}/runs/${runId}?workspace_id=${wsId}`)
        if (cancelled) return
        if (res.status === 404) {
          setError("Run not found in this workspace.")
          return
        }
        if (!res.ok) {
          setError(`Lookup failed (HTTP ${res.status}).`)
          return
        }
        const data = await res.json()
        if (!data?.workflow_id) {
          setError("Run is missing a workflow reference.")
          return
        }
        router.replace(`/workflows/${data.workflow_id}/runs/${runId}`)
      } catch (e) {
        if (!cancelled) setError(`Lookup failed: ${e instanceof Error ? e.message : String(e)}`)
      }
    })()
    return () => { cancelled = true }
  }, [runId, wsId, authFetch, router])

  return (
    <div style={{ padding: 32, fontSize: 13, color: "var(--text-2)" }}>
      {error ? (
        <>
          <div className="eyebrow" style={{ marginBottom: 6, color: "var(--err)" }}>Run not found</div>
          <div style={{ marginBottom: 12 }}>{error}</div>
          <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)" }}>run id: {runId}</div>
        </>
      ) : (
        <div style={{ color: "var(--text-muted)" }}>Resolving run…</div>
      )}
    </div>
  )
}
