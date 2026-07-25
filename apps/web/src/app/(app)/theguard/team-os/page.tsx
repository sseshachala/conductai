"use client"

import { useEffect, useState, useCallback } from "react"
import Link from "next/link"
import { useUser } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"
import AppShell from "@/components/AppShell"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { teamOs } from "@/lib/api"
import { timeAgo } from "@/lib/runUtils"
import type { Instructions, AdoptionRow } from "./types"

// ─── Helpers ──────────────────────────────────────────────────────────────────

const TOOL_LABELS: Record<string, string> = {
  "claude-code": "Claude Code",
  "copilot": "Copilot",
  "cursor": "Cursor",
  "windsurf": "Windsurf",
  "codex": "Codex",
  "gemini": "Gemini",
}

function formatToolLabel(tool: string): string {
  return TOOL_LABELS[tool] ?? tool
}

function getSyncStatus(row: AdoptionRow, currentVersion: string): "current" | "stale" | "not-set-up" {
  if (!row.last_synced || !row.version) return "not-set-up"
  const diffMs = Date.now() - new Date(row.last_synced).getTime()
  const diffH = diffMs / (1000 * 60 * 60)
  if (diffH > 24) return "stale"
  if (row.version !== currentVersion) return "stale"
  return "current"
}

function publishedAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return "just now"
  if (diffMin < 60) return `${diffMin} min ago`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `${diffH} hours ago`
  const diffD = Math.floor(diffH / 24)
  return `${diffD} days ago`
}

// ─── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: "current" | "stale" | "not-set-up" }) {
  const config = {
    current: { label: "Current", bg: "#d1fae5", color: "#065f46", dot: "#10b981" },
    stale: { label: "Stale", bg: "#fef3c7", color: "#92400e", dot: "#f59e0b" },
    "not-set-up": { label: "Not set up", bg: "#fee2e2", color: "#991b1b", dot: "#ef4444" },
  }[status]

  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 5,
      padding: "2px 9px",
      borderRadius: 20,
      fontSize: 12,
      fontWeight: 600,
      background: config.bg,
      color: config.color,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: config.dot, display: "inline-block" }} />
      {config.label}
    </span>
  )
}

// ─── Tool pills ────────────────────────────────────────────────────────────────

function ToolPills({ tools }: { tools: string[] }) {
  if (tools.length === 0) {
    return <span style={{ color: "var(--text-muted)", fontSize: 13 }}>—</span>
  }
  return (
    <span style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
      {tools.map(t => (
        <span key={t} style={{
          padding: "2px 8px",
          borderRadius: 6,
          fontSize: 11.5,
          fontWeight: 500,
          background: "var(--surface-2)",
          color: "var(--text-2)",
          border: "1px solid var(--border)",
        }}>
          {formatToolLabel(t)}
        </span>
      ))}
    </span>
  )
}

// ─── Adoption table ────────────────────────────────────────────────────────────

function AdoptionTable({ rows, currentVersion }: { rows: AdoptionRow[]; currentVersion: string }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13.5 }}>
        <thead>
          <tr>
            {["Engineer", "Tools detected", "Last synced", "Version status"].map(h => (
              <th key={h} style={{
                padding: "8px 14px",
                textAlign: "left",
                fontWeight: 600,
                fontSize: 12,
                color: "var(--text-muted)",
                letterSpacing: ".04em",
                textTransform: "uppercase",
                borderBottom: "1px solid var(--border)",
                whiteSpace: "nowrap",
              }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const status = getSyncStatus(row, currentVersion)
            return (
              <tr key={row.email} style={{ borderBottom: i < rows.length - 1 ? "1px solid var(--border)" : "none" }}>
                <td style={{ padding: "12px 14px", color: "var(--text)", fontWeight: 500 }}>
                  {row.email}
                </td>
                <td style={{ padding: "12px 14px" }}>
                  <ToolPills tools={row.tools} />
                </td>
                <td style={{ padding: "12px 14px", color: "var(--text-2)", whiteSpace: "nowrap" }}>
                  {row.last_synced ? timeAgo(row.last_synced) : <span style={{ color: "var(--text-muted)" }}>never</span>}
                </td>
                <td style={{ padding: "12px 14px" }}>
                  <StatusBadge status={status} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ─── Setup card ───────────────────────────────────────────────────────────────

function SetupCard({ version }: { version: string }) {
  const [copied, setCopied] = useState(false)
  const cmd = "conduct guard sync"

  function copy() {
    navigator.clipboard.writeText(cmd).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    })
  }

  return (
    <div style={{
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 12,
      padding: "20px 24px",
      display: "flex",
      alignItems: "flex-start",
      gap: 20,
      flexWrap: "wrap",
    }}>
      <div style={{ flex: 1, minWidth: 220 }}>
        <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text)", marginBottom: 4 }}>
          Sync instructions to engineers
        </div>
        <div style={{ fontSize: 13, color: "var(--text-2)", marginBottom: 12, lineHeight: 1.5 }}>
          Engineers run this command to pull the latest instructions into their AI tools. Current version: <code style={{ fontSize: 12, fontWeight: 600, color: "var(--accent-text)" }}>{version}</code>
        </div>
        <div style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 10,
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "8px 14px",
          fontFamily: "monospace",
          fontSize: 13.5,
          color: "var(--text)",
        }}>
          <span>$ {cmd}</span>
          <button
            onClick={copy}
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              padding: 0,
              color: copied ? "#10b981" : "var(--text-muted)",
              fontSize: 12,
              fontWeight: 600,
              fontFamily: "inherit",
            }}
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function TeamOSPage() {
  const { authFetch } = useAuthFetch()
  const { activeWorkspace } = useWorkspace()
  const { user } = useUser()

  const [instructions, setInstructions] = useState<Instructions | null>(null)
  const [adoption, setAdoption] = useState<AdoptionRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const syncedCount = adoption.filter(r => getSyncStatus(r, instructions?.version ?? "")).length
  const totalCount = adoption.length

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = activeWorkspace?.id ? { workspace_id: activeWorkspace.id } : undefined
      const instData: Instructions = await teamOs.instructions(authFetch, params)
      setInstructions(instData)
      // adoption is admin-only — silently skip if no permission
      try {
        const adoptData: AdoptionRow[] = await teamOs.adoption(authFetch, params)
        setAdoption(adoptData)
      } catch { /* non-fatal */ }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong")
    } finally {
      setLoading(false)
    }
  }, [authFetch, activeWorkspace?.id])

  useEffect(() => { load() }, [load])

  return (
    <AppShell>
      <div style={{ maxWidth: 1240, margin: "0 auto", padding: "28px 24px 48px" }}>

        {/* Header */}
        <div style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 16,
          marginBottom: 28,
          flexWrap: "wrap",
        }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--text)", margin: 0, marginBottom: 6 }}>
              AI Rollout
            </h1>
            <div style={{ fontSize: 13.5, color: "var(--text-2)" }}>
              {instructions ? (
                <>
                  {syncedCount} of {totalCount} engineer{totalCount !== 1 ? "s" : ""} synced
                  {instructions.updated_at && (
                    <>{" · "}Last published {publishedAgo(instructions.updated_at)}</>
                  )}
                </>
              ) : null}
            </div>
          </div>
          <Link
            href="/theguard/team-os/ai-rollout"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "8px 16px",
              borderRadius: 8,
              background: "var(--accent)",
              color: "#fff",
              fontSize: 13.5,
              fontWeight: 600,
              textDecoration: "none",
              flexShrink: 0,
            }}
          >
            Edit Instructions
          </Link>
        </div>

        {/* Error state */}
        {error && (
          <div style={{
            padding: "14px 18px",
            borderRadius: 10,
            background: "#fef2f2",
            border: "1px solid #fecaca",
            color: "#991b1b",
            fontSize: 13.5,
            marginBottom: 20,
          }}>
            {error}
          </div>
        )}

        {/* Adoption tracker */}
        {!error && (
          <section style={{ marginBottom: 28 }}>
            <div style={{
              fontWeight: 600,
              fontSize: 14,
              color: "var(--text)",
              marginBottom: 12,
            }}>
              Adoption tracker
            </div>
            <div style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: 12,
              overflow: "hidden",
            }}>
              {loading ? (
                <div style={{ padding: "32px 24px", textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
                  Loading...
                </div>
              ) : (
                <AdoptionTable rows={adoption} currentVersion={instructions?.version ?? ""} />
              )}
            </div>
          </section>
        )}

        {/* Setup card */}
        {!error && instructions && (
          <section>
            <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text)", marginBottom: 12 }}>
              Setup
            </div>
            <SetupCard version={instructions.version} />
          </section>
        )}

      </div>
    </AppShell>
  )
}
