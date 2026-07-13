import type { Metadata } from "next";
import { generatePageMetadata } from "@/lib/metadata";
import { WebhookManager } from "./_components/webhook-manager";

export const metadata: Metadata = generatePageMetadata({
  title: "Webhook Subscriptions — Developer Portal",
  description:
    "Self-service webhook configuration: subscribe to platform events, receive HMAC-signed deliveries, rotate secrets.",
  path: "/developers/webhooks",
});

const SUPPORTED_EVENTS = [
  "candidate.created",
  "candidate.updated",
  "match.created",
  "role.created",
  "tickets.created",
  "ai_interview.completed",
  "offer.created",
];

export default function WebhooksPage() {
  return (
    <main className="container mx-auto max-w-5xl px-4 py-12">
      <header className="mb-8 space-y-2">
        <p className="text-xs uppercase tracking-widest text-muted-foreground">
          Webhooks
        </p>
        <h1 className="text-3xl font-bold">Subscribe to platform events</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Webhook deliveries are HMAC-SHA256 signed. The signature is sent in
          the <code>X-Webhook-Signature</code> header; verify it with your
          secret to confirm the call originated from RecruitTech.
        </p>
      </header>

      <WebhookManager supportedEvents={SUPPORTED_EVENTS} />

      <section className="mt-12 space-y-3 rounded-lg border border-border bg-card p-6 text-sm">
        <h2 className="text-base font-semibold">Verification recipe (Python)</h2>
        <pre className="overflow-x-auto rounded bg-muted p-3 text-xs">
          <code>{`import hmac, hashlib

def verify(signature: str, payload: bytes, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
`}</code>
        </pre>
        <p className="text-xs text-muted-foreground">
          Use a constant-time comparison — never compare with <code>==</code>.
        </p>
      </section>
    </main>
  );
}
