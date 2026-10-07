"use client"

import { useCallback, useEffect, useId, useMemo, useState } from "react"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { API, credentials, guard } from "@/lib/api"
import type { GatewayProfileV2Out } from "@/lib/api/guard"
import { validateGatewayProfileFields } from "@/lib/gatewayProfileValidation"
import { validateTargetsAgainstAccepts } from "@/lib/gatewayCapabilityCatalog"
import { catalogTarget, deriveAccepts, type EnvironmentRow, type CredentialRow, type DraftTarget, type EditorState, emptyTarget, stateFromProfile, stateToWorkingCopy, inputStyle } from "./gateway-profile-v2-editor/state"
import { FieldLabel } from "./gateway-profile-v2-editor/fields"
import { TargetRow } from "./gateway-profile-v2-editor/TargetRow"

// #2007 — Gateway Profile v2 draft editor. Loads a profile's working_copy,
// renders it as a form (name, model_alias, accepts, timeouts, ordered
// target list with add/remove/reorder), and saves the draft through the
// Gateway Profile v2 API.

// LLM Model Primitives is the single source of truth for the model
// catalog. No hardcoded fallback — if the fetch fails the editor
// surfaces the error and the dropdown stays empty until the operator
// fixes primitives. Preserves the "one source of truth" invariant even
// when the API is down (better a visible empty state than a stale
// hardcoded list that lies about which models the workspace approved).

export default function GatewayProfileV2Editor({
  workspaceId, profile, envs, isAdmin, onSaved,
}: {
  workspaceId: string
  profile: GatewayProfileV2Out
  envs: EnvironmentRow[]
  isAdmin: boolean
  onSaved: () => void
}) {
  const { authFetch } = useAuthFetch()
  const formId = useId()
  const [state, setState] = useState<EditorState>(() => stateFromProfile(profile))
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState("")
  const [err, setErr] = useState("")
  const [credsByEnv, setCredsByEnv] = useState<Record<string, CredentialRow[]>>({})
  // Workspace-scoped LLM Model Primitives — the SINGLE source of truth
  // for which model IDs a workspace has decided to use per (provider,
  // tier). Fetched once on mount. Error state is loud (banner) so the
  // operator can go fix primitives instead of seeing a stale hardcoded
  // list masquerading as truth.
  const [tierMap, setTierMap] = useState<Record<string, Record<string, string>>>({})
  const [primitivesLoading, setPrimitivesLoading] = useState(true)
  const [primitivesError, setPrimitivesError] = useState("")
  const providerKeys = useMemo(() => Object.keys(tierMap).sort(), [tierMap])

  useEffect(() => {
    setState(stateFromProfile(profile))
    setMsg(""); setErr("")
  }, [profile])

  useEffect(() => {
    if (!workspaceId) return
    setPrimitivesLoading(true)
    setPrimitivesError("")
    ;(async () => {
      try {
        const res = await authFetch(`${API}/workspaces/${workspaceId}/llm-primitives`)
        if (!res.ok) {
          throw new Error(`LLM Model Primitives fetch failed (${res.status})`)
        }
        const data = await res.json() as { tier_map?: Record<string, Record<string, string>> }
        setTierMap(data.tier_map ?? {})
      } catch (e) {
        setPrimitivesError(e instanceof Error ? e.message : "LLM Model Primitives fetch failed")
        setTierMap({})
      } finally {
        setPrimitivesLoading(false)
      }
    })()
  }, [authFetch, workspaceId])

  const loadCreds = useCallback(async (envId: string) => {
    if (!envId || credsByEnv[envId]) return
    try {
      const rows = await credentials.byEnvironment(authFetch, envId)
      setCredsByEnv(prev => ({ ...prev, [envId]: rows as CredentialRow[] }))
    } catch {
      setCredsByEnv(prev => ({ ...prev, [envId]: [] }))
    }
  }, [authFetch, credsByEnv])

  const catalogErrors = useMemo(() => validateTargetsAgainstAccepts({
    accepts: state.accepts,
    targets: state.targets.map(t => ({ id: t.id, ...catalogTarget(t) })),
  }), [state])

  // Client-side Save gate (self-review layer 2): server rejects a save
  // with empty ``credential_ref`` fields as a 14-error blob (three
  // discriminated-union variants × N missing fields). Catch it here so
  // Save is blocked with a readable inline hint instead. Mirrors the
  // server's field-level requirements: id, provider, model, and a full
  // vault:// reference are required per target.
  const targetIssues = useMemo(() => {
    return state.targets.map((t, i) => {
      const issues: string[] = []
      if (!t.id.trim()) issues.push("id is required")
      if (!t.provider.trim() && t.transport !== "http_passthrough") {
        issues.push("provider is required")
      }
      if (!t.model.trim()) issues.push("model is required")
      if (!t.credential_env_id) issues.push("pick a credential vault")
      if (!t.credential_handle) issues.push("pick a credential handle")
      return { index: i, targetId: t.id || `#${i + 1}`, issues }
    }).filter(x => x.issues.length > 0)
  }, [state])

  const fieldErrors = isAdmin ? validateGatewayProfileFields(state) : {}
  const profileIssue = Object.values(fieldErrors)[0]
  const canSave = isAdmin && !profileIssue && targetIssues.length === 0

  async function save() {
    if (!isAdmin) return
    if (profileIssue) {
      setErr(profileIssue)
      return
    }
    if (targetIssues.length > 0) {
      // Belt-and-braces — the button is disabled when this holds, but
      // if a keyboard-driven save slips past the disabled state, catch
      // it here and surface the same message the banner shows.
      setErr(
        `Fix ${targetIssues.length} target issue(s) before saving — ` +
        targetIssues.map(t => `${t.targetId}: ${t.issues[0]}`).join("; "),
      )
      return
    }
    setSaving(true); setErr(""); setMsg("")
    try {
      await guard.gatewayProfilesV2.updateWorkingCopy(
        authFetch, workspaceId, profile.id, stateToWorkingCopy(state),
      )
      setMsg("Working copy saved")
      onSaved()
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Save failed")
    } finally { setSaving(false) }
  }

  function patch(u: Partial<EditorState>) { setState(s => ({ ...s, ...u })); setMsg(""); setErr("") }
  function patchTarget(i: number, u: Partial<DraftTarget>) {
    setState(s => {
      const nextTargets = s.targets.map((t, j) => j === i ? { ...t, ...u } : t)
      // R2: only re-derive accepts when a change actually affects
      // the certified-capabilities calculation. Editing ``model`` or
      // ``credential_handle`` must NOT clobber imported accepts.
      const affectsAccepts =
        u.transport !== undefined || u.provider !== undefined || u.integration !== undefined ||
        (u.provider_options !== undefined && u.provider_options.protocol !== s.targets[i].provider_options?.protocol)
      const nextAccepts = affectsAccepts ? deriveAccepts(nextTargets) : s.accepts
      return { ...s, targets: nextTargets, accepts: nextAccepts }
    })
    setMsg("")
    setErr("")
  }
  function removeTarget(i: number) {
    setState(s => {
      const nextTargets = s.targets.filter((_, j) => j !== i)
      return { ...s, targets: nextTargets, accepts: deriveAccepts(nextTargets) }
    })
    setMsg("")
  }
  function addTarget() {
    setState(s => {
      const nextTargets = [...s.targets, emptyTarget(s.targets)]
      return { ...s, targets: nextTargets, accepts: deriveAccepts(nextTargets) }
    })
  }
  function move(i: number, dir: -1 | 1) {
    setState(s => {
      const next = [...s.targets]
      const j = i + dir
      if (j < 0 || j >= next.length) return s
      ;[next[i], next[j]] = [next[j], next[i]]
      return { ...s, targets: next }
    })
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <FieldLabel label="Name" hint="Display name for this profile." required
          error={fieldErrors.name} errorId={`${formId}-name-error`}>
          <input value={state.name} disabled={!isAdmin} required maxLength={128} aria-label="Name"
            aria-invalid={!!fieldErrors.name} aria-describedby={fieldErrors.name ? `${formId}-name-error` : undefined}
            placeholder="e.g. coding-prod"
            onChange={e => patch({ name: e.target.value })}
            style={{ ...inputStyle, borderColor: fieldErrors.name ? "var(--err)" : undefined }} />
        </FieldLabel>
        <FieldLabel label="Alias" hint="What clients send as `model:` in their request." required
          error={fieldErrors.model_alias} errorId={`${formId}-alias-error`}>
          <input value={state.model_alias} disabled={!isAdmin} required maxLength={128} aria-label="Alias"
            aria-invalid={!!fieldErrors.model_alias} aria-describedby={fieldErrors.model_alias ? `${formId}-alias-error` : undefined}
            onChange={e => patch({ model_alias: e.target.value })}
            placeholder="e.g. coding"
            style={{ ...inputStyle, borderColor: fieldErrors.model_alias ? "var(--err)" : undefined }} />
        </FieldLabel>
        <FieldLabel label="Timeout (s)" hint="End-to-end deadline across every fallback attempt."
          error={fieldErrors.timeout_seconds} errorId={`${formId}-timeout-error`}>
          <input type="number" min={1} max={600} step={1} value={state.timeout_seconds} disabled={!isAdmin} aria-label="Timeout (s)"
            aria-invalid={!!fieldErrors.timeout_seconds} aria-describedby={fieldErrors.timeout_seconds ? `${formId}-timeout-error` : undefined}
            onChange={e => patch({ timeout_seconds: Number(e.target.value) })}
            style={inputStyle} />
        </FieldLabel>
        <FieldLabel label="Max attempts" hint="Cap on target retries (primary + fallbacks)."
          error={fieldErrors.max_attempts} errorId={`${formId}-attempts-error`}>
          <input type="number" min={1} max={5} step={1} value={state.max_attempts} disabled={!isAdmin} aria-label="Max attempts"
            aria-invalid={!!fieldErrors.max_attempts} aria-describedby={fieldErrors.max_attempts ? `${formId}-attempts-error` : undefined}
            onChange={e => patch({ max_attempts: Number(e.target.value) })}
            style={inputStyle} />
        </FieldLabel>
      </div>

      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <span style={{ fontSize: 12, color: "var(--text-2)" }}>
            Targets ({state.targets.length}) — list order is priority
          </span>
          {isAdmin && (
            <button onClick={addTarget} className="btn btn-ghost btn-sm">+ Add target</button>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {state.targets.map((t, i) => (
            <TargetRow key={i} index={i} target={t} envs={envs} isAdmin={isAdmin}
              credentialsByEnv={credsByEnv} onLoadCredsFor={loadCreds}
              tierMap={tierMap}
              onChange={u => patchTarget(i, u)}
              onRemove={() => removeTarget(i)}
              onMoveUp={() => move(i, -1)} onMoveDown={() => move(i, 1)}
              isFirst={i === 0} isLast={i === state.targets.length - 1} />
          ))}
        </div>
      </div>

      {primitivesError && (
        <div className="sbadge err" style={{ display: "block", height: "auto", padding: "10px 12px", borderRadius: 8, whiteSpace: "normal" }}>
          <strong>LLM Model Primitives unreachable</strong>
          <div style={{ fontSize: 12, fontWeight: 400, marginTop: 4 }}>
            {primitivesError}. Provider + Model dropdowns are empty until
            this loads. Fix under Settings → LLM Model Primitives, then
            reload this page.
          </div>
        </div>
      )}

      {!primitivesLoading && !primitivesError && providerKeys.length === 0 && (
        <div className="sbadge warn" style={{ display: "block", height: "auto", padding: "10px 12px", borderRadius: 8, whiteSpace: "normal" }}>
          <strong>No providers configured</strong>
          <div style={{ fontSize: 12, fontWeight: 400, marginTop: 4 }}>
            The workspace's LLM Model Primitives has no providers. Add
            at least one under Settings → LLM Model Primitives before
            saving this profile.
          </div>
        </div>
      )}

      {catalogErrors.length > 0 && (
        <div className="sbadge warn" style={{ display: "block", height: "auto", padding: "10px 12px", borderRadius: 8, whiteSpace: "normal" }}>
          <strong>Capability catalog: {catalogErrors.length} issue(s)</strong>
          <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
            {catalogErrors.map((e, i) => (
              <li key={i} style={{ fontSize: 12, fontWeight: 400 }}>
                <span className="mono">{e.target_id}</span> ({e.where}) can't serve{" "}
                <span className="mono">{e.missing.join(", ")}</span>. {e.hint}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Client-side Save gate (self-review layer 2). Blocks Save with
          an inline banner so the admin never hits the server-side
          discriminated-union noise blob. */}
      {targetIssues.length > 0 && isAdmin && (
        <div className="sbadge warn" style={{ display: "block", height: "auto", padding: "10px 12px", borderRadius: 8, whiteSpace: "normal" }}>
          <strong>{targetIssues.length} target(s) need attention before Save</strong>
          <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
            {targetIssues.map(t => (
              <li key={t.index} style={{ fontSize: 12, fontWeight: 400 }}>
                <span className="mono">#{t.index + 1} {t.targetId}</span>:{" "}
                {t.issues.join(", ")}
              </li>
            ))}
          </ul>
        </div>
      )}

      {fieldErrors.targets && <p role="alert" style={{ margin: 0, color: "var(--err)", fontSize: 12 }}>{fieldErrors.targets}</p>}
      {err && <p role="alert" style={{ margin: 0, color: "var(--err)", fontSize: 12, overflowWrap: "anywhere" }}>{err}</p>}
      {msg && <p style={{ margin: 0, color: "var(--ok)", fontSize: 12 }}>{msg}</p>}

      {isAdmin && (
        <div>
          <button
            onClick={save}
            disabled={saving || !canSave}
            className="btn btn-primary btn-sm"
            title={
              profileIssue ?? (!canSave && targetIssues.length > 0
                ? `Fix ${targetIssues.length} target issue(s) before saving`
                : undefined)
            }
          >
            {saving ? "Saving…" : "Save working copy"}
          </button>
        </div>
      )}
    </div>
  )
}
