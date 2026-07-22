"use client"

import { Check, X, Mail } from "lucide-react"

export default function TeamOSLicensePage() {
  return (
    <div className="max-w-3xl mx-auto px-6 pt-16 pb-24">

      {/* Header */}
      <div className="mb-12">
        <a href="/team-os" className="text-xs font-semibold text-stone-400 hover:text-stone-600 uppercase tracking-widest transition-colors">
          ← Team OS
        </a>
        <h1 className="text-4xl font-black text-stone-900 mt-4 mb-3">License</h1>
        <p className="text-stone-500 text-lg leading-relaxed">
          Team OS is free for individuals and small teams. Companies need a commercial license.
        </p>
        <p className="text-stone-400 text-sm mt-2">
          Copyright © 2026 Conduct AI (Sudhi Seshachala). Last updated July 2026.
        </p>
      </div>

      {/* Tier cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-14">

        {/* Free */}
        <div className="rounded-2xl border-2 border-emerald-200 bg-emerald-50 p-6">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-lg font-black text-emerald-700">Free</span>
            <span className="text-xs bg-emerald-100 text-emerald-600 px-2 py-0.5 rounded-full font-semibold">No license needed</span>
          </div>
          <p className="text-sm text-emerald-700 mb-5">Use, copy, and adapt with attribution.</p>
          <ul className="space-y-2.5">
            {[
              "Individual developers",
              "Teams of fewer than 10 people",
              "Open-source projects",
              "Students and educators",
              "Personal or hobby projects",
            ].map(item => (
              <li key={item} className="flex items-start gap-2 text-sm text-stone-700">
                <Check className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
                {item}
              </li>
            ))}
          </ul>
        </div>

        {/* Commercial */}
        <div className="rounded-2xl border-2 border-stone-200 bg-white p-6">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-lg font-black text-stone-900">Commercial</span>
            <span className="text-xs bg-stone-100 text-stone-500 px-2 py-0.5 rounded-full font-semibold">License required</span>
          </div>
          <p className="text-sm text-stone-500 mb-5">Contact us for a written agreement.</p>
          <ul className="space-y-2.5">
            {[
              "Companies with 10+ employees",
              "Client or consulting engagements",
              "Internal tooling at scale",
              "Embedding in a product or service",
              "Training programmes or workshops",
            ].map(item => (
              <li key={item} className="flex items-start gap-2 text-sm text-stone-700">
                <X className="w-4 h-4 text-stone-400 mt-0.5 shrink-0" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Attribution */}
      <div className="rounded-xl border border-stone-200 bg-stone-50 p-6 mb-10">
        <h2 className="font-bold text-stone-900 mb-2">Attribution required in all cases</h2>
        <p className="text-sm text-stone-600 mb-3">
          Any copy, adaptation, or derivative must include the following notice, visible to the people who use it:
        </p>
        <div className="bg-white border border-stone-200 rounded-lg px-4 py-3 font-mono text-sm text-stone-700">
          Based on Conduct AI Team OS — conductai.ai/team-os
        </div>
        <p className="text-xs text-stone-400 mt-2">Commercial licensees may request removal of this requirement.</p>
      </div>

      {/* Full license text */}
      <div className="mb-12">
        <h2 className="text-xl font-black text-stone-900 mb-4">Full license text</h2>
        <div className="rounded-xl border border-stone-200 bg-stone-50 p-6 font-mono text-xs text-stone-600 leading-relaxed whitespace-pre-wrap">{`Conduct AI Team OS License
Copyright (c) 2026 Conduct AI (Sudhi Seshachala)

─────────────────────────────────────────────────────────────

FREE USE (no license required)

You may use, copy, adapt, and share this work at no cost if
ALL of the following are true:

  1. Your use is non-commercial, OR you are an individual
     developer or a team of fewer than 10 people.
  2. You are not offering a product or service where Team OS
     (or a derivative) is a primary component.
  3. You include the attribution notice in any published or
     distributed copy.

ATTRIBUTION (required in all cases)

  "Based on Conduct AI Team OS — conductai.ai/team-os"

COMMERCIAL LICENSE (required for companies)

A commercial license is required if:

  - Your organisation has 10 or more employees or
    contractors, AND
  - You use this work in a commercial context (internal
    tooling, client work, products, training, or
    consulting), OR
  - You distribute or embed this work as part of a
    commercial product or service.

To obtain a commercial license: hello@conductai.ai

─────────────────────────────────────────────────────────────

NO WARRANTIES

This work is provided as-is, without warranty of any kind.
The authors are not liable for any damages from its use.

─────────────────────────────────────────────────────────────

If you are unsure whether your use requires a commercial
license, email hello@conductai.ai. We respond within
two business days.`}
        </div>
      </div>

      {/* CTA */}
      <div className="rounded-2xl border border-stone-200 bg-white p-8 text-center">
        <h2 className="text-xl font-black text-stone-900 mb-2">Need a commercial license?</h2>
        <p className="text-stone-500 text-sm mb-6 max-w-sm mx-auto">
          We keep it simple. Tell us how you plan to use Team OS and we will send you a written agreement within two business days.
        </p>
        <a
          href="mailto:hello@conductai.ai?subject=Team OS commercial license&body=Hi,%0A%0AWe%27d like to use Team OS commercially. Here%27s how:%0A%0A- Company:%0A- Team size:%0A- Intended use:%0A%0AThanks"
          className="inline-flex items-center gap-2 rounded-xl bg-stone-900 text-white px-6 py-3 text-sm font-semibold hover:bg-stone-700 transition-colors"
        >
          <Mail className="w-4 h-4" />
          hello@conductai.ai
        </a>
        <p className="text-xs text-stone-400 mt-4">Two business day response · No lawyers required to start</p>
      </div>

    </div>
  )
}
