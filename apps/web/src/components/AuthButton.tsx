"use client"

import { useClerk, useUser } from "@clerk/nextjs"
import { useRouter } from "next/navigation"

const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

export default function AuthButton({ afterSignOutUrl = "/" }: { afterSignOutUrl?: string }) {
  if (!clerkEnabled) return null
  return <SignOutButton afterSignOutUrl={afterSignOutUrl} />
}

function SignOutButton({ afterSignOutUrl }: { afterSignOutUrl: string }) {
  const { signOut } = useClerk()
  const { user } = useUser()
  const router = useRouter()

  return (
    <div className="flex items-center gap-3">
      {user?.primaryEmailAddress?.emailAddress && (
        <span className="text-xs text-stone-400 hidden sm:block">
          {user.primaryEmailAddress.emailAddress}
        </span>
      )}
      <button
        onClick={() => signOut(() => router.push(afterSignOutUrl))}
        className="text-xs font-medium text-stone-500 hover:text-stone-900 border border-stone-200 px-3 py-1.5 rounded-lg hover:bg-stone-50 transition-colors"
      >
        Sign out
      </button>
    </div>
  )
}
