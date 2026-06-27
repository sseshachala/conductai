"use client"
import { useAuth } from "@clerk/nextjs"

export function CtaLink({ className, children }: { className: string; children?: React.ReactNode }) {
  const { isSignedIn, isLoaded } = useAuth()
  if (!isLoaded) return <span className={className} aria-hidden />
  return isSignedIn
    ? <a href="https://app.conductai.ai/guard" className={className}>{children ?? "Go to App"}</a>
    : <a href="/sign-up" className={className}>{children ?? "Start Free"}</a>
}
