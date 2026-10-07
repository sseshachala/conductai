"use client"

import { useState, useRef, useEffect, type MouseEvent as ReactMouseEvent } from "react"
import { authEnabled } from "@/lib/auth/runtime"
import Link from "next/link"
import { UserRound } from "lucide-react"
import { useRouter } from "next/navigation"
import { useUser, useClerk } from "@/lib/auth/client"
import type { UserRole } from "./types"

// ── UserChip ──────────────────────────────────────────────────────────────────

export function UserChip({ collapsed, userRole, topbar }: { collapsed: boolean; userRole: UserRole; topbar?: boolean }) {
  const clerkEnabled = authEnabled()
  if (!clerkEnabled) return null
  return <UserChipInner collapsed={collapsed} userRole={userRole} topbar={topbar} />
}

function UserChipInner({ collapsed, userRole, topbar }: { collapsed: boolean; userRole: UserRole; topbar?: boolean }) {
  const { user } = useUser()
  const { signOut } = useClerk()
  const router = useRouter()
  const [menuOpen, setMenuOpen] = useState(false)
  const chipRef = useRef<HTMLDivElement>(null)

  const email = user?.primaryEmailAddress?.emailAddress ?? ""
  const firstName = user?.firstName ?? ""
  const lastName = user?.lastName ?? ""
  const initials = firstName && lastName
    ? `${firstName[0]}${lastName[0]}`.toUpperCase()
    : email ? email[0].toUpperCase() : ""
  const fullName = [firstName, lastName].filter(Boolean).join(" ") || email || "User"
  const roleLabel = userRole ?? "member"
  const avatarUrl = user?.imageUrl

  useEffect(() => {
    function handle(e: MouseEvent) {
      if (chipRef.current && !chipRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener("mousedown", handle)
    return () => document.removeEventListener("mousedown", handle)
  }, [])

  return (
    <div ref={chipRef} style={{ position: "relative" }}>
      <button
        onClick={() => setMenuOpen(v => !v)}
        aria-label={`Account menu for ${fullName}`}
        aria-expanded={menuOpen}
        title={fullName}
        style={{
          display: "flex",
          alignItems: "center",
          gap: topbar ? 0 : collapsed ? 0 : 10,
          padding: topbar ? "3px" : "7px 8px",
          borderRadius: topbar ? "50%" : 9,
          background: "transparent",
          border: "none",
          cursor: "pointer",
          width: topbar ? "auto" : "100%",
          textAlign: "left",
        }}
        onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.background = "var(--surface-2)")}
        onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => (e.currentTarget.style.background = "transparent")}
      >
        <div style={{
          width: 28, height: 28, borderRadius: "50%",
          background: "var(--accent)", color: "#fff",
          fontSize: 11, fontWeight: 700, flexShrink: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          overflow: "hidden",
        }}>
          {avatarUrl
            ? <img src={avatarUrl} alt={fullName} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            : initials || <UserRound size={16} aria-hidden="true" />}
        </div>
        {!collapsed && !topbar && (
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {fullName}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{roleLabel}</div>
          </div>
        )}
      </button>

      {menuOpen && (
        <div style={{
          position: "absolute",
          ...(topbar ? { top: "calc(100% + 6px)", right: 0 } : { bottom: "calc(100% + 4px)", left: 0 }),
          width: 200, background: "var(--surface)",
          border: "1px solid var(--border)", borderRadius: 10,
          boxShadow: "var(--shadow-md)", padding: "4px 0", zIndex: 200,
        }}>
          {email && (
            <>
              <div style={{ padding: "8px 12px" }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis" }}>{fullName}</div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis" }}>{email}</div>
              </div>
              <div style={{ borderTop: "1px solid var(--border)", margin: "2px 0" }} />
            </>
          )}
          <Link
            href="/settings"
            onClick={() => setMenuOpen(false)}
            style={{ display: "block", padding: "8px 12px", fontSize: 13, color: "var(--text-2)", textDecoration: "none" }}
            onMouseEnter={(e: ReactMouseEvent<HTMLAnchorElement>) => { e.currentTarget.style.background = "var(--surface-2)"; e.currentTarget.style.color = "var(--text)" }}
            onMouseLeave={(e: ReactMouseEvent<HTMLAnchorElement>) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-2)" }}
          >
            Settings
          </Link>
          <div style={{ borderTop: "1px solid var(--border)", margin: "2px 0" }} />
          <button
            onClick={() => { setMenuOpen(false); signOut(() => router.push("/sign-in")) }}
            style={{
              width: "100%", textAlign: "left", padding: "8px 12px", fontSize: 13,
              color: "var(--text-2)", background: "transparent", border: "none", cursor: "pointer",
            }}
            onMouseEnter={(e: ReactMouseEvent<HTMLElement>) => { (e.currentTarget as HTMLButtonElement).style.background = "var(--surface-2)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text)" }}
            onMouseLeave={(e: ReactMouseEvent<HTMLElement>) => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; (e.currentTarget as HTMLButtonElement).style.color = "var(--text-2)" }}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}
