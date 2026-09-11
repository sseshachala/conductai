export const DEFAULT_SUGGESTIONS = [
  "Who was blocked today?",
  "Cost by AI tool this month",
  "How many events today?",
  "Show recent blocks",
]

// #C2 — per-page opener chips. First matching regex wins. Empty match falls
// through to /glens/opener data-grounded chips → DEFAULT_SUGGESTIONS.
export const PAGE_SUGGESTIONS: Array<{ match: RegExp; chips: string[] }> = [
  { match: /^\/runs\/[^/]+/,             chips: ["Why did this fail?", "Compare to last run", "Show block trace", "Cost breakdown"] },
  { match: /^\/workflows\/[^/]+\/canvas/, chips: ["Explain this workflow", "Recent runs", "Which blocks fail most?"] },
  { match: /^\/workflows\/[^/]+/,        chips: ["Explain this workflow", "Recent failures", "Who runs this most?"] },
  { match: /^\/workflows\/?$/,           chips: ["Which workflows failed today?", "Most-run workflows", "Longest-running workflows"] },
  { match: /^\/theguard\/policies/,      chips: ["Which rules block the most?", "Show rules with no hits", "Rules changed this week"] },
  { match: /^\/theguard\/spend/,         chips: ["Top spenders this month", "Budgets near limit", "Cost by AI tool"] },
  { match: /^\/theguard\/discovery/,     chips: ["Unguarded agents", "Coverage by framework", "High-risk agents"] },
  { match: /^\/compliance/,              chips: ["Overall compliance grade", "Which frameworks are we missing?", "ASI control status"] },
  { match: /^\/logs\/guard/,             chips: ["Show blocks today", "Warnings by tool", "Events by user"] },
  { match: /^\/marketplace/,             chips: ["Recommend packs for us", "What's installed?", "Newest packs"] },
]

export const SKILL_LABELS: Record<string, string> = {
  report:       "Lens ·Report",
  analytics:    "Lens ·Analytics",
  extract:      "Lens ·Extract",
  memory:       "Lens ·Memory",
  session:      "Lens ·Session",
  rules:        "Lens ·Rules",
  guard_config: "Lens ·Guard Config",
  spend_config: "Lens ·Spend Config",
  discovery:    "Lens ·Discovery",
  compliance:   "Lens ·Compliance",
  governance:   "Lens ·Governance",
}

export const SKILL_APPLY_URL: Record<string, string> = {
  rules:        "/glens/policy/apply",
  guard_config: "/glens/guard_config/apply",
  spend_config: "/glens/spend_config/apply",
}

export function _applyBody(skill: string, action: string, draft: Record<string, unknown>, targetRuleId?: string) {
  if (skill === "rules") return { action, draft, target_rule_id: targetRuleId }
  if (skill === "guard_config") return { draft }
  if (skill === "spend_config") return draft   // SpendConfigApplyRequest fields are top-level
  return { action, draft }
}
