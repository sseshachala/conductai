import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server"
import { type NextRequest, NextResponse } from "next/server"

const isPublicRoute = createRouteMatcher(["/", "/sign-in(.*)", "/sign-up(.*)", "/compare", "/privacy", "/terms", "/benchmark(.*)", "/eval(.*)", "/marketplace", "/docs(.*)"])

const clerkHandler = clerkMiddleware(async (auth, req) => {
  if (isPublicRoute(req)) return

  const { userId } = await auth()
  if (!userId) {
    const signIn = new URL("/sign-in", req.url)
    signIn.searchParams.set("redirect_url", req.url)
    return NextResponse.redirect(signIn)
  }
})

export default function middleware(req: NextRequest, evt: unknown) {
  if (!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    if (process.env.NODE_ENV === "production") {
      // Refuse to serve protected routes without auth in production
      return new NextResponse("Auth not configured", { status: 503 })
    }
    return NextResponse.next()
  }
  return clerkHandler(req, evt as never)
}

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
}
