"use client"

import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"

import AppShell from "@/components/AppShell"
import GatewayProfileV2ImportDialog from "@/components/settings/GatewayProfileV2ImportDialog"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import { guard } from "@/lib/api"
import type { GatewayProfileV2Out, GatewayProfileV2Status } from "@/lib/api/guard"
import { conditIdentifier, latestRevision, profileStatus } from "./_components/presets"
import { ChangesBadge, StatusBadge } from "./_components/StatusBadge"

// Gateway Profiles v2 — list only. Create lives at /new, everything else
// (edit, publish, unpublish, delete, revisions) at /[id].

type Filter = "all" | GatewayProfileV2Status

const FILTERS: Array<{ id: Filter; label: string }> = [
  { id: "all", label: "All" },
  { id: "draft", label: "Draft" },
  { id: "published", label: "Published" },
  { id: "unpublished", label: "Unpublished" },
]

const BASE = "/proxy/gateway-profiles"

export default function GatewayProfilesV2Page() {
  const { authFetch } = useAuthFetch()
  const { activeWorkspace } = useWorkspace()
  const { role } = useGuardRole()
  const router = useRouter()
  const workspaceId = activeWorkspace?.id ?? ""
  const isAdmin = role === "admin"

  // Old deep links: ``?select=<id>`` (and ``?tab=rate_limits``) pointed at
  // the inline editor. Forward them to the detail page.
  const searchParams = useSearchParams()
  const selectParam = searchParams?.get("select") ?? null
  const legacyTab = searchParams?.get("tab") ?? null

  const [profiles, setProfiles] = useState<GatewayProfileV2Out[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [filter, setFilter] = useState<Filter>("all")
  const [showImport, setShowImport] = useState(false)
  const loadGeneration = useRef(0)

  useEffect(() => {
    if (!selectParam) return
    const tab = legacyTab === "rate_limits" ? "?tab=rate-limits" : ""
    router.replace(`${BASE}/${encodeURIComponent(selectParam)}${tab}`)
  }, [selectParam, legacyTab, router])

  const load = useCallback(async () => {
    const current = ++loadGeneration.current
    if (!workspaceId) return
    setLoading(true); setError(""); setProfiles([])
    try {
      const rows = await guard.gatewayProfilesV2.list(authFetch, workspaceId)
      if (current === loadGeneration.current) setProfiles(rows)
    } catch (err) {
      if (current === loadGeneration.current) setError(err instanceof Error ? err.message : "Failed to load profiles")
    } finally { if (current === loadGeneration.current) setLoading(false) }
  }, [authFetch, workspaceId])

  useEffect(() => { if (!selectParam) void load(); return () => { loadGeneration.current++ } }, [load, selectParam])

  const visible = useMemo(
    () => filter === "all" ? profiles : profiles.filter(p => profileStatus(p) === filter),
    [profiles, filter],
  )

  if (selectParam) {
    return <AppShell><div className="page"><p style={{ fontSize: 13, color: "var(--text-3)" }}>Opening profile…</p></div></AppShell>
  }

  return (
    <AppShell>
      <div className="page" style={{ minWidth: 0 }}>
        <div className="page-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
          <div style={{ minWidth: 0 }}>
            <h1 className="page-title">Gateways</h1>
            <p className="page-sub">
              A profile pins an ordered list of upstream targets and a set of vault credentials
              behind a stable identifier. Clients hit the gateway using the profile&apos;s
              <code className="mono" style={{ fontSize: 12 }}> cond-…</code> identifier.
            </p>
          </div>
          {isAdmin && (
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowImport(true)}
                title="Paste a Gateway Profile v2 JSON to import as a new draft.">Import JSON</button>
              <Link href={`${BASE}/new`} className="btn btn-primary btn-sm">New profile</Link>
            </div>
          )}
        </div>

        {error && (
          <div role="alert" className="sbadge err" style={{ display: "block", height: "auto", padding: "10px 14px", borderRadius: 8, marginBottom: 16, whiteSpace: "normal" }}>
            {error}
          </div>
        )}

        <div role="group" aria-label="Filter by status" style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
          {FILTERS.map(f => (
            <button key={f.id} onClick={() => setFilter(f.id)} className="chip" aria-pressed={filter === f.id}
              style={{
                height: 28, fontSize: 12.5,
                background: filter === f.id ? "var(--accent-weak)" : "var(--surface)",
                borderColor: filter === f.id ? "var(--accent-ring)" : "var(--border)",
                color: filter === f.id ? "var(--accent-text)" : "var(--text-2)",
              }}>{f.label}</button>
          ))}
        </div>

        {loading ? (
          <div style={{ height: 96, background: "var(--surface-2)", borderRadius: 8 }} />
        ) : visible.length === 0 ? (
          <div className="card card-pad" style={{ textAlign: "center", background: "var(--surface-2)" }}>
            <p style={{ fontSize: 13, color: "var(--text-3)", margin: 0 }}>
              {profiles.length === 0 ? "No profiles yet. Create one with New profile." : `No ${filter} profiles.`}
            </p>
          </div>
        ) : (
          <div className="card" style={{ padding: 0, overflowX: "auto" }}>
            <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse", minWidth: 640 }}>
              <thead>
                <tr style={{ background: "var(--surface-2)", color: "var(--text-3)" }}>
                  {["Name", "Alias", "Model ID", "Status", "Revisions", "Last published"].map(h => (
                    <th key={h} scope="col" style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, fontSize: 12 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map(p => {
                  const latest = latestRevision(p)
                  return (
                    <tr key={p.id} onClick={() => router.push(`${BASE}/${p.id}`)}
                      style={{ borderTop: "1px solid var(--border)", cursor: "pointer" }}>
                      <td style={{ padding: "8px 12px", fontWeight: 600 }}>
                        <Link href={`${BASE}/${p.id}`} onClick={(e: MouseEvent) => e.stopPropagation()}>{p.name}</Link>
                      </td>
                      <td style={{ padding: "8px 12px" }}><code className="mono">{p.model_alias ?? "—"}</code></td>
                      <td style={{ padding: "8px 12px" }}><code className="mono" style={{ fontSize: 12 }}>{conditIdentifier(p)}</code></td>
                      <td style={{ padding: "8px 12px" }}>
                        <span style={{ display: "inline-flex", gap: 6, flexWrap: "wrap" }}>
                          <StatusBadge profile={p} />
                          <ChangesBadge profile={p} />
                        </span>
                      </td>
                      <td style={{ padding: "8px 12px", color: "var(--text-2)" }}>{p.revisions.length}</td>
                      <td style={{ padding: "8px 12px", color: "var(--text-2)", whiteSpace: "nowrap" }}>
                        {latest ? new Date(latest.published_at).toLocaleDateString() : "—"}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {showImport && (
          <GatewayProfileV2ImportDialog
            workspaceId={workspaceId}
            onClose={() => setShowImport(false)}
            onImported={profileId => router.push(`${BASE}/${profileId}`)}
          />
        )}
      </div>
    </AppShell>
  )
}
