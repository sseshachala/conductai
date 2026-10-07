import type { BlockRow } from "./types"

// ── helpers ───────────────────────────────────────────────────────────────────

export function fmt(ts: string | null) {
  return ts ? new Date(ts).toLocaleString() : "—"
}


/** Pull a human-readable one-liner from a block output */
export function summariseOutput(output: Record<string, unknown>, blockType?: string): string | null {
  if (!output) return null

  // Skipped
  if (output.skipped) return `Skipped — ${output.reason ?? "no integration configured"}`

  // Dry run
  if (output.dry_run) return output.note as string ?? `Dry run — ${output.integration ?? "block"} simulated`

  // Brain output
  if (typeof output.output === "string") {
    const text = output.output.slice(0, 120)
    return text + (output.output.length > 120 ? "…" : "")
  }

  // GitHub
  if (output.pr_url) return `PR opened → ${output.pr_url}`
  if (output.branch) return `Branch created: ${output.branch}`
  if (output.html_url && output.clone_url) return `Repo created: ${output.html_url}`
  if (output.full_name) return `Repo: ${output.full_name} (${output.default_branch})`
  if (output.pull_requests) return `${(output.pull_requests as unknown[]).length} pull request(s) found`

  // Output block (slack / email / both)
  if (output.sent === true && output.integration) {
    const parts: string[] = []
    const slack = output.slack as Record<string, unknown> | undefined
    const email = output.email as Record<string, unknown> | undefined
    if (slack?.channel) parts.push(`Slack → ${slack.channel}`)
    if (email?.to) parts.push(`Email → ${email.to}`)
    if (parts.length) return parts.join("  ·  ")
    return `Sent via ${output.integration}`
  }
  // Slack direct (legacy)
  if (output.ts && output.channel) return `Message sent to ${output.channel}`
  // Email direct (legacy)
  if (output.sent === true && output.to) return `Email sent to ${output.to} — "${output.subject}"`
  if (output.sent === false) return `Not sent — ${output.reason}`

  // Linear
  if (output.identifier && output.title) return `${output.identifier}: ${output.title}`
  if (output.issues) return `${(output.issues as unknown[]).length} issue(s) fetched`
  if (output.success === true && output.comment_id) return `Comment posted`

  // DigitalOcean
  if (output.droplet_id && output.status) return `Droplet ${output.droplet_id} — ${output.status}${output.ip_address ? ` (${output.ip_address})` : ""}`
  if (output.destroyed) return `Droplet ${output.droplet_id} destroyed`

  // Vercel
  if (output.state && output.url) return `Deployment ${output.state} → ${output.url}`
  if (output.deployments && Array.isArray(output.deployments) && output.url === undefined) {
    const count = (output.deployments as unknown[]).length
    return `${count} deployment(s) listed`
  }

  // Railway
  if (output.triggered && output.service_id) return `Railway service ${output.service_id} redeployment triggered`
  if (output.services && Array.isArray(output.services)) return `${(output.services as unknown[]).length} Railway service(s) found`
  if (output.id && output.status && !output.state) return `Railway deployment ${output.status}`

  // Logic
  if (output.route) return `Route: ${output.route}${output.exit_code !== undefined ? ` (exit code ${output.exit_code})` : ""}`

  // Approval
  if (output.decision) return `Decision: ${output.decision}`
  if (output.status === "approval_required") return "Waiting for human approval…"

  // Trigger
  if (output.triggered) return "Triggered successfully"

  return null
}

/** Returns true when an error string indicates a timeout rather than a logic failure */
export function isTimeoutError(error: string | undefined): boolean {
  if (!error) return false
  const s = error.toLowerCase()
  return s.includes("timed out") || s.includes("timeouterror") || s.includes("did not become")
}

// ── Design-token inline style helpers ────────────────────────────────────────

export function statusBadgeStyle(status: string): React.CSSProperties {
  switch (status) {
    case "running":   return { background: "var(--info-bg, #eff6ff)", color: "var(--info, #2563eb)" }
    case "succeeded": return { background: "var(--ok-bg, #f0fdf4)",   color: "var(--ok, #16a34a)" }
    case "failed":    return { background: "var(--err-bg, #fef2f2)",  color: "var(--err, #dc2626)" }
    case "paused":    return { background: "var(--warn-bg, #fffbeb)", color: "var(--warn, #d97706)" }
    case "timed_out": return { background: "var(--warn-bg, #fffbeb)", color: "var(--warn, #d97706)" }
    default:          return { background: "var(--surface-3, #f5f5f4)", color: "var(--text-3, #78716c)" }
  }
}

export function typeChipStyle(type: string): React.CSSProperties {
  switch (type) {
    case "trigger":  return { background: "var(--blk-trigger-bg, #eff6ff)", color: "var(--blk-trigger-dot, #2563eb)" }
    case "brain":    return { background: "var(--blk-brain-bg, #f5f3ff)",   color: "#7c3aed" }
    case "tool":     return { background: "var(--blk-memory-bg, #fef9c3)",  color: "var(--warn, #d97706)" }
    case "logic":    return { background: "var(--surface-3, #f5f5f4)",      color: "var(--text-3, #78716c)" }
    case "approval": return { background: "var(--warn-bg, #fffbeb)",        color: "var(--warn, #d97706)" }
    case "output":   return { background: "var(--err-bg, #fef2f2)",         color: "var(--err, #dc2626)" }
    case "cleanup":  return { background: "var(--surface-2, #fafaf9)",      color: "var(--text-muted, #a8a29e)" }
    default:         return { background: "var(--surface-3, #f5f5f4)",      color: "var(--text-3, #78716c)" }
  }
}

export const FILE_ACTION_COLOR: Record<string, string> = {
  created:  "var(--ok, #16a34a)",
  modified: "var(--info, #2563eb)",
  deleted:  "var(--err, #dc2626)",
}

export const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
}

export function formatModelLabel(model: string): string {
  if (model === "claude-opus-4-7") return "Claude Opus 4.7"
  if (model === "claude-sonnet-4-6") return "Claude Sonnet 4.6"
  if (model === "claude-haiku-4-5-20251001") return "Claude Haiku 4.5"
  if (model === "gpt-4.1") return "GPT-4.1"
  if (model === "gpt-4.1-mini") return "GPT-4.1 Mini"
  return model
}

export function dotStyle(row: BlockRow, isSkipped: boolean): React.CSSProperties {
  let borderColor: string
  let background: string
  let animation: string | undefined

  if (row.status === "completed" && !isSkipped) {
    borderColor = "var(--ok, #16a34a)"; background = "var(--ok, #16a34a)"
  } else if (row.status === "failed" && row.timedOut) {
    borderColor = "var(--warn, #d97706)"; background = "var(--warn, #d97706)"
  } else if (row.status === "failed") {
    borderColor = "var(--err, #dc2626)"; background = "var(--err, #dc2626)"
  } else if (row.status === "running") {
    borderColor = "var(--info, #2563eb)"; background = "var(--info, #2563eb)"; animation = "pulse 2s cubic-bezier(.4,0,.6,1) infinite"
  } else if (isSkipped) {
    borderColor = "var(--surface-3, #f5f5f4)"; background = "var(--surface-3, #f5f5f4)"
  } else {
    borderColor = "var(--surface-3, #f5f5f4)"; background = "var(--surface-3, #f5f5f4)"
  }

  return {
    width: 13,
    height: 13,
    borderRadius: "50%",
    border: `2px solid ${borderColor}`,
    background,
    display: "grid",
    placeItems: "center",
    boxShadow: "0 0 0 4px var(--bg, #fff)",
    ...(animation ? { animation } : {}),
  }
}

export function cardStyle(row: BlockRow): React.CSSProperties {
  if (row.status === "failed" && row.timedOut) {
    return { flex: 1, padding: "12px 15px", background: "var(--warn-bg, #fffbeb)", borderColor: "var(--warn-bd, #fde68a)" }
  }
  if (row.status === "failed") {
    return { flex: 1, padding: "12px 15px", background: "var(--err-bg, #fef2f2)", borderColor: "var(--err-bd, #fecaca)" }
  }
  if (row.output?.status === "approval_required") {
    return { flex: 1, padding: "12px 15px", background: "var(--warn-bg, #fffbeb)", borderColor: "var(--warn-bd, #fde68a)" }
  }
  return { flex: 1, padding: "12px 15px" }
}
