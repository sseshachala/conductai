"use client"

import { useEffect, useState, useCallback } from "react"

interface SlackIntegration {
  id: string
  handle: string
  environment_id: string | null
}

interface Props {
  base: string
  wsId: string | undefined
  buildHeaders: () => Promise<Record<string, string>>
  integrationId: string | null
  channel: string
  isAdmin: boolean
  onSave: (integrationId: string | null, channel: string) => Promise<void>
}

export function SlackIntegrationPicker({ base, wsId, buildHeaders, integrationId, channel, isAdmin, onSave }: Props) {
  const [integrations, setIntegrations] = useState<SlackIntegration[]>([])
  const [loaded, setLoaded] = useState(false)
  const [selectedId, setSelectedId] = useState<string>(integrationId ?? "")
  const [channelInput, setChannelInput] = useState(channel.replace(/^#+/, ""))
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const load = useCallback(async () => {
    if (!wsId) return
    try {
      const headers = await buildHeaders()
      const res = await fetch(`${base}/credentials/integrations/slack?workspace_id=${wsId}`, { headers })
      if (res.ok) setIntegrations(await res.json())
    } catch {}
    setLoaded(true)
  }, [base, wsId, buildHeaders])

  useEffect(() => { load() }, [load])
  useEffect(() => { setSelectedId(integrationId ?? "") }, [integrationId])
  useEffect(() => { setChannelInput(channel.replace(/^#+/, "")) }, [channel])

  async function handleSave() {
    setSaving(true)
    try {
      await onSave(selectedId || null, channelInput)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  if (!loaded) return null

  if (integrations.length === 0) {
    return (
      <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: 8, background: "var(--warn-bg, #fffbeb)", border: "1px solid var(--warn-bd, #fde68a)", fontSize: 12, color: "var(--warn, #92400e)" }}>
        No Slack integration found.{" "}
        <a href="/settings/credentials" style={{ color: "inherit", fontWeight: 600, textDecoration: "underline" }}>
          Add in Settings → Credentials →
        </a>
      </div>
    )
  }

  return (
    <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", gap: 8 }}>
        <select
          value={selectedId}
          disabled={!isAdmin}
          onChange={e => isAdmin && setSelectedId(e.target.value)}
          style={{
            flex: 1, height: 36, padding: "0 10px", fontSize: 13,
            border: "1px solid var(--border-2)", borderRadius: 8,
            background: "var(--surface)", color: "var(--text)",
            opacity: isAdmin ? 1 : 0.6, cursor: isAdmin ? "pointer" : "default",
          }}
        >
          <option value="">Select Slack integration…</option>
          {integrations.map(i => (
            <option key={i.id} value={i.id}>{i.handle}</option>
          ))}
        </select>
        <div style={{ display: "flex", alignItems: "center", border: "1px solid var(--border-2)", borderRadius: 8, overflow: "hidden", width: 180 }}>
          <span style={{ padding: "0 8px", fontSize: 13, color: "var(--text-muted)", background: "var(--surface-2)", borderRight: "1px solid var(--border)", alignSelf: "stretch", display: "flex", alignItems: "center", userSelect: "none" }}>#</span>
          <input
            type="text"
            value={channelInput}
            onChange={e => isAdmin && setChannelInput(e.target.value.replace(/^#+/, ""))}
            placeholder="general"
            disabled={!isAdmin}
            className="mono"
            style={{ flex: 1, fontSize: 13, padding: "0 10px", height: 36, border: "none", background: "transparent", color: "var(--text)", outline: "none", opacity: isAdmin ? 1 : 0.6 }}
            onKeyDown={e => { if (e.key === "Enter" && isAdmin) handleSave() }}
          />
        </div>
        {isAdmin && (
          <button onClick={handleSave} disabled={saving || !selectedId} className="btn btn-ghost btn-sm">
            {saving ? "Saving…" : "Save"}
          </button>
        )}
        {saved && <span style={{ fontSize: 12, color: "var(--ok)", fontWeight: 600, alignSelf: "center" }}>Saved</span>}
      </div>
    </div>
  )
}
