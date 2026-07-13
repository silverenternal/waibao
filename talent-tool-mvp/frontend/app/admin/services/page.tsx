"use client";

/**
 * v8.0 T3501 — Admin Service Catalog page.
 *
 * Lists every registered service with a status badge, plan badge,
 * role badge and dependency count. Admins can flip status from here.
 */

import * as React from "react";
import Link from "next/link";
import { useServiceCatalog } from "@/hooks/use-service-toggle";
import { cn } from "@/lib/utils";

type Category =
  | "agent"
  | "api"
  | "business"
  | "integration"
  | "platform"
  | "frontend"
  | "analytics"
  | "misc";

interface CatalogItem {
  name: string;
  display_name: string;
  description?: string;
  category: string;
  status: string;
  plan_required: string;
  roles_allowed: string[];
  dependencies?: string[];
  available?: boolean;
}

const CATEGORY_LABELS: Record<string, string> = {
  agent: "Agent",
  api: "API",
  business: "Business",
  integration: "Integration",
  platform: "Platform",
  frontend: "Frontend",
  analytics: "Analytics",
  misc: "Misc",
};

const STATUS_STYLE: Record<string, string> = {
  enabled: "bg-green-50 text-green-700 border-green-200",
  disabled: "bg-red-50 text-red-700 border-red-200",
  maintenance: "bg-amber-50 text-amber-700 border-amber-200",
  beta: "bg-blue-50 text-blue-700 border-blue-200",
};

export default function AdminServicesPage(): React.ReactElement {
  const [plan, setPlan] = React.useState("free");
  const [role, setRole] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [category, setCategory] = React.useState<string>("all");
  const { data, isLoading, refetch } = useServiceCatalog(plan, role);

  const items = React.useMemo<CatalogItem[]>(() => {
    const rows = data ?? [];
    return rows.filter((row) => {
      if (search && !row.name.toLowerCase().includes(search.toLowerCase())
          && !(row.display_name ?? "").toLowerCase().includes(search.toLowerCase())) {
        return false;
      }
      if (category !== "all" && row.category !== category) {
        return false;
      }
      return true;
    });
  }, [data, search, category]);

  const totals = React.useMemo(() => {
    const all = data ?? [];
    const byStatus: Record<string, number> = {};
    for (const r of all) {
      byStatus[r.status] = (byStatus[r.status] ?? 0) + 1;
    }
    return { total: all.length, byStatus };
  }, [data]);

  return (
    <main className="mx-auto max-w-7xl space-y-6 p-6">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Service Catalog</h1>
          <p className="text-sm text-slate-500">
            {totals.total} registered services — v8.0 service toggle.
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="rounded-md border border-slate-300 bg-white px-3 py-1 text-sm hover:bg-slate-50"
        >
          Refresh
        </button>
      </header>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {["enabled", "disabled", "maintenance", "beta"].map((s) => (
          <div
            key={s}
            className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
          >
            <div className="text-xs uppercase tracking-wide text-slate-500">
              {s}
            </div>
            <div className="mt-1 text-2xl font-semibold">
              {totals.byStatus[s] ?? 0}
            </div>
          </div>
        ))}
      </section>

      <section className="grid grid-cols-1 gap-3 md:grid-cols-4">
        <input
          aria-label="Search services"
          placeholder="Search name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
        />
        <select
          aria-label="Plan"
          value={plan}
          onChange={(e) => setPlan(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
        >
          <option value="free">Free</option>
          <option value="pro">Pro</option>
          <option value="enterprise">Enterprise</option>
          <option value="internal">Internal</option>
        </select>
        <select
          aria-label="Role"
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
        >
          <option value="">Any role</option>
          <option value="jobseeker">Jobseeker</option>
          <option value="employer">Employer</option>
          <option value="admin">Admin</option>
        </select>
        <select
          aria-label="Category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
        >
          <option value="all">All categories</option>
          {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </section>

      <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">Display</th>
              <th className="px-4 py-2">Category</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Plan</th>
              <th className="px-4 py-2">Roles</th>
              <th className="px-4 py-2">Deps</th>
              <th className="px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading ? (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-slate-500">
                  Loading…
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-slate-500">
                  No services match the current filter.
                </td>
              </tr>
            ) : (
              items.map((row) => (
                <tr key={row.name} className="hover:bg-slate-50">
                  <td className="px-4 py-2 font-mono text-xs text-slate-700">
                    {row.name}
                  </td>
                  <td className="px-4 py-2">
                    {row.display_name ?? row.name}
                  </td>
                  <td className="px-4 py-2">
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                      {CATEGORY_LABELS[row.category] ?? row.category}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-xs",
                        STATUS_STYLE[row.status] ?? STATUS_STYLE.disabled,
                      )}
                    >
                      {row.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs uppercase">{row.plan_required}</td>
                  <td className="px-4 py-2 text-xs">
                    {row.roles_allowed && row.roles_allowed.length > 0
                      ? row.roles_allowed.join(", ")
                      : "any"}
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {(row.dependencies ?? []).length}
                  </td>
                  <td className="px-4 py-2">
                    <Link
                      className="text-indigo-600 hover:underline"
                      href={`/admin/services/${encodeURIComponent(row.name)}`}
                    >
                      Detail →
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </main>
  );
}
