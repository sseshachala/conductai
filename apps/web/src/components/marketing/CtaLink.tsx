"use client"
import { useAuth } from "@clerk/nextjs"

// ponytail: split so useAuth is only called when Clerk is actually wired up.
// Preview builds without NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY get the plain link;
// prod/preview with Clerk get the auth-aware version. Same pattern as
// WorkspaceProvider (lib/WorkspaceContext.tsx).
const CLERK_ENABLED = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

type Props = { className: string; children?: React.ReactNode }

export function CtaLink(props: Props) {
  return CLERK_ENABLED ? <CtaLinkWithAuth {...props} /> : <SignUpLink {...props} />
}

function SignUpLink({ className, children }: Props) {
  return <a href="/sign-up" className={className}>{children ?? "Start Free"}</a>
}

function CtaLinkWithAuth({ className, children }: Props) {
  const { isSignedIn, isLoaded } = useAuth()
  if (!isLoaded) return <span className={className} aria-hidden />
  return isSignedIn
    ? <a href="https://app.conductai.ai/guard" className={className}>{children ?? "Go to App"}</a>
    : <a href="/sign-up" className={className}>{children ?? "Start Free"}</a>
}
