"use client"

import { WorkspaceProvider } from "@/lib/WorkspaceContext"

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  return <WorkspaceProvider clerkEnabled={clerkEnabled}>{children}</WorkspaceProvider>
}
