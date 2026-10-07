"use client"

import type { Dispatch, SetStateAction } from "react"
import Link from "next/link"
import { ActivityRow, ActivityHeader } from "@/components/guard/ActivityRow"
import type { ChainVerifyOut, RecentEvent } from "./types"
import { Skeleton } from "./ui"

// Recent activity feed — top 6, same row component as /guard/activity
export function RecentActivitySection({
  eventFilter, setEventFilter, recentLoaded, recentEvents,
}: {
  eventFilter: "" | "blocked" | "warned"
  setEventFilter: Dispatch<SetStateAction<"" | "blocked" | "warned">>
  recentLoaded: boolean
  recentEvents: RecentEvent[]
}) {
  return (
        <section style={{
          marginTop: 20,
          border: "1px solid var(--border)",
          borderRadius: 8,
          background: "var(--surface-1)",
          overflow: "hidden",
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: "1px solid var(--border)", gap: 12, flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)" }}>Recent activity</div>
              <div style={{ display: "flex", gap: 4 }}>
                {([
                  { key: "", label: "All" },
                  { key: "blocked", label: "Blocked" },
                  { key: "warned", label: "Warned" },
                ] as const).map(chip => {
                  const active = eventFilter === chip.key
                  return (
                    <button
                      key={chip.key || "all"}
                      onClick={() => setEventFilter(chip.key as typeof eventFilter)}
                      style={{
                        fontSize: 11,
                        fontWeight: active ? 600 : 500,
                        padding: "3px 10px",
                        borderRadius: 12,
                        border: `1px solid ${active ? "var(--accent-text)" : "var(--border)"}`,
                        background: active ? "var(--accent-weak)" : "transparent",
                        color: active ? "var(--accent-text)" : "var(--text-2)",
                        cursor: "pointer",
                      }}
                    >
                      {chip.label}
                    </button>
                  )
                })}
              </div>
            </div>
            <Link
              href={eventFilter ? `/theguard/activity?decision=${eventFilter}` : "/theguard/activity"}
              style={{ fontSize: 11, color: "var(--accent-text)" }}
            >
              View all →
            </Link>
          </div>
          {!recentLoaded ? (
            <div style={{ padding: "8px 18px 14px" }}>
              {[0, 1, 2, 3, 4, 5].map(i => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: i < 5 ? "1px solid var(--border)" : "none" }}>
                  <Skeleton height={12} width={70} />
                  <Skeleton height={12} width={90} />
                  <Skeleton height={12} width={120} />
                  <Skeleton height={12} width="40%" />
                </div>
              ))}
            </div>
          ) : recentEvents.length === 0 ? (
            <div style={{ padding: "14px 18px", fontSize: 12, color: "var(--text-3)" }}>
              No events yet. Activity will appear here as your team uses AI tools.
            </div>
          ) : (
            <>
              <ActivityHeader />
              {recentEvents.slice(0, 6).map((ev, i, arr) => (
                <ActivityRow key={ev.id} ev={ev} isLast={i === arr.length - 1} />
              ))}
            </>
          )}
        </section>
  )
}

// Audit log integrity
export function AuditIntegritySection({
  chain, chainLoading, verifyChain,
}: {
  chain: ChainVerifyOut | null
  chainLoading: boolean
  verifyChain: () => Promise<void>
}) {
  return (
        <section style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 18, background: "var(--surface-1)", marginBottom: 20 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-1)", marginBottom: 4 }}>Audit log integrity</div>
              {chain ? (
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: chain.valid ? "var(--ok)" : "var(--err)", display: "inline-block", flexShrink: 0 }} />
                  <span style={{ fontSize: 13, fontWeight: 600, color: chain.valid ? "var(--ok)" : "var(--err)" }}>
                    {chain.valid ? "Chain verified" : "Chain broken"}
                  </span>
                  <span style={{ fontSize: 12, color: "var(--text-3)" }}>
                    {chain.events_checked.toLocaleString()} events verified
                    {chain.first_event && chain.last_event && (
                      <> · {new Date(chain.first_event).toLocaleDateString()} – {new Date(chain.last_event).toLocaleDateString()}</>
                    )}
                  </span>
                  {!chain.valid && chain.broken_at && (
                    <span style={{ fontSize: 12, color: "var(--err)" }}>First broken link: {new Date(chain.broken_at).toLocaleString()}</span>
                  )}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: "var(--text-3)" }}>
                  SHA-256 chain links every audit event to the previous one — custody proof at the execution boundary. Click to confirm the log has not been altered and that every Governance Authorization Artifact is intact.
                </div>
              )}
            </div>
            <button onClick={verifyChain} disabled={chainLoading} className="btn btn-sm" style={{ flexShrink: 0 }}>
              {chainLoading ? "Verifying…" : chain ? "Re-verify" : "Verify integrity"}
            </button>
          </div>
        </section>
  )
}
