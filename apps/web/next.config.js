/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  experimental: {
    serverComponentsExternalPackages: [],
  },
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
