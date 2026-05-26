"use client"

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
    <div className="flex items-start justify-between gap-6 py-4 border-b border-stone-100 last:border-0">
      <div className="flex-1">
        <p className="text-sm font-medium text-stone-900">{label}</p>
        <p className="text-xs text-stone-500 mt-0.5">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors mt-0.5 ${
          checked ? "bg-indigo-500" : "bg-stone-200"
        }`}
      >
        <span
          className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${
            checked ? "translate-x-4.5" : "translate-x-0.5"
          }`}
        />
      </button>
    </div>
  )
}

export default function PreferencesPanel() {
  const { prefs, loading, update } = usePreferences()

  if (loading) {
    return <div className="text-sm text-stone-400 py-4">Loading preferences…</div>
  }

  return (
    <div className="bg-white rounded-xl border border-stone-200 divide-y divide-stone-100 px-5">
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
  )
}
