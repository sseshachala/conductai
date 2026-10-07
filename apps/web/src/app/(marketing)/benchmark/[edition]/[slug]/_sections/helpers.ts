// ─── Data shapes ─────────────────────────────────────────────────────────────

export interface BaselinePlaybook {
  slug: string
  grade: string
  pct: number
  structural_score: number
  quality_score: number
  total_score: number
  total_max: number
}

export interface EditionManifest {
  edition: string
  published_at: string
  model: string
  summary: { total_playbooks: number; average_pct: number }
  playbooks: BaselinePlaybook[]
}

interface ScenarioItem {
  id: string
  label: string
  tags: string[]
  expected_outcome_type: string
  expected_artifact_keys: string[]
  expected_should_review: boolean | null
  expected_should_scan: boolean | null
}

export interface ScenarioSet {
  slug: string
  description: string
  scenario_count: number
  positive_count: number
  negative_count: number
  scenarios: ScenarioItem[]
}

export interface CriterionResult {
  name: string
  passed: boolean
  points_earned: number
  points_possible: number
  detail: string
}

export interface PlaybookLiveDetail {
  slug: string
  grade: string
  pct: number
  total_score: number
  total_max: number
  structural_score: number
  structural_max: number
  quality_score: number
  quality_max: number
  total_criteria?: number
  criteria: CriterionResult[]
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const GRADE_BG: Record<string, string> = {
  A: "var(--ok-bg)",
  B: "#eff6ff",
  C: "var(--warn-bg)",
  D: "#fff7ed",
  F: "var(--err-bg)",
}

const GRADE_C: Record<string, string> = {
  A: "var(--ok)",
  B: "#1d4ed8",
  C: "var(--warn)",
  D: "#c2410c",
  F: "var(--err)",
}

const GRADE_BORDER: Record<string, string> = {
  A: "#6ee7b7",
  B: "#bfdbfe",
  C: "#fde68a",
  D: "#fed7aa",
  F: "#fecaca",
}

const GRADE_BAR: Record<string, string> = {
  A: "var(--ok)",
  B: "#60a5fa",
  C: "var(--warn)",
  D: "#fb923c",
  F: "var(--err)",
}

export function gradeStyles(grade: string) {
  return {
    bg: GRADE_BG[grade] ?? "var(--surface-3)",
    text: GRADE_C[grade] ?? "var(--text-3)",
    bar: GRADE_BAR[grade] ?? "var(--border)",
    border: GRADE_BORDER[grade] ?? "var(--border)",
  }
}

export function fmt(iso: string) {
  try { return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }) }
  catch { return iso }
}
