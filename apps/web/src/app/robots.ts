import type { MetadataRoute } from "next"

// Audit U08: robots policy missed several authenticated route families
// added after this file last shipped. Belt-and-braces against
// (app)/layout.tsx's noindex header — a good crawler respects both;
// a rogue one respects at most robots.txt.
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
          // Added — every (app) route below the ones the file already had.
          "/agent-identity/",
          "/cli-auth/",
          "/credentials/",
          "/lens/",
          "/logs/",
          "/marketplace/",
          "/packs/",
          "/theguard/",
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
