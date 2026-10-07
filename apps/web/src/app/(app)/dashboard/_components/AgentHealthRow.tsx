"use client"

import { type MouseEvent as ReactMouseEvent } from "react"
import Link from "next/link"
import { timeAgo } from "@/lib/runUtils"
import { KPI } from "./widgets"
import type { AgentHealth } from "./types"


// #3: AgentHealthRow rendered in Agent Health section below KPI strip
export function AgentHealthRow({ agent }: { agent: AgentHealth }) {
  const healthLabel =
    agent.last_run_status === null ? "Idle"
    : agent.run_count === 0 ? "Idle"
    : agent.success_rate >= 80 ? "Healthy"
    : agent.success_rate >= 50 ? "Degraded"
    : "Stale"

  const healthColor =
    healthLabel === "Healthy" ? "var(--ok)"
    : healthLabel === "Degraded" ? "var(--warn)"
    : healthLabel === "Stale" ? "var(--err)"
    : "var(--text-3)"

  const healthBg =
    healthLabel === "Healthy" ? "var(--ok-bg)"
    : healthLabel === "Degraded" ? "var(--warn-bg)"
    : healthLabel === "Stale" ? "var(--err-bg)"
    : "var(--surface-3)"

  const successRate = agent.run_count === 0 ? null : agent.success_rate / 100
  const barColor =
    successRate === null ? "var(--surface-3)"
    : successRate >= 0.8 ? "var(--ok)"
    : successRate >= 0.5 ? "var(--warn)"
    : "var(--err)"

  return (
    <Link
      href={`/workflows/${agent.workflow_id}`}
      style={{
        display: "grid",
        gridTemplateColumns: "2fr 1fr 1fr 0.9fr",
        gap: 12,
        padding: "11px 16px",
        borderBottom: "1px solid var(--border)",
        alignItems: "center",
        cursor: "pointer",
        textDecoration: "none",
        color: "inherit",
      }}
      onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => { (e.currentTarget as HTMLElement).style.background = "var(--surface-2)" }}
      onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => { (e.currentTarget as HTMLElement).style.background = "" }}
    >
      {/* Agent name + last run time */}
      <div>
        <div style={{ fontWeight: 600, fontSize: 13.5 }}>{agent.name}</div>
        <div style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 2 }}>
          {agent.last_run_at ? `last run ${timeAgo(agent.last_run_at)}` : "never run"}
        </div>
      </div>

      {/* Status badge */}
      <div>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            height: 21,
            padding: "0 8px",
            borderRadius: 20,
            fontSize: 11,
            fontWeight: 600,
            color: healthColor,
            background: healthBg,
          }}
        >
          <span style={{ width: 5, height: 5, borderRadius: "50%", background: healthColor }} />
          {healthLabel}
        </span>
      </div>

      {/* Success rate bar + % */}
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <div
          style={{
            width: 52,
            height: 5,
            borderRadius: 5,
            background: "var(--surface-3)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: successRate !== null ? `${Math.round(successRate * 100)}%` : "0%",
              height: "100%",
              borderRadius: 5,
              background: barColor,
            }}
          />
        </div>
        <span
          className="mono"
          style={{
            fontSize: 12,
            color: successRate === null ? "var(--text-muted)" : barColor,
          }}
        >
          {successRate !== null ? `${Math.round(successRate * 100)}%` : "—"}
        </span>
      </div>

      {/* Quality grade placeholder */}
      <div>
        <span style={{ color: "var(--text-muted)", fontSize: 12 }}>—</span>
      </div>
    </Link>
  )
}

export function EmptyChecklist() {
  const steps = [
    { label: "Install a starter playbook", href: "/packs", cta: "Browse playbooks →" },
    { label: "Add credentials (GitHub token, Slack)", href: "/settings?tab=credentials", cta: "Open vault →" },
    { label: "Run a test trigger", href: "/runs", cta: "Go to Runs →" },
    { label: "Review the AI trace", href: "/runs", cta: "Open a run →" },
  ]
  return (
    <div
      className="card"
      style={{ padding: "32px 36px", maxWidth: 480, margin: "32px auto 0" }}
    >
      <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>Get started with Conduct</div>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 22 }}>
        No workflows yet. Follow these steps to automate your first engineering task.
      </div>
      <ol style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 16 }}>
        {steps.map((s, i) => (
          <li key={i} style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <span
              style={{
                width: 24,
                height: 24,
                borderRadius: "50%",
                background: "var(--surface-2)",
                color: "var(--text-muted)",
                fontSize: 11,
                fontWeight: 700,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              {i + 1}
            </span>
            <div style={{ flex: 1, fontSize: 13, color: "var(--text)" }}>{s.label}</div>
            {/* #11: Link instead of bare <a> */}
            <Link
              href={s.href}
              style={{
                fontSize: 12,
                color: "var(--accent-text)",
                fontWeight: 600,
                textDecoration: "none",
                flexShrink: 0,
              }}
            >
              {s.cta}
            </Link>
          </li>
        ))}
      </ol>
    </div>
  )
}
