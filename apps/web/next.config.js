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
    ]
  },
}

module.exports = nextConfig
