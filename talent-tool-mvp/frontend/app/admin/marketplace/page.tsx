"use client";

/**
 * T2903 — Admin / Marketplace moderation page.
 *
 * Layout:
 *   - Header (title + queue count)
 *   - Pending plugins queue (approve / reject actions)
 *   - Audit log preview
 *
 * Mirrors /api/marketplace/admin/* endpoints. All endpoints require
 * the admin role; the FastAPI layer enforces this with a 403.
 */

import * as React from "react";
import {
  listPending,
  approvePlugin,
  rejectPlugin,
  getAuditLog,
  type MarketplacePlugin,
} from "@/lib/api-marketplace";

const API = "/api/marketplace/admin";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    credentials: "include",
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`HTTP ${r.status}: ${text}`);
  }
  return r.json();
}

interface AuditEntry {
  id?: string;
  plugin_id?: string;
  action: string;
  actor?: string;
  created_at?: number;
  detail?: Record<string, unknown>;
}

export default function AdminMarketplacePage() {
  const [pending, setPending] = React.useState<MarketplacePlugin[]>([]);
  const [audit, setAudit] = React.useState<AuditEntry[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = React.useState<
    Record<string, string>
  >({});
  const [busy, setBusy] = React.useState<string | null>(null);

  async function reload() {
    setLoading(true);
    setError(null);
    try {
      const [p, a] = await Promise.all([listPending(), getAuditLog(50)]);
      setPending(p.items || []);
      setAudit((a.items as unknown as AuditEntry[]) || []);
    } catch (err) {
      setError((err as Error).message || "Failed to load admin data");
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => {
    reload();
  }, []);

  async function handleApprove(plugin: MarketplacePlugin) {
    if (busy) return;
    setBusy(plugin.id);
    try {
      await approvePlugin(plugin.id);
      await reload();
    } catch (err) {
      setError((err as Error).message || "Approve failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleReject(plugin: MarketplacePlugin) {
    if (busy) return;
    const reason = (rejectionReason[plugin.id] || "").trim();
    if (!reason) {
      setError(`Please provide a rejection reason for ${plugin.name}`);
      return;
    }
    setBusy(plugin.id);
    try {
      await rejectPlugin(plugin.id, reason);
      await reload();
    } catch (err) {
      setError((err as Error).message || "Reject failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="container mx-auto max-w-6xl px-4 py-10">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-widest text-blue-600">
            Admin · Marketplace
          </p>
          <h1 className="mt-1 text-3xl font-bold text-slate-900">
            Plugin moderation queue
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            {pending.length} plugin{pending.length === 1 ? "" : "s"} awaiting
            review. Strapi admin UI is the primary moderator surface; this
            page is the FastAPI mirror.
          </p>
        </div>
        <button
          onClick={reload}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
          data-testid="reload"
        >
          Refresh
        </button>
      </header>

      {error && (
        <div
          className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700"
          data-testid="error"
        >
          {error}
        </div>
      )}

      {loading ? (
        <div className="rounded-md border border-slate-200 bg-white p-6 text-sm text-slate-500">
          Loading queue…
        </div>
      ) : pending.length === 0 ? (
        <div
          className="rounded-md border border-slate-200 bg-white p-6 text-sm text-slate-500"
          data-testid="empty-queue"
        >
          The moderation queue is empty. Nice work!
        </div>
      ) : (
        <ul className="space-y-4" data-testid="pending-list">
          {pending.map((p) => (
            <li
              key={p.id}
              className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
              data-testid="pending-card"
              data-slug={p.slug}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-slate-900">
                    {p.name}{" "}
                    <span className="text-sm font-normal text-slate-500">
                      ({p.slug})
                    </span>
                  </h2>
                  <p className="text-sm text-slate-600">
                    by {p.author_name} · {p.author_email || "no email"}
                  </p>
                  <p className="mt-2 max-w-3xl text-sm text-slate-700">
                    {p.tagline || p.description.slice(0, 200)}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                    <span className="rounded-full bg-slate-100 px-2 py-0.5">
                      {p.category}
                    </span>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5">
                      {p.pricing_model}
                    </span>
                    {p.homepage_url && (
                      <a
                        className="rounded-full bg-blue-50 px-2 py-0.5 text-blue-700 underline"
                        href={p.homepage_url}
                        rel="noreferrer noopener"
                      >
                        homepage ↗
                      </a>
                    )}
                    <span>
                      submitted {new Date(p.created_at * 1000).toLocaleString()}
                    </span>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <button
                    onClick={() => handleApprove(p)}
                    disabled={busy === p.id}
                    className="rounded-md bg-green-600 px-4 py-1.5 text-sm font-semibold text-white shadow-sm transition hover:bg-green-700 disabled:bg-green-300"
                    data-testid="approve-button"
                  >
                    {busy === p.id ? "Working…" : "Approve"}
                  </button>
                  <input
                    placeholder="Rejection reason (required to reject)"
                    value={rejectionReason[p.id] || ""}
                    onChange={(e) =>
                      setRejectionReason((m) => ({
                        ...m,
                        [p.id]: e.target.value,
                      }))
                    }
                    className="w-64 rounded-md border border-slate-300 px-2 py-1 text-xs"
                    data-testid="reject-reason"
                  />
                  <button
                    onClick={() => handleReject(p)}
                    disabled={busy === p.id}
                    className="rounded-md bg-red-600 px-4 py-1.5 text-sm font-semibold text-white shadow-sm transition hover:bg-red-700 disabled:bg-red-300"
                    data-testid="reject-button"
                  >
                    Reject
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      <section className="mt-12">
        <h2 className="mb-3 text-lg font-semibold text-slate-900">
          Recent audit log
        </h2>
        {audit.length === 0 ? (
          <p className="text-sm text-slate-500">No audit entries yet.</p>
        ) : (
          <ul
            className="divide-y divide-slate-100 rounded-md border border-slate-200 bg-white"
            data-testid="audit-list"
          >
            {audit.map((entry, idx) => (
              <li
                key={entry.id ?? idx}
                className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm"
              >
                <div className="flex items-center gap-2">
                  <span
                    className={
                      "rounded-full px-2 py-0.5 text-[10px] font-medium uppercase " +
                      (entry.action === "approve"
                        ? "bg-green-100 text-green-700"
                        : entry.action === "reject"
                          ? "bg-red-100 text-red-700"
                          : entry.action === "install"
                            ? "bg-blue-100 text-blue-700"
                            : "bg-slate-100 text-slate-700")
                    }
                  >
                    {entry.action}
                  </span>
                  <code className="font-mono text-xs text-slate-500">
                    {entry.plugin_id?.slice(0, 8) || "—"}
                  </code>
                </div>
                <div className="text-xs text-slate-500">
                  {entry.actor || "system"}{" "}
                  {entry.created_at
                    ? `· ${new Date(entry.created_at * 1000).toLocaleString()}`
                    : ""}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
