import Link from "next/link"
import AuthButton from "@/components/AuthButton"
import CredentialsManager from "@/components/settings/CredentialsManager"

export default function SettingsPage() {
  return (
    <div className="min-h-screen bg-stone-50">
      <header className="border-b border-stone-200 bg-white px-6 py-4 flex items-center justify-between">
        <span className="font-semibold text-stone-900">Delegator</span>
        <div className="flex items-center gap-4">
          <Link href="/workflows" className="text-sm text-stone-500 hover:text-stone-800 transition-colors">
            My agents
          </Link>
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

        <CredentialsManager />

        <div className="mt-10 pt-8 border-t border-stone-200 text-right">
          <Link
            href="/workflows/new"
            className="rounded-lg px-5 py-2.5 text-sm font-medium bg-stone-900 text-white hover:bg-stone-700 transition-colors"
          >
            Create your first agent →
          </Link>
        </div>
      </main>
    </div>
  )
}
