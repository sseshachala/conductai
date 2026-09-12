// Canonical Session Reports surface lives on the Activity page.
// This route redirects to `/logs/guard?view=session_reports` so users
// who bookmarked the old URL still land in the right place, and there's
// exactly one place in the UI where the list lives.
//
// The [id] detail route is intentionally NOT redirected — it's the
// deep-link permalink for a single report and is linked from Slack /
// email / share URLs.
import { redirect } from "next/navigation"

export default function Page() {
  redirect("/logs/guard?view=session_reports")
}
