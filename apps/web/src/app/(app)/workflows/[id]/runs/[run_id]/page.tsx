"use client"

/**
 * Full run-detail page. Renders <RunDetailPanel> inside the standard AppShell.
 * The panel is the shared implementation — same component is embedded inside
 * Lens RunBubble with the `embedded` prop.
 *
 * #1543 removed the poll inside RunDetailPanel to kill flicker in the Lens
 * embedded surface. In Lens the panel gets fresh state pushed from RunBubble's
 * SSE subscription (#1544). Standalone canvas has no such parent — this page
 * owns a low-frequency poll and pushes fresh RunMeta via `initialRun`, which
 * RunDetailPanel's #1544 useEffect syncs into its own `run` state.
 */
import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import AppShell from "@/components/AppShell"
import RunDetailPanel, { type RunMeta } from "@/components/runs/RunDetailPanel"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"
import { isTerminal } from "@/lib/runUtils"

export default function RunDetailPage() {
  const { id: workflowId, run_id: runId } = useParams<{ id: string; run_id: string }>()
  const { authFetch } = useAuthFetch()
  const [runData, setRunData] = useState<RunMeta | null>(null)

  useEffect(() => {
    if (!workflowId || !runId) return
    let cancelled = false

    async function fetchOnce() {
      try {
        const res = await authFetch(`${API}/workflows/${workflowId}/runs/${runId}`)
        if (!cancelled && res.ok) setRunData(await res.json() as RunMeta)
      } catch { /* transient — next tick will retry */ }
    }
    fetchOnce()

    const id = setInterval(async () => {
      // Stop polling once terminal — the panel keeps its final state.
      if (runData && isTerminal(runData.status)) return
      await fetchOnce()
    }, 4000)
    return () => { cancelled = true; clearInterval(id) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId, runId, runData?.status])

  return (
    <AppShell>
      <RunDetailPanel
        workflowId={workflowId}
        runId={runId}
        initialRun={runData ?? undefined}
      />
    </AppShell>
  )
}
