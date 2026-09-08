"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"

import AppShell from "@/components/AppShell"
import { BlockReceiptCard } from "@/components/guard/BlockReceiptCard"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { blocks, type BlockReceipt } from "@/lib/api/guard"

/**
 * Workspace block-receipt page (#1712 Track 1 quick win 2/3).
 *
 * URL emitted in every Guard block response (`error.receipt_url`). Users
 * signed into their workspace land here to see the receipt + jump into a
 * Lens conversation seeded with a receipt-scoped question.
 */
export default function BlockReceiptPage() {
  const params = useParams()
  const id = typeof params.id === "string" ? params.id : ""
  const { authFetch, workspaceId } = useAuthFetch()

  const [receipt, setReceipt] = useState<BlockReceipt | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!id || !workspaceId) return
    let cancelled = false
    blocks
      .get(authFetch, id)
      .then((r) => { if (!cancelled) setReceipt(r) })
      .catch((e: Error) => { if (!cancelled) setErr(e.message) })
    return () => { cancelled = true }
  }, [id, workspaceId, authFetch])

  return (
    <AppShell>
      {err && (
        <div style={{ maxWidth: 640, margin: "48px auto", padding: 16, color: "var(--muted)" }}>
          Receipt not found. It may have been purged or belongs to another workspace.
        </div>
      )}
      {!err && receipt && <BlockReceiptCard receipt={receipt} />}
    </AppShell>
  )
}
