"use client"

import { useAuth } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import AuditLog from "@/components/settings/AuditLog"

export default function AuditPage() {
  const { getToken } = useAuth()

  return (
    <AppShell>
      <div
        style={{
          maxWidth: 960,
          margin: "0 auto",
          padding: "32px 24px",
          display: "flex",
          flexDirection: "column",
          gap: 24,
        }}
      >
        <div>
          <h1
            style={{
              fontSize: 20,
              fontWeight: 600,
              color: "var(--text)",
              margin: 0,
            }}
          >
            Audit Log
          </h1>
          <p
            style={{
              fontSize: 13,
              color: "var(--text-3)",
              marginTop: 4,
              marginBottom: 0,
            }}
          >
            All workspace activity — credential changes, agent runs, and member events.
          </p>
        </div>
        <AuditLog workspaceId="" getToken={getToken} />
      </div>
    </AppShell>
  )
}
