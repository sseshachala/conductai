"use client"
import { useState } from "react"
import { API } from "@/lib/api"

// Lens `export_audit_log` tool result (#2385). `download_path` is relative to
// the API base and needs the user's Bearer token, so a plain <a href> would
// not work — Download fetches via authFetch and saves a Blob.
export type AuditExportResult = {
  kind: "audit_export"
  row_count: number
  since: string
  until: string
  format: "ndjson" | "csv"
  capped: boolean
  cap: number
  head_hash: string | null
  tail_hash: string | null
  download_path: string
}

type AuthFetch = (url: string, options?: RequestInit) => Promise<Response>

export function parseAuditExport(data: unknown): AuditExportResult | null {
  if (!data || typeof data !== "object") return null
  const d = data as Record<string, unknown>
  const r = d.kind === "audit_export" ? d : d.audit_export
  if (!r || typeof r !== "object") return null
  const x = r as Record<string, unknown>
  return x.kind === "audit_export" && typeof x.download_path === "string"
    ? (x as unknown as AuditExportResult)
    : null
}

export function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback
  const star = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(header)
  if (star) {
    try { return decodeURIComponent(star[1].trim().replace(/^"|"$/g, "")) } catch { /* fall through */ }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header)
  return plain ? plain[1].trim() : fallback
}

const shortHash = (h: string | null) => (h ? `${h.slice(0, 8)}…${h.slice(-4)}` : "—")
const fmtDate = (iso: string) => {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toISOString().replace("T", " ").slice(0, 16) + " UTC"
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ display: "flex", gap: 8, fontSize: 13 }}>
      <span style={{ color: "var(--text-3)", minWidth: 72 }}>{label}</span>
      <span style={{ color: "var(--text)", fontFamily: mono ? "ui-monospace,monospace" : undefined }}>{value}</span>
    </div>
  )
}

export function AuditExportBubble({ result, authFetch }: { result: AuditExportResult; authFetch: AuthFetch }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function download() {
    setBusy(true)
    setError(null)
    try {
      const res = await authFetch(`${API}${result.download_path}`)
      if (res.status === 403) { setError("You need audit log access"); return }
      if (!res.ok) { setError(`Download failed (${res.status})`); return }
      const blob = await res.blob()
      const name = filenameFromDisposition(res.headers.get("Content-Disposition"), `conduct-audit.${result.format}`)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = name
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch {
      setError("Download failed. Check your connection and try again.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16, width: "100%" }}>
      <div style={{
        width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)",
        borderRadius: "4px 14px 14px 14px", padding: "16px 20px",
      }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 8 }}>
          Audit export
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <Row label="Range" value={`${fmtDate(result.since)} to ${fmtDate(result.until)}`} />
          <Row label="Rows" value={result.row_count.toLocaleString("en-GB")} />
          <Row label="Format" value={result.format.toUpperCase()} />
          <Row label="Head hash" value={shortHash(result.head_hash)} mono />
          <Row label="Tail hash" value={shortHash(result.tail_hash)} mono />
        </div>
        {result.capped && (
          <div role="note" style={{ fontSize: 12, color: "#f59e0b", marginTop: 10 }}>
            Capped at {result.cap.toLocaleString("en-GB")} rows — narrow the range
          </div>
        )}
        {error && <div role="alert" style={{ fontSize: 12, color: "var(--err)", marginTop: 10 }}>{error}</div>}
        <div style={{ marginTop: 12 }}>
          <button onClick={download} disabled={busy} className="btn btn-primary btn-sm">
            {busy ? "Downloading…" : "Download"}
          </button>
        </div>
      </div>
    </div>
  )
}
