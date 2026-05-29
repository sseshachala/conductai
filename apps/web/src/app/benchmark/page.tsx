import { redirect } from "next/navigation"
import { CURRENT_EDITION_SLUG } from "@/lib/benchmark-editions"

// Redirect /benchmark → /benchmark/<current-edition>
// Update CURRENT_EDITION_SLUG in lib/benchmark-editions.ts each quarter.
export default function BenchmarkIndexPage() {
  redirect(`/benchmark/${CURRENT_EDITION_SLUG}`)
}
