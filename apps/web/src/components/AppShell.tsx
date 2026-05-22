"use client"

import { useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import AuthButton from "@/components/AuthButton"

const NAV = [
  { href: "/workflows", label: "Agents",   icon: "⚡" },
  { href: "/runs",      label: "Runs",     icon: "▶" },
  { href: "/settings",  label: "Settings", icon: "⚙" },
]

export default function AppShell({ children, noPadding }: { children: React.ReactNode; noPadding?: boolean }) {
  const pathname = usePathname()
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="flex h-screen bg-stone-50">
      <aside className={`relative shrink-0 bg-white border-r border-stone-200 flex flex-col transition-all duration-200 ${collapsed ? "w-14" : "w-44"}`}>

        {/* Logo */}
        <div className={`px-3 py-4 border-b border-stone-100 flex items-center ${collapsed ? "justify-center" : "gap-2"}`}>
          <Link href="/workflows" className="flex items-center gap-2 min-w-0">
            <div className="w-6 h-6 rounded-md bg-stone-900 flex items-center justify-center shrink-0">
              <span className="text-white text-xs">⚡</span>
            </div>
            {!collapsed && (
              <span className="font-bold text-stone-900 text-sm tracking-tight truncate">Delegator</span>
            )}
          </Link>
        </div>

        {/* Nav items */}
        <nav className="flex-1 px-2 py-3 space-y-0.5">
          {NAV.map(item => {
            const active = pathname.startsWith(item.href)
            return (
              <Link
                key={item.href}
                href={item.href}
                title={collapsed ? item.label : undefined}
                className={`flex items-center gap-2.5 px-2 py-2 rounded-lg text-sm font-medium transition-colors ${
                  collapsed ? "justify-center" : ""
                } ${
                  active
                    ? "bg-stone-100 text-stone-900"
                    : "text-stone-500 hover:text-stone-800 hover:bg-stone-50"
                }`}
              >
                <span className="text-base leading-none shrink-0">{item.icon}</span>
                {!collapsed && item.label}
              </Link>
            )
          })}
        </nav>

        {/* User */}
        <div className={`px-2 py-3 border-t border-stone-100 flex ${collapsed ? "justify-center" : ""}`}>
          <AuthButton afterSignOutUrl="/sign-in" dropUp />
        </div>

        {/* Collapse toggle — sits on the right edge */}
        <button
          onClick={() => setCollapsed(v => !v)}
          className="absolute -right-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-white border border-stone-200 shadow-sm flex items-center justify-center text-stone-400 hover:text-stone-700 transition-colors z-10"
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? "›" : "‹"}
        </button>
      </aside>

      <main className={`flex-1 min-h-0 ${noPadding ? "overflow-hidden flex flex-col" : "overflow-auto"}`}>{children}</main>
    </div>
  )
}
