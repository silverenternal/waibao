"use client";

/**
 * v8.0 T3502 — Public service detail page.
 *
 * Shows description, dependency DAG, history (last 20 status changes),
 * SLA badge and related services. The DAG is rendered with a small
 * dependency-free SVG component (DependencyGraph) — see ./DependencyGraph.
 */

import * as React from "react";
import Link from "next/link";

import { DependencyGraph, type DepNode } from "../_components/DependencyGraph";

type ServiceStatus = "enabled" | "beta" | "deprecated" | "disabled" | "maintenance";
type PlanTier = "free" | "pro" | "enterprise";

interface PublicServiceDetail {
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
  sla?: { uptime_target_pct: number; support_response_minutes: number; incident_history_url: string };
  declared_dependencies?: string[];
  dependencies_resolved?: string[];
  dependents?: string[];
  related_services?: Array<{ name: string; display_name: string }>;
  history?: Array<{
    action?: string;
    reason?: string;
    actor_id?: string | null;
    before?: { status?: string } | null;
    after?: { status?: string } | null;
    created_at?: string | null;
  }>;
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

interface PageProps {
  params: Promise<{ name: string }>;
}

export default function ServiceDetailPage({ params }: PageProps): React.ReactElement {
  const { name } = React.use(params);
  const [svc, setSvc] = React.useState<PublicServiceDetail | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [depGraph, setDepGraph] = React.useState<{ nodes: DepNode[]; edges: { from: string; to: string }[] } | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      fetch(`/api/public/services/${encodeURIComponent(name)}`, { cache: "no-store" }).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<PublicServiceDetail>;
      }),
      fetch(`/api/public/services/${encodeURIComponent(name)}/dependencies`, {
        cache: "no-store",
      }).then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([detail, graph]) => {
        if (cancelled) return;
        setSvc(detail);
        if (graph && Array.isArray(graph.nodes)) setDepGraph(graph);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "failed to load");
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [name]);

  if (loading) {
    return (
      <main className="container mx-auto max-w-5xl px-4 py-12">
        <div className="h-32 animate-pulse rounded-lg bg-slate-100" />
      </main>
    );
  }

  if (error || !svc) {
    return (
      <main className="container mx-auto max-w-5xl px-4 py-12">
        <Link href="/services" className="text-sm text-blue-600 hover:text-blue-700">
          ← 返回服务目录
        </Link>
        <div className="mt-6 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error ?? "未找到该服务"}
        </div>
      </main>
    );
  }

  const sla = svc.sla ?? {
    uptime_target_pct: 99.9,
    support_response_minutes: 60,
    incident_history_url: "/status",
  };

  return (
    <main className="container mx-auto max-w-5xl px-4 py-12">
      <Link href="/services" className="text-sm text-blue-600 hover:text-blue-700">
        ← 返回服务目录
      </Link>

      <header className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-widest text-blue-600">{svc.category_display ?? svc.category}</p>
          <h1 className="mt-1 text-3xl font-bold text-slate-900">{svc.display_name}</h1>
          <p className="text-sm text-slate-500">{svc.name}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${
              STATUS_CLASSES[svc.status] ?? STATUS_CLASSES.enabled
            }`}
          >
            {STATUS_LABELS[svc.status] ?? svc.status}
          </span>
          <span className="inline-flex items-center rounded-md bg-indigo-100 px-2.5 py-1 text-xs font-semibold text-indigo-700">
            {PLAN_LABELS[svc.plan_required] ?? svc.plan_required}
          </span>
        </div>
      </header>

      {svc.description ? (
        <p className="mt-6 max-w-3xl text-base text-slate-700">{svc.description}</p>
      ) : null}

      <section className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs uppercase tracking-wide text-slate-500">SLA</p>
          <p className="mt-1 text-2xl font-bold text-slate-900">{sla.uptime_target_pct}%</p>
          <p className="mt-1 text-xs text-slate-500">
            故障响应 {sla.support_response_minutes} 分钟内
          </p>
          <Link
            href={sla.incident_history_url}
            className="mt-3 inline-block text-xs font-medium text-blue-600 hover:text-blue-700"
          >
            查看历史事件 →
          </Link>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs uppercase tracking-wide text-slate-500">依赖</p>
          <p className="mt-1 text-2xl font-bold text-slate-900">
            {(svc.declared_dependencies ?? []).length}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            传递依赖 {(svc.dependencies_resolved ?? []).length} 个
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs uppercase tracking-wide text-slate-500">反向依赖</p>
          <p className="mt-1 text-2xl font-bold text-slate-900">{(svc.dependents ?? []).length}</p>
          <p className="mt-1 text-xs text-slate-500">多少服务依赖本服务</p>
        </div>
      </section>

      <section className="mt-8 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">依赖关系图 (DAG)</h2>
        <p className="mt-1 text-xs text-slate-500">箭头方向：本服务 → 依赖项。绿色 = enabled，蓝色 = beta，红色 = disabled。</p>
        <div className="mt-3 h-72 overflow-auto rounded-md border border-slate-100 bg-slate-50 p-2">
          {depGraph && depGraph.nodes.length > 0 ? (
            <DependencyGraph nodes={depGraph.nodes} edges={depGraph.edges} root={name} />
          ) : (
            <p className="p-6 text-center text-sm text-slate-500">无依赖关系</p>
          )}
        </div>
      </section>

      <section className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">历史变更</h2>
          <ul className="mt-3 space-y-3 text-sm">
            {(svc.history ?? []).length === 0 ? (
              <li className="text-xs text-slate-500">暂无变更记录</li>
            ) : (
              (svc.history ?? []).map((h, idx) => (
                <li key={idx} className="flex flex-col border-b border-slate-100 pb-2 last:border-b-0">
                  <span className="font-mono text-xs text-slate-500">
                    {h.created_at ?? "—"} · {h.action ?? "—"}
                  </span>
                  <span className="mt-1 text-slate-800">
                    {(h.before?.status ?? "?")} → {(h.after?.status ?? "?")}
                  </span>
                  {h.reason ? <span className="text-xs text-slate-500">{h.reason}</span> : null}
                  {h.actor_id ? (
                    <span className="text-xs text-slate-400">by {h.actor_id}</span>
                  ) : null}
                </li>
              ))
            )}
          </ul>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900">关联服务</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {(svc.related_services ?? []).length === 0 ? (
              <li className="text-xs text-slate-500">无关联服务</li>
            ) : (
              (svc.related_services ?? []).map((r) => (
                <li key={r.name}>
                  <Link
                    href={`/services/${encodeURIComponent(r.name)}`}
                    className="text-blue-600 hover:text-blue-700"
                  >
                    {r.display_name} <span className="text-xs text-slate-500">({r.name})</span>
                  </Link>
                </li>
              ))
            )}
          </ul>
          <h3 className="mt-6 text-sm font-semibold text-slate-700">允许角色</h3>
          <div className="mt-2 flex flex-wrap gap-1">
            {(svc.roles_allowed ?? []).length === 0 ? (
              <span className="text-xs text-slate-500">anonymous</span>
            ) : (
              (svc.roles_allowed ?? []).map((r) => (
                <span key={r} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                  {r}
                </span>
              ))
            )}
          </div>
        </div>
      </section>
    </main>
  );
}