"use client"

import type { Dispatch, SetStateAction } from "react"
import type { CertificationOut, FrameworksOut } from "./types"
import { FRAMEWORK_LABEL, Skeleton } from "./ui"

// Framework matrix
export function FrameworkMatrix({
  frameworks, activeFramework, setActiveFramework, certMap,
}: {
  frameworks: FrameworksOut | null
  activeFramework: string | null
  setActiveFramework: Dispatch<SetStateAction<string | null>>
  certMap: Record<string, CertificationOut>
}) {
  return (
        <section style={{
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: 18,
          background: "var(--surface-1)",
          marginBottom: 20,
        }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)" }}>
              Framework coverage
            </div>
            {frameworks && (
              <div style={{ fontSize: 11, color: "var(--text-3)" }}>
                {frameworks.rules_with_framework} of {frameworks.total_rules} rules tagged
              </div>
            )}
          </div>

          {!frameworks ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {[120, 145, 100, 130, 110].map((w, i) => (
                <Skeleton key={i} height={56} width={w} radius={8} />
              ))}
            </div>
          ) : (frameworks.installed.length === 0 && frameworks.bonus.length === 0) ? (
            <div style={{ fontSize: 13, color: "var(--text-3)" }}>
              No frameworks covered yet. Install a compliance pack from the registry to start.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              {/* Tier 1 — frameworks with a dedicated installed pack */}
              {frameworks.installed.length > 0 && (
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 8 }}>
                    Installed frameworks
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {frameworks.installed.map(fw => {
                      const isActive = fw.framework === activeFramework
                      const packCert = fw.packs.map(p => certMap[p]).find(Boolean)
                      const certLabel = packCert
                        ? `certified ${Math.floor((Date.now() - new Date(packCert.certified_at).getTime()) / 86_400_000)}d ago`
                        : null
                      return (
                        <button
                          key={fw.framework}
                          onClick={() => setActiveFramework(fw.framework)}
                          style={{
                            padding: "10px 14px",
                            borderRadius: 8,
                            border: `1px solid ${isActive ? "var(--accent-text)" : "var(--border)"}`,
                            background: isActive ? "var(--accent-weak)" : "var(--surface-2)",
                            color: isActive ? "var(--accent-text)" : "var(--text-1)",
                            cursor: "pointer",
                            fontSize: 13,
                            fontWeight: isActive ? 600 : 500,
                            textAlign: "left",
                          }}
                        >
                          {FRAMEWORK_LABEL[fw.framework] ?? fw.framework}
                          <span style={{ marginLeft: 8, fontSize: 11, color: isActive ? "var(--accent-text)" : "var(--text-3)" }}>
                            {fw.rules_count} {fw.rules_count === 1 ? "rule" : "rules"}
                          </span>
                          {certLabel && (
                            <span style={{ display: "block", fontSize: 10, color: "var(--ok, #16a34a)", marginTop: 2 }}>
                              ✓ {certLabel}
                            </span>
                          )}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Tier 2 — bonus / cross-coverage from installed packs */}
              {frameworks.bonus.length > 0 && (
                <div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
                    <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                      Bonus coverage
                    </span>
                    <span style={{ fontSize: 11, color: "var(--text-3)" }}>
                      cross-tagged rules from your installed packs
                    </span>
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {frameworks.bonus.map(fw => {
                      const isActive = fw.framework === activeFramework
                      return (
                        <button
                          key={fw.framework}
                          onClick={() => setActiveFramework(fw.framework)}
                          style={{
                            padding: "10px 14px",
                            borderRadius: 8,
                            border: `1px dashed ${isActive ? "var(--accent-text)" : "var(--border)"}`,
                            background: isActive ? "var(--accent-weak)" : "var(--surface-1)",
                            color: isActive ? "var(--accent-text)" : "var(--text-2)",
                            cursor: "pointer",
                            fontSize: 13,
                            fontWeight: isActive ? 600 : 500,
                          }}
                        >
                          {FRAMEWORK_LABEL[fw.framework] ?? fw.framework}
                          <span style={{ marginLeft: 8, fontSize: 11, color: isActive ? "var(--accent-text)" : "var(--text-3)" }}>
                            {fw.rules_count} {fw.rules_count === 1 ? "rule" : "rules"}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </section>
  )
}
