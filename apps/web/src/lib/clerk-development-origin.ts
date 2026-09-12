/** Permit only the configured development instance, never an arbitrary origin. */
export function clerkDevelopmentOrigin(key: string): string {
  if (!key.startsWith("pk_test_")) return ""
  try {
    const decoded = atob(key.slice("pk_test_".length))
    if (!decoded.endsWith("$")) return ""
    const host = decoded.slice(0, -1)
    return /^[a-z0-9-]+\.clerk\.accounts\.dev$/.test(host) ? `https://${host}` : ""
  } catch {
    return ""
  }
}
