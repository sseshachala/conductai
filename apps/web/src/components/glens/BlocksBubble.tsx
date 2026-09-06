"use client"

import {
  BarChart, Bar,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts"
import { renderTable } from "@/components/glens/GenericTableBubble"
import type { Column } from "@/components/glens/GenericTableBubble"

// ─── Types ────────────────────────────────────────────────────────────────────

interface StatItem {
  label: string
  value: string
  sub?: string
  color?: "ok" | "err" | "warn" | "info" | "neutral"
}

interface BadgeItem {
  label: string
  value: string
  badge?: "ok" | "err" | "warn" | "info"
}

type Block =
  | { type: "stat-row"; items: StatItem[] }
  | { type: "table"; columns: Column[]; rows: Record<string, unknown>[] }
  | { type: "bar-chart"; title?: string; x_key: string; y_key: string; color?: string; data: Record<string, unknown>[] }
  | { type: "badge-list"; title?: string; items: BadgeItem[] }

// ─── Color map ────────────────────────────────────────────────────────────────

const STAT_COLOR: Record<string, string> = {
  ok:      "var(--accent-text)",
  err:     "#ef4444",
  warn:    "#f59e0b",
  info:    "#3b82f6",
  neutral: "var(--text-1)",
}

// ─── Block renderers ──────────────────────────────────────────────────────────

function StatRow({ items }: { items: StatItem[] }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
      {items.map((item, i) => (
        <div
          key={i}
          style={{
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "12px 16px",
            background: "var(--surface-1)",
            minWidth: 120,
            flex: 1,
          }}
        >
          <div style={{
            fontSize: 11,
            fontWeight: 700,
            color: "var(--text-muted)",
            textTransform: "uppercase",
            letterSpacing: ".04em",
            marginBottom: 4,
          }}>
            {item.label}
          </div>
          <div style={{
            fontSize: 22,
            fontWeight: 700,
            color: item.color ? (STAT_COLOR[item.color] ?? "var(--text)") : "var(--text)",
          }}>
            {item.value}
          </div>
          {item.sub && (
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 3 }}>
              {item.sub}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function BarChartBlock({ block }: { block: Extract<Block, { type: "bar-chart" }> }) {
  const data = block.data.map(row => ({
    x: String(row[block.x_key] ?? ""),
    y: Number(row[block.y_key] ?? 0),
  }))

  return (
    <div>
      {block.title && (
        <div style={{
          fontSize: 11,
          fontWeight: 600,
          color: "var(--text-muted)",
          textTransform: "uppercase",
          letterSpacing: ".04em",
          marginBottom: 10,
        }}>
          {block.title}
        </div>
      )}
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
          <XAxis
            dataKey="x"
            tick={{ fontSize: 10 }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tick={{ fontSize: 10 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={{
              fontSize: 12,
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: "var(--surface)",
            }}
            formatter={(val) => [String(val ?? 0), block.title ?? block.y_key]}
          />
          <Bar
            dataKey="y"
            name={block.title ?? block.y_key}
            fill={block.color ?? "var(--accent)"}
            radius={[3, 3, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

const BADGE_CLASS: Record<string, string> = {
  ok:   "sbadge ok",
  err:  "sbadge err",
  warn: "sbadge warn",
  info: "sbadge info",
}

function BadgeList({ block }: { block: Extract<Block, { type: "badge-list" }> }) {
  return (
    <div>
      {block.title && (
        <div style={{
          fontSize: 11,
          fontWeight: 600,
          color: "var(--text-muted)",
          textTransform: "uppercase",
          letterSpacing: ".04em",
          marginBottom: 8,
        }}>
          {block.title}
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 16px" }}>
        {block.items.map((item, i) => (
          <div key={i} style={{ display: "contents" }}>
            <div style={{ fontSize: 13, color: "var(--text-muted)", alignSelf: "center" }}>
              {item.label}
            </div>
            <div style={{ alignSelf: "center" }}>
              {item.badge ? (
                <span className={BADGE_CLASS[item.badge] ?? "sbadge info"}>{item.value}</span>
              ) : (
                <span style={{ fontSize: 13, color: "var(--text)" }}>{item.value}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function renderBlock(block: Block, i: number) {
  switch (block.type) {
    case "stat-row":
      return <StatRow key={i} items={block.items} />
    case "table":
      return <div key={i}>{renderTable(block.columns, block.rows)}</div>
    case "bar-chart":
      return <BarChartBlock key={i} block={block} />
    case "badge-list":
      return <BadgeList key={i} block={block} />
    default:
      return null
  }
}

// ─── Skill label map (mirrors GLensChatPage) ──────────────────────────────────

const SKILL_LABELS: Record<string, string> = {
  report:       "Report",
  analytics:    "Analytics",
  extract:      "Extract",
  memory:       "Memory",
  session:      "Session",
  rules:        "Rules",
  guard_config: "Guard Config",
  spend_config: "Spend Config",
}

// ─── Component ────────────────────────────────────────────────────────────────

export function BlocksBubble({
  answer,
  blocks,
  warning,
  skill,
  understoodAs,
  drilldown,
}: {
  answer: string
  blocks: Block[]
  warning?: string
  skill?: string
  understoodAs?: string
  drilldown?: { path: string; filters?: Record<string, string> }
}) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16, width: "100%" }}>
      <div style={{
        width: "100%",
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: "4px 14px 14px 14px",
        padding: "16px 20px",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          {skill && (
            <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em" }}>
              {SKILL_LABELS[skill] ?? skill}
            </div>
          )}
          {understoodAs && (
            <div style={{ fontSize: 10, color: "var(--text-muted)", fontStyle: "italic" }}>
              · {understoodAs}
            </div>
          )}
        </div>

        {answer && (
          <div style={{ fontSize: 14, color: "var(--text)", marginBottom: 16, lineHeight: 1.5 }}>
            {answer}
          </div>
        )}

        {warning && (
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
            {warning}
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {blocks.map((block, i) => renderBlock(block, i))}
        </div>

        {drilldown && (
          <div style={{ marginTop: 12, textAlign: "right" }}>
            <a
              href={drilldown.path}
              style={{ fontSize: 12, color: "var(--accent, #6366f1)", textDecoration: "none", fontWeight: 500 }}
            >
              View full &rarr;
            </a>
          </div>
        )}
      </div>
    </div>
  )
}
