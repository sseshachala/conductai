import { consoleError, ConsoleError, exchangeProxyIdentity, proxySettings, requireSameOrigin } from "@/lib/auth/proxy-server"

export const dynamic = "force-dynamic"
type Context = { params: Promise<{ path: string[] }> }

async function forward(request: Request, context: Context) {
  try {
    const settings = proxySettings()
    if (!["GET", "HEAD"].includes(request.method)) requireSameOrigin(request)
    const { path } = await context.params
    if (path.some(part => !part || part === "." || part === ".." || /[\\/\x00-\x20]/.test(part))) {
      throw new ConsoleError(400)
    }
    // Never expose the server-only evidence exchange through this general proxy.
    if (path[0] === "auth" && path[1] === "console") throw new ConsoleError(404)
    const session = await exchangeProxyIdentity(request.headers)
    const target = new URL("/" + path.map(encodeURIComponent).join("/"), settings.api)
    target.search = new URL(request.url).search
    const headers = new Headers({ Authorization: `Bearer ${session.token}` })
    for (const name of ["content-type", "accept", "x-workspace-id", "last-event-id"]) {
      const value = request.headers.get(name)
      if (value) headers.set(name, value)
    }
    const upstream = await fetch(target, {
      method: request.method, headers, cache: "no-store", redirect: "manual", signal: request.signal,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(),
    })
    if (upstream.status >= 300 && upstream.status < 400) throw new ConsoleError(502)
    const outgoing = new Headers({ "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" })
    for (const name of ["content-type", "content-disposition", "retry-after"]) {
      const value = upstream.headers.get(name)
      if (value) outgoing.set(name, value)
    }
    return new Response(upstream.body, { status: upstream.status, headers: outgoing })
  } catch (error) { return consoleError(error) }
}

export { forward as GET, forward as HEAD, forward as POST, forward as PUT, forward as PATCH, forward as DELETE }
