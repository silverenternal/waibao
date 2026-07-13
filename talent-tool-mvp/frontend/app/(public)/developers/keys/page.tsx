import type { Metadata } from "next";
import { generatePageMetadata } from "@/lib/metadata";
import { ManageKeysClient } from "./_components/manage-keys-client";

export const metadata: Metadata = generatePageMetadata({
  title: "API Key Management — Developer Portal",
  description:
    "Mint, label and revoke API keys for your RecruitTech developer apps.",
  path: "/developers/keys",
});

export default function KeysPage() {
  return (
    <main className="container mx-auto max-w-5xl px-4 py-12">
      <header className="mb-8 space-y-2">
        <p className="text-xs uppercase tracking-widest text-muted-foreground">
          API Keys
        </p>
        <h1 className="text-3xl font-bold">Manage your keys</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Keys are issued per developer App. Sandbox keys are scoped to your
          scratch tenant and never touch real candidate data. Rotate anytime —
          the old key is invalidated instantly.
        </p>
      </header>

      <ManageKeysClient />

      <section className="mt-12 rounded-lg border border-border bg-card p-6 text-sm">
        <h2 className="mb-3 text-base font-semibold">
          Best practices
        </h2>
        <ul className="ml-5 list-disc space-y-1 text-sm text-muted-foreground">
          <li>Treat API keys like passwords. Never commit them.</li>
          <li>Prefer short-lived scoped keys over a single long-lived admin key.</li>
          <li>
            Use environment variables (e.g. <code>RECRUIT_API_KEY</code>) and rotate
            on personnel changes.
          </li>
          <li>
            Audit usage under <code>GET /api/developer/apps/&#123;id&#125;/keys/&#123;key_id&#125;/usage</code>.
          </li>
        </ul>
      </section>
    </main>
  );
}
