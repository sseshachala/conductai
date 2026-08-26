// ponytail: thin server layout so we can export route-segment config
// (dynamic = "force-dynamic"). The old client-component layout lives in
// AppSegment.tsx. Route Segment Config exports are ignored on client
// components in Next.js 15, so the split is mandatory.
//
// Every route under (app) needs Clerk + WorkspaceContext at runtime. Preview
// builds without a Clerk publishable key crash at prerender (useAuth outside
// ClerkProvider). Skip prerender for the whole subtree.
export const dynamic = "force-dynamic"

import AppSegment from "./AppSegment"

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AppSegment>{children}</AppSegment>
}
