"use client"

/**
 * Canvas panel — workspace-wide toggles for the workflow canvas UI.
 * Extracted from PreferencesPanel during #1359 so canvas options aren't
 * buried under Appearance (theme/accent). Storage still lives in the
 * same workspace preferences endpoint.
 */

import { usePreferences } from "@/lib/PreferencesContext"

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string
  description: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 24, padding: "14px 0", borderBottom: "1px solid var(--border)" }}>
      <div style={{ flex: 1 }}>
        <p style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text)" }}>{label}</p>
        <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        style={{ position: "relative", display: "inline-flex", width: 36, height: 20, flexShrink: 0, alignItems: "center", borderRadius: 10, border: "none", cursor: "pointer", marginTop: 2, background: checked ? "var(--accent)" : "var(--border-2, #d4d0cb)", transition: "background .15s" }}
      >
        <span
          style={{ display: "inline-block", width: 14, height: 14, borderRadius: "50%", background: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,.2)", transition: "transform .15s", transform: checked ? "translateX(18px)" : "translateX(3px)" }}
        />
      </button>
    </div>
  )
}

export default function CanvasPanel() {
  const { prefs, loading, update } = usePreferences()

  if (loading) {
    return <div style={{ fontSize: 13, color: "var(--text-muted)", padding: "16px 0" }}>Loading preferences…</div>
  }

  return (
    <div style={{ maxWidth: 760 }}>
      <div className="eyebrow" style={{ marginBottom: 12 }}>Canvas toolbar</div>
      <div className="card" style={{ padding: "0 18px" }}>
        <ToggleRow
          label="Show Test Trigger button"
          description="Adds a 'Test Trigger' button to the canvas toolbar — fires a real run with a safe dummy payload."
          checked={prefs.show_test_trigger}
          onChange={v => update({ show_test_trigger: v })}
        />
        <ToggleRow
          label="Show Dry Run button"
          description="Adds a 'Dry Run' button to the canvas toolbar — simulates the workflow without calling any external APIs."
          checked={prefs.show_dry_run}
          onChange={v => update({ show_dry_run: v })}
        />
      </div>
    </div>
  )
}
