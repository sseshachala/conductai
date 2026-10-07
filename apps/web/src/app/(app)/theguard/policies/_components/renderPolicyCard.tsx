"use client"

import type { RuleFire } from "@/lib/api/guard"
import { ActionBadge, GateChips, LockIcon, RuleFiresPanel, SurfaceBadges, Toggle, fieldStyle, formatExceptionExpiry, formatLastTriggered } from "./shared"
import type { Policy, PolicyAction } from "./shared"

export interface PolicyCardContext {
  expandedIds: Set<string>
  toggleExpand: (id: string) => void
  canWrite: boolean
  editId: string | null
  setEditId: (id: string | null) => void
  editAction: PolicyAction
  setEditAction: (a: PolicyAction) => void
  editInjectGuidance: boolean
  setEditInjectGuidance: (v: boolean) => void
  editGuidanceReviewed: boolean
  setEditGuidanceReviewed: (v: boolean) => void
  editGuidance: string
  setEditGuidance: (v: string) => void
  editMessage: string
  setEditMessage: (v: string) => void
  editSaving: boolean
  handleEditSave: (id: string) => void
  confirmDeleteId: string | null
  setConfirmDeleteId: (id: string | null) => void
  setConfirmDeleteValue: (v: string) => void
  handleToggle: (id: string) => void
  ruleFires: Record<string, { loading: boolean; fires: RuleFire[]; error?: string }>
}

// Extracted verbatim from the policies page; called as renderCard(p) there.
export function renderPolicyCard(p: Policy, ctx: PolicyCardContext) {
  const { expandedIds, toggleExpand, canWrite, editId, setEditId, editAction, setEditAction, editInjectGuidance, setEditInjectGuidance, editGuidanceReviewed, setEditGuidanceReviewed, editGuidance, setEditGuidance, editMessage, setEditMessage, editSaving, handleEditSave, confirmDeleteId, setConfirmDeleteId, setConfirmDeleteValue, handleToggle, ruleFires } = ctx
  const expanded = expandedIds.has(p.id)
  const hasException = p.exception_active || p.exception_expired
  const hasProse = !!(p.guarantee || (p.known_limitations && p.known_limitations.length > 0))
  // #1755 Slice 2 — surface badges are always relevant to compliance
  // officers, so every rule is expandable now.
  const hasDetails = true || !!(p.match_pattern || p.match_path_pattern || p.message || hasException || hasProse)
  const locked = !!p.non_overridable
  return (
    <div key={p.id} style={{ opacity: p.enabled ? 1 : 0.55 }}>
      {/* Main row */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 12px", borderRadius: 8, background: "var(--surface)", border: "1px solid var(--border)" }}>
        <ActionBadge action={p.action} />
        <GateChips gates={p.gates} />
        <span className="mono" style={{ fontWeight: 650, fontSize: 12, color: "var(--text-1)", whiteSpace: "nowrap" }}>{p.rule_id}</span>
        {p.exception_active && (
          <span className="sbadge warn" style={{ textTransform: "uppercase", fontSize: 9.5, letterSpacing: ".06em" }}>
            Exception active
          </span>
        )}
        {p.exception_expired && (
          <span className="sbadge err" style={{ textTransform: "uppercase", fontSize: 9.5, letterSpacing: ".06em" }}>
            Exception expired
          </span>
        )}
        {p.tag === "security_policy" && (
          <span className="sbadge err" style={{ textTransform: "uppercase", fontSize: 9.5, letterSpacing: ".06em" }} title="Security policy — code-security enforcement">SEC</span>
        )}
        {locked && <LockIcon />}
        <span style={{ flex: 1, fontSize: 12, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.description || p.message || "—"}</span>
        <span style={{ fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap", flexShrink: 0 }}>
          Last hit: <strong style={{ color: p.last_triggered ? "var(--text-2)" : "var(--text-muted)" }}>{formatLastTriggered(p.last_triggered)}</strong>
        </span>
        {hasDetails && (
          <button onClick={() => toggleExpand(p.id)} style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 5, cursor: "pointer", color: "var(--text-muted)", padding: "2px 6px", flexShrink: 0, display: "flex", alignItems: "center", gap: 3, fontSize: 11 }} title="Show pattern & message">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform .15s" }}><polyline points="6 9 12 15 18 9" /></svg>
          </button>
        )}
        {!locked && canWrite && p.builtin && (
          <button type="button" onClick={() => { setEditId(editId === p.id ? null : p.id); setEditAction(p.action); setEditInjectGuidance(p.inject_guidance ?? false); setEditGuidanceReviewed(true); setEditGuidance(p.guidance ?? ""); setEditMessage(p.message ?? "") }} style={{ background: "none", border: "none", cursor: "pointer", color: editId === p.id ? "var(--accent)" : "var(--text-muted)", padding: 2, flexShrink: 0 }} title="Override">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          </button>
        )}
        {!p.builtin && !locked && canWrite && (
          <button type="button" onClick={() => { if (confirmDeleteId === p.id) { setConfirmDeleteId(null); setConfirmDeleteValue("") } else { setConfirmDeleteId(p.id); setConfirmDeleteValue("") } }} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 2, flexShrink: 0 }} title="Delete">
            <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path fillRule="evenodd" d="M5 3.25V4H2.75a.75.75 0 0 0 0 1.5h.3l.815 8.15A1.5 1.5 0 0 0 5.357 15h5.285a1.5 1.5 0 0 0 1.493-1.35L12.95 5.5h.3a.75.75 0 0 0 0-1.5H11v-.75A2.25 2.25 0 0 0 8.75 1h-1.5A2.25 2.25 0 0 0 5 3.25Zm2.25-.75a.75.75 0 0 0-.75.75V4h3v-.75a.75.75 0 0 0-.75-.75h-1.5ZM6.05 6a.75.75 0 0 1 .787.713l.275 5.5a.75.75 0 0 1-1.498.075l-.275-5.5A.75.75 0 0 1 6.05 6Zm3.9 0a.75.75 0 0 1 .712.787l-.275 5.5a.75.75 0 0 1-1.498-.075l.275-5.5A.75.75 0 0 1 9.95 6Z" clipRule="evenodd" /></svg>
          </button>
        )}
        {locked
          ? <span style={{ fontSize: 10, color: "var(--text-muted)", flexShrink: 0 }}>Required</span>
          : canWrite
            ? <Toggle enabled={p.enabled} onChange={() => handleToggle(p.id)} />
            : <span style={{ width: 32, height: 18, borderRadius: 20, background: p.enabled ? "var(--accent)" : "var(--border-2)", display: "inline-block", opacity: 0.5, flexShrink: 0 }} />
        }
      </div>

      {/* Edit override panel */}
      {editId === p.id && (
        <div style={{ margin: "4px 0 4px 12px", padding: "10px 12px", background: "var(--surface-2)", borderRadius: 8, display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <label style={{ fontSize: 11.5, color: "var(--text-2)", fontWeight: 500, whiteSpace: "nowrap" }}>Action</label>
            <select value={editAction} onChange={e => setEditAction(e.target.value as PolicyAction)} style={{ ...fieldStyle, width: "auto", fontSize: 12 }}>
              <option value="block">Block</option>
              <option value="approval">Require approval</option>
              <option value="warn">Warn</option>
              <option value="audit">Audit</option>
            </select>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11.5, color: "var(--text-2)", cursor: "pointer" }}>
            <input type="checkbox" checked={editInjectGuidance} onChange={e => { setEditInjectGuidance(e.target.checked); if (e.target.checked && !(p.inject_guidance ?? false)) setEditGuidanceReviewed(false) }} style={{ margin: 0 }} />
            Also inject guidance to model
          </label>
          {editInjectGuidance && !editGuidanceReviewed && (
            <div style={{ padding: "8px 10px", background: "var(--surface)", borderRadius: 6, borderLeft: "3px solid var(--warn)", fontSize: 11.5, color: "var(--text-2)" }}>
              <div style={{ fontWeight: 500, marginBottom: 3 }}>Guidance to model</div>
              <div style={{ color: "var(--text-muted)", marginBottom: 6 }}>
                Prepended to the model&apos;s system prompt. Model-directed text (imperative).
              </div>
              <textarea
                value={editGuidance || editMessage}
                onChange={e => setEditGuidance(e.target.value)}
                rows={3}
                placeholder="e.g. Do not reveal API keys. Redact before retry."
                style={{ ...fieldStyle, fontFamily: "var(--font-mono, monospace)", fontSize: 11.5, marginBottom: 6 }}
              />
              <div style={{ display: "flex", gap: 6 }}>
                <button type="button" onClick={() => { if (!editGuidance) setEditGuidance(editMessage); setEditGuidanceReviewed(true) }} className="btn btn-primary btn-sm">Confirm</button>
                <button type="button" onClick={() => { setEditInjectGuidance(false); setEditGuidance(""); setEditGuidanceReviewed(true) }} className="btn btn-ghost btn-sm">Cancel</button>
              </div>
            </div>
          )}
          {editInjectGuidance && editGuidanceReviewed && (
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--ok)" }}>
              <span>✓ Guidance reviewed</span>
              <button type="button" onClick={() => setEditGuidanceReviewed(false)} className="btn btn-ghost btn-sm" style={{ padding: "0 6px", fontSize: 10.5 }}>Edit</button>
            </div>
          )}
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <label style={{ fontSize: 11.5, color: "var(--text-2)", fontWeight: 500, whiteSpace: "nowrap" }}>Message</label>
            <input value={editMessage} onChange={e => setEditMessage(e.target.value)} placeholder={p.message ?? "Override message (optional)"} style={{ ...fieldStyle, fontSize: 12 }} />
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button onClick={() => handleEditSave(p.id)} disabled={editSaving || (editInjectGuidance && !editGuidanceReviewed)} className="btn btn-primary btn-sm" title={editInjectGuidance && !editGuidanceReviewed ? "Confirm the guidance to save." : undefined}>{editSaving ? "Saving…" : "Save override"}</button>
            <button onClick={() => setEditId(null)} className="btn btn-ghost btn-sm">Cancel</button>
          </div>
        </div>
      )}

      {/* Expanded details */}
      {expanded && hasDetails && (
        <div style={{ margin: "4px 0 4px 12px", padding: "8px 12px", background: "var(--surface-2)", borderRadius: 8, display: "flex", flexWrap: "wrap", gap: 12 }}>
          {/* #1755 Slice 2 — PEP verified badges */}
          <div style={{ flexBasis: "100%", display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Enforced by</span>
            <SurfaceBadges policy={p} />
          </div>
          {p.match_tool && <div><span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Tool </span><span className="mono" style={{ fontSize: 11.5, color: "var(--text-2)" }}>{p.match_tool}</span></div>}
          {p.match_pattern && <div><span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Pattern </span><span className="mono" style={{ fontSize: 11, color: "var(--err)", background: "var(--err-bg)", borderRadius: 4, padding: "1px 6px" }}>{p.match_pattern}</span></div>}
          {p.match_path_pattern && <div><span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Path </span><span className="mono" style={{ fontSize: 11, color: "var(--warn)", background: "var(--warn-bg)", borderRadius: 4, padding: "1px 6px" }}>{p.match_path_pattern}</span></div>}
          {p.message && <div><span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Message </span><span style={{ fontSize: 11.5, color: "var(--text-2)", fontStyle: "italic" }}>&ldquo;{p.message}&rdquo;</span></div>}
          {/* #1750 Phase B — retained hand-authored trust prose */}
          {p.guarantee && (
            <div style={{ flexBasis: "100%" }}>
              <span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Guarantee </span>
              <span style={{ fontSize: 11.5, color: "var(--text-2)" }}>{p.guarantee}</span>
            </div>
          )}
          {p.known_limitations && p.known_limitations.length > 0 && (
            <div style={{ flexBasis: "100%" }}>
              <span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Known limitations </span>
              <ul style={{ margin: "3px 0 0 16px", padding: 0, fontSize: 11.5, color: "var(--text-2)" }}>
                {p.known_limitations.map((lim, i) => (
                  <li key={i} style={{ marginBottom: 2 }}>{lim}</li>
                ))}
              </ul>
            </div>
          )}
          {/* #1755 Slice 2 — Recent firings panel (redacted preview). */}
          <div style={{ flexBasis: "100%", paddingTop: 4, borderTop: "1px solid var(--border)" }}>
            <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)", marginBottom: 4 }}>
              Recent firings
            </div>
            <RuleFiresPanel state={ruleFires[p.id]} />
          </div>
          {hasException && (
            <div style={{ flexBasis: "100%", display: "flex", flexWrap: "wrap", gap: 12, paddingTop: 4, borderTop: "1px solid var(--border)" }}>
              <div>
                <span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Exception </span>
                <span style={{ fontSize: 11.5, color: p.exception_active ? "var(--warn)" : "var(--err)", fontWeight: 600 }}>
                  {p.exception_active ? "Active" : "Expired"}
                </span>
              </div>
              {p.exception_reason && (
                <div>
                  <span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Reason </span>
                  <span style={{ fontSize: 11.5, color: "var(--text-2)" }}>{p.exception_reason}</span>
                </div>
              )}
              <div>
                <span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em", color: "var(--text-muted)" }}>Expiry </span>
                <span style={{ fontSize: 11.5, color: "var(--text-2)" }}>{formatExceptionExpiry(p.exception_expires_at)}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
