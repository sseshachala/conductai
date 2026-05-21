"use client"

import { useClerk, useUser } from "@clerk/nextjs"
import { useRouter } from "next/navigation"
import { useState, useRef, useEffect } from "react"

const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

export default function AuthButton({ afterSignOutUrl = "/", dropUp = false }: { afterSignOutUrl?: string; dropUp?: boolean }) {
  if (!clerkEnabled) return null
  return <AccountMenu afterSignOutUrl={afterSignOutUrl} dropUp={dropUp} />
}

function AccountMenu({ afterSignOutUrl, dropUp }: { afterSignOutUrl: string; dropUp?: boolean }) {
  const { signOut } = useClerk()
  const { user } = useUser()
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const email = user?.primaryEmailAddress?.emailAddress ?? ""
  const initials = email ? email[0].toUpperCase() : "?"

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-7 h-7 rounded-full bg-violet-600 text-white text-[11px] font-bold flex items-center justify-center hover:bg-violet-700 transition-colors"
        title={email}
      >
        {initials}
      </button>

      {open && (
        <div className={`absolute right-0 w-52 bg-white border border-stone-200 rounded-xl shadow-lg py-1 z-50 ${dropUp ? "bottom-9" : "top-9"}`}>
          {email && (
            <>
              <p className="px-3 py-2 text-[11px] text-stone-400 truncate">{email}</p>
              <div className="border-t border-stone-100 my-1" />
            </>
          )}
          <button
            onClick={() => { setOpen(false); signOut(() => router.push(afterSignOutUrl)) }}
            className="w-full text-left px-3 py-2 text-sm text-stone-600 hover:bg-stone-50 hover:text-stone-900 transition-colors"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}
