import type { Metadata } from "next";
import { generatePageMetadata, faqJsonLd } from "@/lib/metadata";
import { JsonLd } from "@/components/JsonLd";

export const metadata: Metadata = generatePageMetadata({
  title: "Pricing",
  description:
    "RecruitTech pricing plans — Starter, Growth and Enterprise. Transparent per-seat pricing with optional add-ons for ATS sync, AI interviews and background checks.",
  path: "/pricing",
  jsonLd: [
    faqJsonLd([
      {
        question: "How is RecruitTech priced?",
        answer:
          "Per active talent partner seat, billed monthly or annually. Add-ons like ATS sync and AI interviews are usage-based.",
      },
      {
        question: "Is there a free trial?",
        answer: "Yes — 14-day pilot on the Growth plan with no credit card required.",
      },
    ]),
  ],
});

export default function PricingPage() {
  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "Product",
          name: "RecruitTech",
          description:
            "AI-powered talent platform with candidate matching, copilot dashboards, and multi-persona workflows.",
          brand: { "@type": "Brand", name: "RecruitTech" },
          offers: [
            {
              "@type": "Offer",
              name: "Starter",
              price: "29",
              priceCurrency: "USD",
              category: "subscription",
            },
            {
              "@type": "Offer",
              name: "Growth",
              price: "99",
              priceCurrency: "USD",
              category: "subscription",
            },
            {
              "@type": "Offer",
              name: "Enterprise",
              priceSpecification: {
                "@type": "PriceSpecification",
                priceCurrency: "USD",
                description: "Contact sales",
              },
            },
          ],
        }}
        id="jsonld-pricing-product"
      />
      <main className="mx-auto max-w-5xl px-4 py-12 sm:px-6 sm:py-16">
        <header className="mb-10 text-center">
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            Plans &amp; Pricing
          </h1>
          <p className="mt-3 text-sm text-muted-foreground sm:text-base">
            Transparent pricing built for talent teams of every size — from
            solo recruiters to global agencies.
          </p>
        </header>

        <section
          aria-labelledby="plans"
          className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3"
        >
          <article className="rounded-lg border p-6">
            <h2 id="plans" className="text-lg font-semibold">
              Starter
            </h2>
            <p className="mt-2 text-3xl font-bold">
              $29<span className="text-sm font-medium">/seat/mo</span>
            </p>
            <ul className="mt-4 space-y-1 text-sm text-muted-foreground">
              <li>Up to 200 candidates / mo</li>
              <li>Standard AI matching</li>
              <li>Email support</li>
            </ul>
            <a
              href="/login?plan=starter"
              className="mt-6 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            >
              Start free trial
            </a>
          </article>
          <article className="rounded-lg border p-6 ring-2 ring-primary">
            <h2 className="text-lg font-semibold">Growth</h2>
            <p className="mt-2 text-3xl font-bold">
              $99<span className="text-sm font-medium">/seat/mo</span>
            </p>
            <ul className="mt-4 space-y-1 text-sm text-muted-foreground">
              <li>Up to 5,000 candidates / mo</li>
              <li>Hybrid semantic + structured matching</li>
              <li>AI interviews &amp; scheduling</li>
              <li>Priority support</li>
            </ul>
            <a
              href="/login?plan=growth"
              className="mt-6 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            >
              Start free trial
            </a>
          </article>
          <article className="rounded-lg border p-6">
            <h2 className="text-lg font-semibold">Enterprise</h2>
            <p className="mt-2 text-3xl font-bold">Custom</p>
            <ul className="mt-4 space-y-1 text-sm text-muted-foreground">
              <li>Unlimited candidates</li>
              <li>SSO/SAML, audit log, DLP</li>
              <li>Dedicated success manager</li>
              <li>On-prem / private cloud options</li>
            </ul>
            <a
              href="/login?plan=enterprise"
              className="mt-6 inline-block rounded-md border border-primary px-4 py-2 text-sm font-medium text-primary"
            >
              Contact sales
            </a>
          </article>
        </section>
      </main>
    </>
  );
}
