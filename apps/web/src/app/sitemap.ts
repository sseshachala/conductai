import type { MetadataRoute } from "next"

const SITE = "https://conductai.ai"

const staticRoutes: Array<{ path: string; priority: number; changeFrequency: "daily" | "weekly" | "monthly" }> = [
  { path: "/", priority: 1.0, changeFrequency: "weekly" },
  { path: "/guard-landing", priority: 0.9, changeFrequency: "weekly" },
  { path: "/solutions", priority: 0.8, changeFrequency: "monthly" },
  { path: "/playbooks", priority: 0.8, changeFrequency: "weekly" },
  { path: "/marketplace", priority: 0.7, changeFrequency: "weekly" },
  { path: "/sdd", priority: 0.7, changeFrequency: "monthly" },
  { path: "/compare", priority: 0.7, changeFrequency: "monthly" },
  { path: "/benchmark", priority: 0.6, changeFrequency: "monthly" },
  { path: "/eval", priority: 0.6, changeFrequency: "monthly" },
  { path: "/partners", priority: 0.5, changeFrequency: "monthly" },
  { path: "/about", priority: 0.5, changeFrequency: "monthly" },
  { path: "/docs", priority: 0.7, changeFrequency: "weekly" },
  { path: "/tools", priority: 0.6, changeFrequency: "monthly" },
  { path: "/tools/conduct-cli", priority: 0.6, changeFrequency: "monthly" },
  { path: "/tools/agent-booster", priority: 0.6, changeFrequency: "monthly" },
  { path: "/token-guardrails", priority: 0.5, changeFrequency: "monthly" },
  { path: "/blog", priority: 0.8, changeFrequency: "weekly" },
  { path: "/blog/rtk-how-we-cut-93-percent-of-cli-tokens", priority: 0.6, changeFrequency: "monthly" },
  { path: "/blog/stop-paying-opus-prices-for-haiku-work", priority: 0.6, changeFrequency: "monthly" },
  { path: "/blog/which-ai-model-for-which-task", priority: 0.6, changeFrequency: "monthly" },
  { path: "/blog/why-ai-reads-your-whole-file-when-it-only-needs-three-functions", priority: 0.6, changeFrequency: "monthly" },
  { path: "/blog/conduct-is-open-today", priority: 0.6, changeFrequency: "monthly" },
  { path: "/blog/launch-hero", priority: 0.5, changeFrequency: "monthly" },
  { path: "/privacy", priority: 0.3, changeFrequency: "monthly" },
  { path: "/terms", priority: 0.3, changeFrequency: "monthly" },
]

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date()
  return staticRoutes.map(({ path, priority, changeFrequency }) => ({
    url: `${SITE}${path}`,
    lastModified: now,
    changeFrequency,
    priority,
  }))
}
