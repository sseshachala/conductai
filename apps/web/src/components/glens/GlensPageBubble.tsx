"use client"

import { DecisionBadge } from "@/components/guard/DecisionBadge"
import { ActivityHeader, ActivityRow, type AuditEvent } from "@/components/guard/ActivityRow"
import { ByAiToolTable, type ByAiToolRow } from "@/components/guard/ByAiToolTable"

// ─── Types ─────────────────────────────────────────────────────────────────────

type PageKind = "spend" | "discovery" | "compliance" | "governance" | "activity" | "policies"

// ─── Shared helpers ────────────────────────────────────────────────────────────

function fmtCost(n: number): string {
  return `$${n.toFixed(2)}`
}

function fmtNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return String(n)
}

function relativeTime(ts: string): string {
  try {
    const diff = Date.now() - new Date(ts).getTime()
    const secs = Math.floor(diff / 1000)
    if (secs < 60) return "just now"
    const mins = Math.floor(secs / 60)
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs}h ago`
    const days = Math.floor(hrs / 24)
    return `${days}d ago`
  } catch {
    return ts
  }
}

const FRAMEWORK_LABELS: Record<string, string> = {
  "claude-code":    "Claude Code",
  "claude-desktop": "Claude Desktop",
  "codex":          "Codex",
  "cursor":         "Cursor",
  "windsurf":       "Windsurf",
  "langchain":      "LangChain",
  "crewai":         "CrewAI",
  "autogen":        "AutoGen",
}

const PACK_LABELS: Record<string, string> = {
  "conduct-owasp":   "OWASP",
  "conduct-soc2":    "SOC 2",
  "conduct-hipaa":   "HIPAA",
  "conduct-pci-dss": "PCI DSS",
  "conduct-base":    "Base",
}

// ─── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div style={{
      border: "1px solid var(--border)",
      borderRadius: 8,
      padding: "14px 16px",
      background: "var(--surface-1, var(--surface))",
      minWidth: 100,
      flex: "1 1 0",
    }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: "var(--text)", lineHeight: 1 }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>{sub}</div>
      )}
    </div>
  )
}

function StatRow({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
      {children}
    </div>
  )
}

// ─── Table helpers ─────────────────────────────────────────────────────────────

const TH_STYLE: React.CSSProperties = {
  textAlign: "left",
  padding: "8px 12px",
  fontSize: 11,
  fontWeight: 600,
  color: "var(--text-muted)",
  borderBottom: "1px solid var(--border)",
  whiteSpace: "nowrap",
}

const TD_STYLE: React.CSSProperties = {
  padding: "9px 12px",
  fontSize: 13,
  borderBottom: "1px solid var(--border)",
  color: "var(--text)",
}

function EmbedTable({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden", marginTop: 4 }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        {children}
      </table>
    </div>
  )
}

// ─── SpendEmbed ────────────────────────────────────────────────────────────────

interface SpendRow {
  tool: string
  cost_usd: number
  tokens_saved: number
}

interface DevRow {
  email: string
  cost_usd: number
}

interface SpendData {
  by_ai_tool: SpendRow[]
  by_developer: DevRow[]
  total_cost_usd: number
  tokens_saved_today: number
}

function SpendEmbed({ data }: { data: Record<string, unknown> }) {
  const d = data as unknown as SpendData

  const totalCost = d.total_cost_usd ?? 0
  const byAiTool: SpendRow[] = d.by_ai_tool ?? []

  const tableRows: ByAiToolRow[] = byAiTool.map(r => ({
    tool: r.tool,
    tokens: 0,               // not provided in spend data shape
    costLabel: fmtCost(r.cost_usd ?? 0),
    saved: r.tokens_saved ?? 0,
    pct: totalCost > 0 ? Math.round(((r.cost_usd ?? 0) / totalCost) * 100) : 0,
  }))

  const devs: DevRow[] = [...(d.by_developer ?? [])].sort((a, b) => (b.cost_usd ?? 0) - (a.cost_usd ?? 0))

  return (
    <div>
      <StatRow>
        <StatCard label="Total Cost" value={fmtCost(totalCost)} />
        <StatCard label="Tokens Saved" value={fmtNumber(d.tokens_saved_today ?? 0)} />
      </StatRow>

      {tableRows.length > 0 && <ByAiToolTable rows={tableRows} />}

      {devs.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 650, color: "var(--text-muted)", marginBottom: 8 }}>By developer</div>
          <EmbedTable>
            <thead>
              <tr>
                <th style={TH_STYLE}>Email</th>
                <th style={{ ...TH_STYLE, textAlign: "right" }}>Cost</th>
              </tr>
            </thead>
            <tbody>
              {devs.map((r, i) => (
                <tr key={r.email ?? i}>
                  <td style={TD_STYLE} className="mono">{r.email ?? "—"}</td>
                  <td style={{ ...TD_STYLE, textAlign: "right" }} className="mono">{fmtCost(r.cost_usd ?? 0)}</td>
                </tr>
              ))}
            </tbody>
          </EmbedTable>
        </div>
      )}
    </div>
  )
}

// ─── DiscoveryEmbed ────────────────────────────────────────────────────────────

interface AgentRow {
  name: string
  framework: string
  source: string
  location: string
  risk_score: number
  under_guard: boolean
  proxy_routed: boolean
  last_seen_at: string
}

interface DiscoveryData {
  agents: AgentRow[]
  total: number
  under_guard: number
  coverage_pct: number
}

function RiskBadge({ score }: { score: number }) {
  if (score >= 70) return <span className="sbadge err">High</span>
  if (score >= 40) return <span className="sbadge warn">Medium</span>
  return <span className="sbadge ok">Low</span>
}

function DotLabel({ on, yesText = "Yes", noText = "No" }: { on: boolean; yesText?: string; noText?: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12 }}>
      <span style={{
        width: 7, height: 7, borderRadius: "50%",
        background: on ? "var(--ok, #16a34a)" : "var(--err, #dc2626)",
        flexShrink: 0,
      }} />
      {on ? yesText : noText}
    </span>
  )
}

function DiscoveryEmbed({ data }: { data: Record<string, unknown> }) {
  const d = data as unknown as DiscoveryData
  const agents: AgentRow[] = d.agents ?? []

  return (
    <div>
      <StatRow>
        <StatCard label="Total Agents" value={d.total ?? agents.length} />
        <StatCard label="Under Guard" value={d.under_guard ?? 0} />
        <StatCard label="Coverage" value={`${d.coverage_pct ?? 0}%`} />
      </StatRow>

      {agents.length > 0 && (
        <EmbedTable>
          <thead>
            <tr>
              <th style={TH_STYLE}>Name</th>
              <th style={TH_STYLE}>Framework</th>
              <th style={TH_STYLE}>Source</th>
              <th style={TH_STYLE}>Risk</th>
              <th style={TH_STYLE}>Under Guard</th>
              <th style={TH_STYLE}>Last Seen</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((a, i) => (
              <tr key={a.name ?? i}>
                <td style={TD_STYLE} className="mono">{a.name ?? "—"}</td>
                <td style={TD_STYLE}>{FRAMEWORK_LABELS[a.framework] ?? a.framework ?? "—"}</td>
                <td style={{ ...TD_STYLE, fontSize: 12, color: "var(--text-muted)" }}>{a.source ?? "—"}</td>
                <td style={TD_STYLE}><RiskBadge score={a.risk_score ?? 0} /></td>
                <td style={TD_STYLE}><DotLabel on={!!a.under_guard} /></td>
                <td style={{ ...TD_STYLE, fontSize: 12, color: "var(--text-muted)" }}>{a.last_seen_at ? relativeTime(a.last_seen_at) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </EmbedTable>
      )}
    </div>
  )
}

// ─── ComplianceEmbed ───────────────────────────────────────────────────────────

interface ControlRow {
  control_id: string
  name: string
  status: "active" | "partial" | "missing"
  conduct_enforcement: string
}

interface ComplianceData {
  grade: string
  score: number
  coverage_pct: number
  controls: ControlRow[]
  events_24h: { blocked: number; total: number }
}

function GradeColor(grade: string): string {
  if (grade === "A" || grade === "B") return "var(--ok, #16a34a)"
  if (grade === "C" || grade === "D") return "var(--warn, #d97706)"
  return "var(--err, #dc2626)"
}

function StatusBadge({ status }: { status: string }) {
  if (status === "active") return <span className="sbadge ok">Active</span>
  if (status === "partial") return <span className="sbadge warn">Partial</span>
  return <span className="sbadge err">Missing</span>
}

function ComplianceEmbed({ data }: { data: Record<string, unknown> }) {
  const d = data as unknown as ComplianceData
  const controls: ControlRow[] = d.controls ?? []

  return (
    <div>
      <StatRow>
        <div style={{
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "14px 20px",
          background: "var(--surface-1, var(--surface))",
          display: "flex",
          alignItems: "center",
          gap: 18,
          flex: "0 0 auto",
        }}>
          <span style={{ fontSize: 42, fontWeight: 800, color: GradeColor(d.grade ?? "F"), lineHeight: 1 }}>
            {d.grade ?? "—"}
          </span>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text)" }}>{d.score ?? 0}<span style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 400 }}>/100</span></div>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{d.coverage_pct ?? 0}% coverage</div>
          </div>
        </div>
        {d.events_24h && (
          <>
            <StatCard label="Blocked (24h)" value={d.events_24h.blocked ?? 0} />
            <StatCard label="Total Events (24h)" value={d.events_24h.total ?? 0} />
          </>
        )}
      </StatRow>

      {controls.length > 0 && (
        <EmbedTable>
          <thead>
            <tr>
              <th style={TH_STYLE}>Control</th>
              <th style={TH_STYLE}>Name</th>
              <th style={TH_STYLE}>Status</th>
              <th style={TH_STYLE}>Enforcement</th>
            </tr>
          </thead>
          <tbody>
            {controls.map((c, i) => (
              <tr key={c.control_id ?? i}>
                <td style={{ ...TD_STYLE, fontSize: 12 }} className="mono">{c.control_id ?? "—"}</td>
                <td style={TD_STYLE}>{c.name ?? "—"}</td>
                <td style={TD_STYLE}><StatusBadge status={c.status} /></td>
                <td style={{ ...TD_STYLE, fontSize: 12, color: "var(--text-muted)" }}>{c.conduct_enforcement ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </EmbedTable>
      )}
    </div>
  )
}

// ─── GovernanceEmbed ───────────────────────────────────────────────────────────

interface GovernanceData {
  kpis: {
    events_today: number
    blocked_today: number
    active_developers_today: number
    blocks_mtd: number
    risk_avoided_usd_mtd: number
  }
  frameworks: Array<{ name: string; rules_count: number }>
  recent_events: Array<{
    ts: string
    decision: string
    rule_id: string | null
    ai_tool: string
    user_email: string | null
  }>
}

function GovernanceEmbed({ data }: { data: Record<string, unknown> }) {
  const d = data as unknown as GovernanceData
  const kpis = d.kpis ?? {}
  const frameworks: GovernanceData["frameworks"] = d.frameworks ?? []
  const events: GovernanceData["recent_events"] = d.recent_events ?? []

  return (
    <div>
      <StatRow>
        <StatCard label="Events Today" value={fmtNumber(kpis.events_today ?? 0)} />
        <StatCard label="Blocked Today" value={fmtNumber(kpis.blocked_today ?? 0)} />
        <StatCard label="Active Devs" value={kpis.active_developers_today ?? 0} />
        <StatCard label="Blocks MTD" value={fmtNumber(kpis.blocks_mtd ?? 0)} />
        <StatCard label="Risk Avoided" value={fmtCost(kpis.risk_avoided_usd_mtd ?? 0)} sub="month to date" />
      </StatRow>

      {frameworks.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 650, color: "var(--text-muted)", marginBottom: 8 }}>Frameworks</div>
          <EmbedTable>
            <thead>
              <tr>
                <th style={TH_STYLE}>Framework</th>
                <th style={{ ...TH_STYLE, textAlign: "right" }}>Rules</th>
              </tr>
            </thead>
            <tbody>
              {frameworks.map((f, i) => (
                <tr key={f.name ?? i}>
                  <td style={TD_STYLE}>{f.name ?? "—"}</td>
                  <td style={{ ...TD_STYLE, textAlign: "right" }} className="mono">{f.rules_count ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </EmbedTable>
        </div>
      )}

      {events.length > 0 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 650, color: "var(--text-muted)", marginBottom: 8 }}>Recent events</div>
          <EmbedTable>
            <thead>
              <tr>
                <th style={TH_STYLE}>Decision</th>
                <th style={TH_STYLE}>Actor</th>
                <th style={TH_STYLE}>Tool</th>
                <th style={TH_STYLE}>Rule</th>
                <th style={TH_STYLE}>Time</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e, i) => (
                <tr key={i}>
                  <td style={TD_STYLE}><DecisionBadge decision={e.decision ?? "—"} /></td>
                  <td style={{ ...TD_STYLE, fontSize: 12 }} className="mono">{e.user_email ? e.user_email.split("@")[0] : "—"}</td>
                  <td style={{ ...TD_STYLE, fontSize: 12 }} className="mono">{e.ai_tool ?? "—"}</td>
                  <td style={{ ...TD_STYLE, fontSize: 12, color: e.rule_id ? "var(--err)" : "var(--text-muted)" }} className="mono">{e.rule_id ?? "—"}</td>
                  <td style={{ ...TD_STYLE, fontSize: 12, color: "var(--text-muted)" }}>{e.ts ? relativeTime(e.ts) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </EmbedTable>
        </div>
      )}
    </div>
  )
}

// ─── ActivityEmbed ─────────────────────────────────────────────────────────────

interface ActivityEventRaw {
  ts: string
  decision: string
  user_email: string | null
  ai_tool: string
  tool_name: string | null
  rule_id: string | null
}

interface ActivityData {
  events: ActivityEventRaw[]
}

function ActivityEmbed({ data }: { data: Record<string, unknown> }) {
  const d = data as unknown as ActivityData
  const raw: ActivityEventRaw[] = (d.events ?? []).slice(0, 20)

  const events: AuditEvent[] = raw.map((e, i) => ({
    id: String(i),
    ts: e.ts ?? new Date().toISOString(),
    user_email: e.user_email ?? null,
    ai_tool: e.ai_tool ?? "",
    tool_call: e.tool_name ?? null,
    input_summary: null,
    decision: e.decision ?? "allowed",
    rule_id: e.rule_id ?? null,
  }))

  if (events.length === 0) {
    return <div style={{ fontSize: 13, color: "var(--text-muted)", padding: "12px 0" }}>No activity events.</div>
  }

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
      <ActivityHeader compact />
      {events.map((ev, i) => (
        <ActivityRow key={ev.id} ev={ev} compact isLast={i === events.length - 1} />
      ))}
    </div>
  )
}

// ─── PoliciesEmbed ─────────────────────────────────────────────────────────────

interface PolicyRule {
  rule_id: string
  description: string
  action: "block" | "warn" | "audit" | "approval"
  match_tool: string | null
  enabled: boolean
  severity: "critical" | "high" | "medium" | "low"
  pack_id: string | null
  persona: string | null
}

interface PoliciesData {
  rules: PolicyRule[]
}

function ActionBadge({ action }: { action: string }) {
  if (action === "block") return <span className="sbadge err">Block</span>
  if (action === "warn") return <span className="sbadge warn">Warn</span>
  if (action === "audit") return <span className="sbadge info">Audit</span>
  if (action === "approval") return <span className="sbadge" style={{ background: "#ede9fe", color: "#6d28d9", border: "1px solid #c4b5fd", borderRadius: 4, padding: "2px 8px", fontSize: 11, fontWeight: 600 }}>Approval</span>
  return <span className="sbadge">{action}</span>
}

function SeverityBadge({ severity }: { severity: string }) {
  if (severity === "critical") return <span className="sbadge err">Critical</span>
  if (severity === "high") return <span style={{ display: "inline-block", fontSize: 11, fontWeight: 600, background: "#fff3e0", color: "#e65100", border: "1px solid #ffb74d", borderRadius: 4, padding: "2px 8px" }}>High</span>
  if (severity === "medium") return <span className="sbadge warn">Medium</span>
  if (severity === "low") return <span className="sbadge ok">Low</span>
  return <span className="sbadge">{severity}</span>
}

function EnabledDot({ on }: { on: boolean }) {
  return (
    <span style={{
      display: "inline-block",
      width: 8,
      height: 8,
      borderRadius: "50%",
      background: on ? "var(--ok, #16a34a)" : "var(--text-muted, #9ca3af)",
    }} />
  )
}

function PoliciesEmbed({ data }: { data: Record<string, unknown> }) {
  const d = data as unknown as PoliciesData
  const rules: PolicyRule[] = d.rules ?? []

  if (rules.length === 0) {
    return <div style={{ fontSize: 13, color: "var(--text-muted)", padding: "12px 0" }}>No policy rules.</div>
  }

  return (
    <EmbedTable>
      <thead>
        <tr>
          <th style={TH_STYLE}>Rule ID</th>
          <th style={TH_STYLE}>Description</th>
          <th style={TH_STYLE}>Tool</th>
          <th style={TH_STYLE}>Action</th>
          <th style={TH_STYLE}>Severity</th>
          <th style={TH_STYLE}>Pack</th>
          <th style={TH_STYLE}>On</th>
        </tr>
      </thead>
      <tbody>
        {rules.map((r, i) => (
          <tr key={r.rule_id ?? i}>
            <td style={{ ...TD_STYLE, fontSize: 11 }} className="mono">{r.rule_id ?? "—"}</td>
            <td style={{ ...TD_STYLE, maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              title={r.description ?? undefined}>
              {r.description ?? "—"}
            </td>
            <td style={{ ...TD_STYLE, fontSize: 12 }} className="mono">{r.match_tool ?? "*"}</td>
            <td style={TD_STYLE}><ActionBadge action={r.action ?? ""} /></td>
            <td style={TD_STYLE}><SeverityBadge severity={r.severity ?? ""} /></td>
            <td style={{ ...TD_STYLE, fontSize: 12 }}>{PACK_LABELS[r.pack_id ?? ""] ?? (r.pack_id ?? "—")}</td>
            <td style={TD_STYLE}><EnabledDot on={!!r.enabled} /></td>
          </tr>
        ))}
      </tbody>
    </EmbedTable>
  )
}

// ─── GlensPageBubble (public export) ──────────────────────────────────────────

export function GlensPageBubble({
  answer,
  pageKind,
  data,
  warning,
}: {
  answer: string
  pageKind: PageKind
  data: Record<string, unknown>
  warning?: string
}) {
  return (
    <div style={{ maxWidth: "100%", marginBottom: 16 }}>
      {answer && (
        <div style={{ fontSize: 14, color: "var(--text)", marginBottom: 12, lineHeight: 1.6 }}>
          {answer}
        </div>
      )}
      {warning && (
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
          &#9888; {warning}
        </div>
      )}
      {pageKind === "spend"      && <SpendEmbed data={data} />}
      {pageKind === "discovery"  && <DiscoveryEmbed data={data} />}
      {pageKind === "compliance" && <ComplianceEmbed data={data} />}
      {pageKind === "governance" && <GovernanceEmbed data={data} />}
      {pageKind === "activity"   && <ActivityEmbed data={data} />}
      {pageKind === "policies"   && <PoliciesEmbed data={data} />}
    </div>
  )
}
