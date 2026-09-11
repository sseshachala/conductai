// ponytail: thin server layout so we can export route-segment config
// (dynamic = "force-dynamic"). The old client-component layout lives in
// AppSegment.tsx. Route Segment Config exports are ignored on client
// components in Next.js 15, so the split is mandatory.
//
// Every route under (app) needs Clerk + WorkspaceContext at runtime. Preview
// builds without a Clerk publishable key crash at prerender (useAuth outside
// ClerkProvider). Skip prerender for the whole subtree.
export const dynamic = "force-dynamic"

import type { Metadata } from "next"
import AppSegment from "./AppSegment"

// Audit U08: root metadata declared everything indexable and defaulted
// canonical to the homepage. Authenticated console routes must NEVER be
// indexed — they surface workspace data behind a session — and must NEVER
// self-report as the homepage in the DOM. Set both here so the (app)
// subtree overrides root regardless of what individual pages export.
export const metadata: Metadata = {
  robots: { index: false, follow: false, nocache: true },
  alternates: { canonical: null },
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AppSegment>{children}</AppSegment>
}
