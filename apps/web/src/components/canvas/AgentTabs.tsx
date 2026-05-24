"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

interface Props {
  workflowId: string
  workflowName?: string
}

export default function AgentTabs({ workflowId, workflowName }: Props) {
  const pathname = usePathname()

  const tabs = [
    { label: "Canvas",   href: `/workflows/${workflowId}` },
    { label: "Runs",     href: `/workflows/${workflowId}/runs` },
    { label: "Settings", href: `/workflows/${workflowId}/settings` },
  ]

  return (
    <div className="flex items-center border-b border-stone-200 bg-white px-4 shrink-0" style={{ height: 44 }}>
      {workflowName && (
        <span className="text-sm font-semibold text-stone-700 mr-4 truncate max-w-[160px]">{workflowName}</span>
      )}
      <div className="flex gap-1">
        {tabs.map(tab => {
          const active = tab.label === "Canvas"
            ? pathname === tab.href
            : pathname.startsWith(tab.href)
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`px-3 py-2 text-sm font-medium rounded-t transition-colors border-b-2 -mb-px ${
                active
                  ? "border-stone-900 text-stone-900"
                  : "border-transparent text-stone-400 hover:text-stone-700 hover:border-stone-300"
              }`}
            >
              {tab.label}
            </Link>
          )
        })}
      </div>
    </div>
  )
}
