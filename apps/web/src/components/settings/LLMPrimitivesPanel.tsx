"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API } from "@/lib/api"

interface LLMPrimitives {
  preferred_provider: string
  tier_map: Record<string, string>
  updated_at: string | null
}

const PROVIDERS = ["anthropic", "openai", "perplexity", "together"] as const
const TIERS = ["cheap", "balanced", "smart"] as const

const PROVIDER_HINTS: Record<(typeof PROVIDERS)[number], string> = {
  anthropic:  "Claude models — Opus / Sonnet / Haiku",
  openai:     "GPT models — 4.1 / 4o / o-series",
  perplexity: "Sonar reasoning / search models",
  together:   "Together AI hosted OSS models",
}

export default function LLMPrimitivesPanel({
  workspaceId,
  isAdmin,
}: {
  workspaceId: string
  isAdmin: boolean
}) {
  const { authFetch } = useAuthFetch()
  const [primitives, setPrimitives] = useState<LLMPrimitives | null>(null)
  const [tierMapText, setTierMapText] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState("")

  const load = useCallback(async () => {
    if (!workspaceId) return
    setLoading(true)
    try {
      const res = await authFetch(`${API}/workspaces/${workspaceId}/llm-primitives`)
      if (!res.ok) throw new Error(`Load failed (${res.status})`)
      const data = (await res.json()) as LLMPrimitives
      setPrimitives(data)
      setTierMapText(JSON.stringify(data.tier_map ?? {}, null, 2))
      setError("")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed")
    } finally {
      setLoading(false)
    }
  }, [authFetch, workspaceId])

  useEffect(() => { load() }, [load])

  const parseError = useMemo(() => {
    if (!tierMapText.trim()) return null
    try {
      const parsed = JSON.parse(tierMapText)
      if (typeof parsed !== "object" || Array.isArray(parsed) || parsed === null) {
        return "tier_map must be a JSON object"
      }
      for (const [k, v] of Object.entries(parsed)) {
        if (!(TIERS as readonly string[]).includes(k)) {
          return `Unknown tier ${JSON.stringify(k)} — must be one of ${TIERS.join(", ")}`
        }
        if (typeof v !== "string" || !v.trim()) {
          return `Model for tier ${JSON.stringify(k)} must be a non-empty string`
        }
      }
      return null
    } catch (e) {
      return e instanceof Error ? e.message : "Invalid JSON"
    }
  }, [tierMapText])

  async function save() {
    if (!primitives || parseError) return
    setSaving(true); setError(""); setSaved(false)
    try {
      const tier_map = tierMapText.trim() ? JSON.parse(tierMapText) : {}
      const res = await authFetch(`${API}/workspaces/${workspaceId}/llm-primitives`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          preferred_provider: primitives.preferred_provider,
          tier_map,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.detail ?? `Save failed (${res.status})`)
      }
      const data = (await res.json()) as LLMPrimitives
      setPrimitives(data)
      setTierMapText(JSON.stringify(data.tier_map ?? {}, null, 2))
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed")
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div style={{ height: 120, borderRadius: 12, background: "var(--surface-2)", border: "1px solid var(--border)", opacity: 0.7 }} />
  }

  if (!primitives) {
    return <p style={{ fontSize: 13, color: "var(--text-muted)" }}>{error || "Unable to load LLM Model Primitives."}</p>
  }

  const canSave = isAdmin && !saving && !parseError

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h2 style={{ fontSize: 15, fontWeight: 600, color: "var(--text)", margin: 0 }}>LLM Model Primitives</h2>
        <p style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
          Workspace-scoped routing config for every LLM caller — Lens, workflows, brain blocks. API keys stay in Vault; this tab only decides which provider and model tier is used.
        </p>
      </div>

      <div className="card" style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <label style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text)" }}>Preferred provider</label>
          <select
            value={primitives.preferred_provider}
            onChange={e => setPrimitives({ ...primitives, preferred_provider: e.target.value })}
            disabled={!isAdmin}
            style={{ fontSize: 13, padding: "8px 10px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", color: "var(--text)", outline: "none", maxWidth: 320 }}
          >
            {PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <p style={{ fontSize: 11.5, color: "var(--text-muted)", margin: 0 }}>
            {PROVIDER_HINTS[primitives.preferred_provider as (typeof PROVIDERS)[number]] ?? "Custom provider"}
          </p>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <label style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text)" }}>Tier map (JSON)</label>
          <textarea
            value={tierMapText}
            onChange={e => setTierMapText(e.target.value)}
            disabled={!isAdmin}
            rows={7}
            spellCheck={false}
            className="mono"
            style={{ fontSize: 12, padding: "10px 12px", border: `1px solid ${parseError ? "var(--err-bd)" : "var(--border)"}`, borderRadius: 8, background: "var(--surface)", color: "var(--text)", outline: "none", resize: "vertical" }}
          />
          <p style={{ fontSize: 11.5, color: parseError ? "var(--err)" : "var(--text-muted)", margin: 0 }}>
            {parseError ?? `Keys: ${TIERS.join(" / ")}. Values are model IDs (e.g. claude-sonnet-4-6, gpt-4.1-mini).`}
          </p>
        </div>

        {error && <p style={{ fontSize: 12, color: "var(--err)", margin: 0 }}>{error}</p>}

        {isAdmin && (
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button
              onClick={save}
              disabled={!canSave}
              className="btn btn-primary btn-sm"
              style={{ opacity: canSave ? 1 : 0.5 }}
            >
              {saving ? "Saving…" : saved ? "Saved ✓" : "Save"}
            </button>
            {primitives.updated_at && (
              <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
                Last updated {new Date(primitives.updated_at).toLocaleString()}
              </span>
            )}
          </div>
        )}
      </div>

      <p style={{ fontSize: 11.5, color: "var(--text-muted)", margin: 0 }}>
        Consumer wiring (Lens, workflows, Guard) lands in follow-up PRs — see issue #1347.
      </p>
    </div>
  )
}
