"use client"

import { entriesForEnv, VAULT_SERVICE_LABEL, type VaultEntry, type VaultService } from "./vault"

/**
 * Pick a Vault entry for a PagerDuty / Webhook / Email channel from the entries
 * of the page-level selected Vault (environment). Replaces typing a secret.
 * `optional` (email) adds a "workspace default" choice.
 */
export default function VaultEntryPicker({
  service,
  entries,
  envId,
  value,
  onChange,
  optional = false,
}: {
  service: Exclude<VaultService, "slack">
  entries: VaultEntry[]
  envId: string
  value: string
  onChange: (id: string) => void
  optional?: boolean
}) {
  const label = VAULT_SERVICE_LABEL[service]
  const options = entriesForEnv(entries, envId)
  return (
    <>
      <select
        aria-label={`${label} Vault entry`}
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{ flex: 1, minWidth: 160, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", fontSize: 12.5 }}
      >
        {optional
          ? <option value="">Workspace default credential</option>
          : <option value="" disabled>Select a {label} entry…</option>}
        {options.map(e => (
          <option key={e.id} value={e.id}>{e.handle}{e.environment_name ? ` · ${e.environment_name}` : ""}</option>
        ))}
      </select>
      {options.length === 0 && (
        <a href="/settings?tab=credentials" style={{ fontSize: 11.5, color: "var(--info)", textDecoration: "underline" }}>
          No {label} entry — add one in Settings → Vault
        </a>
      )}
    </>
  )
}
