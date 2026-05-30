"use client"

import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import AuditLog from "@/components/settings/AuditLog"

export default function AuditPage() {
  const { getToken } = useAuth()

  return (
    <AppShell>
      <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        <div>
          <h1 className="text-xl font-semibold text-stone-900">Audit Log</h1>
          <p className="text-sm text-stone-500 mt-1">
            All workspace activity — credential changes, agent runs, and member events.
          </p>
        </div>
        <AuditLog workspaceId="" getToken={getToken} />
      </div>
    </AppShell>
  )
}
