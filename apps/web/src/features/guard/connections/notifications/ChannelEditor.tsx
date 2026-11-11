"use client"

import { useState } from "react"
import VaultEntryPicker from "./VaultEntryPicker"
import type { VaultEntries, VaultEnvironment, VaultService } from "./vault"

/** Fields of a channel row (Guard rule or alert) the editors need. */
export interface EditableChannel {
  channel_type: string
  integration_id?: string | null
  channel_ref: string
}

export interface RelinkBody { integration_id: string; channel_ref?: string }
export interface MoveBody { environment_id: string; handle: string }

const box = { display: "flex", alignItems: "center", gap: 6, marginTop: 6, padding: "6px 8px", background: "var(--surface-2)", borderRadius: 6, flexWrap: "wrap" } as const
const field = { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", fontSize: 12.5 } as const

/**
 * Inline "Edit" form: pick which Vault entry a channel uses (and the recipient
 * for email). The server validates service, workspace and webhook egress.
 */
export function RelinkForm({
  channel, vaultEntries, onSave, onCancel,
}: {
  channel: EditableChannel
  vaultEntries: VaultEntries
  onSave: (body: RelinkBody) => Promise<void> | void
  onCancel: () => void
}) {
  const service = channel.channel_type as VaultService
  const isEmail = service === "email"
  const [entryId, setEntryId] = useState(channel.integration_id ?? "")
  const [recipient, setRecipient] = useState(isEmail ? channel.channel_ref : "")
  // Email may fall back to the workspace credential; every other type needs an entry.
  const canSave = isEmail ? !!recipient.trim() : !!entryId
  return (
    <div style={box} data-testid="relink-form">
      <VaultEntryPicker
        service={service}
        entries={vaultEntries[service] ?? []}
        envId=""
        value={entryId}
        onChange={setEntryId}
        optional={isEmail}
      />
      {isEmail && (
        <input
          aria-label="Recipient address"
          type="email"
          value={recipient}
          onChange={e => setRecipient(e.target.value)}
          style={{ ...field, flex: 1, minWidth: 160 }}
        />
      )}
      <button type="button" className="btn btn-primary btn-sm" style={{ fontSize: 11, opacity: canSave ? 1 : 0.5 }}
        disabled={!canSave}
        onClick={() => void onSave(isEmail ? { integration_id: entryId, channel_ref: recipient.trim() } : { integration_id: entryId })}>
        Save
      </button>
      <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 11 }} onClick={onCancel}>Cancel</button>
    </div>
  )
}

/**
 * Inline "Move to Vault" form for a legacy typed key/URL. Only the target
 * environment and handle are sent; the API reads the secret from the row.
 */
export function MoveToVaultForm({
  channel, environments, defaultEnvId, onMove, onCancel,
}: {
  channel: EditableChannel
  environments: VaultEnvironment[]
  defaultEnvId: string
  onMove: (body: MoveBody) => Promise<void> | void
  onCancel: () => void
}) {
  const [envId, setEnvId] = useState(defaultEnvId || environments[0]?.id || "")
  const [handle, setHandle] = useState(channel.channel_type)
  const canSave = !!envId && !!handle.trim()
  return (
    <div style={box} data-testid="move-form">
      <select aria-label="Vault environment" value={envId} onChange={e => setEnvId(e.target.value)} style={field}>
        {environments.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}
      </select>
      <input
        aria-label="Vault handle"
        value={handle}
        onChange={e => setHandle(e.target.value)}
        placeholder="handle"
        style={{ ...field, flex: 1, minWidth: 120 }}
      />
      <button type="button" className="btn btn-primary btn-sm" style={{ fontSize: 11, opacity: canSave ? 1 : 0.5 }}
        disabled={!canSave} onClick={() => void onMove({ environment_id: envId, handle: handle.trim() })}>
        Move
      </button>
      <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 11 }} onClick={onCancel}>Cancel</button>
    </div>
  )
}
