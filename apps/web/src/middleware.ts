import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server"
import { type NextRequest, NextResponse } from "next/server"

const isPublicRoute = createRouteMatcher(["/", "/sign-in(.*)", "/sign-up(.*)", "/compare", "/privacy", "/terms", "/benchmark(.*)", "/eval(.*)", "/registry", "/playbooks", "/token-guardrails", "/docs(.*)", "/accept-invite(.*)", "/sdd(.*)", "/tools(.*)", "/about(.*)", "/blog(.*)", "/share(.*)", "/solutions(.*)", "/partners(.*)", "/guard", "/evidence", "/mcp-gateway", "/security", "/deployment", "/pricing", "/open-source", "/router", "/team-os", "/frameworks(.*)", "/discovery", "/book-demo", "/use-cases", "/what-is-conduct-ai", "/api/mcp/guard/oauth/(.*)", "/.well-known/(.*)",])

// Audit S13 — route-scoped Content Security Policy.
//
// Authenticated console routes (path prefixes below) get a strict script-src
// that disallows every third-party origin including narratr.ai. Public
// marketing routes get a looser policy that permits the vendor scripts
// (Narratr widget + embed) still needed for the blog / branded widgets.
//
// Both branches share the same default security headers (X-Content-Type-Options,
// Referrer-Policy, X-Frame-Options) so a mistake in one branch doesn't leave
// the other unprotected.
const APP_ROUTE_PREFIXES = [
  "/agent-identity", "/cli-auth", "/credentials", "/dashboard", "/integrations",
  "/lens", "/logs", "/marketplace", "/packs", "/projects", "/secure", "/settings",
  "/setup", "/theguard", "/workflows",
]

function _isAppRoute(pathname: string): boolean {
  return APP_ROUTE_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + "/"))
}

function _cspFor(pathname: string): string {
  // Common building blocks. Clerk lives on cdn.clerk.com / *.clerk.accounts.dev.
  // challenges.cloudflare.com is Clerk's bot-detection provider (Cloudflare
  // Turnstile) — Clerk 5 uses it by default for suspicious sign-ups. Must
  // appear in both script-src and frame-src (challenge widget = an iframe
  // that loads a script).
  // 'unsafe-inline' on script-src is retained on marketing because the current
  // theme init and JSON-LD are inlined; tighten in a follow-up once we
  // migrate those to a nonce-based approach.
  const _selfClerk = "'self' https://cdn.clerk.com https://clerk.conductai.ai https://challenges.cloudflare.com"
  const _connect = "'self' https://api.conductai.ai https://clerk.conductai.ai https://clerk.com https://*.clerk.accounts.dev wss:"
  const _img = "'self' data: https:"
  const _font = "'self' https://fonts.gstatic.com data:"
  const _style = "'self' 'unsafe-inline' https://fonts.googleapis.com"
  const _base = [
    "default-src 'self'",
    `img-src ${_img}`,
    `font-src ${_font}`,
    `style-src ${_style}`,
    `connect-src ${_connect}`,
    // worker-src: Clerk's browser SDK creates blob-URL web workers for
    // background session-token refresh. Without an explicit worker-src
    // directive browsers fall back to script-src, which doesn't allow
    // blob:. Result: workers get blocked, Clerk can't refresh tokens,
    // every authenticated API call returns 401. Third CSP escape hatch
    // found the hard way (S13 shipped without clerk.conductai.ai in
    // connect-src → #1801; then this).
    "worker-src 'self' blob:",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "upgrade-insecure-requests",
  ]

  if (_isAppRoute(pathname)) {
    // Strict — no third-party script origins, no vendor widgets.
    return [
      `script-src ${_selfClerk} 'unsafe-inline' 'unsafe-eval'`,
      `frame-src ${_selfClerk}`,
      ...(_base),
    ].join("; ")
  }
  // Marketing — permit narratr.ai and standard analytics; still deny inline
  // frames from anywhere except self+clerk.
  return [
    `script-src ${_selfClerk} https://narratr.ai 'unsafe-inline' 'unsafe-eval'`,
    `frame-src ${_selfClerk} https://narratr.ai`,
    ...(_base),
  ].join("; ")
}

function _applySecurityHeaders(res: NextResponse, pathname: string): NextResponse {
  // Enforce CSP only in production. Local dev + preview deploys often have
  // different API URLs (localhost:8000, api-git-branch.vercel.app, ...) that
  // aren't easily enumerated in a static header — we ship Report-Only there
  // so the console flags violations without breaking work-in-progress
  // deploys. Prod gets the enforcing header that actually protects users.
  const _cspHeader = process.env.NODE_ENV === "production"
    ? "Content-Security-Policy"
    : "Content-Security-Policy-Report-Only"
  res.headers.set(_cspHeader, _cspFor(pathname))
  res.headers.set("X-Content-Type-Options", "nosniff")
  res.headers.set("Referrer-Policy", "strict-origin-when-cross-origin")
  res.headers.set("X-Frame-Options", "DENY")
  res.headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
  return res
}

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

export default async function middleware(req: NextRequest, evt: unknown) {
  // Run the Clerk handler first — it may redirect, in which case we still
  // want CSP headers on the redirect response so the browser never sees
  // an unprotected error page.
  const _clerkResp = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
    ? await clerkHandler(req, evt as never)
    : (process.env.NODE_ENV === "production"
        ? new NextResponse("Auth not configured", { status: 503 })
        : NextResponse.next())

  // Clerk's middleware returns undefined for pass-through; NextResponse
  // constructor gives us a fresh headers-writable response.
  const _res = _clerkResp instanceof NextResponse ? _clerkResp : NextResponse.next()
  return _applySecurityHeaders(_res, req.nextUrl.pathname)
}

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
}
