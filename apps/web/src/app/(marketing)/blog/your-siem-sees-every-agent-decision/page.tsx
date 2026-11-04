import { CtaLink } from "@/components/marketing/CtaLink"

export const metadata = {
  title: "Your SIEM now sees every agent decision | Conduct",
  description:
    "Stream Conduct's audit log to Splunk, Sentinel or Falcon LogScale with one command. Gateway decisions now join the tamper-evident hash chain, and verifying our own data turned up a concurrency bug we fixed.",
}

export default function BlogPost() {
  return (
    <article className="max-w-2xl mx-auto px-6 py-16">
      <div className="mb-10">
        <div className="flex items-center gap-3 mb-6">
          <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full uppercase tracking-widest">
            Product updates
          </span>
          <span className="text-xs text-stone-400">November 4, 2026</span>
        </div>
        <h1 className="text-4xl font-bold text-stone-900 leading-tight mb-4">
          Your SIEM now sees every agent decision.
        </h1>
        <p className="text-lg text-stone-500 leading-relaxed">
          Conduct&apos;s audit log now streams to the tools your security
          team already watches. One command, no new infrastructure. And
          the log it streams is now complete: decisions from the LLM
          gateway join the same tamper-evident chain as everything else.
        </p>
      </div>

      <div className="prose prose-stone max-w-none">
        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Why the SIEM matters</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Security teams don&apos;t want another console. When a coding
          agent tries to read a secrets file, push to a protected branch
          or call an unapproved MCP server, the analyst on call should
          see it in the same place they see endpoint alerts and login
          anomalies. That means Splunk, Microsoft Sentinel, CrowdStrike
          Falcon LogScale, or whatever sits behind your collector.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          Until now, getting Conduct&apos;s decisions there meant
          exporting from the console or building against the API. Both
          work for an audit. Neither is a feed.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">One command</h2>
        <pre className="bg-stone-950 text-stone-100 p-6 rounded-2xl overflow-x-auto text-sm font-mono leading-relaxed mb-6">
{`pip install -U conduct-cli
conduct audit feed --follow --output /var/log/conduct/audit.ndjson`}
        </pre>
        <p className="text-stone-700 leading-relaxed mb-4">
          <code>conduct audit feed</code> pages through your
          workspace&apos;s audit events and writes one JSON object per
          line. Point Splunk Universal Forwarder, Azure Monitor Agent,
          Falcon LogScale Collector, Fluent Bit or Vector at the file and
          you&apos;re done. Every collector already knows how to tail
          NDJSON.
        </p>
        <ul className="text-stone-700 leading-relaxed mb-6 list-disc pl-6 space-y-3">
          <li>
            <strong>Resumable.</strong> The cursor is checkpointed after
            every page is written. Restart the process, reboot the host,
            and it picks up where it stopped. Nothing is skipped and
            nothing is written twice.
          </li>
          <li>
            <strong>Pull, not push.</strong> The feed runs inside your
            network and reaches out to Conduct. No inbound firewall rule,
            no public HTTP endpoint for us to post to.
          </li>
          <li>
            <strong>Same permission as the console.</strong> The feed is
            served over Conduct&apos;s MCP endpoint and checks the same{" "}
            <code>platform.audit_log.view</code> permission as the Audit
            page. Transport is never the boundary; the API is.
          </li>
          <li>
            <strong>Every event carries its chain fields.</strong>{" "}
            <code>previous_hash</code>, <code>entry_hash</code> and the
            policy hash in force at the time travel with each line, so
            your SIEM holds evidence, not just logs.
          </li>
        </ul>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Know the feed is flowing</h2>
        <p className="text-stone-700 leading-relaxed mb-6">
          A feed that silently stops is worse than no feed. The Audit
          page in the console now shows a SIEM feed card: every collector
          pulling for the workspace, when it last pulled, how far behind
          it is, and how many events it took. If a collector hasn&apos;t
          pulled in 15 minutes it is marked stale, so you find out from
          Conduct before you find out from an empty dashboard.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Closing the gap</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          Conduct enforces one policy across three surfaces: the CLI
          hooks inside coding agents, MCP tool calls, and the LLM
          gateway. Every decision is appended to a SHA-256 hash chain per
          workspace. Each entry commits to the one before it, so a
          deleted or edited row breaks the chain where it happened.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          When we pulled our own workspace through the new feed, the
          numbers said something we didn&apos;t like. Hook and MCP
          decisions were chained. Gateway decisions were recorded, but
          written without chain fields. They were in the log, but outside
          the evidence.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          That&apos;s fixed. Every audit writer, including the gateway,
          approvals, policy edits, SSO logins and ingested events, now
          goes through a single chain-append path. A gateway decision is
          as provable as a blocked shell command.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">The bug verification found</h2>
        <p className="text-stone-700 leading-relaxed mb-4">
          We also ran the chain verifier offline against the exported
          feed. Every entry hash checked out. Nothing had been altered.
          But a few entries shared the same predecessor: two hook events
          landing milliseconds apart had both read the same chain tail
          and linked to it. The chain had forked.
        </p>
        <p className="text-stone-700 leading-relaxed mb-4">
          That is a race, not tampering, but an auditor can&apos;t tell
          the difference from a broken chain alone. So the append path
          now takes a per-workspace Postgres advisory lock, reads the
          tail and stamps the timestamp inside that lock, and guarantees
          each entry sorts strictly after the one it links to. Our
          regression test fires 30 concurrent writers at one workspace
          and checks the result is a single straight line.
        </p>
        <p className="text-stone-700 leading-relaxed mb-6">
          You can check any export yourself, with no access to Conduct
          at all:
        </p>
        <pre className="bg-stone-950 text-stone-100 p-6 rounded-2xl overflow-x-auto text-sm font-mono leading-relaxed mb-6">
{`conduct audit verify /var/log/conduct/audit.ndjson`}
        </pre>
        <p className="text-stone-700 leading-relaxed mb-6">
          It recomputes every hash and walks every link. Add{" "}
          <code>--allow-gaps</code> when verifying a time window that
          doesn&apos;t start at the beginning of the workspace&apos;s
          history.
        </p>

        <h2 className="text-2xl font-bold text-stone-900 mt-12 mb-4">Why we&apos;re telling you</h2>
        <p className="text-stone-700 leading-relaxed mb-8">
          A tamper-evident log is only worth something if someone
          actually checks it. We checked ours, found two real problems,
          and fixed both before writing this post. Your SIEM now gets
          every decision, from every surface, in a chain you can verify
          without trusting us.
        </p>

        <div className="not-prose flex flex-wrap gap-3 mt-12 mb-8">
          <a
            href="https://github.com/sseshachala/conductai/blob/main/docs/reference/siem-feed.md"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg bg-stone-900 text-white px-5 py-3 text-sm font-semibold hover:bg-stone-800 transition-colors"
          >
            SIEM feed docs
          </a>
          <a
            href="https://pypi.org/project/conduct-cli/"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-stone-200 bg-white text-stone-700 px-5 py-3 text-sm font-semibold hover:border-stone-300 hover:shadow-sm transition-all"
          >
            conduct-cli on PyPI
          </a>
        </div>

        <div className="mt-16 pt-8 border-t border-stone-200">
          <CtaLink className="inline-flex items-center gap-2 rounded-xl bg-stone-900 text-white px-7 py-3.5 text-base font-semibold hover:bg-stone-700 transition-colors" />
        </div>
      </div>
    </article>
  )
}
