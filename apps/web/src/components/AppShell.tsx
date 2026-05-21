"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import AuthButton from "@/components/AuthButton"

const NAV = [
  { href: "/workflows", label: "Agents",   icon: "⚡" },
  { href: "/runs",      label: "Runs",     icon: "▶" },
  { href: "/settings",  label: "Settings", icon: "⚙" },
]

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  return (
    <div className="flex h-screen bg-stone-50">
      <aside className="w-44 shrink-0 bg-white border-r border-stone-200 flex flex-col">
        {/* Logo */}
        <div className="px-4 py-5 border-b border-stone-100">
          <Link href="/workflows" className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-stone-900 flex items-center justify-center">
              <span className="text-white text-xs">⚡</span>
            </div>
            <span className="font-bold text-stone-900 text-sm tracking-tight">Delegator</span>
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
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  active
                    ? "bg-stone-100 text-stone-900"
                    : "text-stone-500 hover:text-stone-800 hover:bg-stone-50"
                }`}
              >
                <span className="text-base leading-none">{item.icon}</span>
                {item.label}
              </Link>
            )
          })}
        </nav>
        {/* User */}
        <div className="px-3 py-3 border-t border-stone-100">
          <AuthButton afterSignOutUrl="/sign-in" dropUp />
        </div>
      </aside>
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  )
}
