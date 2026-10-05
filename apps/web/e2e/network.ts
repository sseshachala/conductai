export function isApiRequest(rawUrl: string, baseURL: string, apiURL: string): boolean {
  const url = new URL(rawUrl)
  const web = new URL(baseURL)
  const api = new URL(apiURL || "/api/backend", web)
  if (url.origin === web.origin && url.pathname.startsWith("/api/")) return true
  if (url.origin !== api.origin) return false
  const prefix = api.pathname.replace(/\/$/, "")
  return !prefix || url.pathname === prefix || url.pathname.startsWith(`${prefix}/`)
}
