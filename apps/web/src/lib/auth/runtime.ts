export type AuthMode = "clerk" | "proxy" | "development"
export type PublicRuntimeConfig = {
  authMode: AuthMode
  apiUrl: string
  publicApiUrl: string
  clerkPublishableKey: string
}

// Indexed reads deliberately avoid Next's NEXT_PUBLIC_* build-time substitution.
// Only this allowlist is serialized; no server credentials enter the client bundle.
export function deploymentConfig(env: Record<string, string | undefined>): PublicRuntimeConfig {
  const mode = env["AUTH_MODE"] || "clerk"
  if (!["clerk", "proxy", "development"].includes(mode)) throw new Error("Unsupported AUTH_MODE")
  if (mode === "development" && !["local", "development"].includes(env["ENVIRONMENT"] || "")) {
    throw new Error("Development authentication requires a local environment")
  }
  const publicApiUrl = env["API_BASE_URL"] || env["NEXT_PUBLIC_API_URL"] || ""
  return {
    authMode: mode as AuthMode,
    apiUrl: mode === "proxy" ? "/api/backend" : publicApiUrl,
    publicApiUrl,
    clerkPublishableKey: mode === "clerk" ? env["NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"] || "" : "",
  }
}

export function runtimeConfig(): PublicRuntimeConfig {
  if (typeof document !== "undefined") {
    const data = document.getElementById("conduct-runtime")?.textContent
    if (data) return JSON.parse(data) as PublicRuntimeConfig
  }
  return deploymentConfig(process.env)
}

export const authEnabled = () => runtimeConfig().authMode !== "development"
export const apiUrl = () => runtimeConfig().apiUrl
export const publicApiUrl = () => runtimeConfig().publicApiUrl

export function consoleAppOrigin(env: Record<string, string | undefined>): string {
  const url = new URL(env["APP_URL"] || "")
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error("APP_URL must be an HTTPS origin")
  }
  return url.origin
}

export function serializeRuntime(config: PublicRuntimeConfig): string {
  return JSON.stringify(config).replace(/</g, "\\u003c").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029")
}
