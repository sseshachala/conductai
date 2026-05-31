"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

const TABS = [
  { label: "Activity", href: "/guard" },
  { label: "Policies", href: "/guard/policies" },
  { label: "Spend",    href: "/guard/spend" },
  { label: "Audit",   href: "/guard/audit" },
]

export default function GuardNav() {
  const pathname = usePathname()
  return (
    <div className="flex gap-1 border-b border-stone-200">
      {TABS.map(tab => {
        const active = tab.href === "/guard"
          ? pathname === "/guard"
          : pathname.startsWith(tab.href)
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              active
                ? "border-indigo-600 text-indigo-700"
                : "border-transparent text-stone-500 hover:text-stone-800"
            }`}
          >
            {tab.label}
          </Link>
        )
      })}
    </div>
  )
}
