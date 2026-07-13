"use client";

/**
 * v8.0 T3502 — Public Services catalog.
 *
 * Renders the live service directory backed by `GET /api/public/services`.
 * Three columns per row: name + status pill, plan badge, dependencies count.
 * Includes search + filter (category, plan, status).
 */

import * as React from "react";
import Link from "next/link";

import { cn } from "@/lib/utils";

type ServiceStatus = "enabled" | "beta" | "deprecated" | "disabled" | "maintenance";
type PlanTier = "free" | "pro" | "enterprise";

interface CatalogService {
  name: string;
  display_name: string;
  description?: string;
  category: string;
  category_display?: string;
  status: ServiceStatus;
  plan_required: PlanTier;
  roles_allowed?: string[];
  dependencies?: string[];
  version?: number;
}

const STATUS_LABELS: Record<ServiceStatus, string> = {
  enabled: "ACTIVE",
  beta: "BETA",
  deprecated: "DEPRECATED",
  disabled: "DISABLED",
  maintenance: "MAINTENANCE",
};

const STATUS_CLASSES: Record<ServiceStatus, string> = {
  enabled: "bg-green-100 text-green-700 ring-green-200",
  beta: "bg-blue-100 text-blue-700 ring-blue-200",
  deprecated: "bg-amber-100 text-amber-800 ring-amber-200",
  disabled: "bg-red-100 text-red-700 ring-red-200",
  maintenance: "bg-yellow-100 text-yellow-800 ring-yellow-200",
};

const PLAN_LABELS: Record<PlanTier, string> = {
  free: "Free",
  pro: "Pro",
  enterprise: "Enterprise",
};

const PLAN_CLASSES: Record<PlanTier, string> = {
  free: "bg-slate-100 text-slate-700",
  pro: "bg-indigo-100 text-indigo-700",
  enterprise: "bg-purple-100 text-purple-700",
};

const CATEGORY_OPTIONS = [
  { value: "", label: "All categories" },
  { value: "agent", label: "AI 智能体" },
  { value: "business", label: "业务模块" },
  { value: "frontend", label: "端" },
  { value: "integration", label: "集成" },
  { value: "api", label: "API" },
  { value: "platform", label: "平台" },
  { value: "analytics", label: "分析" },
];

const PLAN_OPTIONS = [
  { value: "", label: "All plans" },
  { value: "free", label: "Free" },
  { value: "pro", label: "Pro" },
  { value: "enterprise", label: "Enterprise" },
];

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "enabled", label: "Active" },
  { value: "beta", label: "Beta" },
  { value: "maintenance", label: "Maintenance" },
];

export default function ServicesPage(): React.ReactElement {
  const [services, setServices] = React.useState<CatalogService[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState("");
  const [category, setCategory] = React.useState("");
  const [plan, setPlan] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [totals, setTotals] = React.useState({ enabled: 0, beta: 0, maintenance: 0 });

  // Subscriber form state
  const [email, setEmail] = React.useState("");
  const [webhook, setWebhook] = React.useState("");
  const [subscribeState, setSubscribeState] = React.useState<
    | { kind: "idle" }
    | { kind: "submitting" }
    | { kind: "ok"; id: string }
    | { kind: "error"; message: string }
  >({ kind: "idle" });

  const fetchServices = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams();
      if (category) qs.set("category", category);
      if (plan) qs.set("plan", plan);
      if (status) qs.set("status", status);
      if (search) qs.set("search", search);
      qs.set("limit", "200");
      const res = await fetch(`/api/public/services?${qs.toString()}`, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = (await res.json()) as { items: CatalogService[]; count: number };
      setServices(payload.items ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to load");
    } finally {
      setLoading(false);
    }
  }, [category, plan, status, search]);

  React.useEffect(() => {
    const t = setTimeout(() => {
      fetchServices();
    }, 200);
    return () => clearTimeout(t);
  }, [fetchServices]);

  React.useEffect(() => {
    fetch("/api/public/services/categories", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((p) => {
        if (p?.totals) setTotals(p.totals);
      })
      .catch(() => undefined);
  }, []);

  const onSubmitSubscribe = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!email && !webhook) return;
    setSubscribeState({ kind: "submitting" });
    try {
      const res = await fetch("/api/public/services/subscribers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email || undefined, webhook_url: webhook || undefined }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = (await res.json()) as { id: string };
      setSubscribeState({ kind: "ok", id: payload.id });
      setEmail("");
      setWebhook("");
    } catch (err) {
      setSubscribeState({
        kind: "error",
        message: err instanceof Error ? err.message : "subscribe failed",
      });
    }
  };

  return (
    <main className="container mx-auto max-w-6xl px-4 py-12">
      <header className="mb-8 space-y-2">
        <p className="text-xs uppercase tracking-widest text-blue-600">
          Service Catalog · v8.0
        </p>
        <h1 className="text-3xl font-bold text-slate-900 sm:text-4xl">
          waibao 服务目录
        </h1>
        <p className="max-w-3xl text-base text-slate-600">
          实时查看 waibao 平台全部对外服务。按 Plan 要求、状态、分类筛选。订阅后我们会在服务状态变更时通过邮箱或 Webhook 通知你。
        </p>
        <div className="mt-3 flex gap-4 text-sm text-slate-600">
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-green-500" /> Active{" "}
            <strong>{totals.enabled}</strong>
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-blue-500" /> Beta <strong>{totals.beta}</strong>
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-yellow-500" /> Maintenance{" "}
            <strong>{totals.maintenance}</strong>
          </span>
        </div>
      </header>

      <section className="mb-6 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
          <input
            aria-label="Search services"
            placeholder="搜索服务名 / 描述"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <Select label="分类" value={category} onChange={setCategory} options={CATEGORY_OPTIONS} />
          <Select label="Plan" value={plan} onChange={setPlan} options={PLAN_OPTIONS} />
          <Select label="状态" value={status} onChange={setStatus} options={STATUS_OPTIONS} />
        </div>
      </section>

      {loading ? (
        <SkeletonGrid />
      ) : error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : services.length === 0 ? (
        <div className="rounded-md border border-slate-200 bg-white px-4 py-12 text-center text-slate-500">
          没有匹配的服务。试试调整筛选条件。
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  名称
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  状态
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  Plan 要求
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  依赖
                </th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-slate-600">
                  详情
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {services.map((s) => (
                <tr key={s.name} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-slate-900">{s.display_name}</span>
                      <span className="text-xs text-slate-500">{s.name}</span>
                      {s.description ? (
                        <span className="mt-1 text-xs text-slate-500">{s.description}</span>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ring-1",
                        STATUS_CLASSES[s.status] ?? STATUS_CLASSES.enabled,
                      )}
                    >
                      {STATUS_LABELS[s.status] ?? s.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "inline-block rounded px-2 py-0.5 text-xs font-semibold",
                        PLAN_CLASSES[s.plan_required] ?? PLAN_CLASSES.free,
                      )}
                    >
                      {PLAN_LABELS[s.plan_required] ?? s.plan_required}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-600">
                    {(s.dependencies ?? []).length} dep
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/services/${encodeURIComponent(s.name)}`}
                      className="text-sm font-medium text-blue-600 hover:text-blue-700"
                    >
                      查看
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <section className="mt-12 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900">订阅服务变更通知</h2>
        <p className="mt-1 text-sm text-slate-600">
          服务上下线 / 进入维护模式时通过邮箱或 Webhook 第一时间通知。
        </p>
        <form onSubmit={onSubmitSubscribe} className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          <input
            type="email"
            placeholder="email@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <input
            type="url"
            placeholder="https://hooks.example.com/notify"
            value={webhook}
            onChange={(e) => setWebhook(e.target.value)}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={subscribeState.kind === "submitting"}
            className="md:col-span-2 inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
          >
            {subscribeState.kind === "submitting" ? "订阅中..." : "订阅"}
          </button>
        </form>
        {subscribeState.kind === "ok" ? (
          <p className="mt-3 text-sm text-green-700">
            订阅成功。订阅 ID: <code>{subscribeState.id}</code>
          </p>
        ) : null}
        {subscribeState.kind === "error" ? (
          <p className="mt-3 text-sm text-red-700">{subscribeState.message}</p>
        ) : null}
      </section>
    </main>
  );
}

interface SelectProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}

function Select({ label, value, onChange, options }: SelectProps): React.ReactElement {
  return (
    <label className="flex flex-col text-xs font-medium text-slate-700">
      <span className="mb-1">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function SkeletonGrid(): React.ReactElement {
  return (
    <div className="space-y-2">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="h-12 animate-pulse rounded-md border border-slate-200 bg-slate-50"
        />
      ))}
    </div>
  );
}