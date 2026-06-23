"use client"

/**
 * /guard/tool-errors — dedicated page for CLI / booster telemetry events
 * (#718 Phase 1B).
 *
 * Same data as the "Tool Events" tab on /guard/activity, surfaced as a
 * top-level Guard nav entry so it's discoverable without drilling into
 * Activity first. Renders the shared <ToolActivityTable/> component.
 */
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import ToolActivityTable from "@/components/guard/ToolActivityTable"
import { useGuardTeam } from "@/hooks/useGuardTeam"

export default function ToolErrorsPage() {
  return (
    <AppShell>
      <ToolErrorsContent />
    </AppShell>
  )
}

function ToolErrorsContent() {
  const { teamId } = useGuardTeam()
  return (
    <GuardShell live lastFetched={new Date()}>
      <div style={{ marginBottom: 16 }}>
        <h1 style={{ fontSize: 18, fontWeight: 600, color: "var(--text)", marginBottom: 4 }}>
          Tool Errors & Warnings
        </h1>
        <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
          Errors and warnings emitted by <code>conduct-cli</code> and <code>agent-booster</code>.
          Same events show up on the Tool Events tab of Activity — this view is the focused feed.
        </p>
      </div>
      <ToolActivityTable workspaceId={teamId} />
    </GuardShell>
  )
}
