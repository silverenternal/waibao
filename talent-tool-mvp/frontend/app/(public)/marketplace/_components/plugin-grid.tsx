"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  listPlugins,
  searchPlugins,
  formatPrice,
  ratingStars,
  type Category,
  type MarketplacePlugin,
} from "@/lib/api-marketplace";

const CATEGORIES: { value: Category | ""; label: string }[] = [
  { value: "", label: "All categories" },
  { value: "integration", label: "Integrations" },
  { value: "analytics", label: "Analytics" },
  { value: "automation", label: "Automation" },
  { value: "sourcing", label: "Sourcing" },
  { value: "assessment", label: "Assessment" },
  { value: "video", label: "Video" },
  { value: "utility", label: "Utilities" },
  { value: "other", label: "Other" },
];

const SORTS = [
  { value: "popular", label: "Most popular" },
  { value: "recent", label: "Recently added" },
  { value: "rating", label: "Top rated" },
  { value: "name", label: "Name (A-Z)" },
] as const;

export function PluginGrid() {
  const [items, setItems] = useState<MarketplacePlugin[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<Category | "">("");
  const [sort, setSort] = useState<(typeof SORTS)[number]["value"]>("popular");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const t = setTimeout(() => {
      const fetcher = query.trim()
        ? searchPlugins(query, { category: category || undefined, limit: 50 })
        : listPlugins({ category: category || undefined, sort, limit: 50 });
      fetcher
        .then((res) => {
          if (!cancelled) {
            setItems(res.items || []);
            setLoading(false);
          }
        })
        .catch((err: Error) => {
          if (!cancelled) {
            setError(err.message || "Failed to load marketplace");
            setLoading(false);
          }
        });
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [query, category, sort]);

  const empty = !loading && items.length === 0 && !error;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-1 gap-2">
          <input
            type="search"
            placeholder="Search plugins by name, tag, or author…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            data-testid="marketplace-search"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as Category | "")}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none"
            data-testid="marketplace-category"
          >
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
          <select
            value={sort}
            onChange={(e) =>
              setSort(e.target.value as (typeof SORTS)[number]["value"])
            }
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none"
            data-testid="marketplace-sort"
          >
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                Sort: {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading && (
        <div
          className="rounded-md border border-slate-200 bg-white p-6 text-sm text-slate-500"
          data-testid="marketplace-loading"
        >
          Loading marketplace…
        </div>
      )}
      {error && (
        <div
          className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700"
          data-testid="marketplace-error"
        >
          {error}
        </div>
      )}
      {empty && (
        <div
          className="rounded-md border border-slate-200 bg-white p-6 text-sm text-slate-500"
          data-testid="marketplace-empty"
        >
          No plugins match your filters yet — check back soon or
          {" "}
          <Link href="/developers" className="text-blue-600 underline">
            publish your own
          </Link>
          .
        </div>
      )}

      <ul
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        data-testid="marketplace-grid"
      >
        {items.map((p) => (
          <li
            key={p.id}
            className="flex flex-col rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition hover:shadow-md"
            data-testid="plugin-card"
            data-slug={p.slug}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <Link
                  href={`/marketplace/${p.slug}`}
                  className="text-base font-semibold text-slate-900 hover:text-blue-600"
                >
                  {p.name}
                </Link>
                <p className="text-xs text-slate-500">
                  by {p.author_name}
                </p>
              </div>
              <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-medium uppercase tracking-wide text-slate-700">
                {p.category}
              </span>
            </div>
            <p className="mt-2 line-clamp-2 text-sm text-slate-600">
              {p.tagline || p.description.slice(0, 120)}
            </p>
            <div className="mt-3 flex flex-wrap gap-1">
              {p.tags.slice(0, 4).map((t) => (
                <span
                  key={t}
                  className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] text-blue-700"
                >
                  {t}
                </span>
              ))}
            </div>
            <div className="mt-auto flex items-end justify-between pt-4">
              <div className="text-xs text-slate-500">
                <div>
                  {p.rating_count > 0 ? (
                    <span title={`${p.avg_rating} / 5`}>
                      {ratingStars(p.avg_rating)}{" "}
                      <span className="text-slate-400">
                        ({p.rating_count})
                      </span>
                    </span>
                  ) : (
                    <span className="text-slate-400">No reviews yet</span>
                  )}
                </div>
                <div>{p.total_installs.toLocaleString()} installs</div>
              </div>
              <div className="text-right">
                <div className="text-sm font-semibold text-slate-900">
                  {formatPrice(p.price_cents)}
                </div>
                {p.pricing_model !== "free" && (
                  <div className="text-[10px] uppercase text-slate-400">
                    {p.pricing_model.replace("_", " ")}
                  </div>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
