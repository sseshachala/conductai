import { consoleError, exchangeProxyIdentity, requireSameOrigin } from "@/lib/auth/proxy-server"

export const dynamic = "force-dynamic"

export async function POST(request: Request) {
  try {
    requireSameOrigin(request)
    const session = await exchangeProxyIdentity(request.headers)
    return Response.json(session, { headers: { "Cache-Control": "no-store" } })
  } catch (error) { return consoleError(error) }
}
