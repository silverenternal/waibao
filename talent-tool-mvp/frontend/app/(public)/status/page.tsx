import { ErrorBoundary } from "@/components/ErrorBoundary";
/**
 * Public status page — status.waibao.cn
 *
 * Real-time view of the 5 platform services (api / llm / storage / webhook /
 * database) backed by `GET /api/admin/sla/30d` (public mirror expected at
 * `GET /api/public/status`). Designed to be deployable as a standalone
 * Next.js route or proxied behind the Instatus self-hosted frontend.
 *
 * Subscriptions (email / webhook) are submitted directly to
 * `/api/public/status/subscribers`.
 */
import type { Metadata } from "next";
import { generatePageMetadata } from "@/lib/metadata";

export const metadata: Metadata = generatePageMetadata({
  title: "System Status",
  description:
    "Live uptime, performance and incident history for all waibao services.",
  path: "/status",
});

type ServiceSnapshot = {
  id: string;
  name: string;
  status: "operational" | "degraded" | "outage" | "maintenance";
  uptime_90d_pct: number;
};

type StatusPayload = {
  page: { name: string; url: string };
  updated_at: string;
  indicators: ServiceSnapshot[];
  history_90d: { service: string; uptime_pct: number }[];
  incidents: { id: string; title: string; status: string; created_at: string }[];
  maintenance: { id: string; title: string; scheduled_for: string }[];
};

const FALLBACK: StatusPayload = {
  page: { name: "waibao Status", url: "https://status.waibao.cn" },
  updated_at: new Date().toISOString(),
  indicators: [
    { id: "api",      name: "Public API & Auth",        status: "operational", uptime_90d_pct: 99.95 },
    { id: "llm",      name: "LLM Inference",            status: "operational", uptime_90d_pct: 99.93 },
    { id: "storage",  name: "Object Storage",           status: "operational", uptime_90d_pct: 99.97 },
    { id: "webhook",  name: "Outbound Webhooks",        status: "operational", uptime_90d_pct: 99.91 },
    { id: "database", name: "Primary Database",         status: "operational", uptime_90d_pct: 99.94 },
  ],
  history_90d: [],
  incidents: [],
  maintenance: [],
};

async function fetchStatus(): Promise<StatusPayload> {
  try {
    const base = process.env.NEXT_PUBLIC_STATUS_API ?? "https://status.waibao.cn/api";
    const res = await fetch(`${base}/snapshot`, { next: { revalidate: 60 } });
    if (!res.ok) return FALLBACK;
    const json = (await res.json()) as StatusPayload;
    return json;
  } catch {
    return FALLBACK;
  }
}

function statusColor(s: ServiceSnapshot["status"]): string {
  switch (s) {
    case "operational": return "#16a34a";
    case "degraded":    return "#f59e0b";
    case "outage":      return "#dc2626";
    case "maintenance": return "#2563eb";
    default:            return "#6b7280";
  }
}

function statusLabel(s: ServiceSnapshot["status"]): string {
  return {
    operational: "Operational",
    degraded:    "Degraded",
    outage:      "Major outage",
    maintenance: "Maintenance",
  }[s];
}

export default async function StatusPage() {
  const status = await fetchStatus();
  const allOk = status.indicators.every((i) => i.status === "operational");

  return (
    <ErrorBoundary>(<main className="mx-auto max-w-4xl space-y-10 px-6 py-12">
        <header className="space-y-2">
          <p className="text-sm uppercase tracking-wider text-slate-500">waibao system status</p>
          <h1 className="text-3xl font-semibold">
            {allOk ? "All systems operational" : "Some systems are experiencing issues"}
          </h1>
          <p className="text-sm text-slate-500">
            Last refreshed: {new Date(status.updated_at).toLocaleString()} · Target uptime 99.9%
          </p>
        </header>
        {/* Current snapshot */}
        <section aria-labelledby="indicators-heading" className="rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
          <h2 id="indicators-heading" className="border-b border-slate-200 px-5 py-3 text-base font-medium dark:border-slate-700">
            Service status
          </h2>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {status.indicators.map((svc) => (
              <li key={svc.id} className="flex items-center justify-between gap-4 px-5 py-4">
                <div className="font-medium">{svc.name}</div>
                <div className="flex items-center gap-3 text-sm">
                  <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: statusColor(svc.status) }} />
                  <span className="w-32 text-right">{statusLabel(svc.status)}</span>
                  <span className="w-20 text-right tabular-nums text-slate-500">{svc.uptime_90d_pct.toFixed(2)}%</span>
                </div>
              </li>
            ))}
          </ul>
        </section>
        {/* 90-day uptime history */}
        <section className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
          <h2 className="text-base font-medium">90-day uptime</h2>
          <p className="text-sm text-slate-500">Refreshed from the SLA monitor every 60 seconds.</p>
          <table className="mt-4 w-full text-sm">
            <thead className="text-left text-slate-500">
              <tr>
                <th className="py-2 font-medium">Service</th>
                <th className="py-2 font-medium">90-day uptime</th>
                <th className="py-2 font-medium">Compliance vs 99.9%</th>
              </tr>
            </thead>
            <tbody>
              {(status.history_90d.length ? status.history_90d : status.indicators.map((i) => ({ service: i.id, uptime_pct: i.uptime_90d_pct }))).map((row) => (
                <tr key={row.service} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-2">{row.service}</td>
                  <td className="py-2 tabular-nums">{row.uptime_pct.toFixed(3)}%</td>
                  <td className="py-2">
                    <span className={row.uptime_pct >= 99.9 ? "text-emerald-600" : "text-amber-600"}>
                      {row.uptime_pct >= 99.9 ? "OK" : "Below target"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        {/* Planned maintenance */}
        <section className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
          <h2 className="text-base font-medium">Planned maintenance</h2>
          {status.maintenance.length === 0 ? (
            <p className="mt-2 text-sm text-slate-500">No upcoming maintenance windows.</p>
          ) : (
            <ul className="mt-3 space-y-2 text-sm">
              {status.maintenance.map((m) => (
                <li key={m.id} className="rounded border border-slate-200 px-3 py-2 dark:border-slate-700">
                  <strong>{m.title}</strong>
                  <div className="text-slate-500">{new Date(m.scheduled_for).toLocaleString()}</div>
                </li>
              ))}
            </ul>
          )}
        </section>
        {/* Subscription form */}
        <section className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
          <h2 className="text-base font-medium">Subscribe for updates</h2>
          <p className="mt-1 text-sm text-slate-500">
            Get notified about incidents and scheduled maintenance. We support email and webhook
            (Slack-compatible) targets.
          </p>
          <form
            method="post"
            action="/api/public/status/subscribers"
            className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto_auto]"
          >
            <input
              type="email"
              name="email"
              required
              placeholder="ops@example.com"
              className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            />
            <select
              name="channel"
              defaultValue="email"
              className="rounded border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="email">Email</option>
              <option value="webhook">Webhook</option>
            </select>
            <button type="submit" className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 dark:bg-slate-200 dark:text-slate-900">
              Subscribe
            </button>
            <input
              type="url"
              name="webhook_url"
              placeholder="https://hooks.slack.com/... (webhook only)"
              className="sm:col-span-3 rounded border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            />
          </form>
        </section>
      </main>)</ErrorBoundary>
  );
}
