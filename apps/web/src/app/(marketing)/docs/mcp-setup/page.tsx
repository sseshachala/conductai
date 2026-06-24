import { redirect } from "next/navigation"

export default function McpSetupRedirect(): never {
  redirect("/docs?tab=mcp-tools")
}
