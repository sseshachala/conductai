"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { useUser } from "@clerk/nextjs"
import { useWorkspace } from "@/lib/WorkspaceContext"
import AppShell from "@/components/AppShell"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { teamOs } from "@/lib/api"
import type { Instructions } from "../types"

// ─── Tool tabs ─────────────────────────────────────────────────────────────────

const TOOL_TABS = [
  { id: "claude-md",     label: "Claude Code",   filename: "CLAUDE.md" },
  { id: "copilot",       label: "Copilot",        filename: ".github/copilot-instructions.md" },
  { id: "agents-md",     label: "Codex",          filename: "AGENTS.md" },
  { id: "cursorrules",   label: "Cursor",         filename: ".cursorrules" },
  { id: "windsurfrules", label: "Windsurf",       filename: ".windsurfrules" },
]

// ─── Guard policy block ────────────────────────────────────────────────────────


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
        scrollbarWidth: "none",
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
              flex: 1,
              padding: "10px 8px",
              fontSize: 12,
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
            {"# ConductGuard policy block (auto-managed by guard sync)"}
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
  const { authFetch } = useAuthFetch()
  const { user } = useUser()
  const { activeWorkspace } = useWorkspace()
  const router = useRouter()

  const [instructions, setInstructions] = useState<Instructions | null>(null)
  const [draft, setDraft] = useState("")
  const [activeTab, setActiveTab] = useState("claude-md")
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [successBanner, setSuccessBanner] = useState(false)
  const [templates, setTemplates] = useState<{ id: string; name: string; content: string }[]>([])
  const [showTemplates, setShowTemplates] = useState(false)

  const load = useCallback(async () => {
    try {
      const params = activeWorkspace?.id ? { workspace_id: activeWorkspace.id } : undefined
      const data: Instructions = await teamOs.instructions(authFetch, params)
      setInstructions(data)
      setDraft(data.content)
      // Load templates (non-fatal)
      try {
        const tData = await teamOs.templates(authFetch)
        setTemplates(tData)
      } catch {}
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to load instructions")
    }
  }, [authFetch, activeWorkspace?.id])

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
      const params = activeWorkspace?.id ? { workspace_id: activeWorkspace.id } : undefined
      const res = await teamOs.publishInstructions(authFetch, params, { content: draft })
      const data: Instructions = await res.json() as Instructions
      setInstructions(data)
      setSaved(true)
      setSuccessBanner(true)
      setTimeout(() => {
        setSaved(false)
        setSuccessBanner(false)
      }, 3000)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to publish")
    } finally {
      setSaving(false)
    }
  }

  return (
    <AppShell>
      {successBanner && (
        <div style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          zIndex: 100,
          background: "#10b981",
          color: "#fff",
          textAlign: "center",
          padding: "12px 16px",
          fontSize: 13.5,
          fontWeight: 600,
        }}>
          Instructions published — engineers will get this on next sync
        </div>
      )}
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
            {instructions && (
              <span style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "monospace" }}>
                {instructions.version}
              </span>
            )}
            {templates.length > 0 && (
              <div style={{ position: "relative" }}>
                <button
                  onClick={() => setShowTemplates(v => !v)}
                  style={{
                    padding: "7px 14px",
                    borderRadius: 8,
                    border: "1px solid var(--border)",
                    background: "var(--surface-2)",
                    color: "var(--text-2)",
                    fontSize: 13,
                    fontWeight: 500,
                    cursor: "pointer",
                  }}
                >
                  Start from template
                </button>
                {showTemplates && (
                  <div style={{
                    position: "absolute",
                    right: 0,
                    top: "calc(100% + 6px)",
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                    borderRadius: 10,
                    boxShadow: "0 4px 20px rgba(0,0,0,.1)",
                    zIndex: 200,
                    minWidth: 200,
                    overflow: "hidden",
                  }}>
                    {templates.map(t => (
                      <button
                        key={t.id}
                        onClick={() => { setDraft(t.content); setShowTemplates(false) }}
                        style={{
                          display: "block",
                          width: "100%",
                          textAlign: "left",
                          padding: "10px 16px",
                          fontSize: 13,
                          fontWeight: 500,
                          color: "var(--text)",
                          background: "transparent",
                          border: "none",
                          cursor: "pointer",
                          borderBottom: "1px solid var(--border)",
                        }}
                        onMouseEnter={e => (e.currentTarget.style.background = "var(--surface-2)")}
                        onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                      >
                        {t.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
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
              placeholder="Customize your team's AI instructions. This template is pre-filled with sensible defaults."
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
          <button
            onClick={() => router.push("/theguard/team-os")}
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
