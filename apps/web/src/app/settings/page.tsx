"use client"

import { useState } from "react"
import AppShell from "@/components/AppShell"
import CredentialsManager from "@/components/settings/CredentialsManager"
import EnvironmentsManager from "@/components/settings/EnvironmentsManager"

type Tab = "integrations" | "environments"

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("integrations")

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl px-6 py-10">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-semibold text-stone-900">Settings</h1>
          <span className="text-xs text-stone-400">Tokens encrypted at rest</span>
        </div>

        {/* Onboarding hint */}
        <div className="mb-6 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 flex items-start gap-3">
          <span className="text-amber-500 text-base leading-none mt-0.5">⚠</span>
          <p className="text-sm text-amber-800 leading-relaxed">
            <span className="font-semibold">Add credentials before running agents.</span>{" "}
            Create an environment under <strong>Environments</strong>, add your GitHub and Slack tokens under <strong>Integrations</strong>, then assign the environment to your agent on the canvas.
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
      </div>
    </AppShell>
  )
}
