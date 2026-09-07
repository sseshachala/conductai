"use client"

/**
 * Report-builder skeleton (#1450 PR 2).
 *
 * One page, three panes:
 *   - Left: saved layouts + "Start from template" buttons.
 *   - Center: widget grid of the active layout.
 *   - Right: widget picker (add) + save/rename.
 *
 * Widget cells are PLACEHOLDER cards in this PR — they show tool name +
 * hint + cell dimensions, sized per HINT_SIZES. PR 3 replaces the
 * placeholder body with live tool-call rendering per hint.
 */
import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"

import AppShell from "@/components/AppShell"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { useWorkspace } from "@/lib/WorkspaceContext"
import {
  HINT_SIZES,
  WIDGETS,
  widgetByName,
  type WidgetHint,
} from "@/lib/reportBuilder/widgets"
import { TEMPLATES, templateBySlug } from "@/lib/reportBuilder/templates"
import { reportLayoutsApi, type ReportLayout, type WidgetSpec } from "@/lib/reportBuilder/api"
import { useReportData } from "@/lib/reportBuilder/fetchers"
import { WidgetRenderer } from "@/lib/reportBuilder/renderers"

type LayoutDraft = {
  slug: string
  name: string
  layout_spec: WidgetSpec[]
  is_pinned: boolean
  existing: boolean // true = server has this slug; PUT vs POST on save
}

function slugify(input: string): string {
  return input
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64)
}

function draftFromLayout(l: ReportLayout): LayoutDraft {
  return {
    slug: l.slug,
    name: l.name,
    layout_spec: l.layout_spec.map((w) => ({ ...w })),
    is_pinned: Boolean(l.is_pinned),
    existing: true,
  }
}

function draftFromTemplate(t: (typeof TEMPLATES)[number]): LayoutDraft {
  return {
    slug: t.slug,
    name: t.name,
    layout_spec: t.widgets.map((w) => ({ ...w })),
    is_pinned: false,
    existing: false,
  }
}

function emptyDraft(): LayoutDraft {
  return { slug: "", name: "", layout_spec: [], is_pinned: false, existing: false }
}

export default function ReportBuilderPage() {
  const router = useRouter()
  const search = useSearchParams()
  const { authFetch } = useAuthFetch()
  const { activeWorkspace } = useWorkspace()
  const workspaceId = activeWorkspace?.id ?? null

  const initialSlug = search.get("slug")

  // #1450 PR 3: live widget data fetch (batches /dashboard once, obs endpoints
  // per unique tool). Re-runs on layout changes via toolNames join key.

  const [layouts, setLayouts] = useState<ReportLayout[]>([])
  const [draft, setDraft] = useState<LayoutDraft>(emptyDraft())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const reportData = useReportData(authFetch, workspaceId, draft.layout_spec)

  const refreshLayouts = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const list = await reportLayoutsApi.list(authFetch, workspaceId)
      setLayouts(list)
      setError(null)
    } catch (e) {
      setError(String((e as Error).message ?? e))
    } finally {
      setLoading(false)
    }
  }, [authFetch, workspaceId])

  useEffect(() => {
    if (!workspaceId) return
    void refreshLayouts()
  }, [workspaceId, refreshLayouts])

  useEffect(() => {
    if (!workspaceId || !initialSlug) return
    // Load a specific layout into the editor. Falls back to empty if 404.
    void (async () => {
      try {
        const l = await reportLayoutsApi.get(authFetch, workspaceId, initialSlug)
        setDraft(draftFromLayout(l))
      } catch {
        setDraft(emptyDraft())
      }
    })()
  }, [authFetch, workspaceId, initialSlug])

  const selectLayout = (l: ReportLayout) => {
    setDraft(draftFromLayout(l))
    router.replace(`/lens/report-builder?slug=${encodeURIComponent(l.slug)}`)
  }

  const startFromTemplate = (slug: string) => {
    const t = templateBySlug(slug)
    if (!t) return
    setDraft(draftFromTemplate(t))
    router.replace(`/lens/report-builder`)
  }

  const startBlank = () => {
    setDraft(emptyDraft())
    router.replace(`/lens/report-builder`)
  }

  const addWidget = (tool_name: string) => {
    const w = widgetByName(tool_name)
    if (!w) return
    setDraft((d) => ({
      ...d,
      layout_spec: [...d.layout_spec, { tool_name: w.tool_name, hint: w.hint }],
    }))
  }

  const removeWidgetAt = (idx: number) => {
    setDraft((d) => ({
      ...d,
      layout_spec: d.layout_spec.filter((_, i) => i !== idx),
    }))
  }

  const moveWidget = (idx: number, delta: -1 | 1) => {
    setDraft((d) => {
      const next = [...d.layout_spec]
      const target = idx + delta
      if (target < 0 || target >= next.length) return d
      ;[next[idx], next[target]] = [next[target], next[idx]]
      return { ...d, layout_spec: next }
    })
  }

  const save = async () => {
    if (!workspaceId) return
    const name = draft.name.trim() || "Untitled report"
    const slug = draft.slug.trim() || slugify(name)
    if (!slug) {
      setError("Slug is required (letters, numbers, hyphens).")
      return
    }
    setBusy(true)
    setError(null)
    try {
      if (draft.existing) {
        await reportLayoutsApi.update(authFetch, workspaceId, slug, {
          name,
          layout_spec: draft.layout_spec,
        })
      } else {
        await reportLayoutsApi.create(authFetch, workspaceId, {
          slug,
          name,
          layout_spec: draft.layout_spec,
        })
      }
      await refreshLayouts()
      setDraft((d) => ({ ...d, slug, name, existing: true }))
      router.replace(`/lens/report-builder?slug=${encodeURIComponent(slug)}`)
    } catch (e) {
      setError(String((e as Error).message ?? e))
    } finally {
      setBusy(false)
    }
  }

  const removeCurrent = async () => {
    if (!workspaceId || !draft.existing) return
    if (!confirm(`Delete report "${draft.name}"?`)) return
    setBusy(true)
    try {
      await reportLayoutsApi.remove(authFetch, workspaceId, draft.slug)
      await refreshLayouts()
      startBlank()
    } catch (e) {
      setError(String((e as Error).message ?? e))
    } finally {
      setBusy(false)
    }
  }

  const togglePin = async () => {
    if (!workspaceId || !draft.existing) return
    const next = !draft.is_pinned
    setDraft((d) => ({ ...d, is_pinned: next }))
    try {
      await reportLayoutsApi.update(authFetch, workspaceId, draft.slug, { is_pinned: next })
      await refreshLayouts()
      // #1450 PR 5: signal AppShell to refetch pinned reports so the sidebar
      // reflects the pin/unpin without a route change.
      window.dispatchEvent(new Event("reports:changed"))
    } catch (e) {
      // Revert on failure
      setDraft((d) => ({ ...d, is_pinned: !next }))
      setError(String((e as Error).message ?? e))
    }
  }

  const picker = useMemo(() => {
    return WIDGETS
  }, [])

  return (
    <AppShell>
      <div className="mx-auto max-w-[1400px] px-6 py-6">
        <header className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Report builder</h1>
            <p className="text-sm text-neutral-500">
              Compose a report from workspace-level widgets. Reports are shared with everyone in this workspace.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {draft.existing && (
              <button
                type="button"
                className={`rounded border px-3 py-1.5 text-sm ${
                  draft.is_pinned
                    ? "border-yellow-400 bg-yellow-50 text-yellow-800"
                    : "border-neutral-300 hover:bg-neutral-50"
                }`}
                onClick={togglePin}
                title={draft.is_pinned ? "Unpin from nav" : "Pin to nav"}
              >
                {draft.is_pinned ? "★ Pinned" : "☆ Pin"}
              </button>
            )}
            <button
              type="button"
              className="rounded border border-neutral-300 px-3 py-1.5 text-sm hover:bg-neutral-50"
              onClick={startBlank}
            >
              New blank
            </button>
            {draft.existing && (
              <button
                type="button"
                className="rounded border border-red-300 px-3 py-1.5 text-sm text-red-600 hover:bg-red-50"
                onClick={removeCurrent}
                disabled={busy}
              >
                Delete
              </button>
            )}
            <button
              type="button"
              className="rounded bg-neutral-900 px-3 py-1.5 text-sm text-white hover:bg-neutral-800 disabled:opacity-50"
              onClick={save}
              disabled={busy || !workspaceId}
            >
              {draft.existing ? "Save" : "Create"}
            </button>
          </div>
        </header>

        {error && (
          <div className="mb-4 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="grid grid-cols-[240px_minmax(0,1fr)_280px] gap-6">
          {/* Left: saved layouts + templates */}
          <aside className="space-y-6">
            <section>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-neutral-500">
                Templates
              </h2>
              <ul className="space-y-1">
                {TEMPLATES.map((t) => (
                  <li key={t.slug}>
                    <button
                      type="button"
                      className="w-full rounded px-2 py-1.5 text-left text-sm hover:bg-neutral-100"
                      onClick={() => startFromTemplate(t.slug)}
                      title={t.description}
                    >
                      {t.name}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-neutral-500">
                Saved reports
              </h2>
              {loading ? (
                <p className="text-sm text-neutral-500">Loading…</p>
              ) : layouts.length === 0 ? (
                <p className="text-sm text-neutral-500">No saved reports yet.</p>
              ) : (
                <ul className="space-y-1">
                  {layouts.map((l) => (
                    <li key={l.id}>
                      <button
                        type="button"
                        className={`w-full rounded px-2 py-1.5 text-left text-sm hover:bg-neutral-100 ${
                          l.slug === draft.slug ? "bg-neutral-100 font-medium" : ""
                        }`}
                        onClick={() => selectLayout(l)}
                      >
                        {l.name}
                        <span className="ml-2 text-xs text-neutral-400">{l.slug}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </aside>

          {/* Center: grid + name/slug */}
          <main className="min-w-0">
            <div className="mb-4 flex items-center gap-3">
              <label className="text-sm font-medium">Name</label>
              <input
                type="text"
                value={draft.name}
                onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                placeholder="Ops Overview"
                className="w-64 rounded border border-neutral-300 px-2 py-1 text-sm"
              />
              <label className="text-sm font-medium">Slug</label>
              <input
                type="text"
                value={draft.slug}
                onChange={(e) => setDraft((d) => ({ ...d, slug: slugify(e.target.value) }))}
                placeholder="ops-overview"
                disabled={draft.existing}
                className="w-48 rounded border border-neutral-300 px-2 py-1 text-sm disabled:bg-neutral-50"
              />
            </div>

            {draft.layout_spec.length === 0 ? (
              <div className="rounded border border-dashed border-neutral-300 p-10 text-center text-sm text-neutral-500">
                Empty report. Pick widgets from the right, or start from a template on the left.
              </div>
            ) : (
              <div
                className="grid gap-4"
                style={{
                  gridTemplateColumns: "repeat(12, minmax(0, 1fr))",
                  gridAutoRows: "80px",
                  gridAutoFlow: "dense",
                }}
              >
                {draft.layout_spec.map((w, idx) => {
                  const meta = widgetByName(w.tool_name)
                  const size = HINT_SIZES[(w.hint as WidgetHint) in HINT_SIZES ? (w.hint as WidgetHint) : "kpi_card"]
                  return (
                    <div
                      key={`${w.tool_name}-${idx}`}
                      style={{
                        gridColumn: `span ${size.col}`,
                        gridRow: `span ${size.row}`,
                        background: "var(--surface)",
                        border: "1px solid var(--border)",
                        borderRadius: 12,
                        padding: 14,
                        boxShadow: "var(--shadow-sm)",
                        display: "flex",
                        flexDirection: "column",
                        minHeight: 0,
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 8 }}>
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {meta?.label ?? w.tool_name}
                          </div>
                          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase", color: "var(--text-muted)", marginTop: 2 }}>
                            {w.hint.replace("_", " ")}
                          </div>
                        </div>
                        <div style={{ display: "flex", gap: 2 }}>
                          <button
                            type="button"
                            style={{ padding: "3px 7px", borderRadius: 6, fontSize: 12, color: "var(--text-muted)", background: "transparent", border: "none", cursor: idx === 0 ? "default" : "pointer", opacity: idx === 0 ? 0.3 : 1 }}
                            onClick={() => moveWidget(idx, -1)}
                            title="Move up"
                            disabled={idx === 0}
                          >
                            ↑
                          </button>
                          <button
                            type="button"
                            style={{ padding: "3px 7px", borderRadius: 6, fontSize: 12, color: "var(--text-muted)", background: "transparent", border: "none", cursor: idx === draft.layout_spec.length - 1 ? "default" : "pointer", opacity: idx === draft.layout_spec.length - 1 ? 0.3 : 1 }}
                            onClick={() => moveWidget(idx, 1)}
                            title="Move down"
                            disabled={idx === draft.layout_spec.length - 1}
                          >
                            ↓
                          </button>
                          <button
                            type="button"
                            style={{ padding: "3px 7px", borderRadius: 6, fontSize: 12, color: "var(--text-muted)", background: "transparent", border: "none", cursor: "pointer" }}
                            onClick={() => removeWidgetAt(idx)}
                            title="Remove"
                          >
                            ×
                          </button>
                        </div>
                      </div>
                      <div style={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
                        <WidgetRenderer hint={w.hint} state={reportData.get(w.tool_name)} />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </main>

          {/* Right: widget picker */}
          <aside>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-neutral-500">
              Widgets
            </h2>
            <ul className="space-y-1">
              {picker.map((w) => (
                <li key={w.tool_name}>
                  <button
                    type="button"
                    className="w-full rounded px-2 py-2 text-left text-sm hover:bg-neutral-100"
                    onClick={() => addWidget(w.tool_name)}
                    title={w.description}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{w.label}</span>
                      <span className="text-xs text-neutral-400">{w.hint}</span>
                    </div>
                    <div className="text-xs text-neutral-500">{w.description}</div>
                  </button>
                </li>
              ))}
            </ul>
          </aside>
        </div>
      </div>
    </AppShell>
  )
}
