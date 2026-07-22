"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { useAuth, useUser } from "@clerk/nextjs"
import AppShell from "@/components/AppShell"
import type { Instructions } from "../types"
import { MOCK_INSTRUCTIONS } from "../types"

// ─── Tool tabs ─────────────────────────────────────────────────────────────────

const TOOL_TABS = [
  { id: "claude-md",          label: "CLAUDE.md",                filename: "CLAUDE.md" },
  { id: "copilot",            label: "copilot-instructions.md",   filename: ".github/copilot-instructions.md" },
  { id: "agents-md",          label: "AGENTS.md",                filename: "AGENTS.md" },
  { id: "cursorrules",        label: ".cursorrules",              filename: ".cursorrules" },
  { id: "windsurfrules",      label: ".windsurfrules",            filename: ".windsurfrules" },
]

// ─── Guard policy block ────────────────────────────────────────────────────────

const GUARD_POLICY_BLOCK = `# ConductGuard — Managed policy block
# This section is auto-managed by ConductGuard. Do not edit manually.

[guard]
proxy = true
policy_version = "latest"
enforce = true
`

// ─── Preview pane ──────────────────────────────────────────────────────────────

function PreviewPane({ content, activeTab }: { content: string; activeTab: string }) {
  const tab = TOOL_TABS.find(t => t.id === activeTab)

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Tab bar */}
      <div style={{
        display: "flex",
        gap: 0,
        borderBottom: "1px solid var(--border)",
        overflowX: "auto",
        flexShrink: 0,
      }}>
        {TOOL_TABS.map(t => (
          <button
            key={t.id}
            data-tab={t.id}
            onClick={e => {
              // bubble up to parent via custom event
              e.currentTarget.dispatchEvent(new CustomEvent("tab-select", { detail: t.id, bubbles: true }))
            }}
            style={{
              padding: "10px 14px",
              fontSize: 12.5,
              fontWeight: activeTab === t.id ? 600 : 400,
              color: activeTab === t.id ? "var(--accent-text)" : "var(--text-2)",
              background: "transparent",
              border: "none",
              borderBottom: activeTab === t.id ? "2px solid var(--accent)" : "2px solid transparent",
              cursor: "pointer",
              whiteSpace: "nowrap",
              fontFamily: "monospace",
              marginBottom: -1,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Filename bar */}
      <div style={{
        padding: "6px 16px",
        fontSize: 11.5,
        color: "var(--text-muted)",
        background: "var(--surface-2)",
        borderBottom: "1px solid var(--border)",
        fontFamily: "monospace",
        flexShrink: 0,
      }}>
        {tab?.filename}
      </div>

      {/* Content area */}
      <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
        {/* Guard block — greyed out, managed */}
        <div style={{
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          padding: "10px 14px",
          marginBottom: 14,
          position: "relative",
        }}>
          <span style={{
            position: "absolute",
            top: 8,
            right: 10,
            fontSize: 10.5,
            fontWeight: 600,
            color: "var(--text-muted)",
            background: "var(--surface-3)",
            border: "1px solid var(--border)",
            borderRadius: 4,
            padding: "1px 6px",
          }}>
            Managed by Guard
          </span>
          <pre style={{
            margin: 0,
            fontFamily: "monospace",
            fontSize: 12,
            color: "var(--text-muted)",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}>
            {GUARD_POLICY_BLOCK}
          </pre>
        </div>

        {/* User content */}
        {content.trim() ? (
          <pre style={{
            margin: 0,
            fontFamily: "monospace",
            fontSize: 13,
            color: "var(--text)",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            lineHeight: 1.6,
          }}>
            {content}
          </pre>
        ) : (
          <div style={{ color: "var(--text-muted)", fontSize: 13, fontStyle: "italic" }}>
            Your instructions will appear here...
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AIRolloutEditorPage() {
  const { getToken } = useAuth()
  const { user } = useUser()
  const router = useRouter()

  const [instructions, setInstructions] = useState<Instructions>(MOCK_INSTRUCTIONS)
  const [draft, setDraft] = useState("")
  const [activeTab, setActiveTab] = useState("claude-md")
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const load = useCallback(async () => {
    try {
      const token = await getToken()
      const base = process.env.NEXT_PUBLIC_API_URL
      const res = await fetch(`${base}/team-os/instructions`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (res.ok) {
        const data: Instructions = await res.json()
        setInstructions(data)
        setDraft(data.content)
      }
    } catch {
      // API not built yet — use mock defaults
      setDraft(MOCK_INSTRUCTIONS.content)
    }
  }, [getToken])

  useEffect(() => { load() }, [load])

  // Listen for tab-select events from PreviewPane
  useEffect(() => {
    function handler(e: Event) {
      const ce = e as CustomEvent<string>
      setActiveTab(ce.detail)
    }
    document.addEventListener("tab-select", handler)
    return () => document.removeEventListener("tab-select", handler)
  }, [])

  async function handlePublish() {
    setSaving(true)
    setSaveError(null)
    try {
      const token = await getToken()
      const base = process.env.NEXT_PUBLIC_API_URL
      const res = await fetch(`${base}/team-os/instructions`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ content: draft }),
      })
      if (!res.ok) {
        const body = await res.text()
        setSaveError(body || `Error ${res.status}`)
      } else {
        const data: Instructions = await res.json()
        setInstructions(data)
        setSaved(true)
        setTimeout(() => setSaved(false), 2000)
      }
    } catch {
      // API not built — optimistic mock update
      setInstructions(prev => ({ ...prev, content: draft, updated_at: new Date().toISOString() }))
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <AppShell>
      <div style={{ maxWidth: 1240, margin: "0 auto", padding: "28px 24px 0", display: "flex", flexDirection: "column", height: "calc(100vh - 60px)" }}>

        {/* Header */}
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 16,
          marginBottom: 20,
          flexShrink: 0,
        }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 700, color: "var(--text)", margin: 0, marginBottom: 4 }}>
              Instructions editor
            </h1>
            <div style={{ fontSize: 13, color: "var(--text-2)" }}>
              Write shared coding standards and AI constraints. Changes are published to all engineers on sync.
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "monospace" }}>
              {instructions.version}
            </span>
          </div>
        </div>

        {/* Split pane */}
        <div style={{
          flex: 1,
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16,
          minHeight: 0,
          marginBottom: 64,
        }}>
          {/* Left: editor */}
          <div style={{
            display: "flex",
            flexDirection: "column",
            border: "1px solid var(--border)",
            borderRadius: 10,
            overflow: "hidden",
            background: "var(--surface)",
          }}>
            <div style={{
              padding: "8px 14px",
              fontSize: 12,
              fontWeight: 600,
              color: "var(--text-muted)",
              borderBottom: "1px solid var(--border)",
              background: "var(--surface-2)",
              letterSpacing: ".04em",
              textTransform: "uppercase",
            }}>
              Markdown editor
            </div>
            <textarea
              value={draft}
              onChange={e => setDraft(e.target.value)}
              placeholder="Write team coding standards, workflow rules, and AI constraints here..."
              spellCheck={false}
              style={{
                flex: 1,
                width: "100%",
                border: "none",
                outline: "none",
                resize: "none",
                fontFamily: "monospace",
                fontSize: 13,
                lineHeight: 1.65,
                padding: "16px",
                background: "var(--surface)",
                color: "var(--text)",
                boxSizing: "border-box",
              }}
            />
          </div>

          {/* Right: tabbed preview */}
          <div style={{
            display: "flex",
            flexDirection: "column",
            border: "1px solid var(--border)",
            borderRadius: 10,
            overflow: "hidden",
            background: "var(--surface)",
          }}>
            <PreviewPane content={draft} activeTab={activeTab} />
          </div>
        </div>

        {/* Bottom bar — fixed */}
        <div style={{
          position: "fixed",
          bottom: 0,
          left: 0,
          right: 0,
          height: 60,
          background: "color-mix(in srgb, var(--surface) 95%, transparent)",
          borderTop: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          padding: "0 32px",
          gap: 10,
          zIndex: 50,
        }}>
          {saveError && (
            <span style={{ fontSize: 12.5, color: "#ef4444" }}>{saveError}</span>
          )}
          {saved && (
            <span style={{ fontSize: 12.5, color: "#10b981", fontWeight: 600 }}>Published</span>
          )}
          <button
            onClick={() => router.push("/team-os")}
            style={{
              padding: "8px 18px",
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: "var(--surface-2)",
              color: "var(--text-2)",
              fontSize: 13.5,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
          <button
            onClick={handlePublish}
            disabled={saving}
            style={{
              padding: "8px 20px",
              borderRadius: 8,
              border: "none",
              background: saving ? "var(--surface-3)" : "var(--accent)",
              color: saving ? "var(--text-muted)" : "#fff",
              fontSize: 13.5,
              fontWeight: 600,
              cursor: saving ? "not-allowed" : "pointer",
            }}
          >
            {saving ? "Publishing..." : "Publish"}
          </button>
        </div>

      </div>
    </AppShell>
  )
}
