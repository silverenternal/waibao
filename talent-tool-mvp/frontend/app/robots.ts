import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/metadata";

/**
 * robots.ts — Next App Router robots.txt endpoint.
 *
 * Public routes are crawlable. Authenticated, API, and search endpoints
 * are disallowed to prevent indexing of private state and minimizing
 * index surface for paging/duplicate content.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/"],
        disallow: [
          "/api/",
          "/login",
          "/account/",
          "/mind/",
          "/mothership/",
          "/jobseeker/",
          "/employer/",
          "/realtime/",
          "/search/",
          "/_next/",
        ],
      },
      {
        userAgent: "GPTBot",
        disallow: "/",
      },
      {
        userAgent: "CCBot",
        disallow: "/",
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
