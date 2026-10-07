import type { FrameworksOut, KpisOut } from "./types"
import { fmtUsd } from "./ui"

// Hero status banner — dominates the screenshot
export function HeroBanner({ kpis, frameworks }: { kpis: KpisOut | null; frameworks: FrameworksOut | null }) {
          const installedCount = frameworks?.installed.length ?? 0
          const bonusCount = frameworks?.bonus.length ?? 0
          const totalFrameworks = installedCount + bonusCount
          const totalRules = (frameworks?.installed ?? []).reduce((s, f) => s + f.rules_count, 0)
            + (frameworks?.bonus ?? []).reduce((s, f) => s + f.rules_count, 0)
          const blocksMtd = kpis?.blocks_mtd ?? 0
          const riskAvoidedUsd = kpis?.risk_avoided_usd_mtd ?? 0

          let tone: "good" | "warn" | "info" = "good"
          let title = "All systems compliant"
          let sub = `Covers ${totalFrameworks} framework${totalFrameworks === 1 ? "" : "s"}`
          let action: { label: string; href: string } | null = null

          if (totalFrameworks === 0) {
            tone = "info"
            title = "No compliance frameworks active"
            sub = "Install a pack from the registry to start coverage"
            action = { label: "Browse Registry →", href: "/packs" }
          } else if (blocksMtd > 0) {
            tone = "warn"
            title = `${blocksMtd.toLocaleString()} risk event${blocksMtd === 1 ? "" : "s"} intercepted this month`
            sub = `~${fmtUsd(riskAvoidedUsd)} risk avoided · covers ${totalFrameworks} framework${totalFrameworks === 1 ? "" : "s"}`
            action = { label: "View Activity →", href: "/theguard/activity?decision=blocked" }
          }

          const colors = {
            good: { bg: "var(--ok-bg)",  border: "var(--ok-bd)",  text: "var(--ok)",  iconBg: "var(--ok)" },
            warn: { bg: "var(--accent-weak)", border: "var(--accent)", text: "var(--accent)", iconBg: "var(--accent)" },
            info: { bg: "var(--info-bg)", border: "var(--info-bd)", text: "var(--info)", iconBg: "var(--info)" },
          }[tone]

          return (
            <section style={{
              display: "flex",
              alignItems: "center",
              gap: 16,
              padding: "20px 22px",
              borderRadius: 12,
              border: `1.5px solid ${colors.border}`,
              background: colors.bg,
              marginBottom: 20,
            }}>
              <span style={{
                width: 44,
                height: 44,
                borderRadius: 10,
                background: colors.iconBg,
                color: "#fff",
                display: "grid",
                placeItems: "center",
                flexShrink: 0,
              }}>
                {tone === "good" ? (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : tone === "warn" ? (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                    <polyline points="9 12 11 14 15 10" />
                  </svg>
                ) : (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                )}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 19, fontWeight: 700, color: colors.text, letterSpacing: "-0.01em", lineHeight: 1.2 }}>
                  {title}
                </div>
                <div style={{ fontSize: 13, color: "var(--text-2)", marginTop: 4 }}>
                  {sub}
                </div>
              </div>
              {action && (
                <a href={action.href} style={{
                  fontSize: 13,
                  fontWeight: 600,
                  padding: "8px 14px",
                  borderRadius: 8,
                  border: `1px solid ${colors.border}`,
                  background: "var(--surface)",
                  color: colors.text,
                  textDecoration: "none",
                  whiteSpace: "nowrap",
                  flexShrink: 0,
                }}>
                  {action.label}
                </a>
              )}
            </section>
          )
}
