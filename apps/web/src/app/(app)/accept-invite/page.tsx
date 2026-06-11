"use client"

import { useEffect } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Suspense } from "react"

function AcceptInviteInner() {
  const router = useRouter()
  const params = useSearchParams()

  useEffect(() => {
    const workspaceId = params.get("workspace_id")
    if (workspaceId) {
      document.cookie = `delegator_project_id=${workspaceId}; path=/; max-age=31536000; SameSite=Lax`
    }
    router.replace("/guard")
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center bg-stone-50">
      <p className="text-sm text-stone-400">Joining workspace…</p>
    </div>
  )
}

export default function AcceptInvitePage() {
  return (
    <Suspense>
      <AcceptInviteInner />
    </Suspense>
  )
}
