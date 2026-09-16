"use client"

import { useEffect, useState } from "react"

import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import type { GatewayProfileV2ImportOut } from "@/lib/api/guard"

/**
 * Import a Gateway Profile v2 from pasted JSON.
 *
 * Sibling of GatewayProfileV2PublishDialog / RollbackDialog /
 * DeleteDialog — same overlay + card shape so the whole page feels
 * consistent. Uses the same endpoint the CLI's ``conduct import
 * --gateway-config`` hits (backend PR #2046), so what admins run
 * locally is the same code path the UI drives.
 *
 * Server strips credentials on import; the response's
 * ``credential_gaps`` is surfaced inline post-submit so the admin
 * sees exactly what to fill in the editor (and the editor's Save
 * gate blocks Save until they're filled).
 */
export default function GatewayProfileV2ImportDialog({
  workspaceId, onClose, onImported,
}: {
  workspaceId: string
  onClose: () => void
  onImported: (profileId: string) => void
}) {
  const { authFetch } = useAuthFetch()
  const [jsonText, setJsonText] = useState("")
  const [nameOverride, setNameOverride] = useState("")
  const [importing, setImporting] = useState(false)
  const [err, setErr] = useState("")
  const [result, setResult] = useState<GatewayProfileV2ImportOut | null>(null)

  useEffect(() => {
    function handleKey(e: KeyboardEvent) { if (e.key === "Escape" && !importing) onClose() }
    document.addEventListener("keydown", handleKey)
    return () => document.removeEventListener("keydown", handleKey)
  }, [onClose, importing])

  const canSubmit = jsonText.trim().length > 0 && !importing

  async function doImport() {
    if (!canSubmit) return
    setErr("")
    let parsed: Record<string, unknown>
    try {
      const raw = JSON.parse(jsonText)
      if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
        throw new Error("Expected a JSON object (the working_copy dict).")
      }
      parsed = raw as Record<string, unknown>
    } catch (e) {
      setErr(e instanceof Error ? `Invalid JSON: ${e.message}` : "Invalid JSON")
      return
    }
    setImporting(true)
    try {
      const body: { working_copy: Record<string, unknown>; name_override?: string } = {
        working_copy: parsed,
      }
      if (nameOverride.trim()) body.name_override = nameOverride.trim()
      const out = await guard.gatewayProfilesV2.importJson(authFetch, workspaceId, body)
      setResult(out)
    } catch (e) {
      // guard.ts _mutateJson throws GatewayValidationError with .message
      // pre-formatted as summary + per-line errors. Structured errors
      // land here readable.
      setErr(e instanceof Error ? e.message : "Import failed")
    } finally {
      setImporting(false)
    }
  }

  function finish() {
    if (result) onImported(result.profile.id)
    onClose()
  }

  const gaps = result?.credential_gaps ?? []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,.35)" }} onClick={importing ? undefined : onClose}>
      <div className="card card-pad" style={{ width: "100%", maxWidth: 640, margin: "0 16px" }}
        onClick={e => e.stopPropagation()}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 650 }}>Import Gateway Profile</h3>
        <p style={{ margin: "4px 0 16px", color: "var(--text-3)", fontSize: 12.5 }}>
          Paste a portable Gateway Profile v2 JSON — the same shape
          <code className="mono"> conduct export --gateway-config </code>
          emits. Server strips credentials on import; you'll pick a
          vault + handle per target after the draft lands.
        </p>

        {result ? (
          <div>
            <div style={{ padding: "10px 12px", border: "1px solid var(--ok-bd)", borderRadius: 8, background: "var(--surface-2)" }}>
              <div style={{ fontSize: 11, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 4 }}>
                Imported
              </div>
              <div style={{ fontSize: 13 }}>
                <strong>{result.profile.name}</strong>{" "}
                <span style={{ color: "var(--text-3)" }}>
                  · <code className="mono">cond-{result.profile.cond_code}-{result.profile.model_alias ?? ""}</code>
                </span>
              </div>
            </div>

            {gaps.length > 0 && (
              <div className="sbadge warn" style={{ display: "block", height: "auto", padding: "10px 12px", borderRadius: 8, whiteSpace: "normal", marginTop: 12 }}>
                <strong>{gaps.length} target(s) need credentials before publish</strong>
                <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
                  {gaps.map((g, i) => (
                    <li key={i} style={{ fontSize: 12, fontWeight: 400 }}>
                      <span className="mono">#{g.target_index + 1} {g.target_id}</span> ({g.transport}): {g.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
              <button className="btn btn-primary btn-sm" onClick={finish}>
                {gaps.length > 0 ? "Open editor to fill credentials" : "Open editor"}
              </button>
            </div>
          </div>
        ) : (
          <div>
            <label style={{ fontSize: 12, color: "var(--text-2)", display: "block", marginBottom: 4 }}>
              Profile JSON (working_copy shape)
            </label>
            <textarea
              value={jsonText}
              onChange={e => setJsonText(e.target.value)}
              placeholder='{\n  "name": "claude-sonnet",\n  "model_alias": "claude-sonnet",\n  "accepts": ["anthropic_messages"],\n  "targets": [...]\n}'
              rows={12}
              spellCheck={false}
              style={{
                width: "100%",
                border: "1px solid var(--border)",
                borderRadius: 8,
                padding: "10px 12px",
                fontSize: 12,
                fontFamily: "var(--font-mono, monospace)",
                background: "var(--surface)",
                color: "var(--text)",
                outline: "none",
                resize: "vertical",
                minHeight: 180,
              }}
              disabled={importing}
            />

            <div style={{ marginTop: 12 }}>
              <label style={{ fontSize: 12, color: "var(--text-2)", display: "block", marginBottom: 4 }}>
                Name override (optional) — use if the JSON's name is already taken here
              </label>
              <input
                value={nameOverride}
                onChange={e => setNameOverride(e.target.value)}
                placeholder="my-imported-profile"
                disabled={importing}
                style={{
                  width: "100%",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  padding: "9px 11px",
                  fontSize: 13,
                  background: "var(--surface)",
                  color: "var(--text)",
                  outline: "none",
                }}
              />
            </div>

            {err && (
              <p style={{ marginTop: 10, color: "var(--err)", fontSize: 12, whiteSpace: "pre-wrap" }}>{err}</p>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
              <button className="btn btn-ghost btn-sm" onClick={onClose} disabled={importing}>
                Cancel
              </button>
              <button
                onClick={() => void doImport()}
                disabled={!canSubmit}
                className="btn btn-primary btn-sm"
              >
                {importing ? "Importing…" : "Import"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
