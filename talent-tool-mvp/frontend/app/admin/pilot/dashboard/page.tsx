"use client";

/**
 * T3801 — Pilot 合作方实时 Dashboard.
 *
 * - 顶部 KPI 概览 (总数 / 平均 NPS / 平均续约概率 / 告警数)
 * - 每家 partner 卡片: 日活趋势 / 关键功能使用 / NPS / Top 痛点 / 续约概率 / 告警
 * - SSE 实时刷新 (60s)
 */

import * as React from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  TrendingUp,
  Users,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface DashboardSummary {
  programs: number;
  avg_nps: number | null;
  avg_renewal_probability: number | null;
  active_alerts: number;
  by_status: Record<string, number>;
  generated_at?: string;
}

interface PartnerRow {
  program_id: string;
  program_name: string;
  organisation_name: string | null;
  status: "recruiting" | "active" | "completed" | "cancelled";
  started_at: string | null;
  days_in_pilot: number;
  weekly_active_rate: number;
  feature_usage: Array<{ feature: string; unique_users: number }>;
  nps: {
    responses: number;
    nps: number | null;
    promoters: number;
    passives: number;
    detractors: number;
  };
  pain_points: Array<{ category: string; feature: string; count: number }>;
  renewal_probability: number;
  alerts: string[];
  dal_trend: Array<{ day: string; users: number; events: number; platforms: string[] }>;
}

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("sb_token") || "";
}

const STATUS_COLORS: Record<string, string> = {
  recruiting: "bg-slate-100 text-slate-700",
  active: "bg-emerald-100 text-emerald-700",
  completed: "bg-blue-100 text-blue-700",
  cancelled: "bg-rose-100 text-rose-700",
};

export default function PilotDashboardPage() {
  const [summary, setSummary] = React.useState<DashboardSummary | null>(null);
  const [partners, setPartners] = React.useState<PartnerRow[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [sseConnected, setSseConnected] = React.useState(false);

  const fetchOnce = React.useCallback(async () => {
    try {
      const res = await fetch("/api/pilot/dashboard?days=30", {
        headers: { Authorization: `Bearer ${getToken()}` },
        credentials: "include",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSummary(data.summary);
      setPartners(data.partners || []);
      setError(null);
    } catch (e: any) {
      setError(e?.message || "fetch failed");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    fetchOnce();
    if (typeof EventSource === "undefined") return;
    const es = new EventSource("/api/pilot/dashboard/stream?interval=60");
    es.onopen = () => setSseConnected(true);
    es.onerror = () => setSseConnected(false);
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.summary) setSummary(data.summary);
        if (Array.isArray(data.partners)) setPartners(data.partners);
      } catch {
        // ignore parse errors
      }
    };
    return () => es.close();
  }, [fetchOnce]);

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Pilot 实时 Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            监控 5+ 中型企业 30 天试用情况, 自动刷新 (SSE, 60s)。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={sseConnected ? "default" : "outline"} className="gap-1">
            <span
              className={cn(
                "inline-block h-2 w-2 rounded-full",
                sseConnected ? "bg-emerald-500" : "bg-slate-400",
              )}
            />
            {sseConnected ? "实时" : "离线"}
          </Badge>
          <Button variant="outline" size="sm" onClick={fetchOnce}>
            <RefreshCw className="mr-1 h-4 w-4" />
            刷新
          </Button>
        </div>
      </header>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> 加载中…
        </div>
      )}

      {error && (
        <Card className="border-rose-300 bg-rose-50 p-4 text-sm text-rose-800">
          数据获取失败: {error}
        </Card>
      )}

      {summary && (
        <section className="grid grid-cols-2 gap-4 md:grid-cols-5">
          <KpiCard
            icon={<Users className="h-5 w-5" />}
            label="合作方"
            value={String(summary.programs)}
            sub={`${summary.by_status?.active ?? 0} active · ${summary.by_status?.completed ?? 0} completed`}
          />
          <KpiCard
            icon={<TrendingUp className="h-5 w-5" />}
            label="平均 NPS"
            value={summary.avg_nps?.toString() ?? "—"}
            sub={summary.avg_nps !== null ? (summary.avg_nps >= 40 ? "达标" : "偏低") : "无数据"}
            tone={summary.avg_nps !== null && summary.avg_nps >= 40 ? "ok" : "warn"}
          />
          <KpiCard
            icon={<Activity className="h-5 w-5" />}
            label="平均续约概率"
            value={
              summary.avg_renewal_probability !== null
                ? `${Math.round(summary.avg_renewal_probability * 100)}%`
                : "—"
            }
            sub={
              summary.avg_renewal_probability !== null && summary.avg_renewal_probability >= 0.6
                ? "健康"
                : "关注"
            }
            tone={
              summary.avg_renewal_probability !== null && summary.avg_renewal_probability >= 0.6
                ? "ok"
                : "warn"
            }
          />
          <KpiCard
            icon={<AlertTriangle className="h-5 w-5" />}
            label="活跃告警"
            value={String(summary.active_alerts)}
            sub={summary.active_alerts > 0 ? "需处理" : "无"}
            tone={summary.active_alerts > 0 ? "danger" : "ok"}
          />
          <KpiCard
            icon={<CheckCircle2 className="h-5 w-5" />}
            label="目标"
            value="5+ / 30d"
            sub="≥ 5 家中型企业"
          />
        </section>
      )}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {partners.map((p) => (
          <PartnerCard key={p.program_id} partner={p} />
        ))}
        {partners.length === 0 && !loading && (
          <Card className="col-span-full p-8 text-center text-sm text-muted-foreground">
            暂无活跃 Pilot。运行{" "}
            <code className="rounded bg-slate-100 px-1">scripts/seed_pilot_partners.py</code> 创建。
          </Card>
        )}
      </section>
    </main>
  );
}

function KpiCard({
  icon,
  label,
  value,
  sub,
  tone = "ok",
}:{ icon: React.ReactNode; label: string; value: string; sub?: string; tone?: "ok" | "warn" | "bad" }) {
  const toneClass = tone === "bad" ? "text-red-600" : tone === "warn" ? "text-amber-600" : "text-emerald-600";
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>{label}</span>
        <span className={toneClass}>{icon}</span>
      </div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </Card>
  );
}
