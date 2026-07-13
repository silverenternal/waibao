import type { Metadata } from "next";
import { PluginGrid } from "./_components/plugin-grid";
import { faqJsonLd, generatePageMetadata } from "@/lib/metadata";
import { JsonLd } from "@/components/JsonLd";

export const metadata: Metadata = generatePageMetadata({
  title: "Marketplace — Apps, integrations, automations",
  description:
    "Extend your RecruitTech workspace with 1-click installs, reviews, and built-in billing. Browse, search, and discover community plugins, integrations, and analytics apps.",
  path: "/marketplace",
  jsonLd: [
    faqJsonLd([
      {
        question: "What is the RecruitTech Marketplace?",
        answer:
          "It is a public catalog of third-party plugins and integrations built on top of the v6.0 Plugin SDK. Authors submit listings; admins review; tenants install with one click.",
      },
      {
        question: "How does 1-click install work?",
        answer:
          "The marketplace compiles a plugin.yaml manifest and hands it to the RecruitTech Plugin SDK runner. The plugin is sandboxed, loaded, and registered without restarting the workspace.",
      },
      {
        question: "Are paid plugins supported?",
        answer:
          "Yes — Stripe, WeChat Pay and Alipay are supported. The platform takes a 30% revenue share; authors get 70%. Refunds and webhook confirmation are built in.",
      },
      {
        question: "How do I publish my own plugin?",
        answer:
          "Sign in, register a developer app from the Developer Portal, then POST /api/marketplace/publish with the listing details. The team will review and approve within 1 business day.",
      },
    ]),
  ],
});

export default function MarketplacePage() {
  return (
    <main className="container mx-auto max-w-6xl px-4 py-12">
      <header className="mb-8 space-y-2">
        <p className="text-xs uppercase tracking-widest text-blue-600">
          Marketplace · v6.0 Plugin SDK
        </p>
        <h1 className="text-3xl font-bold text-slate-900 sm:text-4xl">
          Extend your workspace with apps and automations
        </h1>
        <p className="max-w-3xl text-base text-slate-600">
          Discover community-built plugins — DingTalk approvals, WeChat bridges,
          video interview integrations, custom analytics. Install with one click,
          review and rate what works, build a plugin of your own and earn
          revenue on every paid install.
        </p>
      </header>

      <section className="mb-10 grid gap-4 sm:grid-cols-3" data-testid="marketplace-stats">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-xs uppercase text-slate-500">Pricing</div>
          <div className="mt-1 text-2xl font-semibold text-slate-900">70/30</div>
          <p className="text-xs text-slate-500">
            Author revenue share / platform fee on paid plugins
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-xs uppercase text-slate-500">Runtime</div>
          <div className="mt-1 text-2xl font-semibold text-slate-900">
            Sandboxed
          </div>
          <p className="text-xs text-slate-500">
            Every plugin runs inside a ResourceMonitor / rlimit sandbox
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-xs uppercase text-slate-500">Review SLA</div>
          <div className="mt-1 text-2xl font-semibold text-slate-900">24h</div>
          <p className="text-xs text-slate-500">
            New listings reviewed by the moderation team within 1 business day
          </p>
        </div>
      </section>

      <PluginGrid />

      <section className="mt-12 rounded-lg border border-dashed border-slate-300 bg-slate-50 p-6 text-sm text-slate-600">
        <h2 className="text-lg font-semibold text-slate-900">
          Want to publish a plugin?
        </h2>
        <p className="mt-1 max-w-2xl">
          Visit the{" "}
          <a className="text-blue-600 underline" href="/developers">
            Developer Portal
          </a>{" "}
          to register an app and start building on the v6.0 Plugin SDK. Once
          your plugin passes review, it appears here in the public catalog.
        </p>
      </section>
    </main>
  );
}
