import * as React from "react";
import { JsonLd } from "@/components/JsonLd";
import {
  organizationJsonLd,
  breadcrumbJsonLd,
  faqJsonLd,
  jobPostingJsonLd,
} from "@/lib/metadata";

/**
 * <Seo /> — server-component wrapper that renders one or more Schema.org
 * JSON-LD payloads for rich results (breadcrumbs, FAQ, JobPosting,
 * Organization). Pair with generatePageMetadata() in the same page.tsx.
 *
 * This component renders ONLY structured data; the <title>/OG/Twitter
 * metadata is emitted by Next's Metadata API from generateMetadata().
 *
 * Usage (inside a server component, returned from the page body):
 *
 *   <Seo
 *     breadcrumbs={[{ name: "Home", url: SITE_URL }, { name: "Pricing", url: `${SITE_URL}/pricing` }]}
 *     faq={[{ question: "...", answer: "..." }]}
 *   />
 */
export interface SeoProps {
  /** Breadcrumb trail (root-first). */
  breadcrumbs?: Array<{ name: string; url: string }>;
  /** FAQ entries for FAQPage rich results. */
  faq?: Array<{ question: string; answer: string }>;
  /** JobPosting payload (for public job detail pages). */
  jobPosting?: Parameters<typeof jobPostingJsonLd>[0];
  /** Render the global Organization payload (home page only). */
  organization?: boolean;
  /** Extra arbitrary JSON-LD objects. */
  extra?: Record<string, unknown> | Record<string, unknown>[];
}

export function Seo({
  breadcrumbs,
  faq,
  jobPosting,
  organization = false,
  extra,
}: SeoProps) {
  const payloads: Record<string, unknown>[] = [];

  if (organization) payloads.push(organizationJsonLd());
  if (breadcrumbs?.length) payloads.push(breadcrumbJsonLd(breadcrumbs));
  if (faq?.length) payloads.push(faqJsonLd(faq));
  if (jobPosting) payloads.push(jobPostingJsonLd(jobPosting));
  if (extra) {
    const arr = Array.isArray(extra) ? extra : [extra];
    payloads.push(...arr);
  }

  if (payloads.length === 0) return null;

  return <JsonLd data={payloads} id="seo-jsonld" />;
}

export default Seo;
