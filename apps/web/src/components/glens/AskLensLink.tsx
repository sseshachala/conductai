"use client"

import Link from "next/link"
import type { MouseEvent } from "react"
import { MessageCircle } from "lucide-react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { lensEntryHref, openLensEntry, type LensEntry } from "@/lib/lens-entry"

export function AskLensLink({ kind, resourceId, blockId, workspaceId }: {
  kind: LensEntry["kind"]; resourceId?: string; blockId?: string; workspaceId?: string
}) {
  const { workspaceId: activeWorkspace } = useAuthFetch()
  const workspace = workspaceId ?? activeWorkspace
  if (!workspace) return null
  let href: string
  const entry = { kind, workspace_id: workspace, resource_id: resourceId, block_id: blockId }
  try {
    href = lensEntryHref(entry)
  } catch { return null }
  return (
    <Link href={href} className="btn btn-ghost btn-sm" title="Ask Lens" onClick={(e: MouseEvent<HTMLAnchorElement>) => {
      e.stopPropagation()
      if (e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey && openLensEntry(entry)) e.preventDefault()
    }}
      style={{ display: "inline-flex", alignItems: "center", gap: 6, whiteSpace: "nowrap" }}>
      <MessageCircle size={14} aria-hidden="true" /> Ask Lens
    </Link>
  )
}
