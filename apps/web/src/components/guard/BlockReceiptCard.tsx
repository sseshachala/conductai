"use client"

import Link from "next/link"
import type { BlockReceipt } from "@/lib/api/guard"
import { DecisionBadge } from "./DecisionBadge"

/**
 * Receipt card for a single Guard block (#1712 Track 1 quick win 2/3).
 *
 * Renders the audit-row fields the SDK error message linked to, plus four
 * pre-canned prompts that seed a Lens conversation via ?q= — the user
 * clicks, lands in Lens with the question already typed, presses enter.
 *
 * `mode="public"` swaps the "Ask Lens →" CTAs for a sign-up funnel so
 * anonymous trial signup users (Cursor / one-liner install) end up
 * activated instead of hitting a login wall.
 */
export function BlockReceiptCard({
  receipt,
  mode = "workspace",
}: {
  receipt: BlockReceipt
  mode?: "workspace" | "public"
}) {
  const ts = receipt.ts ? new Date(receipt.ts) : null
  const promptsForReceipt: Array<{ label: string; q: string }> = [
    {
      label: "Why did this block?",
      q: `Explain why the rule ${receipt.rule_id ?? "(unknown)"} blocked this prompt (block ${receipt.receipt_id}).`,
    },
    {
      label: "Show me the rule",
      q: `Show me the full policy for rule ${receipt.rule_id ?? "(unknown)"} — matcher, message, and current enforcement level.`,
    },
    {
      label: "What would have allowed it?",
      q: `What change to the prompt or the policy would have allowed block ${receipt.receipt_id}? Suggest both a caller-side fix and a policy exception.`,
    },
    {
      label: "Draft an exception",
      q: `Draft a scoped exception for rule ${receipt.rule_id ?? "(unknown)"} that covers block ${receipt.receipt_id} only — YAML I can paste.`,
    },
  ]

  return (
    <div style={{ maxWidth: 760, margin: "0 auto", padding: "24px 16px" }}>
      <div
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
          borderRadius: 12,
          padding: 20,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <DecisionBadge decision={receipt.decision} />
          <span style={{ fontFamily: "var(--mono, monospace)", fontSize: 12, color: "var(--muted)" }}>
            {receipt.receipt_id}
          </span>
          {ts && (
            <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)" }}>
              {ts.toLocaleString()}
            </span>
          )}
        </div>

        <h1 style={{ fontSize: 20, margin: "8px 0 4px", lineHeight: 1.3 }}>
          {receipt.rule_message || receipt.rule_id || "Guard block"}
        </h1>
        {receipt.rule_id && (
          <div style={{ fontFamily: "var(--mono, monospace)", fontSize: 12, color: "var(--muted)", marginBottom: 12 }}>
            rule · {receipt.rule_id}
          </div>
        )}

        <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 12px", fontSize: 13, margin: "16px 0" }}>
          {receipt.provider && (<>
            <dt style={{ color: "var(--muted)" }}>Provider</dt>
            <dd style={{ margin: 0 }}>{receipt.provider}</dd>
          </>)}
          {receipt.model && (<>
            <dt style={{ color: "var(--muted)" }}>Model</dt>
            <dd style={{ margin: 0, fontFamily: "var(--mono, monospace)" }}>{receipt.model}</dd>
          </>)}
          {receipt.ai_tool && (<>
            <dt style={{ color: "var(--muted)" }}>Caller</dt>
            <dd style={{ margin: 0 }}>{receipt.ai_tool}</dd>
          </>)}
          {typeof receipt.defense_score === "number" && (<>
            <dt style={{ color: "var(--muted)" }}>Defense score</dt>
            <dd style={{ margin: 0 }}>{receipt.defense_score}</dd>
          </>)}
        </dl>

        {receipt.input_summary && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--muted)", marginBottom: 4 }}>
              Prompt summary
            </div>
            <pre
              style={{
                margin: 0, padding: 12, borderRadius: 8,
                background: "var(--input-bg, #0b0c10)",
                fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-word",
              }}
            >
              {receipt.input_summary}
            </pre>
          </div>
        )}

        {receipt.evaluated_rules && receipt.evaluated_rules.length > 1 && (
          <details style={{ fontSize: 13, marginBottom: 12 }}>
            <summary style={{ cursor: "pointer", color: "var(--muted)" }}>
              {receipt.evaluated_rules.length} rules evaluated
            </summary>
            <ul style={{ margin: "8px 0 0 18px" }}>
              {receipt.evaluated_rules.map((r, i) => (
                <li key={i} style={{ fontFamily: "var(--mono, monospace)", fontSize: 12 }}>
                  {String((r as { id?: string; rule_id?: string }).id ?? (r as { rule_id?: string }).rule_id ?? JSON.stringify(r))}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>

      <div style={{ marginTop: 20 }}>
        <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6, color: "var(--muted)", marginBottom: 8 }}>
          Ask Lens about this block
        </div>
        <div style={{ display: "grid", gap: 8 }}>
          {promptsForReceipt.map((p) => (
            <ReceiptCta key={p.label} label={p.label} q={p.q} mode={mode} />
          ))}
        </div>
      </div>

      {receipt.conductai_run_id && mode === "workspace" && (
        <div style={{ marginTop: 16, fontSize: 12 }}>
          <Link href={`/runs/${receipt.conductai_run_id}`} style={{ color: "var(--accent-text)" }}>
            View run trace →
          </Link>
        </div>
      )}
    </div>
  )
}

function ReceiptCta({ label, q, mode }: { label: string; q: string; mode: "workspace" | "public" }) {
  const encoded = encodeURIComponent(q)
  const href =
    mode === "workspace"
      ? `/lens?q=${encoded}`
      : `/sign-up?next=${encodeURIComponent(`/lens?q=${encoded}`)}`
  return (
    <Link
      href={href}
      style={{
        display: "block",
        padding: "10px 12px",
        borderRadius: 8,
        border: "1px solid var(--border)",
        background: "var(--card)",
        color: "inherit",
        textDecoration: "none",
        fontSize: 14,
      }}
    >
      {label} →
    </Link>
  )
}
