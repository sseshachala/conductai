/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  serverExternalPackages: [],
  webpack: (config) => {
    // .md imports return raw string contents, inlined at build time.
    // Used by /docs to render docs/reference/*.md as the single source of truth.
    config.module.rules.push({ test: /\.md$/, type: "asset/source" })
    return config
  },
  async redirects() {
    return [
      { source: "/docs/self-hosted", destination: "/deployment", permanent: true },
      { source: "/docs/templates", destination: "/registry", permanent: true },
      {
        source: "/products/agent-booster",
        destination: "/tools/agent-booster",
        permanent: true,
      },
      { source: "/guard-landing", destination: "/guard", permanent: true },
      { source: "/playbooks",   destination: "/registry", permanent: true },
      { source: "/templates",   destination: "/registry", permanent: true },
      { source: "/marketplace", destination: "/registry", permanent: true },
      { source: "/marketplace/:slug*", destination: "/packs/:slug*", permanent: true },
      { source: "/theguard/activity", destination: "/logs/guard", permanent: true },
      { source: "/runs", destination: "/logs/runs", permanent: true },
      { source: "/observability", destination: "/logs/observability", permanent: true },
    ]
  },
  async rewrites() {
    return [
      // #1712 Track 1 — `curl -fsSL conductai.ai/install | sh` serves the
      // shell installer from public/install.sh. Rewrite (not redirect) so
      // the URL in marketing copy stays `/install` — clean and stable.
      { source: "/install", destination: "/install.sh" },
    ]
  },
  async headers() {
    return ["/install", "/install.sh"].map((source) => ({
      source,
      headers: [{ key: "Content-Type", value: "text/x-shellscript; charset=utf-8" }],
    }))
  },
}

module.exports = nextConfig
