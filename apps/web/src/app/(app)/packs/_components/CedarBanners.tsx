"use client"

import { useState } from "react"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { API } from "@/lib/api/client"

export function CedarImportBanner({ getToken }: { getToken: (() => Promise<string | null>) | null }) {
  const { activeWorkspace } = useWorkspace()
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [packSlug, setPackSlug] = useState("")
  const [packName, setPackName] = useState("")
  const [installing, setInstalling] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<any | null>(null)

  async function handleImport(installNow: boolean) {
    if (!file || !packSlug || !packName) {
      setError("File, slug, and name are required")
      return
    }
    setInstalling(true)
    setError(null)
    setResult(null)
    try {
      const text = await file.text()
      const parsed = JSON.parse(text)
      const policies = Array.isArray(parsed) ? parsed : [parsed]
      const headers: Record<string, string> = { "Content-Type": "application/json" }
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }
      // Backend resolves the target workspace from this header. Without it,
      // /guard/registry/import-cedar 400s with "Invalid workspace ID" even
      // when the user is clearly inside a workspace in the UI.
      const workspaceId = activeWorkspace?.id ?? null
      if (workspaceId) headers["X-Workspace-Id"] = workspaceId
      const res = await fetch(`${API}/guard/registry/import-cedar`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          format: "cedar_json",
          policies,
          pack_slug: packSlug,
          pack_name: packName,
          pack_version: "1.0.0",
          preview_only: !installNow,
        }),
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setError(err.detail || `Request failed (${res.status})`)
        return
      }
      setResult(await res.json())
    } catch (e: any) {
      setError(e.message || String(e))
    } finally {
      setInstalling(false)
    }
  }

  if (!open) {
    return (
      <div className="card" style={{ padding: 16, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, background: "var(--accent-weak)", border: "1px solid var(--accent)" }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>Bring your Cedar policies</div>
          <div style={{ fontSize: 12, color: "var(--text-2)", marginTop: 2 }}>Import Cedar JSON policies from AWS Verified Permissions, Dogwood, or your own IAM stack.</div>
        </div>
        <button onClick={() => setOpen(true)} className="btn btn-primary btn-sm">Import Cedar</button>
      </div>
    )
  }

  return (
    <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h3 style={{ fontSize: 15, fontWeight: 650, margin: 0 }}>Import Cedar policy</h3>
        <button onClick={() => { setOpen(false); setResult(null); setError(null) }} className="btn btn-ghost btn-sm">Close</button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <label style={{ fontSize: 12, color: "var(--text-2)" }}>
          Cedar JSON file
          <input
            type="file"
            accept=".json,application/json"
            onChange={e => setFile(e.target.files?.[0] || null)}
            style={{ display: "block", marginTop: 4, fontSize: 13 }}
          />
        </label>
        <label style={{ fontSize: 12, color: "var(--text-2)" }}>
          Pack slug
          <input
            type="text"
            value={packSlug}
            onChange={e => setPackSlug(e.target.value)}
            placeholder="my-cedar-import"
            style={{ display: "block", marginTop: 4, width: "100%", padding: "6px 10px", fontSize: 13, border: "1px solid var(--border)", borderRadius: 6, background: "var(--surface)" }}
          />
        </label>
        <label style={{ fontSize: 12, color: "var(--text-2)" }}>
          Pack name
          <input
            type="text"
            value={packName}
            onChange={e => setPackName(e.target.value)}
            placeholder="My Cedar Import"
            style={{ display: "block", marginTop: 4, width: "100%", padding: "6px 10px", fontSize: 13, border: "1px solid var(--border)", borderRadius: 6, background: "var(--surface)" }}
          />
        </label>
      </div>
      {error && <div style={{ padding: 10, background: "var(--red-weak, #fee)", color: "var(--red, #c00)", borderRadius: 6, fontSize: 12 }}>{error}</div>}
      {result && (
        <div style={{ padding: 10, background: "var(--surface-2)", borderRadius: 6, fontSize: 12 }}>
          <div>Rules imported: <b>{result.rules_imported}</b></div>
          <div>Rules rejected: <b>{result.rules_rejected}</b></div>
          {result.rejections?.length > 0 && (
            <details style={{ marginTop: 6 }}>
              <summary style={{ cursor: "pointer" }}>Rejection details</summary>
              <ul style={{ fontSize: 11, marginTop: 6 }}>
                {result.rejections.map((r: any, i: number) => (
                  <li key={i}>[{r.index}] {r.error?.error}: {r.error?.message}</li>
                ))}
              </ul>
            </details>
          )}
          {result.installed && <div style={{ color: "var(--green, green)", marginTop: 6 }}>✓ Installed in your workspace</div>}
        </div>
      )}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button
          onClick={() => handleImport(false)}
          disabled={installing || !file}
          className="btn btn-ghost"
        >
          {installing ? "Working…" : "Preview"}
        </button>
        <button
          onClick={() => handleImport(true)}
          disabled={installing || !file || !packSlug || !packName}
          className="btn btn-primary"
        >
          {installing ? "Installing…" : "Import and install"}
        </button>
      </div>
    </div>
  )
}

/**
 * Mirror of CedarImportBanner — announces the reverse direction so buyers
 * see the bidirectional interchange story on the same page. No lock-in.
 */
export function CedarExportBanner() {
  return (
    <div className="card" style={{ padding: 16, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>Take your policies back out</div>
        <div style={{ fontSize: 12, color: "var(--text-2)", marginTop: 2 }}>
          Every installed pack renders to Cedar — the AWS Verified Permissions
          language. Click <strong>⤓ Cedar</strong> on any pack to download.
          Bidirectional interchange by design.
        </div>
      </div>
      <a href="/docs/schema" className="btn btn-ghost btn-sm">Schema docs →</a>
    </div>
  )
}

/**
 * Per-tile Cedar download — fetches the rendered Cedar for one pack, saves
 * as `{slug}.cedar`. No navigation; one-click from the list.
 */
export function CedarPackDownload({ slug, getToken }: { slug: string; getToken: (() => Promise<string | null>) | null }) {
  const { activeWorkspace } = useWorkspace()
  const [busy, setBusy] = useState(false)

  async function download() {
    if (!activeWorkspace?.id) return
    setBusy(true)
    try {
      const headers: Record<string, string> = {}
      if (getToken) {
        const token = await getToken()
        if (token) headers["Authorization"] = `Bearer ${token}`
      }
      const res = await fetch(
        `${API}/guard/registry/packs/${slug}/cedar?workspace_id=${activeWorkspace.id}`,
        { headers },
      )
      if (!res.ok) return
      const text = await res.text()
      const blob = new Blob([text], { type: "text/plain;charset=utf-8" })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${slug}.cedar`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setBusy(false)
    }
  }

  return (
    <button
      onClick={download}
      disabled={busy}
      title="Download this pack as Cedar (AWS Verified Permissions language)"
      className="btn btn-ghost btn-sm"
      style={{ fontSize: 11.5 }}
    >
      {busy ? "…" : "⤓ Cedar"}
    </button>
  )
}
