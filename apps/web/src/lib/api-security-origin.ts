const localEnvironment = (environment: string | undefined) =>
  environment === "local" || environment === "development"
const loopback = (hostname: string) => ["localhost", "127.0.0.1", "[::1]"].includes(hostname)

export function isLocalHttpOrigin(rawUrl: string, environment?: string): boolean {
  try {
    const url = new URL(rawUrl)
    return localEnvironment(environment) && url.protocol === "http:" && loopback(url.hostname) &&
      !url.username && !url.password
  } catch { return false }
}

export function apiSecurityOrigin(rawUrl: string, environment?: string): string {
  try {
    const url = new URL(rawUrl)
    if (url.username || url.password) return ""
    return url.protocol === "https:" || isLocalHttpOrigin(rawUrl, environment) ? url.origin : ""
  } catch { return "" }
}
