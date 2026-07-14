import { ErrorBoundary } from "@/components/ErrorBoundary";
import type { Metadata } from "next";
import { ApiReferenceExplorer } from "./_components/api-reference-explorer";
import { CodeExampleTabs } from "./_components/code-example-tabs";
import { faqJsonLd, generatePageMetadata } from "@/lib/metadata";
import { JsonLd } from "@/components/JsonLd";

export const metadata: Metadata = generatePageMetadata({
  title: "Developer Portal — Open API",
  description:
    "RecruitTech public API: register a developer app, mint API keys, OAuth 2.0, self-service webhooks, sandbox + live, OpenAPI docs and SDKs.",
  path: "/developers",
  jsonLd: [
    faqJsonLd([
      {
        question: "How do I get an API key?",
        answer:
          "Sign in to a workspace, register a developer app, then create a sandbox or live key. Live keys require completed billing.",
      },
      {
        question: "Do you support OAuth?",
        answer:
          "Yes — full RFC 6749 authorization code flow with PKCE (RFC 7636). Tokens are opaque (not JWT) and revoked server-side.",
      },
      {
        question: "Where is the OpenAPI spec?",
        answer:
          "Live at GET /openapi.json. We render it through Scalar (modern UI) and Swagger UI as a fallback.",
      },
      {
        question: "Are SDKs auto-generated?",
        answer:
          "Yes — Python, TypeScript and Go SDKs are produced by openapi-generator-cli on every release and shipped as GitHub Release assets.",
      },
    ]),
  ],
});

export default function DevelopersPage() {
  return (
    <ErrorBoundary>(<main className="container mx-auto max-w-6xl px-4 py-12">
        <header className="mb-10 space-y-4">
          <p className="text-xs uppercase tracking-widest text-muted-foreground">
            Developer Portal
          </p>
          <h1 className="text-4xl font-bold">RecruitTech Open API v3.0</h1>
          <p className="max-w-3xl text-lg text-muted-foreground">
            Build integrations that move candidates across ATS, HRIS, assessment and
            background-check systems. Register an app, mint a sandbox key in under a
            minute, then graduate to live when you&apos;re ready.
          </p>
          <div className="flex flex-wrap gap-3">
            <a
              href="/developers/keys"
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              Manage API Keys
            </a>
            <a
              href="/developers/sandbox"
              className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium hover:bg-muted"
            >
              Try Sandbox
            </a>
            <a
              href="/developers/webhooks"
              className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium hover:bg-muted"
            >
              Configure Webhooks
            </a>
            <a
              href="/openapi.json"
              className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium hover:bg-muted"
            >
              Download OpenAPI Spec
            </a>
          </div>
        </header>
        <section aria-labelledby="quickstart" className="mb-12">
          <h2 id="quickstart" className="mb-4 text-2xl font-semibold">
            Quick start
          </h2>
          <CodeExampleTabs />
        </section>
        <section aria-labelledby="api-reference" className="mb-12">
          <h2 id="api-reference" className="mb-4 text-2xl font-semibold">
            API Reference
          </h2>
          <p className="mb-4 max-w-2xl text-sm text-muted-foreground">
            Browse the full schema, search endpoints, view request / response
            examples and try live calls against the sandbox tenant. Scalar powers
            this surface; Swagger UI remains available at{" "}
            <a href="/docs" className="underline">/docs</a>.
          </p>
          <ApiReferenceExplorer />
        </section>
        <section aria-labelledby="sdks" className="mb-12">
          <h2 id="sdks" className="mb-4 text-2xl font-semibold">
            Official SDKs
          </h2>
          <p className="mb-4 max-w-2xl text-sm text-muted-foreground">
            Auto-generated from the OpenAPI spec on every release — published as
            GitHub Release assets. Install with your favourite language manager.
          </p>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {[
              { lang: "Python", install: "pip install recruittech" },
              { lang: "TypeScript", install: "npm install @recruittech/sdk" },
              { lang: "Go", install: "go get github.com/recruittech/sdk-go" },
            ].map((sdk) => (
              <div
                key={sdk.lang}
                className="rounded-lg border border-border bg-card p-4 text-sm"
              >
                <p className="mb-2 text-sm font-semibold">{sdk.lang}</p>
                <pre className="overflow-x-auto rounded bg-muted p-2 text-xs">
                  <code>{sdk.install}</code>
                </pre>
              </div>
            ))}
          </div>
        </section>
        <JsonLd
          data={{
            "@context": "https://schema.org",
            "@type": "WebAPI",
            name: "RecruitTech Developer API",
            documentation: "https://recruittech.com/developers",
          }}
        />
      </main>)</ErrorBoundary>
  );
}
