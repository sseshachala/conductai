import { appendFileSync } from "node:fs"
import { pathToFileURL } from "node:url"
import { parsePublishableKey } from "@clerk/shared/keys"

export function prepareEnvironment(env) {
  const required = ["NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "CLERK_SECRET_KEY",
    ...["admin", "security", "developer", "viewer"].flatMap(role =>
      [role, `CLERK_TEST_USER_${role.toUpperCase()}`])]
  const missing = required.filter(name => !env[name]?.trim())
  if (missing.length) throw new Error(`Missing web-smoke configuration: ${missing.join(", ")}`)

  const key = parsePublishableKey(env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY)
  if (!key || key.instanceType !== "development" || !key.frontendApi.endsWith(".accounts.dev") ||
      !env.CLERK_SECRET_KEY.startsWith("sk_test_")) {
    throw new Error("Web smoke requires a Clerk development instance, never production credentials")
  }
  if (env.CLERK_FRONTEND_API && env.CLERK_FRONTEND_API !== key.frontendApi) {
    throw new Error("CLERK_TEST_FRONTEND_API does not match CLERK_TEST_PUBLISHABLE_KEY")
  }
  return {
    AUTH_MODE: "clerk",
    NEXT_PUBLIC_AUTH_MODE: "clerk",
    CLERK_FRONTEND_API: key.frontendApi,
    PLAYWRIGHT_SERVER_MODE: "production",
    NEXT_PUBLIC_API_URL: new URL("//127.0.0.1:8000", "http://localhost").origin,
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const values = prepareEnvironment(process.env)
    if (!process.env.GITHUB_ENV) throw new Error("GITHUB_ENV is required")
    appendFileSync(process.env.GITHUB_ENV, Object.entries(values).map(([k, v]) => `${k}=${v}\n`).join(""))
    console.log("Clerk sandbox configuration validated; API issuer derived from publishable key")
  } catch (error) {
    console.error(error.message)
    process.exitCode = 1
  }
}
