"use client"

import { useEffect } from "react"
import { useRouter, useSearchParams } from "next/navigation"

const TAB_TO_URL: Record<string, string> = {
  notifications: "/theguard/connections/notifications",
  sync:          "/theguard/connections/sync",
  guardrails:    "/theguard/spend/optimization",
  enforcement:   "/theguard/policies/enforcement",
}

// Legacy Guard settings route. All four panels moved to their own URLs;
// this file now just redirects — kept so old bookmarks and rail links
// (AppShell / GuardShell still point here) keep working.
export default function GuardSettingsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()

  useEffect(() => {
    const tab = searchParams?.get("tab") ?? ""
    router.replace(TAB_TO_URL[tab] ?? "/theguard/policies/enforcement")
  }, [searchParams, router])

  return null
}
