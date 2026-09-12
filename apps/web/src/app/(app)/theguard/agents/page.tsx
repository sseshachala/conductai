import { redirect } from "next/navigation"

// Guard IA 1c: Agents section canonical URL. Redirects to the existing
// Agent Identity page until the physical move in Phase 2.
// Preserves any incoming query (e.g. ?tab=tokens) so deep links keep working.
export default async function GuardAgentsPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>
}) {
  const params = (await searchParams) ?? {}
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (typeof v === "string") qs.set(k, v)
    else if (Array.isArray(v) && v[0]) qs.set(k, v[0])
  }
  const suffix = qs.toString()
  redirect(suffix ? `/agent-identity?${suffix}` : "/agent-identity")
}
