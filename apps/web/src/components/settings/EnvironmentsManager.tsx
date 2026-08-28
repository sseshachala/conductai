"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { environments as environmentsApi, credentials } from "@/lib/api"

interface Environment {
  id: string
  name: string
  created_at: string
  allowed_hosts?: string[] | null
}

interface EnvVar { key: string; value: string; handle?: string }

// Canonical env var names are uppercase by convention (POSIX + 12-factor).
function normalizeKey(raw: string): string {
  return raw.trim().toUpperCase()
}

function EyeIcon({ open }: { open: boolean }) {
  return open ? (
    <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
    </svg>
  ) : (
    <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
    </svg>
  )
}

export default function EnvironmentsManager({ isAdmin = true }: { isAdmin?: boolean }) {
  return <EnvironmentsManagerInner isAdmin={isAdmin} />
}

function EnvironmentsManagerInner({ isAdmin }: { isAdmin: boolean }) {
  const { activeWorkspace } = useWorkspace()
  const { authFetch } = useAuthFetch()
  const [environments, setEnvironments] = useState<Environment[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [showNewEnv, setShowNewEnv] = useState(false)
  const [newEnvName, setNewEnvName] = useState("")
  const [creatingEnv, setCreatingEnv] = useState(false)
  const [createError, setCreateError] = useState("")
  const loadingRef = useRef(false)

  const loadEnvironments = useCallback(async () => {
    if (loadingRef.current) return
    loadingRef.current = true
    try {
      const envs: Environment[] = await environmentsApi.list(authFetch)
      setEnvironments(envs)
      if (envs.length > 0 && !activeId) setActiveId(envs[0].id)
    } catch { /* silent */ }
    finally {
      loadingRef.current = false
      setListLoading(false)
    }
  }, [activeId, authFetch])

  useEffect(() => { loadEnvironments() }, [loadEnvironments])

  async function addEnv() {
    const name = newEnvName.trim()
    if (!name) return
    setCreatingEnv(true)
    setCreateError("")
    try {
      const res = await environmentsApi.create(authFetch, { name })
      if (res.ok) {
        setNewEnvName("")
        setShowNewEnv(false)
        setCreateError("")
        await loadEnvironments()
      } else {
        const body = await res.json().catch(() => ({}))
        setCreateError(body?.detail ?? `Create failed (${res.status})`)
      }
    } catch { setCreateError("Network error — could not create vault.") }
    finally { setCreatingEnv(false) }
  }

  if (listLoading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {[1, 2].map(i => (
          <div key={i} style={{ height: 64, borderRadius: 12, background: "var(--surface-2)", border: "1px solid var(--border)", opacity: 0.7 }} />
        ))}
      </div>
    )
  }

  if (environments.length === 0) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 14, alignItems: "center", padding: "40px 0", textAlign: "center" }}>
        <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No vaults yet.</p>
        {showNewEnv ? (
          <>
            <div style={{ display: "flex", gap: 8, maxWidth: 380 }}>
              <input autoFocus value={newEnvName} onChange={e => setNewEnvName(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") addEnv(); if (e.key === "Escape") { setShowNewEnv(false); setNewEnvName("") } }}
                placeholder="e.g. Production"
                style={{ flex: 1, border: "1px solid var(--border)", borderRadius: 9, padding: "8px 12px", fontSize: 13.5, color: "var(--text)", background: "var(--surface)", outline: "none" }} />
              <button onClick={addEnv} disabled={creatingEnv || !newEnvName.trim()} className="btn btn-primary btn-sm" style={{ opacity: (creatingEnv || !newEnvName.trim()) ? 0.4 : 1 }}>
                {creatingEnv ? "Creating…" : "Create"}
              </button>
              <button onClick={() => { setShowNewEnv(false); setNewEnvName(""); setCreateError("") }} className="btn btn-ghost btn-sm">Cancel</button>
            </div>
            {createError && <p style={{ fontSize: 12, color: "var(--err)", marginTop: 4 }}>{createError}</p>}
          </>
        ) : (
          <button className="btn btn-primary btn-sm" onClick={() => setShowNewEnv(true)}>+ New vault</button>
        )}
      </div>
    )
  }

  const activeEnv = environments.find(e => e.id === activeId) ?? environments[0]

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
        {environments.map(e => {
          const on = e.id === activeEnv.id
          return (
            <button key={e.id} onClick={() => setActiveId(e.id)} className="chip" style={{ height: 32, cursor: "pointer", fontWeight: 600, gap: 7,
              background: on ? "var(--accent-weak)" : "var(--surface)", borderColor: on ? "var(--accent-ring)" : "var(--border)", color: on ? "var(--accent-text)" : "var(--text-2)" }}>
              {e.name}
            </button>
          )
        })}
        {showNewEnv ? (
          <>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input autoFocus value={newEnvName} onChange={e => setNewEnvName(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") addEnv(); if (e.key === "Escape") { setShowNewEnv(false); setNewEnvName("") } }}
                placeholder="Vault name"
                style={{ height: 32, border: "1px solid var(--border)", borderRadius: 8, padding: "0 10px", fontSize: 13, color: "var(--text)", background: "var(--surface)", outline: "none" }} />
              <button onClick={addEnv} disabled={creatingEnv || !newEnvName.trim()} className="btn btn-primary btn-sm" style={{ height: 32, opacity: (creatingEnv || !newEnvName.trim()) ? 0.4 : 1 }}>
                {creatingEnv ? "…" : "Create"}
              </button>
              <button onClick={() => { setShowNewEnv(false); setNewEnvName(""); setCreateError("") }} className="btn btn-ghost btn-sm" style={{ height: 32 }}>✕</button>
            </div>
            {createError && <p style={{ fontSize: 12, color: "var(--err)", margin: "4px 0 0" }}>{createError}</p>}
          </>
        ) : (
          <button onClick={() => setShowNewEnv(true)} className="btn btn-ghost btn-sm" style={{ height: 32 }}>+ New vault</button>
        )}
      </div>

      <EnvironmentDetail
        key={activeEnv.id}
        environment={activeEnv}
        authFetch={authFetch}
        isAdmin={isAdmin}
      />
    </div>
  )
}

function EnvironmentDetail({
  environment,
  authFetch,
  isAdmin,
}: {
  environment: Environment
  authFetch: (url: string, opts?: RequestInit) => Promise<Response>
  isAdmin: boolean
}) {
  const [vars, setVars] = useState<EnvVar[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")
  const [saved, setSaved] = useState(false)
  const [showValues, setShowValues] = useState<Record<string, boolean>>({})
  const [newKey, setNewKey] = useState("")
  const [newValue, setNewValue] = useState("")
  const [showNew, setShowNew] = useState(false)
  const [showPaste, setShowPaste] = useState(false)
  const [pasteText, setPasteText] = useState("")
  const [confirmVarIndex, setConfirmVarIndex] = useState<number | null>(null)
  const [pendingImport, setPendingImport] = useState<{ vars: EnvVar[]; newCount: number; updateCount: number } | null>(null)
  const [confirmVarValue, setConfirmVarValue] = useState("")
  const [confirmHost, setConfirmHost] = useState<string | null>(null)
  const [confirmHostValue, setConfirmHostValue] = useState("")

  const [hosts, setHosts] = useState<string[]>(environment.allowed_hosts ?? [])
  const [hostInput, setHostInput] = useState("")
  const [hostSaving, setHostSaving] = useState(false)

  async function saveHosts(updated: string[]) {
    setHostSaving(true)
    try {
      await environmentsApi.update(authFetch, environment.id, { allowed_hosts: updated.length > 0 ? updated : null })
    } finally { setHostSaving(false) }
  }

  function addHost() {
    const h = hostInput.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/.*$/, "")
    if (!h || hosts.includes(h)) { setHostInput(""); return }
    const updated = [...hosts, h]
    setHosts(updated)
    setHostInput("")
    saveHosts(updated)
  }

  function removeHost(h: string) {
    const updated = hosts.filter(x => x !== h)
    setHosts(updated)
    saveHosts(updated)
  }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await credentials.envVars.get(authFetch, environment.id)
      setVars(Array.isArray(data) ? data : [])
    } finally { setLoading(false) }
  }, [authFetch, environment.id])

  useEffect(() => { load() }, [load])

  async function saveAll(updated: EnvVar[]) {
    setSaving(true); setError(""); setSaved(false)
    try {
      const res = await credentials.envVars.update(authFetch, environment.id, updated.map(v => ({ key: v.key, value: v.value })) as unknown as Record<string, unknown>)
      if (!res.ok) throw new Error("Save failed")
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch { setError("Save failed") } finally { setSaving(false) }
  }

  function updateVar(i: number, field: "key" | "value", val: string) {
    setVars(prev => prev.map((v, idx) => idx === i ? { ...v, [field]: val } : v))
  }

  function removeVar(i: number) {
    const updated = vars.filter((_, idx) => idx !== i)
    setVars(updated)
    setConfirmVarIndex(null)
    setConfirmVarValue("")
    saveAll(updated)
  }

  function addVar() {
    if (!newKey.trim()) return
    const key = normalizeKey(newKey)
    const updated = [...vars, { key, value: newValue }]
    setVars(updated)
    setNewKey(""); setNewValue(""); setShowNew(false)
    saveAll(updated)
  }

  function parseEnvText(text: string): EnvVar[] {
    const parsed: EnvVar[] = []
    for (const raw of text.split("\n")) {
      const line = raw.trim()
      if (!line || line.startsWith("#")) continue
      const eq = line.indexOf("=")
      if (eq === -1) continue
      const key = normalizeKey(line.slice(0, eq))
      const value = line.slice(eq + 1).trim().replace(/^["\x27]|["\x27]$/g, "")
      if (key) parsed.push({ key, value })
    }
    return parsed
  }

  function handlePasteImport() {
    const parsed = parseEnvText(pasteText)
    if (parsed.length === 0) { setError("No KEY=value pairs found — check the format."); return }
    const merged = [...vars]
    let newCount = 0, updateCount = 0
    for (const p of parsed) {
      const existing = merged.findIndex(v => v.key === p.key)
      if (existing >= 0) { merged[existing] = p; updateCount++ }
      else { merged.push(p); newCount++ }
    }
    setPendingImport({ vars: merged, newCount, updateCount })
  }

  function confirmImport() {
    if (!pendingImport) return
    setVars(pendingImport.vars)
    saveAll(pendingImport.vars)
    setPendingImport(null)
    setPasteText("")
    setShowPaste(false)
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 22 }}>
        <span style={{ width: 32, height: 32, borderRadius: 8, background: "var(--accent-weak)", color: "var(--accent-text)", display: "grid", placeItems: "center", fontSize: 11, fontWeight: 700, flexShrink: 0 }}>
          {environment.name.slice(0, 2).toUpperCase()}
        </span>
        <div>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", margin: 0 }}>{environment.name}</h2>
          <p style={{ fontSize: 11.5, color: "var(--text-muted)", margin: 0 }}>{vars.length} variable{vars.length !== 1 ? "s" : ""}</p>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <button onClick={() => { setShowPaste(p => !p); setError("") }} className="btn btn-ghost btn-sm">Paste dotenv</button>
          <button onClick={() => saveAll(vars)} disabled={saving} className="btn btn-primary btn-sm" style={{ opacity: saving ? 0.5 : 1 }}>
            {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
          </button>
        </div>
      </div>

      {showPaste && (
        <div className="card" style={{ padding: "14px 16px", background: "var(--surface-2)", marginBottom: 14, display: "flex", flexDirection: "column", gap: 10 }}>
          <p style={{ fontSize: 12, color: "var(--text-2)" }}>Paste the contents of your dotenv file. Existing keys will be overwritten; new keys will be added.</p>
          <textarea
            autoFocus
            value={pasteText}
            onChange={e => setPasteText(e.target.value)}
            placeholder={"GITHUB_TOKEN=ghp_...\nANTHROPIC_API_KEY=sk-ant-...\nSLACK_BOT_TOKEN=xoxb-..."}
            rows={7}
            className="mono"
            style={{ width: "100%", fontSize: 12, color: "var(--text)", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 12px", background: "var(--surface)", outline: "none", resize: "vertical", boxSizing: "border-box" }}
          />
          {pendingImport ? (
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <span style={{ fontSize: 12, color: "var(--text-3)" }}>
                {pendingImport.newCount} new · {pendingImport.updateCount} update — confirm?
              </span>
              <div style={{ display: "flex", gap: 8 }}>
                <button onClick={confirmImport} className="btn btn-primary btn-sm">Confirm import</button>
                <button onClick={() => setPendingImport(null)} className="btn btn-ghost btn-sm">Back</button>
              </div>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={handlePasteImport} className="btn btn-primary btn-sm">Preview</button>
              <button onClick={() => { setShowPaste(false); setPasteText(""); setError("") }} className="btn btn-ghost btn-sm">Cancel</button>
            </div>
          )}
        </div>
      )}

      {error && <p style={{ marginBottom: 10, fontSize: 12, color: "var(--err)" }}>{error}</p>}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", borderBottom: "1px solid var(--border)", padding: "8px 16px", background: "var(--surface-2)" }}>
          <p className="eyebrow">Key</p>
          <p className="eyebrow">Value</p>
          <p style={{ width: 64 }} />
        </div>

        {loading ? (
          <p style={{ fontSize: 13, color: "var(--text-muted)", padding: "20px 16px" }}>Loading…</p>
        ) : vars.length === 0 ? (
          <p style={{ fontSize: 13, color: "var(--text-muted)", padding: "20px 16px" }}>No variables yet — add one or paste a dotenv file.</p>
        ) : (
          vars.map((v, i) => (
            <div key={v.key || i} style={{ borderBottom: i < vars.length - 1 ? "1px solid var(--border)" : "none" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", padding: "8px 16px", alignItems: "center" }}>
                <input
                  value={v.key}
                  onChange={e => updateVar(i, "key", e.target.value)}
                  className="mono"
                  style={{ fontSize: 12, color: "var(--text)", background: "transparent", border: "none", outline: "none", width: "100%", paddingRight: 16 }}
                />
                <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                  <input
                    type={showValues[v.key] ? "text" : "password"}
                    value={v.value}
                    onChange={e => updateVar(i, "value", e.target.value)}
                    className="mono"
                    style={{ fontSize: 12, color: "var(--text-2)", background: "transparent", border: "none", outline: "none", width: "100%", paddingRight: 28 }}
                  />
                  <button type="button" onClick={() => setShowValues(prev => ({ ...prev, [v.key]: !prev[v.key] }))}
                    style={{ position: "absolute", right: 4, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center" }}>
                    <EyeIcon open={!!showValues[v.key]} />
                  </button>
                </div>
                <button
                  onClick={() => {
                    if (confirmVarIndex === i) {
                      setConfirmVarIndex(null)
                      setConfirmVarValue("")
                    } else {
                      setConfirmVarIndex(i)
                      setConfirmVarValue("")
                    }
                  }}
                  style={{ fontSize: 12, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer", width: 64, textAlign: "right" }}
                >
                  Remove
                </button>
              </div>

              {confirmVarIndex === i && (
                <div style={{ margin: "0 16px 10px", padding: "10px 12px", border: "1px solid var(--err-bd)", borderRadius: 10, background: "var(--err-bg)", display: "flex", flexDirection: "column", gap: 8 }}>
                  <p style={{ margin: 0, fontSize: 11, color: "var(--err)" }}>
                    Type <strong>{v.key || "key"}</strong> to confirm removal.
                  </p>
                  <div style={{ display: "flex", gap: 6, width: "100%" }}>
                    <input
                      value={confirmVarValue}
                      onChange={e => setConfirmVarValue(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === "Enter" && confirmVarValue === v.key) removeVar(i)
                        if (e.key === "Escape") { setConfirmVarIndex(null); setConfirmVarValue("") }
                      }}
                      placeholder={v.key || "key"}
                      className="mono"
                      style={{ flex: 1, minWidth: 0, fontSize: 11.5, border: "1px solid var(--err-bd, #fecaca)", borderRadius: 8, padding: "6px 10px", outline: "none", background: "var(--surface)", color: "var(--text)" }}
                    />
                    <button
                      onClick={() => removeVar(i)}
                      disabled={confirmVarValue !== v.key}
                      className="btn btn-sm"
                      style={{ background: "var(--err)", color: "#fff", border: "none", opacity: confirmVarValue !== v.key ? 0.4 : 1 }}
                    >
                      Confirm
                    </button>
                    <button
                      onClick={() => { setConfirmVarIndex(null); setConfirmVarValue("") }}
                      className="btn btn-ghost btn-sm"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))
        )}

        {isAdmin && (showNew ? (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", borderTop: "1px solid var(--border)", padding: "8px 16px", alignItems: "center", background: "var(--surface-2)" }}>
            <input autoFocus value={newKey} onChange={e => setNewKey(e.target.value)} onKeyDown={e => e.key === "Enter" && addVar()}
              placeholder="VARIABLE_NAME" className="mono"
              style={{ fontSize: 12, color: "var(--text)", background: "transparent", border: "none", outline: "none", width: "100%", paddingRight: 16 }} />
            <input value={newValue} onChange={e => setNewValue(e.target.value)} onKeyDown={e => e.key === "Enter" && addVar()}
              placeholder="value" type="password" className="mono"
              style={{ fontSize: 12, color: "var(--text-2)", background: "transparent", border: "none", outline: "none", width: "100%", paddingRight: 16 }} />
            <div style={{ display: "flex", gap: 8, width: 64, justifyContent: "flex-end" }}>
              <button onClick={addVar} style={{ fontSize: 12, fontWeight: 600, color: "var(--ok)", background: "none", border: "none", cursor: "pointer" }}>Add</button>
              <button onClick={() => { setShowNew(false); setNewKey(""); setNewValue("") }} style={{ fontSize: 12, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}>✕</button>
            </div>
          </div>
        ) : (
          <div style={{ borderTop: "1px solid var(--border)", padding: "8px 16px" }}>
            <button onClick={() => setShowNew(true)} style={{ fontSize: 12.5, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer" }}>
              + Add variable
            </button>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 24 }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 8 }}>
          <div>
            <p style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text)" }}>Allowed hosts</p>
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 3 }}>Leave empty for unrestricted outbound access. Use <code className="mono" style={{ fontSize: 11 }}>*.example.com</code> for subdomains. Applies to integration blocks only.</p>
          </div>
          {hostSaving && <span style={{ fontSize: 10.5, color: "var(--text-muted)" }}>Saving…</span>}
        </div>
        <div className="card" style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
          {hosts.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {hosts.map(h => (
                <span key={h} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, background: "var(--warn-bg)", color: "var(--warn)", border: "1px solid var(--warn-bd)", padding: "3px 10px", borderRadius: 20 }} className="mono">
                  {h}
                  {isAdmin && (
                    <button
                      onClick={() => { setConfirmHost(h); setConfirmHostValue("") }}
                      style={{ color: "var(--warn)", background: "none", border: "none", cursor: "pointer", lineHeight: 1, fontSize: 13 }}
                    >
                      ×
                    </button>
                  )}
                </span>
              ))}
            </div>
          )}

          {isAdmin && confirmHost && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <p style={{ margin: 0, fontSize: 12, color: "var(--err)" }}>
                Type <strong>{confirmHost}</strong> to confirm allowed host removal.
              </p>
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  value={confirmHostValue}
                  onChange={e => setConfirmHostValue(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === "Enter" && confirmHostValue === confirmHost) {
                      removeHost(confirmHost)
                      setConfirmHost(null)
                      setConfirmHostValue("")
                    }
                    if (e.key === "Escape") { setConfirmHost(null); setConfirmHostValue("") }
                  }}
                  placeholder={confirmHost}
                  className="mono"
                  style={{ flex: 1, fontSize: 12, border: "1px solid var(--err-bd, #fecaca)", borderRadius: 8, padding: "6px 10px", outline: "none" }}
                />
                <button
                  className="btn btn-sm"
                  onClick={() => {
                    if (confirmHostValue !== confirmHost) return
                    removeHost(confirmHost)
                    setConfirmHost(null)
                    setConfirmHostValue("")
                  }}
                  disabled={confirmHostValue !== confirmHost}
                  style={{ background: "var(--err)", color: "#fff", border: "none", opacity: confirmHostValue !== confirmHost ? 0.4 : 1 }}
                >
                  Confirm
                </button>
                <button className="btn btn-ghost btn-sm" onClick={() => { setConfirmHost(null); setConfirmHostValue("") }}>
                  Cancel
                </button>
              </div>
            </div>
          )}
          {isAdmin && (
            <div style={{ display: "flex", gap: 8 }}>
              <input
                value={hostInput}
                onChange={e => setHostInput(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addHost() } }}
                placeholder="e.g. api.github.com or *.slack.com"
                className="mono"
                style={{ flex: 1, fontSize: 12, color: "var(--text)", border: "1px solid var(--border)", borderRadius: 8, padding: "7px 10px", background: "var(--surface)", outline: "none" }}
              />
              <button onClick={addHost} disabled={!hostInput.trim()} className="btn btn-ghost btn-sm" style={{ opacity: hostInput.trim() ? 1 : 0.4 }}>Add</button>
            </div>
          )}
          {hosts.length === 0 && !isAdmin && (
            <p style={{ fontSize: 12, color: "var(--text-muted)" }}>No restrictions — agents can reach any host.</p>
          )}
        </div>
      </div>
    </div>
  )
}
