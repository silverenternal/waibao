"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { MetricTile } from "@/components/shared/metric-tile";
import { FunnelFilter, type FunnelFilterValue } from "@/components/FunnelFilter";
import { RecruitmentFunnel } from "@/components/charts/recruitment-funnel";
import { StageConversion } from "@/components/charts/stage-conversion";
import { FunnelCostChart } from "@/components/charts/funnel-cost-chart";
import { FunnelTrendChart } from "@/components/charts/funnel-trend-chart";
import { trackFunnelEvent } from "@/lib/funnel-tracker";
import { Users, Target, TrendingUp, Briefcase, DollarSign } from "lucide-react";
import type {
  FunnelResponse,
  FunnelStagesResponse,
} from "@/lib/types";

export default function FunnelPage() {
  const [filter, setFilter] = useState<FunnelFilterValue>({
    days: 30,
    source: "",
    department: "",
  });
  const [data, setData] = useState<FunnelResponse | null>(null);
  const [stages, setStages] = useState<FunnelStagesResponse | null>(null);
  const [costData, setCostData] = useState<FunnelResponse | null>(null);
  const [trend, setTrend] = useState<
    Array<{ week_start: string; week_end: string; by_stage: Record<string, number> }>
  >([]);
  const [loading, setLoading] = useState(true);

  // T1803 — 页面打开时埋一次 "sourced" 漏斗事件 (active session)
  useEffect(() => {
    trackFunnelEvent({
      stage: "sourced",
      source: "mothership_funnel_page",
      metadata: { page: "/mothership/analytics/funnel" },
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [funnel, stagesRes, withCosts, trendRes] = await Promise.all([
          apiClient.analytics.funnel(filter.days),
          apiClient.analytics.funnelStages(filter.days),
          apiClient.analytics
            .funnelWithCosts(filter.days)
            .catch(() => null),
          apiClient.analytics.funnelTrend(13).catch(() => ({ trend: [] })),
        ]);
        if (!cancelled) {
          setData(funnel);
          setStages(stagesRes);
          setCostData(withCosts ?? funnel);
          setTrend(trendRes?.trend ?? []);
        }
      } catch (err) {
        if (!cancelled) {
          console.error("[funnel] load failed", err);
          setData(null);
          setStages(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [filter.days]);

  const sources = data ? Object.keys(data.by_source || {}).sort() : [];

  return (
    <ErrorBoundary>(<div className="space-y-6 p-6">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Recruitment Funnel
            </h1>
            <p className="text-sm text-muted-foreground">
              Pipeline health across sourced → hired stages.
            </p>
          </div>
          <FunnelFilter
            value={filter}
            onChange={setFilter}
            sources={sources}
          />
        </header>
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <MetricTile
            label="Total candidates"
            value={data?.total_candidates ?? 0}
            icon={<Users className="h-4 w-4" />}
            loading={loading}
          />
          <MetricTile
            label="Overall conversion"
            value={
              data
                ? `${(data.overall_conversion ?? 0).toFixed(1)}%`
                : "—"
            }
            icon={<Target className="h-4 w-4" />}
            loading={loading}
          />
          <MetricTile
            label="Top stage"
            value={
              stages?.stages?.length
                ? stages.stages.reduce((max, s) =>
                    s.candidates > max.candidates ? s : max,
                  ).stage
                : "—"
            }
            icon={<TrendingUp className="h-4 w-4" />}
            loading={loading}
          />
          <MetricTile
            label="Hires"
            value={
              stages?.stages?.find((s) => s.stage === "hired")?.candidates ?? 0
            }
            icon={<Briefcase className="h-4 w-4" />}
            loading={loading}
          />
          <MetricTile
            label="Total spend"
            value={
              costData?.stages
                ? `¥${(
                    costData.stages.reduce(
                      (s, x) => s + ((x as any).total_cost_cents ?? 0),
                      0,
                    ) / 100
                  ).toFixed(0)}`
                : "—"
            }
            icon={<DollarSign className="h-4 w-4" />}
            loading={loading}
          />
        </section>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Stage breakdown</CardTitle>
            </CardHeader>
            <CardContent>
              {loading || !stages ? (
                <Skeleton className="h-[280px] w-full" />
              ) : (
                <RecruitmentFunnel stages={stages.stages} />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Stage-to-stage conversion</CardTitle>
            </CardHeader>
            <CardContent>
              {loading || !stages ? (
                <Skeleton className="h-[280px] w-full" />
              ) : (
                <StageConversion
                  conversionRates={stages.conversion_rates || {}}
                />
              )}
            </CardContent>
          </Card>
        </div>
        {/* T1803 — Cost overlay + weekly trend */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Cost per stage (¥)</CardTitle>
            </CardHeader>
            <CardContent>
              {loading || !costData ? (
                <Skeleton className="h-[260px] w-full" />
              ) : (
                <FunnelCostChart
                  stages={costData.stages as unknown as Array<{
                    stage: string;
                    candidates: number;
                    total_cost_cents: number;
                    avg_cost_cents: number;
                  }>}
                />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Weekly trend (13 weeks)</CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <Skeleton className="h-[260px] w-full" />
              ) : (
                <FunnelTrendChart trend={trend} />
              )}
            </CardContent>
          </Card>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>By source</CardTitle>
          </CardHeader>
          <CardContent>
            {loading || !data ? (
              <Skeleton className="h-[160px] w-full" />
            ) : sources.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                No channel breakdown recorded.
              </p>
            ) : (
              <div className="rounded-md border overflow-x-auto">
                <table className="w-full text-sm min-w-[640px]">
                  <thead>
                    <tr className="border-b bg-muted text-left">
                      <th className="px-3 py-2 font-medium">Channel</th>
                      {data.stages.map((s) => (
                        <th key={s.stage} className="px-3 py-2 font-medium capitalize">
                          {s.stage}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sources.map((src) => (
                      <tr key={src} className="border-b last:border-0">
                        <td className="px-3 py-2 font-medium">{src}</td>
                        {data.stages.map((s) => (
                          <td key={s.stage} className="px-3 py-2">
                            {data.by_source?.[src]?.[s.stage] ?? 0}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>)</ErrorBoundary>
  );
}