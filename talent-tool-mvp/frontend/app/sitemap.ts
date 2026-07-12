import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/metadata";

/**
 * sitemap.ts — Next App Router sitemap endpoint.
 *
 * Combines static public routes with dynamic data-backed routes
 * (legal pages, public landing pages). Authenticated routes are NOT
 * included (they're behind login and emit noindex).
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();

  const staticRoutes: MetadataRoute.Sitemap = [
    {
      url: `${SITE_URL}/`,
      lastModified: now,
      changeFrequency: "weekly",
      priority: 1.0,
      alternates: {
        languages: {
          en: `${SITE_URL}/en`,
          zh: `${SITE_URL}/zh`,
          ja: `${SITE_URL}/ja`,
        },
      },
    },
    {
      url: `${SITE_URL}/pricing`,
      lastModified: now,
      changeFrequency: "weekly",
      priority: 0.9,
    },
  ];

  const legalSlugs = ["privacy", "terms", "cookies", "dpa"];
  const legalRoutes: MetadataRoute.Sitemap = legalSlugs.map((slug) => ({
    url: `${SITE_URL}/legal/${slug}`,
    lastModified: now,
    changeFrequency: "monthly",
    priority: 0.6,
  }));

  // Dynamic additions — fetch from public APIs at build time.
  let jobs: MetadataRoute.Sitemap = [];
  try {
    const apiBase =
      process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
    const res = await fetch(`${apiBase}/api/public/roles`, {
      // Re-build every 5 minutes via revalidate elsewhere; default cache here.
      next: { revalidate: 300 },
    });
    if (res.ok) {
      const data: any = await res.json();
      const roles: any[] = data?.roles ?? data?.items ?? [];
      jobs = roles.slice(0, 500).map((r: any) => ({
        url: `${SITE_URL}/jobs/${r.id ?? r.slug}`,
        lastModified: new Date(r.updated_at ?? now),
        changeFrequency: "daily",
        priority: 0.8,
      }));
    }
  } catch {
    // Network errors should not break sitemap generation.
    jobs = [];
  }

  return [...staticRoutes, ...legalRoutes, ...jobs];
}
