"use client"

import { useParams } from "next/navigation"
import AppShell from "@/components/AppShell"
import { GLensChatPage } from "@/components/glens/GLensChatPage"

/**
 * Deep-link entry for a Lens chat session. Renders the same chat UI as
 * `/lens`, but seeded with the sessionId from the URL — the chat picks it
 * up via GLensChatPage's `initialSessionId` prop and loads the thread.
 *
 * Sessions with dashboards render their GlensDashboard bubble inline, so
 * this route absorbs the old dashboard-only viewer without losing the
 * "share link" flow.
 */
export default function LensSessionPage() {
  const params = useParams()
  const sessionId = typeof params.sessionId === "string" ? params.sessionId : ""

  return (
    <AppShell>
      <GLensChatPage initialSessionId={sessionId} />
    </AppShell>
  )
}
