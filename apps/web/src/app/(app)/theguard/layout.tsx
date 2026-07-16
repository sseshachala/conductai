"use client"

import { GLensPanel } from "@/components/glens/GLensPanel"

export default function GuardLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
      <GLensPanel />
    </>
  )
}
