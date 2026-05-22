import type { Metadata } from "next"
import "./globals.css"
import { ClerkProvider } from "@clerk/nextjs"

export const metadata: Metadata = {
  title: "Deligators — AI engineer that opens draft PRs you approve",
  description:
    "Open-source AI engineer for small teams. Label a GitHub issue, get a tested draft PR — approved in Slack before anything merges.",
}

const clerkEnabled = !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY

export default function RootLayout({ children }: { children: React.ReactNode }) {
  if (clerkEnabled) {
    return (
      <ClerkProvider>
        <html lang="en">
          <body>{children}</body>
        </html>
      </ClerkProvider>
    )
  }
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
