"use client";

/**
 * T1904 — /admin/analytics/cross-platform
 *
 * 跨端日活统一统计仪表盘。
 *
 * - 顶部 KPI：DAU/WAU/MAU（统一去重）
 * - 按端拆分柱状图（4 端：webapp / minip / feishu / dingtalk）
 * - 跨端用户矩阵（端 × 端重合人数热力图）
 * - 7 天 DAU 趋势折线
 *
 * 依赖：
 *   GET /api/analytics/cross-platform/summary?ref_date=
 *   GET /api/analytics/cross-platform/dau?days=
 */

import * as React from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function adminFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------

interface PlatformActive {
  platform: string;
  label: string;
  dau: number;
  wau: number;
  mau: number;
}

interface CrossPlatformSummary {
  period_start: string;
  period_end: string;
  by_platform: PlatformActive[];
  unified: { dau: number; wau: number; mau: number };
  cross_platform: {
    multi_platform_users: number;
    multi_platform_share: number;
  };
  overlap: Record<string, Record<string, number>>;
}

interface DauSeries {
  days: number;
  series: { date: string; by_platform: Record<string, number>; unified: number }[];
}

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

const PLATFORM_ORDER = ["webapp", "minip", "feishu", "dingtalk"] as const;
const PLATFORM_LABELS: Record<string, string> = {
  webapp: "Web 浏览器",
  minip: "微信小程序",
  feishu: "飞书应用",
  dingtalk: "钉钉应用",
};
const PLATFORM_COLORS: Record<string, string> = {
  webapp: "#3b82f6",
  minip: "#10b981",
  feishu: "#f59e0b",
  dingtalk: "#ef4444",
};

const formatNumber = (n: number): string => {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
};

// ---------------------------------------------------------------------------
// 仪表盘
// ---------------------------------------------------------------------------

export default function CrossPlatformDashboard() {
  const [refDate, setRefDate] = React.useState<string>(
    new Date().toISOString().slice(0, 10)
  );
  const [summary, setSummary] = React.useState<CrossPlatformSummary | null>(null);
  const [dau, setDau] = React.useState<DauSeries | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const loadData = React.useCallback(async (date: string) => {
    setLoading(true);
    setError(null);
    try {
      const [s, d] = await Promise.all([
        adminFetch<CrossPlatformSummary>(
          `/api/analytics/cross-platform/summary?ref_date=${encodeURIComponent(date)}`
        ),
        adminFetch<DauSeries>(`/api/analytics/cross-platform/dau?days=7`),
      ]);
      setSummary(s);
      setDau(d);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "加载失败";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    loadData(refDate);
  }, [refDate, loadData]);

  return (
    <main className="mx-auto max-w-6xl space-y-6 px-4 py-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            跨端日活统计
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            DAU / WAU / MAU 按端拆分，跨端用户去重，多端用户画像
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">参考日期</span>
          <input
            type="date"
            value={refDate}
            onChange={(e) => setRefDate(e.target.value)}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
            max={new Date().toISOString().slice(0, 10)}
          />
        </div>
      </header>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* KPI */}
      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiCard
          label="DAU (跨端去重)"
          value={summary?.unified.dau}
          loading={loading}
        />
        <KpiCard
          label="WAU (跨端去重)"
          value={summary?.unified.wau}
          loading={loading}
        />
        <KpiCard
          label="MAU (跨端去重)"
          value={summary?.unified.mau}
          loading={loading}
        />
        <KpiCard
          label="多端用户占比"
          value={
            summary
              ? `${(summary.cross_platform.multi_platform_share * 100).toFixed(1)}%`
              : undefined
          }
          loading={loading}
          hint={
            summary
              ? `${summary.cross_platform.multi_platform_users.toLocaleString()} 用户跨 ≥2 端活跃`
              : undefined
          }
        />
      </section>

      {/* 按端拆分 DAU/WAU/MAU */}
      <Card>
        <CardHeader>
          <CardTitle>按端拆分 — DAU / WAU / MAU</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-64 w-full" />
          ) : summary ? (
            <PlatformSplitChart data={summary.by_platform} />
          ) : null}
        </CardContent>
      </Card>

      {/* 端×端重合热图 */}
      <Card>
        <CardHeader>
          <CardTitle>跨端用户重合矩阵 (MAU 30 天)</CardTitle>
          <p className="text-xs text-muted-foreground">
            行/列均为端；单元格 = 同时活跃于两端的人数。颜色越深=重合越多。
          </p>
        </CardHeader>
        <CardContent>
          {loading || !summary ? (
            <Skeleton className="h-48 w-full" />
          ) : (
            <OverlapHeatmap overlap={summary.overlap} />
          )}
        </CardContent>
      </Card>

      {/* 7 天 DAU 趋势 */}
      <Card>
        <CardHeader>
          <CardTitle>DAU 7 天趋势 (按端 + 统一)</CardTitle>
        </CardHeader>
        <CardContent>
          {loading || !dau ? (
            <Skeleton className="h-56 w-full" />
          ) : (
            <DauTrendChart dau={dau} />
          )}
        </CardContent>
      </Card>
    </main>
  );
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

function KpiCard({
  label,
  value,
  loading,
  hint,
}: {
  label: string;
  value: number | string | undefined;
  loading: boolean;
  hint?: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-8 w-24" />
        ) : (
          <div className="text-2xl font-semibold">
            {value === undefined ? "—" : typeof value === "number" ? formatNumber(value) : value}
          </div>
        )}
        {hint && !loading && (
          <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
        )}
      </CardContent>
    </Card>
  );
}

function PlatformSplitChart({ data }: { data: PlatformActive[] }) {
  const maxMau = Math.max(1, ...data.map((d) => d.mau));
  return (
    <div className="space-y-4">
      {data.map((row) => (
        <div key={row.platform} className="space-y-1">
          <div className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <span
                className="inline-block h-3 w-3 rounded-sm"
                style={{ backgroundColor: PLATFORM_COLORS[row.platform] ?? "#888" }}
                aria-hidden
              />
              <span className="font-medium">
                {PLATFORM_LABELS[row.platform] ?? row.platform}
              </span>
              <Badge variant="outline" className="font-mono text-xs">
                {row.platform}
              </Badge>
            </div>
            <div className="flex gap-4 text-xs text-muted-foreground">
              <span>DAU {formatNumber(row.dau)}</span>
              <span>WAU {formatNumber(row.wau)}</span>
              <span className="font-semibold text-foreground">
                MAU {formatNumber(row.mau)}
              </span>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-1">
            <Bar pct={(row.dau / maxMau) * 100} color={PLATFORM_COLORS[row.platform]} />
            <Bar pct={(row.wau / maxMau) * 100} color={PLATFORM_COLORS[row.platform]} muted />
            <Bar pct={(row.mau / maxMau) * 100} color={PLATFORM_COLORS[row.platform]} />
          </div>
        </div>
      ))}
    </div>
  );
}

function Bar({ pct, color, muted }: { pct: number; color: string; muted?: boolean }) {
  return (
    <div className="h-3 overflow-hidden rounded-sm bg-muted">
      <div
        className="h-full rounded-sm transition-all"
        style={{
          width: `${Math.min(100, Math.max(0, pct))}%`,
          backgroundColor: muted ? `${color}80` : color,
        }}
      />
    </div>
  );
}

function OverlapHeatmap({
  overlap,
}: {
  overlap: Record<string, Record<string, number>>;
}) {
  const values = Object.values(overlap).flatMap((r) => Object.values(r));
  const max = Math.max(1, ...values);
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th className="px-2 py-1 text-left text-xs text-muted-foreground"></th>
            {PLATFORM_ORDER.map((p) => (
              <th key={p} className="px-2 py-1 text-center text-xs font-medium">
                {PLATFORM_LABELS[p]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {PLATFORM_ORDER.map((row) => (
            <tr key={row}>
              <td className="whitespace-nowrap px-2 py-1 text-xs font-medium">
                {PLATFORM_LABELS[row]}
              </td>
              {PLATFORM_ORDER.map((col) => {
                const v = overlap[row]?.[col] ?? 0;
                const intensity = v / max;
                return (
                  <td
                    key={col}
                    className="border border-border/40 px-3 py-2 text-center font-mono text-xs"
                    style={{
                      backgroundColor:
                        v === 0
                          ? "transparent"
                          : `rgba(59, 130, 246, ${0.1 + intensity * 0.85})`,
                      color: intensity > 0.45 ? "#fff" : undefined,
                    }}
                  >
                    {formatNumber(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DauTrendChart({ dau }: { dau: DauSeries }) {
  const allUnified = dau.series.map((s) => s.unified);
  const max = Math.max(1, ...allUnified);
  return (
    <div className="space-y-3">
      <div className="flex items-end gap-1 h-40">
        {dau.series.map((day) => {
          const unifiedH = (day.unified / max) * 100;
          return (
            <div key={day.date} className="flex-1 flex flex-col items-center gap-1">
              <div className="flex items-end gap-0.5 h-full w-full justify-center">
                {PLATFORM_ORDER.map((p) => {
                  const v = day.by_platform[p] ?? 0;
                  const h = (v / max) * 100;
                  return (
                    <div
                      key={p}
                      className="w-2 rounded-sm"
                      style={{
                        height: `${Math.max(1, h)}%`,
                        backgroundColor: PLATFORM_COLORS[p],
                      }}
                      title={`${PLATFORM_LABELS[p]}: ${v}`}
                    />
                  );
                })}
              </div>
              <div className="text-[10px] text-muted-foreground">
                {day.date.slice(5)}
              </div>
              <div
                className="text-[10px] font-medium"
                style={{ color: "#3b82f6" }}
                title="跨端去重 DAU"
              >
                {formatNumber(day.unified)}
              </div>
              <div
                className="h-0.5 w-full rounded-sm"
                style={{
                  height: `${Math.max(2, unifiedH)}%`,
                  backgroundColor: "#3b82f6",
                  opacity: 0.4,
                }}
                aria-hidden
              />
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs">
        {PLATFORM_ORDER.map((p) => (
          <div key={p} className="flex items-center gap-1">
            <span
              className="inline-block h-2 w-2 rounded-sm"
              style={{ backgroundColor: PLATFORM_COLORS[p] }}
            />
            <span>{PLATFORM_LABELS[p]}</span>
          </div>
        ))}
        <div className="flex items-center gap-1">
          <span className="inline-block h-0.5 w-6 bg-blue-500 opacity-60" />
          <span>跨端去重</span>
        </div>
      </div>
    </div>
  );
}
