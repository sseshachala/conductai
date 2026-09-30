import { consoleError, requireSameOrigin } from "@/lib/auth/proxy-server"

export async function POST(request: Request) {
  try {
    requireSameOrigin(request)
    return new Response(null, { status: 204, headers: { "Cache-Control": "no-store" } })
  } catch (error) { return consoleError(error) }
}
