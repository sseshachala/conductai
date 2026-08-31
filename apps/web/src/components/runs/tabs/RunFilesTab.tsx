"use client"

import type { RunMeta } from "@/components/runs/RunDetailPanel"

export interface RunFilesTabProps {
  run: RunMeta
}

export default function RunFilesTab({ run }: RunFilesTabProps) {
  const triggerCtx = run.state as Record<string, unknown> | null | undefined
  const t = ((triggerCtx?._trigger ?? triggerCtx?.github_issue) ?? {}) as Record<string, unknown>
  const prUrlTrigger = triggerCtx?.pr_url as string | undefined
  const prNumTrigger = (t.pull_request as Record<string, unknown>)?.number as number | undefined

  const state = (run.state ?? {}) as Record<string, unknown>
  const blocks = Object.entries(state).filter(([k]) => !k.startsWith("__") && !k.startsWith("_"))
  const allPrUrls: { url: string; num?: number; block: string; prState?: string | null }[] = []
  const allFiles: { file: string; block: string }[] = []
  let diffStat = ""
  for (const [blockId, val] of blocks) {
    const v = val as Record<string, unknown>
    if (v?.pr_url) allPrUrls.push({ url: v.pr_url as string, num: v.pr_number as number | undefined, block: blockId, prState: (v?.pr_state as string) || (v?.pr_merged ? "merged" : v?.pr_closed ? "closed" : null) })
    if (Array.isArray(v?.files_changed)) {
      for (const f of v.files_changed as string[]) allFiles.push({ file: f, block: blockId })
    }
    if (v?.diff_stat && !diffStat) diffStat = v.diff_stat as string
  }
  if (prUrlTrigger && !allPrUrls.find(p => p.url === prUrlTrigger)) {
    allPrUrls.push({ url: prUrlTrigger, num: prNumTrigger, block: "trigger", prState: null })
  }

  if (allPrUrls.length === 0 && allFiles.length === 0 && !diffStat) return (
    <div style={{ textAlign: "center", padding: "48px 0" }}>
      <p style={{ fontSize: 14, fontWeight: 600, color: "var(--text-2)", marginBottom: 6 }}>No file artifacts yet</p>
      <p style={{ fontSize: 13, color: "var(--text-muted)" }}>PRs opened and files changed will appear here once the run completes.</p>
    </div>
  )

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {allPrUrls.length > 0 && (
        <div>
          <p className="eyebrow" style={{ marginBottom: 10 }}>Pull request</p>
          {allPrUrls.map((pr, i) => (
            <div key={i} className="card" style={{ padding: "15px 18px", display: "flex", alignItems: "center", gap: 12, marginBottom: i < allPrUrls.length - 1 ? 8 : 0 }}>
              <span style={{ width: 32, height: 32, borderRadius: 8, background: "var(--text)", color: "var(--surface)", display: "grid", placeItems: "center", flexShrink: 0 }}>
                <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><circle cx={18} cy={18} r={3}/><circle cx={6} cy={6} r={3}/><path d="M13 6h3a2 2 0 0 1 2 2v7"/><line x1={6} y1={9} x2={6} y2={21}/></svg>
              </span>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 650, fontSize: 14 }}>{pr.num ? `#${pr.num} · Pull Request` : "Pull Request"}</div>
                <div className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>{pr.prState ?? "open"}</div>
              </div>
              <a href={pr.url} target="_blank" rel="noopener noreferrer" className="btn btn-ghost btn-sm" style={{ color: "var(--accent-text)", borderColor: "var(--accent-ring, var(--border))", textDecoration: "none" }}>Open →</a>
            </div>
          ))}
        </div>
      )}
      {allFiles.length > 0 && (
        <div>
          <p className="eyebrow" style={{ marginBottom: 10 }}>Diff summary</p>
          <div className="card" style={{ overflow: "hidden" }}>
            {allFiles.map(({ file }, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 16px", borderBottom: i < allFiles.length - 1 ? "1px solid var(--border)" : "none" }}>
                <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{ color: "var(--text-muted)", flexShrink: 0 }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                <span className="mono" style={{ fontSize: 12.5, flex: 1 }}>{file}</span>
              </div>
            ))}
            {diffStat && (
              <div style={{ padding: "10px 16px", fontSize: 12, color: "var(--text-muted)", background: "var(--surface-2)" }}>{diffStat}</div>
            )}
          </div>
        </div>
      )}
      {!allFiles.length && diffStat && (
        <div>
          <p className="eyebrow" style={{ marginBottom: 8 }}>Diff Summary</p>
          <pre className="card mono" style={{ background: "var(--surface-3)", fontSize: 12, padding: "14px 16px", overflowX: "auto", whiteSpace: "pre-wrap", color: "var(--text-2)" }}>{diffStat}</pre>
        </div>
      )}
    </div>
  )
}
