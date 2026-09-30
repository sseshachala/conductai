import "server-only"
import { consoleAppOrigin, deploymentConfig } from "./runtime"

export class ConsoleError extends Error {
  constructor(public status: number) { super("Console authentication failed") }
}

export function proxySettings() {
  if (deploymentConfig(process.env).authMode !== "proxy") throw new ConsoleError(404)
  const app = consoleAppOrigin(process.env)
  const api = new URL(process.env.API_URL || "")
  if (!["https:", "http:"].includes(api.protocol) || api.username || api.password
      || api.search || api.hash || api.pathname !== "/") {
    throw new ConsoleError(503)
  }
  const secret = process.env.CONSOLE_PROXY_SECRET || ""
  if (Buffer.byteLength(secret) < 32) throw new ConsoleError(503)
  return { app, api: api.origin, secret }
}

export function requireSameOrigin(request: Request) {
  const { app } = proxySettings()
  if (request.headers.get("origin") !== app
      || ["cross-site", "same-site"].includes(request.headers.get("sec-fetch-site") || "")) {
    throw new ConsoleError(403)
  }
}

export async function exchangeProxyIdentity(headers: Headers) {
  const { api, secret } = proxySettings()
  const authorization = headers.get("authorization") || ""
  if (!authorization.startsWith("Bearer ") || authorization.length > 16400) throw new ConsoleError(401)
  const response = await fetch(`${api}/auth/console/session`, {
    method: "POST", cache: "no-store", redirect: "error", signal: AbortSignal.timeout(10000),
    headers: { "Content-Type": "application/json", "X-Conduct-Proxy-Secret": secret },
    body: JSON.stringify({ identity_token: authorization.slice(7) }),
  })
  if (!response.ok) throw new ConsoleError([401, 403].includes(response.status) ? response.status : 503)
  return await response.json() as { token: string; expires_at: number; user: { id: string; name: string } }
}

export function consoleError(error: unknown) {
  return Response.json({ error: "Console authentication unavailable" }, {
    status: error instanceof ConsoleError ? error.status : 503,
    headers: { "Cache-Control": "no-store" },
  })
}
