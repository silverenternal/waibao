import type { Metadata } from "next";
import { generatePageMetadata, faqJsonLd } from "@/lib/metadata";
import { JsonLd } from "@/components/JsonLd";

export const metadata: Metadata = generatePageMetadata({
  title: "Pricing — SaaS Subscription Plans",
  description:
    "Transparent tiered pricing for RecruitTech — Starter for solo recruiters, Growth for talent teams, Enterprise with SSO, audit and SLA. Pay monthly or annually with a 14-day pilot.",
  path: "/pricing",
  jsonLd: [
    faqJsonLd([
      {
        question: "How is RecruitTech priced?",
        answer:
          "Per active talent-partner seat, billed monthly or annually with a 20% annual discount. All plans include multi-tenant RLS isolation, audit trail, GDPR/PIPL/CCPA tools, and the open REST API.",
      },
      {
        question: "Is there a free trial?",
        answer:
          "Yes — 14-day pilot on Growth, no credit card required. Enterprise includes a 30-day paid pilot under a signed pilot agreement.",
      },
      {
        question: "Can I switch plans?",
        answer:
          "Yes — upgrade any time (pro-rated, immediate effect). Downgrade takes effect at the end of the current billing cycle and never deletes your data.",
      },
      {
        question: "What does Enterprise include?",
        answer:
          "Unlimited seats, dedicated tenant + optional VPC, SSO/SAML + SCIM, MFA enforcement, 99.9% SLA with credits, 24/7 priority support with dedicated CSM and TAM, custom RLS policies, BYOK encryption, audit-log retention up to 7 years.",
      },
      {
        question: "What regions are available?",
        answer:
          "Growth: CN, HK, SG. Enterprise: CN, HK, SG, EU (Frankfurt), plus optional customer-specified regions. Self-hosted available on Enterprise and OEM.",
      },
      {
        question: "How is data protected?",
        answer:
          "Multi-tenant Row-Level Security at the Postgres layer, AES-256 at rest, TLS 1.3 in transit, GDPR/PIPL/CCPA APIs for export and forget, SOC 2 Type II and ISO 27001 reports available under NDA.",
      },
    ]),
  ],
});

type Plan = {
  id: "starter" | "growth" | "enterprise";
  name: string;
  tagline: string;
  monthly: number | null;
  badge?: string;
  highlight?: boolean;
  cta: { label: string; href: string; variant: "primary" | "secondary" };
  features: string[];
  limits: { label: string; value: string }[];
  sla: string;
};

const PLANS: Plan[] = [
  {
    id: "starter",
    name: "Starter",
    tagline: "Solo recruiters & small teams",
    monthly: 29,
    cta: { label: "Start 14-day trial", href: "/login?plan=starter", variant: "primary" },
    limits: [
      { label: "Candidates", value: "200 / mo" },
      { label: "AI interview", value: "10 / mo" },
      { label: "API rate", value: "5 RPS · 50k / day" },
    ],
    sla: "99.5% uptime · 48h ticket response",
    features: [
      "Standard semantic matching",
      "Email support",
      "GDPR/PIPL/CCPA export & forget",
      "Audit log 90 days",
      "1 ATS integration (Greenhouse or Lever)",
    ],
  },
  {
    id: "growth",
    name: "Growth",
    tagline: "Talent teams scaling up",
    monthly: 99,
    badge: "Most popular",
    highlight: true,
    cta: { label: "Start 14-day trial", href: "/login?plan=growth", variant: "primary" },
    limits: [
      { label: "Candidates", value: "5,000 / mo" },
      { label: "AI interview", value: "100 / mo" },
      { label: "API rate", value: "30 RPS · 500k / day" },
    ],
    sla: "99.9% uptime · 8h ticket response",
    features: [
      "Hybrid semantic + structured matching with rerank",
      "RAG with citations (10 docs / query)",
      "Multi-agent workflows (5 built-in)",
      "SSO via Google / Microsoft",
      "Audit log 1 year",
      "Regions: CN · HK · SG",
      "Priority support",
    ],
  },
  {
    id: "enterprise",
    name: "Enterprise",
    tagline: "Large orgs, regulated industries",
    monthly: null,
    cta: { label: "Contact sales", href: "/login?plan=enterprise", variant: "secondary" },
    limits: [
      { label: "Candidates", value: "Unlimited" },
      { label: "AI interview", value: "Unlimited" },
      { label: "API rate", value: "200 RPS · bespoke" },
    ],
    sla: "99.9% + 99.95% backup · 1h P0 response",
    features: [
      "Dedicated tenant + optional VPC",
      "SSO/SAML + SCIM, MFA + FIDO2 enforced",
      "Custom RLS policies",
      "BYOK encryption (AWS KMS / Aliyun KMS)",
      "Audit log up to 7 years",
      "All regions incl. EU + customer-specified",
      "24/7 phone / DingTalk / Feishu support",
      "Dedicated CSM + TAM, QBR",
    ],
  },
];

export default function PricingPage() {
  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "Product",
          name: "RecruitTech",
          description:
            "AI-powered talent platform with candidate matching, RAG, multi-agent workflows, multi-tenant isolation, audit trail, GDPR/PIPL/CCPA tools, and 99.9% SLA.",
          brand: { "@type": "Brand", name: "RecruitTech" },
          offers: PLANS.map((p) =>
            p.monthly === null
              ? {
                  "@type": "Offer",
                  name: p.name,
                  priceSpecification: {
                    "@type": "PriceSpecification",
                    priceCurrency: "USD",
                    description: "Contact sales",
                  },
                }
              : {
                  "@type": "Offer",
                  name: p.name,
                  price: String(p.monthly),
                  priceCurrency: "USD",
                  category: "subscription",
                }
          ),
        }}
        id="jsonld-pricing-product"
      />

      <main className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-20">
        {/* Header */}
        <header className="mb-12 text-center">
          <span className="inline-block rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
            v7.0 · SaaS + Multi-tenant + SLA
          </span>
          <h1 className="mt-4 text-4xl font-bold tracking-tight sm:text-5xl">
            Pricing that scales with your team
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-base text-muted-foreground sm:text-lg">
            Three tiers, transparent pricing, billed per seat. Every plan
            includes multi-tenant RLS isolation, the audit trail, GDPR/PIPL/CCPA
            APIs, and the open REST API.
          </p>
          <p className="mt-3 text-sm text-muted-foreground">
            Already on v6?{" "}
            <a href="/login" className="text-primary hover:underline">
              Sign in
            </a>{" "}
            — your data and integrations are preserved.
          </p>
        </header>

        {/* Plan grid */}
        <section
          aria-labelledby="plans-heading"
          className="grid gap-6 md:grid-cols-3"
        >
          <h2 id="plans-heading" className="sr-only">
            Subscription plans
          </h2>
          {PLANS.map((plan) => (
            <article
              key={plan.id}
              aria-labelledby={`plan-${plan.id}`}
              className={[
                "relative flex flex-col rounded-2xl border p-6 shadow-sm transition",
                plan.highlight
                  ? "border-primary ring-2 ring-primary/50 shadow-primary/10"
                  : "border-border hover:border-primary/30",
              ].join(" ")}
              data-testid={`plan-card-${plan.id}`}
            >
              {plan.badge ? (
                <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-0.5 text-xs font-semibold text-primary-foreground">
                  {plan.badge}
                </span>
              ) : null}
              <div className="mb-4">
                <h3
                  id={`plan-${plan.id}`}
                  className="text-lg font-semibold tracking-tight"
                >
                  {plan.name}
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  {plan.tagline}
                </p>
              </div>
              <div className="mb-4">
                {plan.monthly === null ? (
                  <p className="text-3xl font-bold">Custom</p>
                ) : (
                  <>
                    <p className="text-3xl font-bold">
                      ${plan.monthly}
                      <span className="text-sm font-medium text-muted-foreground">
                        {" "}
                        / seat / mo
                      </span>
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Annual billing saves 20% · USD · taxes excluded
                    </p>
                  </>
                )}
              </div>
              <ul className="mb-4 space-y-1 text-sm" aria-label="Plan limits">
                {plan.limits.map((l) => (
                  <li
                    key={l.label}
                    className="flex justify-between border-b border-border/50 py-1"
                  >
                    <span className="text-muted-foreground">{l.label}</span>
                    <span className="font-medium">{l.value}</span>
                  </li>
                ))}
              </ul>
              <ul
                className="mb-6 space-y-2 text-sm"
                aria-label={`${plan.name} features`}
              >
                {plan.features.map((f) => (
                  <li key={f} className="flex gap-2">
                    <CheckIcon />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <div className="mb-4 rounded-md bg-muted/50 p-3 text-xs">
                <span className="font-semibold">SLA:</span> {plan.sla}
              </div>
              <a
                href={plan.cta.href}
                className={[
                  "mt-auto inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition",
                  plan.cta.variant === "primary"
                    ? "bg-primary text-primary-foreground hover:bg-primary/90"
                    : "border border-primary text-primary hover:bg-primary/10",
                ].join(" ")}
              >
                {plan.cta.label}
              </a>
            </article>
          ))}
        </section>

        {/* Trust strip */}
        <section
          aria-labelledby="trust-heading"
          className="mt-14 flex flex-wrap items-center justify-center gap-3 text-xs text-muted-foreground"
        >
          <h2 id="trust-heading" className="sr-only">
            Trust and compliance
          </h2>
          <TrustBadge>Multi-tenant RLS</TrustBadge>
          <TrustBadge>SOC 2 Type II</TrustBadge>
          <TrustBadge>ISO 27001</TrustBadge>
          <TrustBadge>GDPR / PIPL / CCPA</TrustBadge>
          <TrustBadge>99.9% SLA</TrustBadge>
          <TrustBadge>SAML / SCIM</TrustBadge>
        </section>

        {/* FAQ */}
        <section
          aria-labelledby="faq-heading"
          className="mt-16 rounded-2xl border border-border bg-card p-6 sm:p-8"
        >
          <h2
            id="faq-heading"
            className="text-2xl font-semibold tracking-tight"
          >
            Frequently asked questions
          </h2>
          <dl className="mt-6 space-y-6 text-sm">
            <Faq
              q="Can I switch plans?"
              a="Yes — upgrade any time and we'll pro-rate the difference. Downgrade takes effect at the end of your current cycle and never deletes your data."
            />
            <Faq
              q="What payment methods are supported?"
              a="Credit card (Visa, Mastercard, Amex) for self-serve, wire transfer for Enterprise contracts. Invoices in CNY, USD, EUR, SGD, HKD."
            />
            <Faq
              q="Is there a refund policy?"
              a="Self-serve plans have a 7-day no-questions-asked refund on first order. Enterprise refunds follow your master service agreement."
            />
            <Faq
              q="Where is data stored?"
              a="Choose from CN (Beijing), HK (Hong Kong), SG (Singapore), or EU (Frankfurt) for SaaS plans. Self-hosted deployments are fully under your control."
            />
            <Faq
              q="Do you offer a non-profit / startup discount?"
              a="Yes — qualified non-profits and early-stage startups (< 2 years, < $2M ARR) receive 30% off Starter or Growth for 12 months."
            />
          </dl>
        </section>

        {/* CTA strip */}
        <section className="mt-16 rounded-2xl bg-gradient-to-br from-primary/20 via-primary/5 to-transparent p-8 text-center sm:p-12">
          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
            Not sure which plan fits?
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-sm text-muted-foreground sm:text-base">
            Book a 30-minute call with a solutions engineer. We&apos;ll
            recommend the right tier, walk through the API, and run a custom
            cost model.
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <a
              href="/login?plan=enterprise"
              className="inline-flex items-center justify-center rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              Book a 30-min call
            </a>
            <a
              href="/status"
              className="inline-flex items-center justify-center rounded-md border border-border bg-background px-5 py-2.5 text-sm font-medium hover:bg-muted"
            >
              View live status
            </a>
          </div>
        </section>
      </main>
    </>
  );
}

function CheckIcon() {
  return (
    <svg
      aria-hidden="true"
      className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2.5}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

function TrustBadge({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-background px-3 py-1">
      <svg
        aria-hidden="true"
        className="h-3 w-3 text-primary"
        viewBox="0 0 20 20"
        fill="currentColor"
      >
        <path
          fillRule="evenodd"
          d="M10 1l2.39 4.84L18 7l-4 3.9.94 5.5L10 13.9 5.06 16.4 6 10.9 2 7l5.61-1.16L10 1z"
          clipRule="evenodd"
        />
      </svg>
      {children}
    </span>
  );
}

function Faq({ q, a }: { q: string; a: string }) {
  return (
    <div>
      <dt className="font-semibold">{q}</dt>
      <dd className="mt-1 text-muted-foreground">{a}</dd>
    </div>
  );
}
