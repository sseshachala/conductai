// Enforcement settings merged into the Policies page's "Enforcement
// coverage" tab so users configure enforcement mode + see coverage in
// one place. This route stays as a redirect so old bookmarks and the
// palette entry "Guard · Enforcement" (AppShell) still land users on
// the right tab.
import { redirect } from "next/navigation"

export default function Page() {
  redirect("/theguard/policies?view=coverage")
}
