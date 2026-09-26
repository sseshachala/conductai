"use client"

import { useEffect, useId, useState } from "react"
import { Settings, X } from "lucide-react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"

type SettingsData = { environment_id: string | null; vaults: { id: string; name: string }[]; can_edit: boolean }

export function LensSettings({ disabled = false }: { disabled?: boolean }) {
  const { workspaceId } = useAuthFetch()
  return <WorkspaceLensSettings key={workspaceId} disabled={disabled} />
}

function WorkspaceLensSettings({ disabled }: { disabled: boolean }) {
  const selectId = useId()
  const { authFetch, workspaceId } = useAuthFetch()
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<SettingsData | null>(null)
  const [selected, setSelected] = useState("")
  const [error, setError] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open || !workspaceId) return
    const controller = new AbortController()
    setData(null); setError("")
    authFetch(`${API}/glens/settings`, { signal: controller.signal }).then(async res => {
      if (!res.ok) throw new Error("Unable to load Lens settings.")
      const value: SettingsData = await res.json()
      if (!controller.signal.aborted) { setData(value); setSelected(value.environment_id ?? "") }
    }).catch(() => { if (!controller.signal.aborted) setError("Unable to load Lens settings.") })
    return () => controller.abort()
  }, [open, workspaceId, authFetch])

  async function save() {
    setSaving(true); setError("")
    try {
      const res = await authFetch(`${API}/glens/settings`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ environment_id: selected }),
      })
      if (!res.ok) throw new Error(res.status === 403 ? "Only workspace administrators can change the Lens Vault." : "Unable to save. Refresh the Vault list and try again.")
      setOpen(false)
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to save Lens settings.") }
    finally { setSaving(false) }
  }

  return <div style={{ position: "relative", display: "flex", justifyContent: "flex-end", padding: "8px 12px" }}>
    <button type="button" aria-label="Lens settings" title="Lens settings" aria-expanded={open}
      disabled={disabled || !workspaceId} onClick={() => setOpen(!open)}
      style={{ width: 32, height: 32, display: "grid", placeItems: "center", border: "1px solid var(--border)", borderRadius: 6, background: "var(--surface)", color: "var(--text)" }}>
      <Settings size={18} />
    </button>
    {open && <section aria-label="Lens settings" style={{ position: "absolute", top: 44, right: 12, zIndex: 40, width: 300, maxWidth: "calc(100vw - 40px)", padding: 16, border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", boxShadow: "0 4px 16px #0002" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <strong>Lens settings</strong>
        <button type="button" aria-label="Close Lens settings" title="Close" disabled={saving} onClick={() => setOpen(false)}><X size={16} /></button>
      </div>
      {data ? <>
        <label htmlFor={selectId}>Workspace Vault</label>
        <select id={selectId} value={selected} disabled={!data.can_edit || saving || disabled}
          onChange={e => setSelected(e.target.value)} style={{ width: "100%", marginTop: 8, padding: 8 }}>
          <option value="" disabled>Default (not configured)</option>
          {selected && !data.vaults.some(v => v.id === selected) && <option value={selected} disabled>Unavailable Vault</option>}
          {data.vaults.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
        </select>
        {!data.vaults.length && <p>No Vaults available.</p>}
        {!data.can_edit && <p>Managed by your workspace administrator.</p>}
        {data.can_edit && <button type="button" onClick={save} disabled={saving || disabled || !data.vaults.some(v => v.id === selected)} style={{ marginTop: 12 }}>{saving ? "Saving..." : "Save"}</button>}
      </> : !error && <p>Loading...</p>}
      {error && <p role="alert">{error}</p>}
    </section>}
  </div>
}
