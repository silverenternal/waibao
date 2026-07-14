import { ErrorBoundary } from "@/components/ErrorBoundary";
import type { Metadata } from "next";
import { generatePageMetadata } from "@/lib/metadata";
import { SandboxPlayground } from "./_components/sandbox-playground";

export const metadata: Metadata = generatePageMetadata({
  title: "Sandbox — Developer Portal",
  description:
    "Run live API calls against a throwaway sandbox tenant. No keys required for read-only example calls.",
  path: "/developers/sandbox",
});

const PRESET_REQUESTS = [
  {
    label: "Whoami (live)",
    method: "GET",
    path: "/api/v2/version",
    body: undefined,
  },
  {
    label: "List candidates",
    method: "GET",
    path: "/api/v1/candidates?limit=5",
    body: undefined,
  },
  {
    label: "Open roles",
    method: "GET",
    path: "/api/v1/roles?status=open",
    body: undefined,
  },
  {
    label: "Create candidate (POST)",
    method: "POST",
    path: "/api/v1/candidates",
    body: JSON.stringify(
      {
        full_name: "Sandbox Tester",
        email: "sandbox@example.com",
        headline: "Demo candidate",
      },
      null,
      2,
    ),
  },
];

export default function SandboxPage() {
  return (
    <ErrorBoundary>(<main className="container mx-auto max-w-5xl px-4 py-12">
        <header className="mb-8 space-y-2">
          <p className="text-xs uppercase tracking-widest text-muted-foreground">
            Sandbox
          </p>
          <h1 className="text-3xl font-bold">Try the API in your browser</h1>
          <p className="max-w-2xl text-sm text-muted-foreground">
            Pick a preset (or paste your own request) and fire it against the
            sandbox tenant. Requests go through the same middleware stack as
            production traffic — you&apos;ll see the real headers, real quotas,
            and real deprecation markers.
          </p>
        </header>
        <SandboxPlayground presets={PRESET_REQUESTS} />
        <section className="mt-12 rounded-lg border border-amber-400 bg-amber-50 p-6 text-sm dark:bg-amber-950/30">
          <p className="font-semibold text-amber-900 dark:text-amber-100">
            Sandbox quotas
          </p>
          <ul className="ml-5 mt-2 list-disc space-y-1 text-amber-800 dark:text-amber-200">
            <li>60 requests per minute, per session.</li>
            <li>Synthetic data only — no real candidate PII.</li>
            <li>Resets every calendar day.</li>
          </ul>
        </section>
      </main>)</ErrorBoundary>
  );
}
