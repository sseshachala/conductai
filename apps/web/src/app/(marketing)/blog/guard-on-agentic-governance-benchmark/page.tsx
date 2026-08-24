import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "We scored Conduct Guard on the Agentic Governance Benchmark. Here's the honest scorecard. | Conduct",
  description:
    "The AGB measures whether AI runtime governance is actually enforced — six weighted dimensions, five maturity tiers. We ran Guard through it. 80/100, Enforced tier. Here's the per-dimension evidence and what we're not claiming.",
}

export default function BlogPost() {
  return (
    <article className="max-w-2xl mx-auto px-6 py-16">
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
            Benchmark
          </span>
          <span className="text-xs text-stone-400">August 24, 2026</span>
        </div>
        <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
          We scored Guard on the Agentic Governance Benchmark.
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed">
          The AGB measures whether AI runtime governance is actually
          enforced — six weighted dimensions, five maturity tiers. We
          ran Conduct Guard through it. Here is the per-dimension
          evidence and what we are not claiming.
        </p>
      </div>

      <div className="prose prose-stone max-w-none">
        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Why we took the test</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          The Agentic Governance Benchmark (Paper VII in the ExecLayer
          research series,{" "}
          <a
            href="https://doi.org/10.5281/zenodo.20496565"
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-600 hover:underline"
          >
            DOI 10.5281/zenodo.20496565
          </a>
          ) grades runtime governance against six weighted dimensions
          and puts the aggregate on a five-tier maturity scale. It is
          the clearest public rubric we have seen for the "policy on
          the wire, not policy in a doc" argument we have been making
          for a year.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          Every vendor in this category will eventually be scored
          against something like it. We would rather publish our own
          honest number than let someone else guess.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">The rubric</h2>
        <div className="overflow-x-auto mb-6">
          <table className="w-full text-sm border border-stone-200 rounded-lg">
            <thead className="bg-stone-50">
              <tr>
                <th className="text-left px-4 py-2 border-b border-stone-200">Dimension</th>
                <th className="text-left px-4 py-2 border-b border-stone-200">Weight</th>
                <th className="text-left px-4 py-2 border-b border-stone-200">What it measures</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="px-4 py-2 border-b border-stone-100 font-semibold">Policy Determinism</td>
                <td className="px-4 py-2 border-b border-stone-100">25%</td>
                <td className="px-4 py-2 border-b border-stone-100">Same input → same verdict, no probabilistic variance</td>
              </tr>
              <tr>
                <td className="px-4 py-2 border-b border-stone-100 font-semibold">Enforcement Latency</td>
                <td className="px-4 py-2 border-b border-stone-100">20%</td>
                <td className="px-4 py-2 border-b border-stone-100">Blocks fire pre-execution, not after-the-fact logging</td>
              </tr>
              <tr>
                <td className="px-4 py-2 border-b border-stone-100 font-semibold">Receipt Provenance</td>
                <td className="px-4 py-2 border-b border-stone-100">20%</td>
                <td className="px-4 py-2 border-b border-stone-100">Signed, chained decision records</td>
              </tr>
              <tr>
                <td className="px-4 py-2 border-b border-stone-100 font-semibold">Scope Containment</td>
                <td className="px-4 py-2 border-b border-stone-100">15%</td>
                <td className="px-4 py-2 border-b border-stone-100">Verifiable proof agent stayed within authorized boundaries</td>
              </tr>
              <tr>
                <td className="px-4 py-2 border-b border-stone-100 font-semibold">Jurisdictional Enforcement</td>
                <td className="px-4 py-2 border-b border-stone-100">10%</td>
                <td className="px-4 py-2 border-b border-stone-100">Regulatory frameworks applied per request</td>
              </tr>
              <tr>
                <td className="px-4 py-2 font-semibold">Override Integrity</td>
                <td className="px-4 py-2">10%</td>
                <td className="px-4 py-2">Human overrides remain governed and receipted</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-stone-700 leading-relaxed mb-6">
          Maturity tiers: <strong>Ungoverned</strong> (0-14),{" "}
          <strong>Reactive</strong> (15-39), <strong>Structured</strong>{" "}
          (40-64), <strong>Enforced</strong> (65-89),{" "}
          <strong>Sovereign</strong> (90-100).
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Guard scorecard: 80 / 100 — Enforced</h2>

        <div className="overflow-x-auto mb-8">
          <table className="w-full text-sm border border-stone-200 rounded-lg">
            <thead className="bg-stone-50">
              <tr>
                <th className="text-left px-4 py-2 border-b border-stone-200">Dimension</th>
                <th className="text-left px-4 py-2 border-b border-stone-200">Score</th>
                <th className="text-left px-4 py-2 border-b border-stone-200">Evidence</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="px-4 py-2 border-b border-stone-100 font-semibold align-top">Policy Determinism</td>
                <td className="px-4 py-2 border-b border-stone-100 align-top">22 / 25</td>
                <td className="px-4 py-2 border-b border-stone-100">YAML rules, deterministic engine, no LLM in the decision path for regex/keyword/tool rules. Optional LLM-classifier rules exist and carry probabilistic variance — we dock ourselves 3 points for that.</td>
              </tr>
              <tr>
                <td className="px-4 py-2 border-b border-stone-100 font-semibold align-top">Enforcement Latency</td>
                <td className="px-4 py-2 border-b border-stone-100 align-top">14 / 20</td>
                <td className="px-4 py-2 border-b border-stone-100">Pre-forward block on the request body — the model never sees violating input. Mid-stream termination of a streaming response when a spend-limit or content rule trips is on the roadmap (issue #824) but not shipped. Full 20 lands with that ship.</td>
              </tr>
              <tr>
                <td className="px-4 py-2 border-b border-stone-100 font-semibold align-top">Receipt Provenance</td>
                <td className="px-4 py-2 border-b border-stone-100 align-top">15 / 20</td>
                <td className="px-4 py-2 border-b border-stone-100">SHA-256 hash chain rooted at workspace genesis; every decision appends prev_hash → entry_hash. One-click <code>verify_chain</code> endpoint. Signed per-workspace. Linear chain, not Merkle tree — we dock ourselves 5 points until Merkle receipts ship.</td>
              </tr>
              <tr>
                <td className="px-4 py-2 border-b border-stone-100 font-semibold align-top">Scope Containment</td>
                <td className="px-4 py-2 border-b border-stone-100 align-top">12 / 15</td>
                <td className="px-4 py-2 border-b border-stone-100">MCP OAuth with per-tool policy gates. Persona-scoped rule application (proxy / hook / MCP surfaces). Agent identity via signed <code>cond_agt_*</code> tokens. Persistent behavioral risk score is a known gap — 3 points held back.</td>
              </tr>
              <tr>
                <td className="px-4 py-2 border-b border-stone-100 font-semibold align-top">Jurisdictional Enforcement</td>
                <td className="px-4 py-2 border-b border-stone-100 align-top">9 / 10</td>
                <td className="px-4 py-2 border-b border-stone-100">20+ compliance packs with real clause mappings: SOC 2 CC7.3, HIPAA §164.312, PCI DSS 4.0, EU AI Act Art. 15/16, NIST AI RMF, ISO 42001. Applied per request, not per audit.</td>
              </tr>
              <tr>
                <td className="px-4 py-2 font-semibold align-top">Override Integrity</td>
                <td className="px-4 py-2 align-top">8 / 10</td>
                <td className="px-4 py-2">Human-in-the-loop approvals via Slack Approve/Reject. Decision, approver identity, and timestamp land as a signed audit row. Timeout sweep on unresolved requests. Missing: cryptographic co-sign on the approver's decision itself — 2 points held.</td>
              </tr>
            </tbody>
          </table>
        </div>

        <p className="text-stone-700 leading-relaxed mb-6">
          <strong>Total: 80 / 100.</strong> Solidly in the{" "}
          <strong>Enforced</strong> tier (65-89). One mid-stream ship
          and a Merkle receipt upgrade puts Guard in the{" "}
          <strong>Sovereign</strong> tier (90-100).
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Where we are not claiming full marks</h2>
        <ul className="text-stone-700 leading-relaxed mb-6 list-disc pl-6 space-y-3">
          <li>
            <strong>Merkle receipts.</strong> Linear hash chains give
            you tamper detection but not selective proof of inclusion.
            Merkle receipts let a customer prove one decision without
            exposing the whole ledger. Real difference for regulated
            buyers.
          </li>
          <li>
            <strong>Mid-stream termination.</strong> We enforce on the
            request. We do not yet terminate a streaming response
            mid-token when a spend-limit or content rule trips inside
            the stream. That is a real capability gap, not a semantics
            quibble.
          </li>
          <li>
            <strong>Behavioral risk score.</strong> Agent identity is
            static today. Persistent cross-session risk scoring (with
            decay and quarantine) is the shape the RFP question "how
            do you detect a compromised agent?" actually wants.
          </li>
          <li>
            <strong>Co-signed approvals.</strong> An approver's
            decision is recorded as a signed audit event. The approval
            authorization itself is not cryptographically bound to the
            request receipt yet.
          </li>
        </ul>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Where the benchmark under-counts what Guard actually does</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          The AGB is a good rubric for the wire-level enforcement
          layer. It intentionally does not score the surrounding
          product surface. For a buyer, these matter too:
        </p>
        <ul className="text-stone-700 leading-relaxed mb-6 list-disc pl-6 space-y-3">
          <li><strong>Cross-tool coverage</strong> — one ruleset enforcing on Claude Code, Cursor, Copilot, Codex, MCP servers, and LiteLLM / OpenRouter / Portkey upstreams. AGB scores per-request enforcement, not surface breadth.</li>
          <li><strong>Playbook runtime</strong> — Guard is embedded inside a workflow engine, not a standalone firewall. Policy runs inside brain-block execution, not only at the network edge.</li>
          <li><strong>Guidance injection</strong> — <code>inject_guidance</code> lets a rule nudge the model without blocking. Neither "allow" nor "deny" captures it.</li>
          <li><strong>Team memory</strong> — session state and recall context that persist across agents. Nothing in AGB touches this because most vendors do not have it.</li>
        </ul>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">What we are doing about the gaps</h2>
        <p className="text-stone-700 leading-relaxed mb-6">
          The Enforced-to-Sovereign delta is roughly two focused
          sprints of work:{" "}
          <a
            href="https://github.com/sseshachala/conductai/issues/824"
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-600 hover:underline"
          >
            #824
          </a>{" "}
          for mid-stream response termination, a Merkle receipt
          upgrade layered over the existing hash chain, behavioral
          risk scoring on <code>cond_agt_*</code> tokens, and
          co-signed approvals on the HITL path. Timeline is tracked
          in the Loopers re-audit epic (
          <a
            href="https://github.com/sseshachala/conductai/issues/1190"
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-600 hover:underline"
          >
            #1190
          </a>
          ). Publishing this scorecard is what puts a clock on it.
        </p>

        <p className="text-stone-700 leading-relaxed mb-8">
          If you evaluate governance vendors and want a rubric, use
          the AGB. If you have already scored Guard yourself and got a
          different number, tell us — we will publish the delta.
        </p>

        <div className="not-prose flex flex-wrap gap-3 mt-12 mb-8">
          <a
            href="https://doi.org/10.5281/zenodo.20496565"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg bg-stone-900 text-white px-5 py-3 text-sm font-semibold hover:bg-stone-800 transition-colors"
          >
            Read the AGB paper
          </a>
          <a
            href="/theguard"
            className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white text-stone-700 px-5 py-3 text-sm font-semibold hover:border-stone-300 hover:shadow-sm transition-all"
          >
            Guard product page
          </a>
        </div>

        <div className="mt-16 pt-8 border-t border-stone-200">
          <CtaLink className="inline-flex items-center gap-2 rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors" />
        </div>
      </div>
    </article>
  )
}
