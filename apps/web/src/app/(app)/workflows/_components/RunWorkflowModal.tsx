"use client"

import type { RefObject } from "react"

export interface RunWorkflowModalProps {
  runModal: { id: string; name: string }
  runModalRef: RefObject<HTMLDivElement>
  setRunModal: (v: { id: string; name: string } | null) => void
  runStep: "configure" | "review"
  setRunStep: (v: "configure" | "review") => void
  runParams: string
  setRunParams: (v: string) => void
  runGuard: boolean
  setRunGuard: (v: boolean) => void
  runDryRun: boolean
  setRunDryRun: (v: boolean) => void
  runError: string | null
  runLoading: boolean
  runWorkflow: () => void
}

// Extracted verbatim from the workflows page run modal.
export function RunWorkflowModal({ runModal, runModalRef, setRunModal, runStep, setRunStep, runParams, setRunParams, runGuard, setRunGuard, runDryRun, setRunDryRun, runError, runLoading, runWorkflow }: RunWorkflowModalProps) {
  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={() => { setRunModal(null); setRunStep("configure") }}
    >
      {/* #23: wrapped in form with onSubmit; #7: ref for focus trap */}
      <div
        ref={runModalRef}
        style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, boxShadow: "var(--shadow-lg)", padding: 24, width: 440, maxWidth: "90vw" }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ fontWeight: 650, fontSize: 15, marginBottom: 16 }}>Run — {runModal.name}</div>

        {runStep === "configure" ? (
          <form onSubmit={e => { e.preventDefault(); setRunStep("review") }}>
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>Parameters (optional)</div>
              {/* #23: maxHeight to cap textarea resize */}
              <textarea
                rows={4}
                value={runParams}
                onChange={e => setRunParams(e.target.value)}
                placeholder={"MODEL=claude-sonnet-4-6\nBRANCH=main"}
                style={{ width: "100%", fontSize: 12.5, fontFamily: "var(--font-mono, monospace)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 12px", background: "var(--surface-2)", color: "var(--text)", resize: "vertical", maxHeight: 200, boxSizing: "border-box" }}
              />
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>One KEY=VALUE per line</div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
                <input type="checkbox" checked={runGuard} onChange={e => setRunGuard(e.target.checked)} />
                Enable Guard
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
                <input type="checkbox" checked={runDryRun} onChange={e => setRunDryRun(e.target.checked)} />
                Dry run (simulate without executing)
              </label>
            </div>

            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button type="button" className="btn btn-ghost" onClick={() => { setRunModal(null); setRunStep("configure") }}>Cancel</button>
              <button type="submit" className="btn btn-primary">Review →</button>
            </div>
          </form>
        ) : (
          <div>
            <div style={{ marginBottom: 16 }}>
              {(() => {
                const parsedInputs = runParams
                  .split("\n")
                  .map(l => l.trim())
                  .filter(l => l.includes("="))
                  .map(l => { const i = l.indexOf("="); return [l.slice(0, i).trim(), l.slice(i + 1).trim()] as [string, string] })
                return parsedInputs.length > 0 ? (
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, fontFamily: "var(--font-mono, monospace)" }}>
                    <thead>
                      <tr>
                        <th style={{ textAlign: "left", padding: "4px 8px", fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-sans, sans-serif)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>Key</th>
                        <th style={{ textAlign: "left", padding: "4px 8px", fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-sans, sans-serif)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}>Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {parsedInputs.map(([k, v], i) => (
                        <tr key={i} style={{ borderTop: "1px solid var(--border)" }}>
                          <td style={{ padding: "6px 8px", color: "var(--text-2)" }}>{k}</td>
                          <td style={{ padding: "6px 8px", color: "var(--text)" }}>{v}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p style={{ fontSize: 13, color: "var(--text-muted)", margin: 0 }}>No parameters — using workflow defaults.</p>
                )
              })()}
            </div>

            {runError && <div style={{ fontSize: 12, color: "var(--err)", marginBottom: 12 }}>{runError}</div>}

            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button type="button" className="btn btn-ghost" onClick={() => setRunStep("configure")}>← Back</button>
              <button type="button" className="btn btn-primary" disabled={runLoading} onClick={() => runWorkflow()}>
                {runLoading ? "Starting…" : "Run now"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
