// Secure module IA — mirrors the Guard six-section pattern.
// Only two sections today; grows without changing shell code.

export type SecureSectionId = "overview" | "findings"

export interface SecureSection {
  id: SecureSectionId
  label: string
  href: string
  activePrefixes: readonly string[]
}

export const SECURE_SECTIONS: readonly SecureSection[] = [
  { id: "overview", label: "Overview", href: "/secure",          activePrefixes: ["/secure"] },
  { id: "findings", label: "Findings", href: "/secure/activity", activePrefixes: ["/secure/activity"] },
]

export function activeSecureSection(pathname: string): SecureSectionId | null {
  if (pathname === "/secure") return "overview"
  for (const s of SECURE_SECTIONS) {
    if (s.id === "overview") continue
    if (s.activePrefixes.some(p => pathname === p || pathname.startsWith(p + "/"))) {
      return s.id
    }
  }
  return null
}
