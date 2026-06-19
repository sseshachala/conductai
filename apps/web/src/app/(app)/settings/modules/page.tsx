"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"

export default function ModulesRedirect() {
  const router = useRouter()
  useEffect(() => { router.replace("/marketplace?tab=modules") }, [router])
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "50vh" }}>
      <div style={{ width: 20, height: 20, border: "2px solid var(--border-2)", borderTopColor: "var(--accent)", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} />
    </div>
  )
}
