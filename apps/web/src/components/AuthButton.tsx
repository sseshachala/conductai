"use client"

import { UserButton } from "@clerk/nextjs"

const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

export default function AuthButton({ afterSignOutUrl = "/sign-in" }: { afterSignOutUrl?: string }) {
  if (!clerkEnabled) return null
  return <UserButton afterSignOutUrl={afterSignOutUrl} />
}
