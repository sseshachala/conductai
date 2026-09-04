import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server"
import { type NextRequest, NextResponse } from "next/server"

const isPublicRoute = createRouteMatcher(["/", "/sign-in(.*)", "/sign-up(.*)", "/compare", "/privacy", "/terms", "/benchmark(.*)", "/eval(.*)", "/registry", "/playbooks", "/token-guardrails", "/docs(.*)", "/accept-invite(.*)", "/sdd(.*)", "/tools(.*)", "/about(.*)", "/blog(.*)", "/share(.*)", "/solutions(.*)", "/partners(.*)", "/guard", "/evidence", "/api/mcp/guard/oauth/(.*)", "/.well-known/(.*)",])

const isAppSubdomain = (req: NextRequest) =>
  req.headers.get("host")?.startsWith("app.")

const MARKETING_TO_APP: Record<string, string> = {
  "/guard": "/theguard",
  "/registry": "/packs",
}

const clerkHandler = clerkMiddleware(async (auth, req) => {
  // app.conductai.ai/ → send logged-in users to dashboard, others to sign-in
  if (isAppSubdomain(req) && req.nextUrl.pathname === "/") {
    const { userId } = await auth()
    return NextResponse.redirect(new URL(userId ? "/theguard" : "/sign-in", req.url))
  }

  // Redirect logged-in users from marketing pages to their app equivalents
  const appDest = MARKETING_TO_APP[req.nextUrl.pathname]
  if (appDest) {
    const { userId } = await auth()
    if (userId) return NextResponse.redirect(new URL(appDest, req.url))
  }

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
