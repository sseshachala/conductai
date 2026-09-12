"use client"

import { useEffect, useState } from "react"
import { useAuth } from "@clerk/nextjs"
import { useTokenGuardrails, patchTokenGuardrails } from "@/hooks/useTokenGuardrails"
import { API } from "@/lib/api/client"
import { GuardToggle } from "@/features/guard/GuardToggle"

export default function CostPerformancePanel({
  workspaceId,
  isAdmin,
}: {
  workspaceId: string | null
  isAdmin: boolean
}) {
  const { getToken } = useAuth()
  const { guardrails: tokenGuardrails, refresh: refreshGuardrails } = useTokenGuardrails(workspaceId)
  const [guardrailState, setGuardrailState] = useState({ prompt_caching: true, model_routing: true, prompt_splitting: true })
  const [guardrailSaved, setGuardrailSaved] = useState(false)

  useEffect(() => {
    if (!tokenGuardrails) return
    setGuardrailState({
      prompt_caching:   tokenGuardrails.prompt_caching,
      model_routing:    tokenGuardrails.model_routing,
      prompt_splitting: tokenGuardrails.prompt_splitting,
    })
  }, [tokenGuardrails])

  async function handleGuardrailToggle(field: "prompt_caching" | "model_routing" | "prompt_splitting", value: boolean) {
    if (!workspaceId) return
    setGuardrailState(s => ({ ...s, [field]: value }))
    try {
      const token = await getToken()
      await patchTokenGuardrails(workspaceId, token ?? "", API, { [field]: value })
      refreshGuardrails()
      setGuardrailSaved(true)
      setTimeout(() => setGuardrailSaved(false), 2000)
    } catch {
      setGuardrailState(s => ({ ...s, [field]: !value }))
    }
  }

  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <div style={{ padding: "15px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ width: 30, height: 30, borderRadius: 8, background: "var(--accent)", color: "#fff", display: "grid", placeItems: "center", flexShrink: 0 }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
          </svg>
        </span>
        <div style={{ fontWeight: 650, fontSize: 14.5 }}>Token guardrails</div>
        <a href="/token-guardrails" target="_blank" style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-3)", textDecoration: "none" }}>
          Learn more →
        </a>
        {guardrailSaved && (
          <span style={{ fontSize: 12, color: "var(--ok)", fontWeight: 600 }}>Saved</span>
        )}
      </div>

      {/* Detected (auto) status — shown first */}
      <div style={{ padding: "4px 20px 8px" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", padding: "10px 0 4px" }}>Detected</div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>Passive detection from installed tools and active policies. Full enforcement coming in a future release.</div>
        {tokenGuardrails === null ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[...Array(4)].map((_, i) => (
              <div key={i} style={{ height: 36, background: "var(--surface-2)", borderRadius: 6, opacity: 0.6 }} />
            ))}
          </div>
        ) : (
          ([
            { key: "deterministic_offload", label: "Deterministic offload", desc: "Detects whether the warn-deterministic-compute policy is active. In-sandbox offloading coming soon." },
            { key: "output_compression",    label: "Output compression",    desc: "Detects RTK install. RTK compresses terminal output today — sandbox run compression coming soon." },
            { key: "structured_retrieval",  label: "Structured retrieval",  desc: "Detects Agent Booster install. Smart file reads inside sandbox runs coming soon." },
            { key: "metrics_budgets",       label: "Metrics & budgets",     desc: "Spend budgets enforced on proxy traffic. Workflow run budget enforcement coming soon." },
          ] as const).map((item, i) => {
            const detected = tokenGuardrails[item.key] ?? false
            return (
              <div key={item.key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "11px 0", borderTop: i > 0 ? "1px solid var(--border)" : undefined }}>
                <div>
                  <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--text)" }}>{item.label}</div>
                  <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>{item.desc}</div>
                </div>
                <span style={{ fontSize: 11, fontWeight: 600, color: detected ? "var(--ok)" : "var(--text-3)", flexShrink: 0, marginLeft: 12 }}>
                  {detected ? "Detected" : "Not detected"}
                </span>
              </div>
            )
          })
        )}
      </div>

      {/* Manual toggles — shown below Detected */}
      <div style={{ padding: "4px 20px 16px", borderTop: "1px solid var(--border)" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", padding: "10px 0 4px" }}>Toggleable</div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>Workspace-wide controls — flip off to opt the whole team out.</div>
        {([
          { key: "prompt_caching",   label: "Prompt caching",   desc: "System prompts cached on every agent run — repeat calls don't re-pay for the same tokens. Enforced.", pending: false },
          { key: "model_routing",    label: "Model routing",    desc: "Each run routes to the cheapest model tier that can handle the task — Haiku for simple, Opus for complex. Enforced.", pending: false },
          { key: "prompt_splitting", label: "Prompt splitting", desc: "Split large prompts into chunks to stay within context limits. Not yet implemented.", pending: true },
        ] as const).map(item => (
          <div key={item.key} style={{ display: "flex", alignItems: "center", gap: 14, padding: "13px 0", borderTop: "1px solid var(--border)" }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 13.5, display: "flex", alignItems: "center", gap: 8 }}>
                {item.label}
                {item.pending && (
                  <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: ".04em", color: "#92400e", background: "#fef3c7", borderRadius: 4, padding: "1px 5px" }}>PENDING</span>
                )}
              </div>
              <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 2 }}>{item.desc}</div>
            </div>
            <GuardToggle
              on={guardrailState[item.key]}
              onClick={() => handleGuardrailToggle(item.key, !guardrailState[item.key])}
              disabled={!isAdmin || item.pending}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
