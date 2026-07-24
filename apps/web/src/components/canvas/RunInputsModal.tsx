"use client"

import { useEffect, useState } from "react"
import { workflows } from "@/lib/api"
import type { AuthFetch } from "@/lib/api"

interface MissingInput {
  key: string
  label: string
  type: string
}

interface InputSpec {
  type?: string
  label?: string
  default?: unknown
  options?: string[]
  hint?: string
  placeholder?: string
}

interface Props {
  open: boolean
  workflowId: string
  getToken: (() => Promise<string | null>) | null
  workspaceId: string
  initialInputs: Record<string, unknown>
  onConfirm: (inputs: Record<string, unknown>) => void
  onCancel: () => void
}

export default function RunInputsModal({
  open,
  workflowId,
  getToken,
  workspaceId,
  initialInputs,
  onConfirm,
  onCancel,
}: Props) {
  const [missing, setMissing] = useState<MissingInput[]>([])
  const [spec, setSpec] = useState<Record<string, InputSpec>>({})
  const [values, setValues] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    ;(async () => {
      try {
        const authFetch: AuthFetch = async (url, opts) => {
          const headers: Record<string, string> = { ...(opts?.headers as Record<string, string> | undefined) }
          if (getToken) { const t = await getToken(); if (t) headers["Authorization"] = `Bearer ${t}` }
          if (workspaceId) headers["X-Workspace-ID"] = workspaceId
          return fetch(url, { ...opts, headers })
        }
        const res = await workflows.validateInputs(authFetch, workflowId, { inputs: initialInputs, phase: "run" })
        if (!res.ok) { onCancel(); return }
        const data = await res.json()
        setSpec(data.inputs_spec || {})
        setMissing(data.missing || [])
        const v: Record<string, string> = {}
        for (const m of (data.missing || []) as MissingInput[]) v[m.key] = ""
        setValues(v)
      } catch {
        onCancel()
      } finally {
        setLoading(false)
      }
    })()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, workflowId])

  if (!open) return null

  function handleSubmit() {
    onConfirm({ ...initialInputs, ...values })
  }

  const allFilled = missing.every(m => values[m.key]?.trim())

  return (
    <div
      style={{ position: "fixed", inset: 0, zIndex: 200, background: "rgba(0,0,0,0.45)", backdropFilter: "blur(4px)", display: "flex", alignItems: "center", justifyContent: "center" }}
      onClick={onCancel}
    >
      <div
        className="card"
        onClick={e => e.stopPropagation()}
        style={{ width: 480, maxWidth: "calc(100vw - 32px)", maxHeight: "80vh", overflow: "auto", padding: 24, boxShadow: "var(--shadow-lg)" }}
      >
        <h2 style={{ fontSize: 18, fontWeight: 600, color: "var(--text)", margin: 0, marginBottom: 6 }}>
          Required inputs
        </h2>
        <p style={{ fontSize: 13, color: "var(--text-3)", margin: "0 0 16px" }}>
          This run needs the following before it can start.
        </p>
        {loading ? (
          <p style={{ fontSize: 13, color: "var(--text-3)" }}>Loading…</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {missing.map(m => {
              const s = spec[m.key] || {}
              return (
                <div key={m.key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label style={{ fontSize: 13, fontWeight: 500, color: "var(--text-2)" }}>
                    {m.label} <span style={{ color: "var(--err)" }}>*</span>
                  </label>
                  {s.type === "select" && s.options?.length ? (
                    <select
                      value={values[m.key] || ""}
                      onChange={e => setValues({ ...values, [m.key]: e.target.value })}
                      style={{ height: 36, border: "1px solid var(--border)", borderRadius: 8, padding: "0 12px", fontSize: 13, background: "var(--surface)", color: "var(--text)" }}
                    >
                      <option value="">Select…</option>
                      {s.options.map(o => <option key={String(o)} value={String(o)}>{String(o)}</option>)}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={values[m.key] || ""}
                      onChange={e => setValues({ ...values, [m.key]: e.target.value })}
                      placeholder={s.placeholder || ""}
                      style={{ height: 36, border: "1px solid var(--border)", borderRadius: 8, padding: "0 12px", fontSize: 13, background: "var(--surface)", color: "var(--text)" }}
                    />
                  )}
                  {s.hint && <span style={{ fontSize: 12, color: "var(--text-3)" }}>{s.hint}</span>}
                </div>
              )
            })}
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
          <button onClick={onCancel} className="btn btn-ghost btn-sm">Cancel</button>
          <button onClick={handleSubmit} disabled={!allFilled || loading} className="btn btn-primary btn-sm">
            Run
          </button>
        </div>
      </div>
    </div>
  )
}
