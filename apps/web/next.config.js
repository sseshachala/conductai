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
}

module.exports = nextConfig
