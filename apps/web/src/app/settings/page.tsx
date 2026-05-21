"use client"

import { useState } from "react"
import Link from "next/link"
import AppShell from "@/components/AppShell"
import CredentialsManager from "@/components/settings/CredentialsManager"
import EnvironmentsManager from "@/components/settings/EnvironmentsManager"

type Tab = "integrations" | "environments"

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("integrations")

  return (
    <AppShell>
      <div className="mx-auto max-w-2xl px-6 py-12">
        <div className="mb-8">
          <h1 className="text-2xl font-semibold text-stone-900">Settings</h1>
          <p className="text-sm text-stone-500 mt-1.5">
            Manage your integrations and environments.
            All tokens are encrypted with AES-256-GCM before storage.
          </p>
        </div>

        {/* Tab bar */}
        <div className="flex bg-stone-100 rounded-lg p-1 mb-6 w-fit">
          <button
            onClick={() => setActiveTab("integrations")}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              activeTab === "integrations"
                ? "bg-white text-stone-900 shadow-sm"
                : "text-stone-500 hover:text-stone-800"
            }`}
          >
            Integrations
          </button>
          <button
            onClick={() => setActiveTab("environments")}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              activeTab === "environments"
                ? "bg-white text-stone-900 shadow-sm"
                : "text-stone-500 hover:text-stone-800"
            }`}
          >
            Environments
          </button>
        </div>

        {activeTab === "integrations" && <CredentialsManager />}
        {activeTab === "environments" && <EnvironmentsManager />}

        <div className="mt-10 pt-8 border-t border-stone-200 text-right">
          <Link
            href="/workflows/new"
            className="rounded-lg px-5 py-2.5 text-sm font-medium bg-stone-900 text-white hover:bg-stone-700 transition-colors"
          >
            Create your first agent →
          </Link>
        </div>
      </div>
    </AppShell>
  )
}
