"use client"

import { authEnabled } from "@/lib/auth/runtime"
import { useParams } from "next/navigation"
import { useAuth } from "@/lib/auth/client"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { DeepDiveContent } from "./_sections/DeepDiveContent"

// ─── Auth wrapper (optional — benchmark is public) ────────────────────────────

function DeepDiveWithAuth({
  editionSlug,
  playbookSlug,
}: {
  editionSlug: string
  playbookSlug: string
}) {
  const { getToken, isLoaded } = useAuth()
  const { activeWorkspace } = useWorkspace()
  if (!isLoaded) return null
  return <DeepDiveContent editionSlug={editionSlug} playbookSlug={playbookSlug} getToken={getToken} workspaceId={activeWorkspace?.id ?? null} />
}

export default function BenchmarkDeepDivePage() {
  const params = useParams()
  const editionSlug  = Array.isArray(params.edition) ? params.edition[0] : (params.edition as string)
  const playbookSlug = Array.isArray(params.slug)    ? params.slug[0]    : (params.slug    as string)
  const clerkEnabled = authEnabled()
  if (clerkEnabled) return <DeepDiveWithAuth editionSlug={editionSlug} playbookSlug={playbookSlug} />
  return <DeepDiveContent editionSlug={editionSlug} playbookSlug={playbookSlug} getToken={null} workspaceId={null} />
}
