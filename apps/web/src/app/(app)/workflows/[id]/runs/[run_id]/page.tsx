"use client"

/**
 * Full run-detail page. Renders <RunDetailPanel> inside the standard AppShell.
 * The panel is the shared implementation — same component is embedded inside
 * Lens RunBubble with the `embedded` prop.
 */
import { useParams } from "next/navigation"
import AppShell from "@/components/AppShell"
import RunDetailPanel from "@/components/runs/RunDetailPanel"

export default function RunDetailPage() {
  const { id: workflowId, run_id: runId } = useParams<{ id: string; run_id: string }>()
  return (
    <AppShell>
      <RunDetailPanel workflowId={workflowId} runId={runId} />
    </AppShell>
  )
}
