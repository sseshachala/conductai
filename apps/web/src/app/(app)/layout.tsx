"use client"

import { useEffect } from "react"
import { usePathname, useRouter } from "next/navigation"
import { useAuth } from "@clerk/nextjs"
import { WorkspaceProvider } from "@/lib/WorkspaceContext"
import { GuardRoleClerkProvider, GuardRoleAdminProvider } from "@/lib/GuardRoleContext"

const API = process.env.NEXT_PUBLIC_API_URL ?? ""
const SETUP_VERIFIED_KEY = "conduct_setup_verified"

function GuardRoleProviderBranch({ children }: { children: React.ReactNode }) {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <GuardRoleClerkProvider>{children}</GuardRoleClerkProvider>
  return <GuardRoleAdminProvider>{children}</GuardRoleAdminProvider>
}

// First-time setup gate (#858 slice 1).
// One status fetch per tab session: cached in sessionStorage after the first
// "complete" response so subsequent route navigations skip the network call.
function SetupGate({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { getToken, isLoaded, isSignedIn } = useAuth()

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return
    if (pathname === "/setup") return
    if (typeof window !== "undefined" && sessionStorage.getItem(SETUP_VERIFIED_KEY) === "1") return

    let cancelled = false
    ;(async () => {
      try {
        const token = await getToken?.()
        const headers: Record<string, string> = {}
        if (token) headers["Authorization"] = `Bearer ${token}`
        const res = await fetch(`${API}/me/setup-status`, { headers })
        if (!res.ok || cancelled) return
        const data = await res.json()
        if (cancelled) return
        if (data?.setup_completed === false) {
          router.replace("/setup")
        } else {
          sessionStorage.setItem(SETUP_VERIFIED_KEY, "1")
        }
      } catch { /* fail open */ }
    })()
    return () => { cancelled = true }
  }, [pathname, getToken, isLoaded, isSignedIn, router])

  return <>{children}</>
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  return (
    <WorkspaceProvider clerkEnabled={clerkEnabled}>
      <GuardRoleProviderBranch>
        <SetupGate>{children}</SetupGate>
      </GuardRoleProviderBranch>
    </WorkspaceProvider>
  )
}
