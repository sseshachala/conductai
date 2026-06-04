"use client"

import { useState, useEffect } from "react"
import { usePreferences } from "@/lib/PreferencesContext"

const ACCENTS: Record<string, { base: string; hover: string; ring: string; weak: string; weak2: string; text: string }> = {
  indigo:  { base: "#4f46e5", hover: "#4338ca", ring: "#818cf8", weak: "#eef2ff", weak2: "#e0e7ff", text: "#4338ca" },
  violet:  { base: "#7c3aed", hover: "#6d28d9", ring: "#a78bfa", weak: "#f5f3ff", weak2: "#ede9fe", text: "#6d28d9" },
  emerald: { base: "#059669", hover: "#047857", ring: "#34d399", weak: "#ecfdf5", weak2: "#d1fae5", text: "#047857" },
  blue:    { base: "#2563eb", hover: "#1d4ed8", ring: "#93c5fd", weak: "#eff6ff", weak2: "#dbeafe", text: "#1d4ed8" },
  amber:   { base: "#d97706", hover: "#b45309", ring: "#fcd34d", weak: "#fffbeb", weak2: "#fef3c7", text: "#b45309" },
}

function hexToRgb(hex: string): [number, number, number] | null {
  const clean = hex.trim().replace(/^#/, "")
  if (!/^[0-9a-fA-F]{6}$/.test(clean)) return null
  return [
    Number.parseInt(clean.slice(0, 2), 16),
    Number.parseInt(clean.slice(2, 4), 16),
    Number.parseInt(clean.slice(4, 6), 16),
  ]
}

function getAccentContrast(hex: string): string {
  const rgb = hexToRgb(hex)
  if (!rgb) return "#ffffff"
  const [r, g, b] = rgb
  const srgb = [r, g, b].map(v => v / 255).map(v =>
    v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
  )
  const l = (0.2126 * srgb[0]) + (0.7152 * srgb[1]) + (0.0722 * srgb[2])
  return l > 0.45 ? "#111827" : "#ffffff"
}

const SEMANTIC_VARS = [
  "--ok", "--ok-bg", "--ok-bd",
  "--warn", "--warn-bg", "--warn-bd",
  "--err", "--err-bg", "--err-bd",
  "--info", "--info-bg", "--info-bd",
]

function applyTheme(look: string, accent: string) {
  if (typeof document === "undefined") return
  document.documentElement.setAttribute("data-theme", look === "dark" ? "dark" : "light")
  const A = ACCENTS[accent] ?? ACCENTS.indigo
  const dark = look === "dark"
  const r = document.documentElement.style
  r.setProperty("--accent",       A.base)
  r.setProperty("--accent-hover", dark ? A.ring  : A.hover)
  r.setProperty("--accent-ring",  A.ring)
  r.setProperty("--accent-weak",  dark ? `color-mix(in srgb, ${A.base} 18%, transparent)` : A.weak)
  r.setProperty("--accent-weak-2",dark ? `color-mix(in srgb, ${A.base} 30%, transparent)` : A.weak2)
  r.setProperty("--accent-text",  dark ? A.ring  : A.text)
  r.setProperty("--accent-contrast", getAccentContrast(A.base))

  // Ensure semantic tokens come from CSS theme definitions, not stale inline overrides.
  for (const v of SEMANTIC_VARS) r.removeProperty(v)
}

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

function ThemePreview({ dark }: { dark: boolean }) {
  const v = dark
    ? { bg: "#0b0a09", side: "#141210", bd: "#2a2624", t: "#f5f3f0", t2: "#8c847d", card: "#1c1917", acc: "var(--accent)" }
    : { bg: "#faf9f7", side: "#ffffff", bd: "#e7e5e4", t: "#1c1917", t2: "#a8a29e", card: "#ffffff", acc: "var(--accent)" }
  return (
    <div style={{ display: "flex", height: 96, borderRadius: 9, overflow: "hidden", border: "1px solid " + v.bd, background: v.bg }}>
      <div style={{ width: 46, background: v.side, borderRight: "1px solid " + v.bd, padding: 8, display: "flex", flexDirection: "column", gap: 5 }}>
        <div style={{ width: 16, height: 16, borderRadius: 5, background: v.acc }} />
        <div style={{ height: 6, borderRadius: 3, background: v.acc, opacity: .9 }} />
        <div style={{ height: 6, borderRadius: 3, background: v.t2, opacity: .4 }} />
        <div style={{ height: 6, borderRadius: 3, background: v.t2, opacity: .4 }} />
      </div>
      <div style={{ flex: 1, padding: 10 }}>
        <div style={{ height: 8, width: "55%", borderRadius: 3, background: v.t, marginBottom: 9 }} />
        <div style={{ display: "flex", gap: 6 }}>
          {[0, 1, 2].map(i => <div key={i} style={{ flex: 1, height: 30, borderRadius: 6, background: v.card, border: "1px solid " + v.bd }} />)}
        </div>
        <div style={{ height: 18, borderRadius: 5, background: v.card, border: "1px solid " + v.bd, marginTop: 8 }} />
      </div>
    </div>
  )
}

export default function PreferencesPanel() {
  const { prefs, loading, update } = usePreferences()
  const [look, setLookState] = useState("light")
  const [accent, setAccentState] = useState("indigo")

  useEffect(() => {
    if (typeof window !== "undefined") {
      setLookState(localStorage.getItem("conduct-theme") ?? "light")
      setAccentState(localStorage.getItem("conduct-accent") ?? "indigo")
    }
  }, [])

  function setLook(k: string) {
    setLookState(k)
    if (typeof window !== "undefined") localStorage.setItem("conduct-theme", k)
    applyTheme(k, accent)
  }

  function setAccent(k: string) {
    setAccentState(k)
    if (typeof window !== "undefined") localStorage.setItem("conduct-accent", k)
    applyTheme(look, k)
  }

  if (loading) {
    return <div style={{ fontSize: 13, color: "var(--text-muted)", padding: "16px 0" }}>Loading preferences…</div>
  }

  return (
    <div style={{ maxWidth: 760 }}>
      <div className="eyebrow" style={{ marginBottom: 12 }}>Theme</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 30 }}>
        {[
          { k: "light", title: "Light", sub: "The default developer-focused light theme." },
          { k: "dark",  title: "Command Center", sub: "A bolder dark theme for dashboards and long sessions." },
        ].map(o => {
          const sel = look === o.k
          return (
            <div key={o.k} onClick={() => setLook(o.k)} className="card"
              style={{ padding: 14, cursor: "pointer", borderColor: sel ? "var(--accent-ring)" : "var(--border)", boxShadow: sel ? "var(--shadow-md)" : "none" }}>
              <ThemePreview dark={o.k === "dark"} />
              <div style={{ display: "flex", alignItems: "center", gap: 9, marginTop: 13 }}>
                <span style={{ width: 17, height: 17, borderRadius: "50%", border: "2px solid " + (sel ? "var(--accent)" : "var(--border-2)"), display: "grid", placeItems: "center", flexShrink: 0 }}>
                  {sel && <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--accent)" }} />}
                </span>
                <div>
                  <div style={{ fontWeight: 650, fontSize: 14 }}>{o.title}</div>
                  <div style={{ fontSize: 12, color: "var(--text-3)" }}>{o.sub}</div>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <div className="eyebrow" style={{ marginBottom: 12 }}>Accent colour</div>
      <div className="card" style={{ padding: "16px 18px", display: "flex", alignItems: "center", gap: 16, marginBottom: 30 }}>
        <div style={{ display: "flex", gap: 11 }}>
          {(Object.entries({ indigo: "#4f46e5", violet: "#7c3aed", emerald: "#059669", blue: "#2563eb", amber: "#d97706" }) as [string, string][]).map(([k, v]) => {
            const sel = accent === k
            return (
              <button key={k} onClick={() => setAccent(k)} title={k}
                style={{ width: 34, height: 34, borderRadius: 10, background: v, cursor: "pointer",
                  border: sel ? "2.5px solid var(--text)" : "2.5px solid transparent",
                  outline: sel ? "1px solid var(--border)" : "none",
                  boxShadow: "inset 0 0 0 1.5px rgba(255,255,255,.35)" }} />
            )
          })}
        </div>
        <span style={{ fontSize: 12.5, color: "var(--text-muted)", textTransform: "capitalize" }}>Selected: {accent}</span>
      </div>

      <div className="eyebrow" style={{ marginBottom: 12 }}>Canvas options</div>
      <div className="card" style={{ padding: "0 18px" }}>
        <ToggleRow
          label="Show Test Trigger button"
          description="Adds a 'Test Run' button to the canvas toolbar — fires a real run with a safe dummy payload."
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
