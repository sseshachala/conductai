"use client"

import { useState, type MouseEvent as ReactMouseEvent } from "react"
import { timeAgo } from "@/lib/runUtils"
import { DecisionBadge } from "./DecisionBadge"
import { LifecyclePill } from "./LifecyclePill"
import { ALL_COLUMNS, type ColumnKey } from "./common/GuardToolbar"
import { formatTokensUsed } from "./common/formatTokens"
import { AskLensLink } from "@/components/glens/AskLensLink"
import { AttributionDetails } from "@/components/federation/AttributionDetails"
import { SessionUsageDetails } from "./SessionUsageDetails"
import { SessionSpend } from "./SessionSpend"
import { buildGridTemplate, resolveVisible } from "./activity-row/layout"
import type { AuditEvent } from "./activity-row/types"
import {
  BlastRadiusBadge,
  LocalRiskPill,
  ProxyPill,
  ToolBadge,
  formatToolCall,
  formatTs,
  isProxyEvent,
} from "./activity-row/badges"
import { SignatureTamperRow } from "./activity-row/SignatureTamperRow"

import { AgentAvatar } from "./AgentAvatar"

/**
 * Shared event row used by /guard/activity (full feed) and /governance
 * (Recent activity preview). Same shape, same badges, same column widths —
 * so a user moving between pages sees one consistent representation of a
 * guard event.
 *
 * If a caller wants a slimmer layout (e.g. dashboard preview), pass
 * `compact={true}` to drop Blast Radius and Tool columns.
 */
import Link from "next/link"

export type { AuditEvent } from "./activity-row/types"
export {
  BlastRadiusBadge,
  LocalRiskPill,
  ProxyPill,
  ToolBadge,
  formatToolCall,
  formatTs,
  isProxyEvent,
} from "./activity-row/badges"
export { SignatureTamperRow } from "./activity-row/SignatureTamperRow"
export { DecisionBadge } from "./DecisionBadge"



export function ActivityRow({ ev, compact = false, isLast = false, visibleColumns, nowOffsetMs }: {
  ev: AuditEvent
  compact?: boolean
  isLast?: boolean
  visibleColumns?: readonly ColumnKey[]
  // #1990 item D — server-time drift threaded from the page state so
  // LifecyclePill's client-side 'expired' detection stays honest even
  // if the browser clock is skewed.
  nowOffsetMs?: number
}) {
  const [hovered, setHovered] = useState(false)
  const [open, setOpen] = useState(false)

  if (ev.rule_id === "policy_signature_invalid") {
    return <SignatureTamperRow ev={ev} isLast={isLast} />
  }

  const { set: showCol } = resolveVisible(visibleColumns, compact)
  const cols = buildGridTemplate(
    ALL_COLUMNS.map(c => c.key).filter(k => showCol.has(k))
  )

  const bg = ev.decision === "blocked"
    ? "var(--err-bg)"
    : hovered ? "var(--surface-2)" : "transparent"

  return (
    <>
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => setOpen(o => !o)}
      style={{
        display: "grid",
        gridTemplateColumns: cols,
        gap: 12,
        padding: "10px 18px",
        borderBottom: (isLast && !open) ? "none" : "1px solid var(--border)",
        alignItems: "center",
        background: bg,
        transition: "background .1s",
        cursor: "pointer",
      }}
    >
      {showCol.has("time") && (
        <div className="mono" style={{ fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }} title={formatTs(ev.ts)}>{timeAgo(ev.ts)}</div>
      )}
      {showCol.has("actor") && (
      <div style={{ minWidth: 0, overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, overflow: "hidden" }}
          title={ev.user_email ?? ev.agent_identity_id ?? undefined}>
          <span className="mono" style={{ fontSize: 11.5, color: "var(--text-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {ev.user_email ? ev.user_email.split("@")[0] : ev.conductai_workflow ?? <AgentAvatar agentId={ev.agent_identity_id} size={20} />}
          </span>
          {(() => {
            const isHuman = !!ev.user_email
            const pill = (
              <span style={{
                fontSize: 9, fontWeight: 700, letterSpacing: ".04em",
                padding: "1px 4px", borderRadius: 3,
                background: isHuman ? "var(--surface-2)" : "#e0e7ff",
                color: isHuman ? "var(--text-muted)" : "#3730a3",
                whiteSpace: "nowrap",
              }}>
                {isHuman ? "HUMAN" : "AGENT"}
              </span>
            )
            // AGENT rows always link to /agent-identity — deep-link with
            // ?id=<uuid> when the identity is known (highlight from PR #1286),
            // fall back to the identities list otherwise (#1471).
            if (!isHuman) {
              const href = ev.agent_identity_id
                ? `/agent-identity?tab=identities&id=${ev.agent_identity_id}`
                : "/agent-identity?tab=identities"
              return (
                <a href={href}
                   title={ev.agent_identity_id ? `View agent identity ${ev.agent_identity_id}` : "View agent identities"}
                   onClick={(e: ReactMouseEvent<HTMLAnchorElement>) => e.stopPropagation()}
                   style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4 }}>
                  {pill}
                  {ev.agent_identity_id && (
                    <span className="mono" style={{ fontSize: 9.5, color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                      {ev.agent_identity_id.slice(0, 6)}
                    </span>
                  )}
                </a>
              )
            }
            return pill
          })()}
        </div>
        {(ev.hook_session_id || ev.session_id) && (
          <div className="mono" style={{ fontSize: 9.5, color: "var(--text-muted)", marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            title={ev.hook_session_id || ev.session_id || ""}>
            {(ev.hook_session_id || ev.session_id || "").slice(-8)}
          </div>
        )}
      </div>
      )}
      {showCol.has("tool") && (
        <div>
          {ev.source === "brain_block" && ev.conductai_workflow ? (
            ev.conductai_run_id ? (
              <Link href={`/workflows/${ev.conductai_workflow_id}/runs/${ev.conductai_run_id}`}
                onClick={(e: ReactMouseEvent<HTMLAnchorElement>) => e.stopPropagation()}
                style={{ textDecoration: "none", fontSize: 11.5, fontFamily: "var(--font-mono, monospace)", color: "var(--accent-text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block", maxWidth: "100%" }}>
                {ev.conductai_workflow}
              </Link>
            ) : (
              <span style={{ fontSize: 11.5, fontFamily: "var(--font-mono, monospace)", color: "var(--text-2)" }}>{ev.conductai_workflow}</span>
            )
          ) : (
            ev.conductai_run_id ? (
              <Link href={`/workflows/${ev.conductai_workflow_id}/runs/${ev.conductai_run_id}`} onClick={(e: ReactMouseEvent<HTMLAnchorElement>) => e.stopPropagation()} style={{ textDecoration: "none" }}>
                <ToolBadge tool={ev.ai_tool} />
              </Link>
            ) : (
              <ToolBadge tool={ev.ai_tool} />
            )
          )}
        </div>
      )}
      {showCol.has("call") && (
        <div style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
          <div className="mono" style={{ fontSize: 11.5, fontWeight: 600, display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
            <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {((ev.source === "proxy") || (ev.source === "gateway")) && ev.provider
                ? `${ev.provider}/${ev.model ?? "?"}`
                : ev.source === "local_audit"
                  ? (ev.provider ? `${ev.provider} key found` : "local key found")
                  : formatToolCall(ev.tool_call)}
            </span>
            {(ev.source === "proxy" || ev.source === "gateway") && <ProxyPill />}
            {ev.source === "brain_block" && (() => {
              const pill = (
                <span style={{ fontSize: 8, fontWeight: 700, letterSpacing: ".06em", padding: "1px 5px", borderRadius: 3, background: "#ede9fe", color: "#6d28d9", border: "1px solid #c4b5fd" }}>
                  AGENT
                </span>
              )
              // #1471 — link the brain_block AGENT badge to the specific identity
              // when known; fall back to the agent identity list otherwise.
              const href = ev.agent_identity_id
                ? `/agent-identity?tab=identities&id=${ev.agent_identity_id}`
                : "/agent-identity?tab=identities"
              return (
                <a href={href}
                   title={ev.agent_identity_id ? `View agent identity ${ev.agent_identity_id}` : "View agent identities"}
                   onClick={(e: ReactMouseEvent<HTMLAnchorElement>) => e.stopPropagation()}
                   style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4 }}>
                  {pill}
                  {ev.agent_identity_id && (
                    <span className="mono" style={{ fontSize: 9, color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                      {ev.agent_identity_id.slice(0, 6)}
                    </span>
                  )}
                </a>
              )
            })()}
            {ev.source === "local_audit" && <LocalRiskPill />}
          </div>
          <div className="mono" style={{ fontSize: 11, color: "var(--text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>
            {ev.source === "brain_block" && ev.provider && ev.model
              ? `${ev.input_summary || "vendor"} → ${ev.provider} · ${ev.model}`
              : ev.input_summary ? `${ev.input_summary}…` : "—"}
          </div>
        </div>
      )}
      {showCol.has("rule") && (
      <div className="mono" style={{ fontSize: 11, color: ev.rule_id ? "var(--err)" : "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0, display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{ev.rule_id ?? "—"}</span>
        {ev.evaluated_rules && ev.evaluated_rules.length > 1 && (
          <span
            title={`Also flagged by: ${ev.evaluated_rules
              .filter(r => r.rule_id !== ev.rule_id)
              .map(r => r.rule_id)
              .join(", ")}`}
            style={{
              fontSize: 10,
              fontWeight: 600,
              color: "var(--text-2)",
              background: "var(--bg-2)",
              border: "1px solid var(--border)",
              borderRadius: 4,
              padding: "0 5px",
              flexShrink: 0,
            }}
          >
            +{ev.evaluated_rules.length - 1}
          </span>
        )}
      </div>
      )}
      {showCol.has("decision") && (
      <div>
        {ev.execution_status === "error" || ev.execution_status === "timeout" ? (
          <span title={ev.result_summary || "Gateway execution failed"} style={{ display: "inline-flex", fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 4, color: "var(--err)", background: "var(--err-bg)" }}>
            {ev.execution_status === "timeout" ? "Timeout" : "Error"}
          </span>
        ) : ev.conductai_run_id ? (
          <Link href={`/workflows/${ev.conductai_workflow_id}/runs/${ev.conductai_run_id}`} onClick={(e: ReactMouseEvent<HTMLAnchorElement>) => e.stopPropagation()} style={{ display: "inline-flex", alignItems: "center", gap: 3, textDecoration: "none" }}>
            <DecisionBadge decision={ev.decision} />
            <span style={{ fontSize: 11, color: "var(--accent-text)" }}>→</span>
          </Link>
        ) : (
          <DecisionBadge decision={ev.decision} />
        )}
      </div>
      )}
      {showCol.has("blast") && (
        <div>
          {ev.blast_radius ? (
            <BlastRadiusBadge br={ev.blast_radius} />
          ) : (
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>—</span>
          )}
        </div>
      )}
      {showCol.has("lifecycle") && (
        <div>
          <LifecyclePill state={ev.lifecycle_state} leaseExpiresAt={ev.lease_expires_at} nowOffsetMs={nowOffsetMs} />
        </div>
      )}
      {showCol.has("tokens") && (
        <div style={{ textAlign: "right", fontSize: 12, color: "var(--text-2)" }}>
          {formatTokensUsed(ev.tokens_before, ev.tokens_after) ?? (
            <span style={{ color: "var(--text-muted)" }}>—</span>
          )}
        </div>
      )}
    </div>
    {open && (
      <div style={{
        padding: "12px 18px 14px",
        borderBottom: isLast ? "none" : "1px solid var(--border)",
        background: "var(--surface-2)",
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: "8px 24px",
        fontSize: 11,
      }}>
        <div style={{ gridColumn: "1 / -1" }}><AskLensLink kind="event" resourceId={ev.id} /></div>
        {ev.input_summary && (
          <div style={{ gridColumn: "1 / -1" }}>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Input</span>
            <span className="mono" style={{ color: "var(--text-2)", wordBreak: "break-all" }}>{ev.input_summary}</span>
          </div>
        )}
        <div>
          <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Time</span>
          <span className="mono" style={{ color: "var(--text-2)" }}>{formatTs(ev.ts)}</span>
        </div>
        {ev.policy_hash && (
          <div>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Policy</span>
            <span className="mono" style={{ color: "var(--text-2)" }} title={ev.policy_hash}>sha:{ev.policy_hash.slice(0, 8)}</span>
          </div>
        )}
        {ev.entry_hash && (
          <div>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Chain</span>
            <span className="mono" style={{ color: "var(--text-2)" }} title={ev.entry_hash}>sha:{ev.entry_hash.slice(0, 8)}</span>
          </div>
        )}
        {ev.blast_radius && (
          <div>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Blast radius</span>
            <span style={{ color: "var(--text-2)" }}>{ev.blast_radius.files} files · {ev.blast_radius.tier}</span>
          </div>
        )}
        {(ev.provider || ev.model) && (
          <div>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Model</span>
            <span className="mono" style={{ color: "var(--text-2)" }}>{[ev.provider, ev.model].filter(Boolean).join(" / ")}</span>
          </div>
        )}
        {ev.agent_identity_id && <div>
          <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Agent ID</span>
          <Link href={`/agent-identity?tab=identities&id=${encodeURIComponent(ev.agent_identity_id)}`}
            className="mono" style={{ color: "var(--text-2)", overflowWrap: "anywhere" }}>{ev.agent_identity_id}</Link>
        </div>}
        {ev.routing_meta?.gateway_profile && <div>
          <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Gateway profile</span>
          <Link href={`/proxy/gateway-profiles${ev.routing_meta.gateway_profile_id ? `?select=${encodeURIComponent(ev.routing_meta.gateway_profile_id)}` : ""}`}
            className="mono" style={{ color: "var(--text-2)", overflowWrap: "anywhere" }}>{ev.routing_meta.gateway_profile}</Link>
        </div>}
        {ev.federation && <AttributionDetails value={ev.federation} />}
        {ev.routing_meta?.session_usage && <>
          <SessionUsageDetails value={ev.routing_meta.session_usage} />
          <SessionSpend eventId={ev.id} />
        </>}
        {ev.routing_meta && (ev.routing_meta.tier_form || ev.routing_meta.resolved_model || ev.routing_meta.resolution_source) && (
          <div>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Routed</span>
            <span className="mono" style={{ color: "var(--text-2)" }}>
              {ev.routing_meta.tier_form ?? "?"} → {ev.routing_meta.resolved_model ?? ev.model ?? "?"}
            </span>
            {ev.routing_meta.resolution_source && (
              <span style={{ color: "var(--text-muted)", marginLeft: 6, fontSize: 11 }}>
                via {ev.routing_meta.resolution_source.replace(/_/g, " ")}
              </span>
            )}
          </div>
        )}
        {ev.rule_id && (
          <div>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Rule</span>
            <span className="mono" style={{ color: "var(--err)" }}>{ev.rule_id}</span>
          </div>
        )}
        {(ev.hostname || ev.hook_session_id) && (
          <div style={{ gridColumn: "1 / -1" }}>
            <span style={{ color: "var(--text-muted)", fontWeight: 600, marginRight: 6 }}>Session</span>
            <span className="mono" style={{ color: "var(--text-2)" }}>
              {ev.hostname && <>{ev.hostname} · </>}{ev.hook_session_id ?? ev.session_id ?? "—"}
            </span>
          </div>
        )}
      </div>
    )}
    </>
  )
}

/** Column header strip — same widths/labels as the rows, with optional compact mode. */
export function ActivityHeader({ compact = false, visibleColumns }: {
  compact?: boolean
  visibleColumns?: readonly ColumnKey[]
}) {
  const { list, set: showCol } = resolveVisible(visibleColumns, compact)
  const cols = buildGridTemplate(list)
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: cols,
      gap: 12,
      padding: "10px 18px",
      borderBottom: "1px solid var(--border)",
      background: "var(--surface-2)",
      fontSize: 10,
      fontWeight: 600,
      letterSpacing: ".06em",
      textTransform: "uppercase",
      color: "var(--text-muted)",
    }}>
      {showCol.has("time") && <div>Time</div>}
      {showCol.has("actor") && <div>Actor</div>}
      {showCol.has("tool") && <div>Tool</div>}
      {showCol.has("call") && <div>Action</div>}
      {showCol.has("rule") && <div>Rule</div>}
      {showCol.has("decision") && <div>Decision</div>}
      {showCol.has("blast") && <div>Blast</div>}
      {showCol.has("lifecycle") && <div>Lifecycle</div>}
      {showCol.has("tokens") && <div style={{ textAlign: "right" }}>Tokens</div>}
    </div>
  )
}
