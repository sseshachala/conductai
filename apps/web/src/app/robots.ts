import type { MetadataRoute } from "next"

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: [
          "/api/",
          "/audit/",
          "/dashboard/",
          "/governance/",
          "/integrations/",
          "/observability/",
          "/playbook-queue/",
          "/projects/",
          "/runs/",
          "/secure/",
          "/security/",
          "/settings/",
          "/setup/",
          "/workflows/",
          "/sign-in",
          "/sign-up",
          "/accept-invite",
        ],
      },
    ],
    sitemap: "https://conductai.ai/sitemap.xml",
    host: "https://conductai.ai",
  }
}
