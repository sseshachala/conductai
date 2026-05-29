// Benchmark edition metadata.
// Add a new entry here each quarter and update CURRENT_EDITION_SLUG.
// The leaderboard data itself is live from the API; only editorial content is static.

export interface EditionFinding {
  headline: string
  detail: string
}

export interface BenchmarkEdition {
  slug: string           // URL slug — matches /benchmark/[edition]
  label: string          // "Edition 001"
  period: string         // "Q2 2026"
  publishedAt: string    // ISO date string
  totalPlaybooks: number
  modelLabel: string     // describes the scoring model/method
  findings: EditionFinding[]
  prevEditionSlug?: string
  nextEditionSlug?: string
  /** Slug used by the API baseline endpoint, e.g. "edition-001".
   *  When present the benchmark page fetches frozen scores from
   *  GET /eval/benchmark/editions/{apiEditionSlug} instead of live eval. */
  apiEditionSlug?: string
}

export const EDITIONS: BenchmarkEdition[] = [
  {
    slug: "2026-q2",
    label: "Edition 001",
    period: "Q2 2026",
    publishedAt: "2026-06-01",
    totalPlaybooks: 19,
    modelLabel: "Claude · structural scoring",
    apiEditionSlug: "edition-001",
    findings: [
      {
        headline: "Security and incident playbooks lead the leaderboard",
        detail:
          "Playbooks with well-defined trigger wiring, complete parameter sets, and explicit output blocks consistently reach A grades. Security Scanner, Incident Responder, and Postmortem Drafter exemplify this pattern — each earns full marks on the structural checks that most reliably separate A from B.",
      },
      {
        headline: "Quality criteria are the primary differentiator between B and C",
        detail:
          "Raw structural scores are tightly clustered across the 19 playbooks. The gap between a B and a C grade is almost always in the quality layer: description completeness, output block clarity, and parameter documentation. These are low-effort, high-leverage improvements for any playbook sitting in the C range.",
      },
      {
        headline: "Failing criteria concentrate in two areas",
        detail:
          "Across all 19 playbooks, missing required parameters and incomplete output block definitions account for the majority of failing criteria. Teams maintaining community playbooks should audit these two areas first when trying to improve a grade.",
      },
    ],
  },
]

export const CURRENT_EDITION_SLUG = "2026-q2"

export function getEdition(slug: string): BenchmarkEdition | undefined {
  return EDITIONS.find(e => e.slug === slug)
}

// Canonical display names — keep in sync with marketplace FRIENDLY_NAMES.
// Slugs not found here fall back to title-casing the slug.
export const PLAYBOOK_NAMES: Record<string, string> = {
  ai_ready:                 "AI Ready",
  autopilot:                "Autopilot",
  autopilot_quick:          "Autopilot Quick",
  autopilot_full:           "Autopilot Full",
  autopilot_approved:       "Autopilot + Approval",
  pr_reviewer:              "PR Reviewer",
  issue_triage:             "Issue Triage",
  release_notes:            "Release Notes",
  ci_notify:                "CI Failure Alert",
  incident_responder:       "Incident Responder",
  dependency_updater:       "Dependency Updater",
  copilot_reviewer:         "Copilot / AI PR Reviewer",
  security_scanner:         "Security Scanner",
  security_patch_updater:   "Security Patch Updater",
  flaky_test_detective:     "Flaky Test Detective",
  release_readiness:        "Release Readiness Reviewer",
  postmortem_drafter:       "Postmortem Drafter",
  docs_drift_detector:      "Docs Drift Detector",
  terraform_reviewer:       "Terraform Plan Reviewer",
  smoke_test:               "Smoke Test",
}

export function playbookDisplayName(slug: string): string {
  return (
    PLAYBOOK_NAMES[slug] ??
    slug.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())
  )
}
