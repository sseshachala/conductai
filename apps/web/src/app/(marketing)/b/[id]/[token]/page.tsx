"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import Link from "next/link"

import { BlockReceiptCard } from "@/components/guard/BlockReceiptCard"
import { blocks, type BlockReceipt } from "@/lib/api/guard"

/**
 * Anonymous trial receipt page (#1712 Track 1 quick win 2/3).
 *
 * Short public URL — the token in the path is checked server-side against
 * a sha256 hash stored on the audit row, and the workspace must still be
 * on the trial plan (see apps/api/app/modules/guard/routers/blocks.py).
 *
 * This is the Priya-story moment: Cursor error → click → receipt + Lens
 * prompts without logging in. The Lens CTAs route through /sign-up?next=
 * so activation converts to a real workspace.
 */
export default function PublicBlockReceiptPage() {
  const params = useParams()
  const id = typeof params.id === "string" ? params.id : ""
  const token = typeof params.token === "string" ? params.token : ""

  const [receipt, setReceipt] = useState<BlockReceipt | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!id || !token) return
    let cancelled = false
    blocks
      .getPublic(id, token)
      .then((r) => { if (!cancelled) setReceipt(r) })
      .catch((e: Error) => { if (!cancelled) setErr(e.message) })
    return () => { cancelled = true }
  }, [id, token])

  return (
    <main style={{ minHeight: "100vh", padding: "48px 0", background: "var(--bg)" }}>
      <div style={{ maxWidth: 760, margin: "0 auto 24px", padding: "0 16px" }}>
        <Link href="/" style={{ fontSize: 12, color: "var(--muted)", textDecoration: "none" }}>
          ← conduct.ai
        </Link>
      </div>
      {err && (
        <div style={{ maxWidth: 640, margin: "48px auto", padding: 16, color: "var(--muted)" }}>
          This receipt link is expired or invalid. Trial receipts are
          preserved for the life of the trial workspace.
        </div>
      )}
      {!err && receipt && <BlockReceiptCard receipt={receipt} mode="public" />}
    </main>
  )
}
