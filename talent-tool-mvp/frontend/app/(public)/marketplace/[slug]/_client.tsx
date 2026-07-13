"use client";

import { useEffect, useState } from "react";
import {
  getPlugin,
  formatPrice,
  ratingStars,
  type MarketplacePlugin,
} from "@/lib/api-marketplace";
import { InstallButton } from "../_components/install-button";
import { ReviewSection } from "../_components/review-form";

const DEMO_TENANT_ID = "demo-tenant";

export function PluginDetailClient({
  slug,
  initial,
}: {
  slug: string;
  initial: MarketplacePlugin | null;
}) {
  const [plugin, setPlugin] = useState<MarketplacePlugin | null>(initial);
  const [loading, setLoading] = useState(initial == null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (plugin) return;
    setLoading(true);
    getPlugin(slug)
      .then((p) => {
        setPlugin(p);
        setError(null);
      })
      .catch((err) => {
        setError((err as Error).message || "Failed to load plugin");
      })
      .finally(() => setLoading(false));
  }, [slug, plugin]);

  if (loading) {
    return (
      <main className="container mx-auto max-w-4xl px-4 py-12">
        <div className="rounded-md border border-slate-200 bg-white p-6 text-sm text-slate-500">
          Loading…
        </div>
      </main>
    );
  }

  if (error || !plugin) {
    return (
      <main className="container mx-auto max-w-4xl px-4 py-12">
        <div
          className="rounded-md border border-slate-200 bg-white p-6 text-sm text-slate-600"
          data-testid="plugin-not-found"
        >
          Plugin <code>{slug}</code> not found.{" "}
          <a className="text-blue-600 underline" href="/marketplace">
            Back to marketplace
          </a>
        </div>
      </main>
    );
  }

  return (
    <main className="container mx-auto max-w-5xl px-4 py-12">
      <a
        href="/marketplace"
        className="mb-4 inline-block text-xs text-slate-500 hover:text-slate-700"
      >
        ← All plugins
      </a>
      <header className="mb-6 grid gap-6 sm:grid-cols-[1fr_320px]">
        <div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span className="rounded-full bg-slate-100 px-2 py-1 font-medium uppercase tracking-wide text-slate-700">
              {plugin.category}
            </span>
            <span>by {plugin.author_name}</span>
            {plugin.reviewed_at && (
              <span className="text-slate-400">
                · approved{" "}
                {new Date(plugin.reviewed_at * 1000).toLocaleDateString()}
              </span>
            )}
          </div>
          <h1
            className="mt-2 text-3xl font-bold text-slate-900"
            data-testid="plugin-name"
          >
            {plugin.name}
          </h1>
          {plugin.tagline && (
            <p className="mt-1 text-lg text-slate-600">{plugin.tagline}</p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-slate-700">
            <span title={`${plugin.avg_rating} / 5`} className="text-amber-500">
              {ratingStars(plugin.avg_rating)}
            </span>
            <span>
              {plugin.avg_rating.toFixed(1)} ({plugin.rating_count} reviews)
            </span>
            <span>·</span>
            <span>{plugin.total_installs.toLocaleString()} installs</span>
          </div>
          {plugin.tags.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1">
              {plugin.tags.map((t) => (
                <span
                  key={t}
                  className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] text-blue-700"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
          {plugin.homepage_url && (
            <a
              className="mt-3 inline-block text-xs text-blue-600 underline"
              href={plugin.homepage_url}
              rel="noreferrer noopener"
            >
              Project homepage ↗
            </a>
          )}
        </div>
        <InstallButton plugin={plugin} tenantId={DEMO_TENANT_ID} />
      </header>

      <section className="mb-8 rounded-lg border border-slate-200 bg-white p-6">
        <h2 className="mb-2 text-lg font-semibold text-slate-900">
          About this plugin
        </h2>
        <p className="whitespace-pre-line text-sm text-slate-700">
          {plugin.description}
        </p>
      </section>

      {plugin.releases && plugin.releases.length > 0 && (
        <section className="mb-8 rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="mb-3 text-lg font-semibold text-slate-900">
            Releases
          </h2>
          <ul className="space-y-3">
            {plugin.releases.map((r) => (
              <li
                key={r.id}
                className="rounded-md border border-slate-100 bg-slate-50 p-3"
                data-testid="release-row"
              >
                <div className="flex items-center justify-between">
                  <code className="font-mono text-sm font-semibold text-slate-900">
                    v{r.version}
                  </code>
                  <span className="text-xs text-slate-500">
                    {r.downloads.toLocaleString()} downloads
                  </span>
                </div>
                {r.changelog && (
                  <p className="mt-1 text-sm text-slate-600">{r.changelog}</p>
                )}
                <div className="mt-1 text-xs text-slate-400">
                  min waibao {r.min_waibao_ver}
                  {r.max_waibao_ver ? ` / max ${r.max_waibao_ver}` : ""}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-lg border border-slate-200 bg-white p-6">
        <ReviewSection slug={plugin.slug} />
      </section>
    </main>
  );
}
