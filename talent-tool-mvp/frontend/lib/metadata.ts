import type { Metadata } from "next";
import type { OpenGraph } from "next/dist/lib/metadata/types/opengraph-types";
import type { Twitter } from "next/dist/lib/metadata/types/twitter-types";

/**
 * metadata.ts — central SEO helper.
 *
 * Use generatePageMetadata() in every page.tsx (server component) to ensure
 * consistent title template, OpenGraph, Twitter cards, canonical URLs and
 * robots directives. Use generatePrivacyMetadata() for protected routes to
 * emit "title only" metadata (noindex, no description).
 */

export const SITE_NAME = "RecruitTech";
export const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL || "https://recruittech.example.com";
export const DEFAULT_LOCALE = "en";
export const SUPPORTED_LOCALES = ["en", "zh", "ja"] as const;
export const BRAND_DESCRIPTION =
  "AI-powered talent platform: intelligent candidate matching, copilot dashboards, and multi-persona workflows for modern recruitment.";

export interface PageMetadataInput {
  /** Page-specific title (without brand suffix). */
  title: string;
  /** Short page description, < 160 chars. */
  description?: string;
  /** Canonical path, e.g. "/legal/privacy". Defaults to current pathname. */
  path?: string;
  /** OG image override (absolute URL or path under /public). */
  ogImage?: string;
  /** Robots override, defaults to index,follow. */
  robots?: Metadata["robots"];
  /** Locale, default "en". */
  locale?: (typeof SUPPORTED_LOCALES)[number];
  /** Schema.org JSON-LD payloads to render via <JsonLd />. */
  jsonLd?: Record<string, unknown>[];
  /** Whether this is the canonical home route (true adds og:type=website). */
  isHome?: boolean;
  /** SEO keywords (rendered as <meta name="keywords">). */
  keywords?: string[];
}

export function buildCanonical(path: string): string {
  const cleaned = path.startsWith("/") ? path : `/${path}`;
  return `${SITE_URL}${cleaned}`;
}

export function buildOgImage(path?: string): string {
  if (path && /^https?:\/\//.test(path)) return path;
  const suffix = path || "/og-default.png";
  return `${SITE_URL}${suffix.startsWith("/") ? suffix : `/${suffix}`}`;
}

export function generatePageMetadata(input: PageMetadataInput): Metadata {
  const {
    title,
    description = BRAND_DESCRIPTION,
    path = "/",
    ogImage,
    robots,
    locale = DEFAULT_LOCALE,
    isHome = false,
    keywords,
  } = input;

  const fullTitle = `${title} | ${SITE_NAME}`;
  const canonical = buildCanonical(path);
  const ogImageUrl = buildOgImage(ogImage);

  const openGraph: OpenGraph = {
    type: isHome ? "website" : "article",
    siteName: SITE_NAME,
    title: fullTitle,
    description,
    url: canonical,
    locale,
    images: [{ url: ogImageUrl, width: 1200, height: 630, alt: title }],
  };

  const twitter: Twitter = {
    card: "summary_large_image",
    title: fullTitle,
    description,
    images: [ogImageUrl],
  };

  return {
    title: fullTitle,
    description,
    keywords: keywords?.length ? keywords : undefined,
    alternates: {
      canonical,
      languages: Object.fromEntries(
        SUPPORTED_LOCALES.map((l) => [l, buildCanonical(`/${l}${path}`)])
      ),
    },
    openGraph,
    twitter,
    robots: robots ?? { index: true, follow: true },
    metadataBase: new URL(SITE_URL),
  };
}

/**
 * Alias matching the task spec naming convention. Identical to
 * {@link generatePageMetadata}. Prefer the explicit name in new code.
 */
export const generateMetadata = generatePageMetadata;

/**
 * i18n-aware variant. Accepts a translations map (the part of the messages
 * bundle that contains title/description/keywords for the page) and the
 * current locale, then forwards to {@link generatePageMetadata}.
 *
 * Example:
 *   export async function generateMetadata() {
 *     const locale = await getLocale();
 *     const t = (await getMessages()).seo?.pricing ?? {};
 *     return generateI18nMetadata({ path: "/pricing", namespace: "pricing", locale, t });
 *   }
 */
export interface I18nMetadataInput extends Omit<PageMetadataInput, "title" | "description" | "keywords"> {
  /** Page namespace key into the translations map. */
  namespace: string;
  /** Locale for OG locale tag. */
  locale?: (typeof SUPPORTED_LOCALES)[number];
  /** Translations for this page: { title, description, keywords? }. */
  t: { title?: string; description?: string; keywords?: string[] | string };
}

export function generateI18nMetadata(input: I18nMetadataInput): Metadata {
  const { namespace, t, ...rest } = input;
  const keywords = Array.isArray(t.keywords)
    ? t.keywords
    : typeof t.keywords === "string"
      ? t.keywords.split(",").map((k) => k.trim()).filter(Boolean)
      : undefined;
  return generatePageMetadata({
    ...rest,
    title: t.title ?? namespace,
    description: t.description,
    keywords,
  });
}

/**
 * Privacy-preserving variant — title only.
 *
 * For protected/authenticated routes. Drops description, og, twitter,
 * and disallows indexing. Title still flows into <title> and browser tab.
 */
export function generatePrivacyMetadata(title: string): Metadata {
  return {
    title: `${title} | ${SITE_NAME}`,
    robots: {
      index: false,
      follow: false,
      nocache: true,
      googleBot: { index: false, follow: false },
    },
    // Explicit suppression of previews.
    openGraph: { title: `${title} | ${SITE_NAME}`, siteName: SITE_NAME },
    twitter: { card: "summary", title: `${title} | ${SITE_NAME}` },
  };
}

export interface JobPostingJsonLdInput {
  title: string;
  description: string;
  datePosted: string; // ISO-8601
  organizationName: string;
  organizationUrl: string;
  jobLocation?: string;
  employmentType?: string;
  baseSalary?: { currency: string; minValue: number; maxValue: number; unitText: string };
  validThrough?: string;
}

export function jobPostingJsonLd(input: JobPostingJsonLdInput) {
  return {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    title: input.title,
    description: input.description,
    datePosted: input.datePosted,
    validThrough: input.validThrough,
    employmentType: input.employmentType,
    hiringOrganization: {
      "@type": "Organization",
      name: input.organizationName,
      sameAs: input.organizationUrl,
    },
    jobLocation: input.jobLocation
      ? {
          "@type": "Place",
          address: { "@type": "PostalAddress", addressLocality: input.jobLocation },
        }
      : undefined,
    baseSalary: input.baseSalary
      ? {
          "@type": "MonetaryAmount",
          currency: input.baseSalary.currency,
          value: {
            "@type": "QuantitativeValue",
            minValue: input.baseSalary.minValue,
            maxValue: input.baseSalary.maxValue,
            unitText: input.baseSalary.unitText,
          },
        }
      : undefined,
  };
}

export function organizationJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: SITE_NAME,
    url: SITE_URL,
    logo: `${SITE_URL}/icons/icon-512.png`,
    sameAs: [
      "https://www.linkedin.com/company/recruittech",
      "https://twitter.com/recruittech",
    ],
  };
}

export function breadcrumbJsonLd(
  items: Array<{ name: string; url: string }>
) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((it, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: it.name,
      item: it.url,
    })),
  };
}

export function faqJsonLd(
  items: Array<{ question: string; answer: string }>
) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((q) => ({
      "@type": "Question",
      name: q.question,
      acceptedAnswer: { "@type": "Answer", text: q.answer },
    })),
  };
}
