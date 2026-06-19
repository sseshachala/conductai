"use client"

import { WorkspaceProvider } from "@/lib/WorkspaceContext"
import { GuardRoleClerkProvider, GuardRoleAdminProvider } from "@/lib/GuardRoleContext"

function GuardRoleProviderBranch({ children }: { children: React.ReactNode }) {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  if (clerkEnabled) return <GuardRoleClerkProvider>{children}</GuardRoleClerkProvider>
  return <GuardRoleAdminProvider>{children}</GuardRoleAdminProvider>
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  return (
    <WorkspaceProvider clerkEnabled={clerkEnabled}>
      <GuardRoleProviderBranch>{children}</GuardRoleProviderBranch>
    </WorkspaceProvider>
  )
}
