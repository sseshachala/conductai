"use client"

import { useState } from "react"
import { Check, Search, ShieldOff, RotateCcw, KeyRound, ShieldCheck } from "lucide-react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"

export type McpGovernance = {
  state: "needs_review" | "approved" | "quarantined" | "revoked"
  revision: number
  approved_digest?: string
  observed_digest?: string
}

type Tool = { name: string; description: string; inputSchema: unknown; outputSchema?: unknown; annotations?: unknown }

export function McpReview({ id, governance, onChange }: {
  id: string
  governance?: McpGovernance | null
  onChange: (governance: McpGovernance) => void
}) {
  const { authFetch } = useAuthFetch()
  const [inspection, setInspection] = useState<{ tools: Tool[]; digest: string | null } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const stopped = governance?.state === "quarantined" || governance?.state === "revoked"

  async function run(action: string) {
    if (action === "revoke" && !window.confirm("Remove this registration's saved credential and deny Conduct MCP calls?")) return
    setBusy(true)
    setError("")
    try {
      const res = await authFetch(`${API}/mcp-servers/${id}/${action === "inspect" ? "inspect" : "review"}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        ...(action === "inspect" ? {} : { body: JSON.stringify({ action, revision: governance?.revision ?? 0, digest: inspection?.digest ?? null }) }),
      })
      const body = await res.json()
      if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "MCP review failed")
      if (action === "inspect") setInspection(body)
      else {
        onChange(body.governance)
        setInspection(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "MCP review failed")
    } finally { setBusy(false) }
  }

  return (
    <div style={{ borderTop: "1px solid var(--border)", marginTop: 12, paddingTop: 12, minWidth: 0 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
        <span>{governance ? governance.state.replace(/_/g, " ") : "Review not enabled"}</span>
        {!governance && <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => run("require_review")}><ShieldCheck size={14} /> Require review</button>}
        {governance && !stopped && <>
          <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => run("inspect")}><Search size={14} /> Inspect tools</button>
          <button className="btn btn-ghost btn-sm" disabled={busy || !inspection?.digest} onClick={() => run("approve")}><Check size={14} /> Approve inspected tools</button>
        </>}
        {!stopped && <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => run("quarantine")}><ShieldOff size={14} /> Quarantine</button>}
        {stopped && <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => run("restore")}><RotateCcw size={14} /> Restore for review</button>}
        {governance?.state !== "revoked" && <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => run("revoke")}><KeyRound size={14} /> Revoke saved credential</button>}
      </div>
      {error && <p role="alert" style={{ color: "var(--err)" }}>{error}</p>}
      {inspection && <div style={{ marginTop: 8, overflowWrap: "anywhere" }}>
        <div>{inspection.tools.length} tools · {inspection.digest === governance?.approved_digest ? "Matches approval" : "Review required"}</div>
        {inspection.tools.map(tool => <details key={tool.name} style={{ padding: "6px 0" }}>
          <summary>{tool.name}</summary>
          <p>{tool.description}</p>
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 240, overflow: "auto" }}>{JSON.stringify({ inputSchema: tool.inputSchema, outputSchema: tool.outputSchema, annotations: tool.annotations }, null, 2)}</pre>
        </details>)}
      </div>}
    </div>
  )
}
