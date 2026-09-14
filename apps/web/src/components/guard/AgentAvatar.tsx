"use client"

import Link from "next/link"
import { Bot } from "lucide-react"
import type { MouseEvent as ReactMouseEvent } from "react"

export function AgentAvatar({ agentId, size = 22 }: { agentId?: string | null; size?: number }) {
  const avatar = (
    <span
      aria-label="Agent identity"
      title={agentId ? `Agent identity ${agentId}` : "Agent identity not attached"}
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        flex: "0 0 auto",
        background: "#e0e7ff",
        color: "#3730a3",
      }}
    >
      <Bot size={Math.round(size * 0.62)} strokeWidth={2.2} aria-hidden="true" />
    </span>
  )

  if (!agentId) return avatar
  return (
    <Link href={`/agent-identity?tab=identities&id=${agentId}`} onClick={(e: ReactMouseEvent<HTMLAnchorElement>) => e.stopPropagation()} style={{ display: "inline-flex", textDecoration: "none" }}>
      {avatar}
    </Link>
  )
}
