import Link from "next/link"
import AuthButton from "@/components/AuthButton"
import CredentialsManager from "@/components/settings/CredentialsManager"

async function getCredentials() {
  try {
    const res = await fetch(`${process.env.API_URL}/credentials`, { cache: "no-store" })
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
  }
}

export default async function SettingsPage() {
  const credentials = await getCredentials()
  const hasAny = credentials.length > 0

  return (
    <div className="min-h-screen bg-stone-50">
      <header className="border-b border-stone-200 bg-white px-6 py-4 flex items-center justify-between">
        <span className="font-semibold text-stone-900">Delegator</span>
        <div className="flex items-center gap-4">
          {hasAny && (
            <Link href="/workflows" className="text-sm text-stone-500 hover:text-stone-800 transition-colors">
              My agents
            </Link>
          )}
          <AuthButton afterSignOutUrl="/sign-in" />
        </div>
      </header>

      <main className="mx-auto max-w-2xl px-6 py-12">
        <div className="mb-8">
          <h1 className="text-2xl font-semibold text-stone-900">Connect your tools</h1>
          <p className="text-sm text-stone-500 mt-1.5">
            Add credentials for the integrations your agents will use.
            All tokens are encrypted with AES-256-GCM before storage.
          </p>
        </div>

        <CredentialsManager initialCredentials={credentials} />

        <div className="mt-10 pt-8 border-t border-stone-200 flex items-center justify-between">
          <p className="text-sm text-stone-400">
            {hasAny
              ? `${credentials.length} integration${credentials.length > 1 ? "s" : ""} connected`
              : "Connect at least one integration to continue"}
          </p>
          <Link
            href="/workflows/new"
            className={`rounded-lg px-5 py-2.5 text-sm font-medium transition-colors ${
              hasAny
                ? "bg-stone-900 text-white hover:bg-stone-700"
                : "bg-stone-100 text-stone-400 pointer-events-none"
            }`}
          >
            Create your first agent →
          </Link>
        </div>
      </main>
    </div>
  )
}
