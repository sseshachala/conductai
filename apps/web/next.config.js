/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  serverExternalPackages: [],
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
      { source: "/marketplace/:slug*", destination: "/registry/:slug*", permanent: true },
      { source: "/theguard/activity", destination: "/logs/guard", permanent: true },
      { source: "/runs", destination: "/logs/runs", permanent: true },
      { source: "/observability", destination: "/logs/observability", permanent: true },
    ]
  },
}

module.exports = nextConfig
