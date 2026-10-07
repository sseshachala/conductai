"use client"

import { useState, useEffect } from "react"
import { useSearchParams } from "next/navigation"
import { useGuardTeam } from "@/hooks/useGuardTeam"
import { useAuthFetch } from "@/hooks/useAuthFetch"
import { guard } from "@/lib/api"
import type { GuardPolicyPatch, RuleFire } from "@/lib/api/guard"
import { useGuardRole } from "@/hooks/useGuardRole"
import { useWorkspace } from "@/lib/WorkspaceContext"
import AppShell from "@/components/AppShell"
import { GuardShell } from "@/components/guard/GuardShell"
import { EnforcementCoverageMatrix } from "@/components/guard/EnforcementCoverageMatrix"
import EnforcementPanel from "@/features/guard/policies/enforcement/Panel"
import { ACTION_RESTRICTIVENESS, PACK_LABELS, PolicyExceptionModal, formatUpdatedAt, normalizePolicy } from "./_components/shared"
import type { Gate, Policy, PolicyAction, PolicyExceptionRequest } from "./_components/shared"
import { AddRuleModal } from "./_components/AddRuleModal"
import type { AddRuleFormData } from "./_components/AddRuleModal"
import { renderPolicyCard } from "./_components/renderPolicyCard"

// ─── Main page ────────────────────────────────────────────────────────────────

export default function PoliciesPage() {
  return <AppShell><PoliciesContent /></AppShell>
}

function PoliciesContent() {
  const { authFetch } = useAuthFetch()
  const searchParams = useSearchParams()
  useEffect(() => {
    const p = searchParams.get("persona")
    if (p) setTimeout(() => document.getElementById(`section-${p}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 300)
    // Land on the Enforcement coverage tab when redirected from the old
    // /theguard/policies/enforcement URL (or any ?view=coverage deep link).
    const v = searchParams.get("view")
    if (v === "policies" || v === "coverage") setPageView(v)
  }, [searchParams])
  const { teamId, loading: teamLoading, error: teamError } = useGuardTeam()
  const { activeWorkspace } = useWorkspace()
  const { permissions, loading: permissionsLoading } = useGuardRole(teamId, activeWorkspace?.id ?? null)
  const [policies, setPolicies] = useState<Policy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pageView, setPageView] = useState<"policies" | "coverage">("policies")
  const [policyTab, setPolicyTab] = useState<string>("agent")
  const [showModal, setShowModal] = useState(false)
  const [modalPersona, setModalPersona] = useState<"agent" | "proxy">("agent")
  const [submitting, setSubmitting] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [confirmDeleteValue, setConfirmDeleteValue] = useState("")
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const [editId, setEditId] = useState<string | null>(null)
  const [editAction, setEditAction] = useState<PolicyAction>("block")
  const [editInjectGuidance, setEditInjectGuidance] = useState(false)
  const [editGuidanceReviewed, setEditGuidanceReviewed] = useState(true)
  const [editGuidance, setEditGuidance] = useState("")
  const [editMessage, setEditMessage] = useState("")
  const [editSaving, setEditSaving] = useState(false)
  const [exceptionRequest, setExceptionRequest] = useState<PolicyExceptionRequest | null>(null)
  const [exceptionSaving, setExceptionSaving] = useState(false)
  const [successBanner, setSuccessBanner] = useState<string | null>(null)
  const [gateFilter, setGateFilter] = useState<"all" | Gate>("all")  // #1733/#1750 Phase B
  // #1755 Slice 2 — per-rule firings cache. Map ruleId → { loading, fires }.
  // Populated lazily on expand (see toggleExpand below).
  const [ruleFires, setRuleFires] = useState<Record<string, { loading: boolean; fires: RuleFire[]; error?: string }>>({})

  const canWrite = !permissionsLoading && permissions.canEditPolicies

  useEffect(() => {
    if (!teamLoading && !teamId) setLoading(false)
  }, [teamLoading, teamId])

  useEffect(() => {
    async function load() {
      if (!teamId) return
      setLoading(true)
      setError(null)
      try {
        const data = await guard.policies.list(authFetch, teamId)
        setPolicies(data.map(normalizePolicy))
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load policies.")
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [authFetch, teamId])

  useEffect(() => {
    const msg = sessionStorage.getItem("guard.policies.saved")
    if (msg) {
      sessionStorage.removeItem("guard.policies.saved")
      setSuccessBanner(msg)
      const t = setTimeout(() => setSuccessBanner(null), 5000)
      return () => clearTimeout(t)
    }
  }, [])

  async function handleRefreshBuiltins() {
    if (!teamId) return
    setRefreshing(true)
    try {
      await guard.policies.reinstallBase(authFetch, teamId)
      const data = await guard.policies.list(authFetch, teamId)
      setPolicies(data.map(normalizePolicy))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Refresh failed.")
    } finally {
      setRefreshing(false)
    }
  }

  async function handleToggle(id: string) {
    const prev = policies.find(p => p.id === id)
    if (!prev || !teamId) return

    if (prev.builtin && prev.enabled) {
      setExceptionRequest({
        policyId: id,
        patch: { enabled: false },
        title: `Disable ${prev.rule_id}?`,
        description: "Built-in and pack rules can only be disabled temporarily. Add a reason and expiry for this policy exception.",
      })
      return
    }

    const nextEnabled = !prev.enabled
    setPolicies(ps => ps.map(p => p.id === id ? { ...p, enabled: nextEnabled } : p))
    try {
      const updated = await guard.policies.patch(authFetch, id, teamId, { enabled: nextEnabled })
      setPolicies(ps => ps.map(p => p.id === id ? updated : p))
    } catch (e) {
      setPolicies(ps => ps.map(p => p.id === id ? { ...p, enabled: prev.enabled } : p))
      setError(e instanceof Error ? e.message : "Failed to update rule. Please try again.")
    }
  }

  async function handleEditSave(id: string) {
    if (!teamId) return
    const policy = policies.find(p => p.id === id)
    if (!policy) return

    const patch: GuardPolicyPatch = {}
    if (editAction !== policy.action) patch.action = editAction
    if (editInjectGuidance !== (policy.inject_guidance ?? false)) patch.inject_guidance = editInjectGuidance
    if (editGuidance !== (policy.guidance ?? "")) patch.guidance = editGuidance
    if (editMessage !== (policy.message ?? "")) patch.message = editMessage
    if (Object.keys(patch).length === 0) {
      setEditId(null)
      return
    }

    if (
      policy.builtin
      && patch.action
      && ACTION_RESTRICTIVENESS[patch.action] < ACTION_RESTRICTIVENESS[policy.action]
    ) {
      setExceptionRequest({
        policyId: id,
        patch,
        title: `Weaken ${policy.rule_id}?`,
        description: `Changing this rule from ${policy.action} to ${patch.action} requires a temporary policy exception.`,
        closeEditor: true,
      })
      return
    }

    setEditSaving(true)
    try {
      const updated = await guard.policies.patch(authFetch, id, teamId, patch)
      setPolicies(ps => ps.map(p => p.id === id ? updated : p))
      setEditId(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save")
    } finally {
      setEditSaving(false)
    }
  }

  async function handleExceptionSubmit(reason: string, expiresAt: string) {
    if (!teamId || !exceptionRequest) return
    setExceptionSaving(true)
    try {
      const updated = await guard.policies.patch(
        authFetch,
        exceptionRequest.policyId,
        teamId,
        { ...exceptionRequest.patch, reason, expires_at: expiresAt },
      )
      setPolicies(ps => ps.map(p => p.id === updated.id ? updated : p))
      if (exceptionRequest.closeEditor) setEditId(null)
      setExceptionRequest(null)
    } finally {
      setExceptionSaving(false)
    }
  }

  async function handleDelete(id: string) {
    const prev = policies.find(p => p.id === id)
    if (!prev || prev.builtin || !teamId) return
    if (confirmDeleteValue !== prev.rule_id) return
    setConfirmDeleteId(null)
    setConfirmDeleteValue("")
    setPolicies(ps => ps.filter(p => p.id !== id))
    try {
      const res = await guard.policies.delete(authFetch, id, teamId)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
    } catch (e) {
      setPolicies(ps => [...ps, prev].sort((a, b) => a.rule_id.localeCompare(b.rule_id)))
      setError(e instanceof Error ? e.message : "Failed to delete rule. Please try again.")
    }
  }

  async function handleAddRule(formData: AddRuleFormData) {
    setSubmitting(true)
    try {
      const rule: Record<string, unknown> = {
        rule_id: formData.rule_id.trim(),
        description: formData.description.trim(),
        match_tool: formData.match_tool,
        match_pattern: formData.match_pattern.trim(),
        action: formData.action,
        inject_guidance: formData.inject_guidance,
        guidance: formData.guidance.trim() || undefined,
        message: formData.message.trim(),
        enabled: true,
        builtin: false,
        persona: formData.persona,
      }
      if (formData.match_ai_tool.trim()) rule.match_ai_tool = formData.match_ai_tool.trim()
      if (formData.match_path_pattern.trim()) rule.match_path_pattern = formData.match_path_pattern.trim()

      // Lint before saving
      if (teamId) {
        try {
          const lintRes = await guard.policies.lint(authFetch, teamId, { rules: [rule] })
          const lintData = await lintRes.json() as { errors: { field: string; message: string }[] }
          if (lintData.errors?.length > 0) {
            throw new Error(lintData.errors.map((e: { field: string; message: string }) => `${e.field}: ${e.message}`).join(" · "))
          }
        } catch (lintErr) {
          if (lintErr instanceof Error && lintErr.message.includes(":")) throw lintErr
          // non-fatal if lint endpoint is down
        }
      }

      const body = { ...rule, ...(teamId ? { workspace_id: teamId } : {}) }
      const createRes = await guard.policies.create(authFetch, body)
      const created: Policy = await createRes.json() as Policy
      setPolicies(ps => [...ps, created])
      setShowModal(false)
      setPolicyTab("custom")
    } catch (e) {
      throw e
    } finally {
      setSubmitting(false)
    }
  }

  // Build tabs: Agent + Proxy + Custom (user-created) + one per installed pack
  const installedPackIds = [...new Set(policies.filter(p => p.pack_id).map(p => p.pack_id!))]
  const customRules = policies.filter(p => !p.builtin)
  const securityRules = policies.filter(p => p.tag === "security_policy")
  const policyTabs = [
    { id: "security", label: "Security", count: securityRules.length },
    { id: "agent",   label: "Agent",   count: policies.filter(p => p.builtin && (!p.persona || p.persona === "agent")).length },
    // Legacy ``proxy`` persona counted here — same rules, new label.
    { id: "gateway", label: "Gateway", count: policies.filter(p => p.builtin && (p.persona === "gateway" || p.persona === "proxy")).length },
    { id: "custom", label: "Custom", count: customRules.length },
    ...installedPackIds.map(id => ({
      id,
      label: PACK_LABELS.find(l => l.id === id)?.name ?? id,
      count: policies.filter(p => p.pack_id === id).length,
    })),
  ].filter(t => t.count > 0 || t.id === "agent" || t.id === "custom" || t.id === "security")
  const _tabScope = policyTab === "security"
    ? securityRules
    : policyTab === "agent"
    ? policies.filter(p => p.builtin && (!p.persona || p.persona === "agent"))
    : policyTab === "gateway"
    ? policies.filter(p => p.builtin && (p.persona === "gateway" || p.persona === "proxy"))
    : policyTab === "custom"
    ? customRules
    : policies.filter(p => p.pack_id === policyTab)
  // #1733/#1750 Phase B — filter by gate. `all` bypasses; otherwise keep rules
  // whose gates list includes the selected gate (falls back to ['action'] if
  // the backend hasn't stamped gates yet — matches derive_gates default).
  const visiblePolicies = gateFilter === "all"
    ? _tabScope
    : _tabScope.filter(p => (p.gates && p.gates.length ? p.gates : ["action"]).includes(gateFilter))

  const latestUpdated = policies
    .map(p => p.updated_at)
    .filter(Boolean)
    .sort()
    .at(-1)

  function toggleExpand(id: string) {
    setExpandedIds(prev => {
      const next = new Set(prev)
      const isOpening = !next.has(id)
      isOpening ? next.add(id) : next.delete(id)
      // #1755 Slice 2 — lazy-fetch firings on first expand.
      if (isOpening && !ruleFires[id]) {
        setRuleFires(s => ({ ...s, [id]: { loading: true, fires: [] } }))
        guard.events.ruleFires(authFetch, id, teamId ?? undefined)
          .then(fires => setRuleFires(s => ({ ...s, [id]: { loading: false, fires } })))
          .catch(err => setRuleFires(s => ({
            ...s, [id]: { loading: false, fires: [], error: String(err?.message ?? err) },
          })))
      }
      return next
    })
  }

  return (
    <>
      <GuardShell>
        <div
          role="tablist"
          aria-label="Policy views"
          style={{ display: "flex", gap: 4, marginBottom: 18, borderBottom: "1px solid var(--border)" }}
        >
          {([
            { id: "policies", label: "Policies" },
            { id: "coverage", label: "Enforcement coverage" },
          ] as const).map(view => (
            <button
              key={view.id}
              type="button"
              role="tab"
              aria-selected={pageView === view.id}
              onClick={() => setPageView(view.id)}
              style={{
                marginBottom: -1,
                padding: "8px 12px",
                border: 0,
                borderBottom: pageView === view.id ? "2px solid var(--accent)" : "2px solid transparent",
                background: "transparent",
                color: pageView === view.id ? "var(--text)" : "var(--text-muted)",
                fontSize: 12.5,
                fontWeight: pageView === view.id ? 650 : 500,
                cursor: "pointer",
              }}
            >
              {view.label}
            </button>
          ))}
        </div>

        {pageView === "coverage" ? (
          <>
            {/* Enforcement settings — merged here from the standalone
                /theguard/policies/enforcement page. One home for
                everything enforcement: settings on top, coverage matrix
                below. Old URL now redirects to ?view=coverage. */}
            <div style={{ marginBottom: 20 }}>
              <EnforcementPanel
                workspaceId={activeWorkspace?.id ?? null}
                isAdmin={permissions.canEditSettings}
              />
            </div>
            <EnforcementCoverageMatrix workspaceId={teamId} />
          </>
        ) : (
          <>
        {/* Sub-header row */}
        <div style={{ display: "flex", alignItems: "center", marginBottom: 16 }}>
          <span style={{ fontSize: 13.5, color: "var(--text-3)" }}>
            Rules sync to every developer&apos;s machine within <strong style={{ color: "var(--text)" }}>60 seconds</strong>.
            {" "}{policies.filter(p => p.enabled).length} active.
          </span>
          {canWrite && (
            <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
              <button
                onClick={handleRefreshBuiltins}
                disabled={refreshing}
                className="btn btn-sm"
                style={{ opacity: refreshing ? 0.6 : 1 }}
                title="Re-sync built-in policies from latest YAML definitions"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="23 4 23 10 17 10" />
                  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
                </svg>
                {refreshing ? "Refreshing…" : "Refresh built-ins"}
              </button>
            </div>
          )}
        </div>

        {/* Success */}
        {successBanner && (
          <div style={{ borderRadius: 10, border: "1px solid var(--success-bd, #bbf7d0)", background: "var(--success-bg, #f0fdf4)", padding: "10px 16px", fontSize: 13, color: "var(--success, #15803d)", marginBottom: 16 }}>
            {successBanner}
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{ borderRadius: 10, border: "1px solid var(--err-bd)", background: "var(--err-bg)", padding: "10px 16px", fontSize: 13, color: "var(--err)", marginBottom: 16 }}>
            {error}
          </div>
        )}

        {/* Guard not installed */}
        {!loading && teamError && (
          <div className="card" style={{ padding: "48px 24px", textAlign: "center" }}>
            <p style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", marginBottom: 8 }}>ConductGuard not set up</p>
            <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 0 }}>
              Run <code style={{ fontFamily: "ui-monospace,monospace", background: "var(--surface-2)", padding: "1px 6px", borderRadius: 4 }}>conduct guard install</code> in your terminal to get started.
            </p>
          </div>
        )}

        {/* Empty */}
        {!loading && !teamError && !error && policies.length === 0 && (
          <div className="card" style={{ padding: "48px 24px", textAlign: "center" }}>
            <p style={{ fontSize: 13, color: "var(--text-muted)" }}>No policies yet. Install a skill pack to get started.</p>
          </div>
        )}

        {!loading && !error && policies.length > 0 && (
          <>
            {/* Main content — two sections */}
            <div style={{ flex: 1, minWidth: 0 }}>
            {(() => {
              function renderCard(p: Policy) {
                return renderPolicyCard(p, { expandedIds, toggleExpand, canWrite, editId, setEditId, editAction, setEditAction, editInjectGuidance, setEditInjectGuidance, editGuidanceReviewed, setEditGuidanceReviewed, editGuidance, setEditGuidance, editMessage, setEditMessage, editSaving, handleEditSave, confirmDeleteId, setConfirmDeleteId, setConfirmDeleteValue, handleToggle, ruleFires })
              }

              function SectionHeader({ title, description, onAdd }: { title: string; description: string; onAdd: () => void }) {
                return (
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                    <div>
                      <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".07em", color: "var(--text-muted)" }}>{title}</span>
                      <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 8 }}>{description}</span>
                    </div>
                    <span style={{ height: 1, flex: 1, background: "var(--border)" }} />
                    {canWrite && (
                      <button type="button" onClick={onAdd} className="btn btn-ghost btn-sm" style={{ fontSize: 11.5, padding: "3px 10px" }}>
                        + Add rule
                      </button>
                    )}
                  </div>
                )
              }

              return (
                <>
                  {/* Tab pills */}
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 14, flexWrap: "wrap" }}>
                    {policyTabs.map(tab => (
                      <button
                        key={tab.id}
                        onClick={() => setPolicyTab(tab.id)}
                        style={{
                          padding: "4px 12px", borderRadius: 20, fontSize: 12, fontWeight: 600, cursor: "pointer",
                          border: policyTab === tab.id ? "1.5px solid var(--accent)" : "1.5px solid var(--border)",
                          background: policyTab === tab.id ? "var(--accent-bg, #eff6ff)" : "var(--surface)",
                          color: policyTab === tab.id ? "var(--accent)" : "var(--text-3)",
                          transition: "all .12s",
                        }}
                      >
                        {tab.label}
                        <span style={{ marginLeft: 5, fontSize: 11, opacity: 0.7 }}>{tab.count}</span>
                      </button>
                    ))}
                    <span style={{ flex: 1 }} />
                    {/* #1733/#1750 Phase B — filter by gate */}
                    <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11.5, color: "var(--text-muted)" }}>
                      Gate
                      <select
                        value={gateFilter}
                        onChange={(e) => setGateFilter(e.target.value as "all" | Gate)}
                        style={{
                          padding: "3px 8px", borderRadius: 6, fontSize: 12,
                          border: "1px solid var(--border)", background: "var(--surface)",
                          color: "var(--text-2)", cursor: "pointer",
                        }}
                        title="Show only rules that fire at this enforcement gate (action, prompt, or response)"
                      >
                        <option value="all">All</option>
                        <option value="action">Action</option>
                        <option value="prompt">Prompt</option>
                        <option value="response">Response</option>
                      </select>
                    </label>
                    {canWrite && (policyTab === "agent" || policyTab === "proxy" || policyTab === "custom") && (
                      <button
                        type="button"
                        onClick={() => {
                          setModalPersona(policyTab === "custom" ? "agent" : policyTab as "agent" | "proxy")
                          setShowModal(true)
                        }}
                        className="btn btn-ghost btn-sm"
                        style={{ fontSize: 11.5, padding: "3px 10px" }}
                      >
                        + Add rule
                      </button>
                    )}
                  </div>

                  {/* Rule list */}
                  {visiblePolicies.length === 0
                    ? <div className="card" style={{ padding: "24px", textAlign: "center" }}>
                        <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
                          {policyTab === "proxy" ? "No gateway rules." : policyTab === "agent" ? "No agent rules." : "No rules in this pack."}
                        </p>
                      </div>
                    : <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>{visiblePolicies.map(p => renderCard(p))}</div>
                  }
                </>
              )
            })()}

            {/* Footer */}
            {policies.length > 0 && (
              <p style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "center", paddingTop: 16, paddingBottom: 8 }}>
                Policy last updated: {formatUpdatedAt(latestUpdated)} · Synced to developers
              </p>
            )}
            </div>{/* end main col */}
          </>
        )}
          </>
        )}
      </GuardShell>

      {showModal && (
        <AddRuleModal
          onClose={() => setShowModal(false)}
          onSubmit={handleAddRule}
          submitting={submitting}
          initialPersona={modalPersona}
        />
      )}

      {exceptionRequest && (
        <PolicyExceptionModal
          key={`${exceptionRequest.policyId}-${JSON.stringify(exceptionRequest.patch)}`}
          request={exceptionRequest}
          submitting={exceptionSaving}
          onClose={() => {
            if (!exceptionSaving) setExceptionRequest(null)
          }}
          onSubmit={handleExceptionSubmit}
        />
      )}

      {/* Delete confirm modal */}
      {confirmDeleteId && (() => {
        const target = policies.find(p => p.id === confirmDeleteId)
        if (!target) return null
        return (
          <div
            style={{
              position: "fixed", inset: 0, zIndex: 200,
              background: "rgba(0,0,0,0.45)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
            onClick={() => { setConfirmDeleteId(null); setConfirmDeleteValue("") }}
          >
            <div
              className="card"
              style={{ width: 400, padding: "24px", display: "flex", flexDirection: "column", gap: 14 }}
              onClick={e => e.stopPropagation()}
            >
              <div>
                <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text)", margin: 0 }}>Delete policy</h2>
                <p style={{ fontSize: 13, color: "var(--text-3)", marginTop: 6 }}>
                  This cannot be undone. Type <strong style={{ color: "var(--err)" }}>{target.rule_id}</strong> to confirm.
                </p>
              </div>
              <input
                autoFocus
                value={confirmDeleteValue}
                onChange={e => setConfirmDeleteValue(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Enter") handleDelete(target.id)
                  if (e.key === "Escape") { setConfirmDeleteId(null); setConfirmDeleteValue("") }
                }}
                placeholder={target.rule_id}
                style={{ fontSize: 13, border: "1px solid var(--err-bd, #fecaca)", borderRadius: 8, padding: "8px 12px", outline: "none", background: "var(--surface)", color: "var(--text)" }}
              />
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                <button onClick={() => { setConfirmDeleteId(null); setConfirmDeleteValue("") }} className="btn btn-ghost btn-sm">Cancel</button>
                <button
                  onClick={() => handleDelete(target.id)}
                  disabled={confirmDeleteValue !== target.rule_id}
                  className="btn btn-sm"
                  style={{ background: "var(--err)", color: "#fff", border: "none", opacity: confirmDeleteValue !== target.rule_id ? 0.4 : 1 }}
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        )
      })()}
    </>
  )
}
