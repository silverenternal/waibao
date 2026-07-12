"use client";

/**
 * T1702 — 使用度统计组件 (admin/partner 端, 展示 NPS / 周活 / 痛点).
 *
 * - 拉取 /api/pilot/programs/{id}/stats
 * - 用 recharts 渲染目标达成进度条
 * - 顶部 KPI 卡 (NPS / WAU / Feedback / Pain points)
 */

import * as React from "react";
import {
  Activity,
  CheckCircle2,
  XCircle,
  TrendingUp,
  AlertTriangle,
  Loader2,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";

export interface UsageStatsData {
  program_id: string;
  invitations_total: number;
  invitations_accepted: number;
  invitations_pending: number;
  invitations_expired: number;
  active_users: number;
  weekly_active_users: number;
  weekly_active_rate: number | null;
  nps: number | null;
  nps_responses: number;
  promoters: number;
  passives: number;
  detractors: number;
  feedback_total: number;
  feedback_by_category: Record<string, number>;
  feedback_by_feature: Record<string, number>;
  top_pain_points: Array<{
    tag: string;
    count: number;
    samples: string[];
  }>;
  targets: {
    nps: boolean;
    weekly_active: boolean;
    top_pain_points: boolean;
    thresholds: {
      nps: number;
      weekly_active: number;
      top_pain_points_max: number;
    };
  };
}

export interface UsageStatsProps {
  programId: string;
  /** 自动刷新间隔 (ms, 0 = 不刷新). */
  refreshMs?: number;
  /** 受控 data (跳过 fetch). */
  data?: UsageStatsData;
  className?: string;
}

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("sb_token") || "";
}

function pct(value: number | null): string {
  if (value === null || value === undefined) return "N/A";
  return `${(value * 100).toFixed(0)}%`;
}

export function UsageStats({
  programId,
  refreshMs = 0,
  data: dataProp,
  className,
}: UsageStatsProps) {
  const [data, setData] = React.useState<UsageStatsData | null>(dataProp ?? null);
  const [loading, setLoading] = React.useState(dataProp === undefined);
  const [error, setError] = React.useState<string | null>(null);

  const fetchStats = React.useCallback(async () => {
    try {
      const res = await fetch(`/api/pilot/programs/${programId}/stats`, {
        headers: { Authorization: `Bearer ${getToken()}` },
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "fetch failed");
    } finally {
      setLoading(false);
    }
  }, [programId]);

  React.useEffect(() => {
    if (dataProp) return;
    fetchStats();
    if (refreshMs > 0) {
      const id = setInterval(fetchStats, refreshMs);
      return () => clearInterval(id);
    }
    return undefined;
  }, [fetchStats, refreshMs, dataProp]);

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8 text-muted-foreground">
        <Loader2 className="mr-2 size-4 animate-spin" />
        加载统计中...
      </div>
    );
  }

  if (error) {
    return (
      <Card className="border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
        <AlertTriangle className="mr-2 inline size-4" />
        加载失败: {error}
      </Card>
    );
  }

  if (!data) return null;

  const { targets, thresholds } = (data.targets as any) ?? {
    targets: { nps: false, weekly_active: false, top_pain_points: false },
    thresholds: { nps: 40, weekly_active: 0.7, top_pain_points_max: 5 },
  };

  return (
    <div className={cn("space-y-4", className)}>
      {/* 顶部 KPI 卡 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard
          label="NPS"
          value={data.nps ?? "N/A"}
          ok={targets.nps}
          hint={`目标 ≥ ${thresholds.nps} · 样本 ${data.nps_responses}`}
          icon={<TrendingUp className="size-4" />}
        />
        <KpiCard
          label="周活用户"
          value={data.weekly_active_users}
          ok={targets.weekly_active}
          hint={`周活率 ${pct(data.weekly_active_rate)} · 目标 ≥ ${pct(thresholds.weekly_active)}`}
          icon={<Activity className="size-4" />}
        />
        <KpiCard
          label="反馈总数"
          value={data.feedback_total}
          hint={`已邀请 ${data.invitations_accepted} / ${data.invitations_total}`}
        />
        <KpiCard
          label="Top 痛点"
          value={data.top_pain_points.length}
          ok={targets.top_pain_points}
          hint={`上限 ≤ ${thresholds.top_pain_points_max}`}
          icon={<AlertTriangle className="size-4" />}
        />
      </div>

      {/* NPS 分布 */}
      <Card className="p-4">
        <h3 className="mb-3 text-sm font-semibold">NPS 分布</h3>
        <div className="flex h-3 overflow-hidden rounded-full bg-muted">
          {data.nps_responses > 0 ? (
            <>
              <div
                className="bg-emerald-500"
                style={{ width: `${(data.promoters / data.nps_responses) * 100}%` }}
                aria-label={`Promoter ${data.promoters}`}
              />
              <div
                className="bg-amber-500"
                style={{ width: `${(data.passives / data.nps_responses) * 100}%` }}
                aria-label={`Passive ${data.passives}`}
              />
              <div
                className="bg-rose-500"
                style={{ width: `${(data.detractors / data.nps_responses) * 100}%` }}
                aria-label={`Detractor ${data.detractors}`}
              />
            </>
          ) : (
            <div className="flex-1 bg-muted" />
          )}
        </div>
        <div className="mt-2 flex justify-between text-xs text-muted-foreground">
          <span>Promoter: {data.promoters}</span>
          <span>Passive: {data.passives}</span>
          <span>Detractor: {data.detractors}</span>
        </div>
      </Card>

      {/* Top 痛点 */}
      {data.top_pain_points.length > 0 && (
        <Card className="p-4">
          <h3 className="mb-3 text-sm font-semibold">Top 痛点</h3>
          <ul className="space-y-2">
            {data.top_pain_points.map((p, i) => (
              <li key={p.tag} className="flex items-start gap-2 text-sm">
                <span className="mt-0.5 inline-flex size-5 items-center justify-center rounded-full bg-rose-100 text-xs font-bold text-rose-700">
                  {i + 1}
                </span>
                <div className="flex-1">
                  <p className="font-medium">
                    {p.tag} <span className="text-xs text-muted-foreground">×{p.count}</span>
                  </p>
                  {p.samples[0] && (
                    <p className="text-xs text-muted-foreground line-clamp-1">
                      {p.samples[0]}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function KpiCard({
  label,
  value,
  ok,
  hint,
  icon,
}: {
  label: string;
  value: string | number;
  ok?: boolean;
  hint?: string;
  icon?: React.ReactNode;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        {ok !== undefined &&
          (ok ? (
            <CheckCircle2 className="size-4 text-emerald-500" aria-label="达标" />
          ) : (
            <XCircle className="size-4 text-rose-500" aria-label="未达标" />
          ))}
        {icon && ok === undefined}
      </div>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </Card>
  );
}

export default UsageStats;