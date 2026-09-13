import { redirect } from "next/navigation"

// Proxy & Gateways moved to /proxy as a first-class CONNECT item.
// Keep this redirect so old bookmarks and cross-links keep working.
export default function LegacyGuardProxyRedirect() {
  redirect("/proxy")
}
