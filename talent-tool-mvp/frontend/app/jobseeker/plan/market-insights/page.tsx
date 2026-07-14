"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v9.1 — 市场行情 (T3607)
 *
 *  - 头部过滤 (目标岗位 + 城市)
 *  - KPI band (薪资中位 / P25 / P75 / 岗位样本数)
 *  - 薪资趋势图 (MarketSalaryChart)
 *  - 热门技能雷达 (HotSkillsRadar)
 *  - 岗位供给趋势 (JobTrendChart)
 *  - 自绘 offer 分位定位器 (CompareToMarket)
 *  - 样本岗位列表 (内部卡片,带排序)
 *
 * 复用: MarketSalaryChart / HotSkillsRadar / JobTrendChart / TremorShell
 */

import * as React from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Banknote,
  Building2,
  MapPin,
  Search,
  Loader2,
  Award,
  Briefcase,
  Sparkles,
  AlertTriangle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { MarketSalaryChart } from "@/components/plan/MarketSalaryChart";
import { HotSkillsRadar } from "@/components/plan/HotSkillsRadar";
import { JobTrendChart } from "@/components/plan/JobTrendChart";
import {
  fetchMarketInsights,
  type MarketInsights,
  type JobPosting,
  type SalaryPoint,
  type SkillDemand,
} from "@/lib/api-market";
import {
  TremorKpiCard,
  TremorKpiGrid,
  TremorPanel,
  TremorShell,
} from "@/components/charts/tremor-shell";
import { cn } from "@/lib/utils";

const CITY_PRESETS = ["上海", "北京", "深圳", "杭州", "广州", "成都", "远程"] as const;

const ROLE_PRESETS = [
  "Python 后端",
  "前端工程师",
  "算法工程师",
  "数据分析师",
  "产品经理",
  "DevOps",
] as const;

type SortKey = "salary_desc" | "company" | "title";

export default function MarketInsightsPage() {
  const [role, setRole] = React.useState("Python 后端");
  const [city, setCity] = React.useState("上海");
  const [data, setData] = React.useState<MarketInsights | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [sort, setSort] = React.useState<SortKey>("salary_desc");
  // 我的 offer (用于分位定位) — 默认值便于演示
  const [myOffer, setMyOffer] = React.useState<number>(28);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const mi = await fetchMarketInsights(role, city);
      setData(mi);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [role, city]);

  React.useEffect(() => {
    void load();
  }, [load]);

  // ---- derived ----
  const stats = React.useMemo(() => {
    if (!data) {
      return {
        median: 0,
        p25: 0,
        p75: 0,
        sample: 0,
        latest: null as SalaryPoint | null,
      };
    }
    const last = data.salary_trends?.[data.salary_trends.length - 1] ?? null;
    return {
      median: last?.median_k ?? 0,
      p25: last?.p25_k ?? 0,
      p75: last?.p75_k ?? 0,
      sample: last?.sample_size ?? 0,
      latest: last,
    };
  }, [data]);

  const sortedJobs = React.useMemo(() => {
    const list = [...(data?.sample_jobs ?? [])];
    if (sort === "salary_desc") {
      list.sort((a, b) => (b.salary_max_k ?? 0) - (a.salary_max_k ?? 0));
    } else if (sort === "company") {
      list.sort((a, b) => a.company.localeCompare(b.company));
    } else if (sort === "title") {
      list.sort((a, b) => a.title.localeCompare(b.title));
    }
    return list;
  }, [data, sort]);

  const toolbar = (
    <Button asChild size="sm" variant="outline">
      <Link href="/jobseeker/plan">
        <ArrowLeft className="mr-1.5 size-3.5" /> 返回规划
      </Link>
    </Button>
  );

  return (
    <ErrorBoundary>(<TremorShell
        title="市场行情"
        subtitle="基于真实招聘数据的市场洞察 — 判断目标岗位的供需与薪资趋势"
        badge={data?.provider ?? "—"}
        toolbar={toolbar}
      >
        {/* filter bar */}
        <Card>
          <CardContent className="flex flex-wrap items-end gap-3 p-4">
            <div className="min-w-[180px] flex-1">
              <label className="mb-1 block text-xs text-muted-foreground">目标岗位</label>
              <Input
                value={role}
                onChange={(e) => setRole(e.target.value)}
                placeholder="例:Python 后端 / 前端 / 算法"
              />
              <div className="mt-2 flex flex-wrap gap-1">
                {ROLE_PRESETS.map((r) => (
                  <button
                    key={r}
                    onClick={() => setRole(r)}
                    className={cn(
                      "rounded-full border px-2 py-0.5 text-[11px] transition",
                      role === r
                        ? "border-blue-300 bg-blue-50 text-blue-700"
                        : "border-slate-200 text-slate-600 hover:bg-slate-50",
                    )}
                  >
                    {r}
                  </button>
                ))}
              </div>
            </div>
            <div className="min-w-[180px] flex-1">
              <label className="mb-1 block text-xs text-muted-foreground">城市</label>
              <Input
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="上海"
              />
              <div className="mt-2 flex flex-wrap gap-1">
                {CITY_PRESETS.map((c) => (
                  <button
                    key={c}
                    onClick={() => setCity(c)}
                    className={cn(
                      "rounded-full border px-2 py-0.5 text-[11px] transition",
                      city === c
                        ? "border-blue-300 bg-blue-50 text-blue-700"
                        : "border-slate-200 text-slate-600 hover:bg-slate-50",
                    )}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </div>
            <Button onClick={() => void load()} disabled={loading}>
              {loading ? (
                <Loader2 className="mr-1.5 size-3.5 animate-spin" />
              ) : (
                <Search className="mr-1.5 size-3.5" />
              )}
              刷新
            </Button>
          </CardContent>
        </Card>
        {error && (
          <Card className="border-rose-200 bg-rose-50/60">
            <CardContent className="flex items-center gap-3 p-3 text-sm text-rose-700">
              <AlertTriangle className="size-4" />
              <span>{error}</span>
              <Button size="sm" variant="outline" className="ml-auto" onClick={() => void load()}>
                重试
              </Button>
            </CardContent>
          </Card>
        )}
        {/* KPI band */}
        <TremorKpiGrid>
          <TremorKpiCard
            title="薪资中位数"
            value={stats.median || "—"}
            unit={stats.median ? "k" : ""}
            helper={stats.latest ? `${stats.latest.period} · ${role}` : "暂无数据"}
          />
          <TremorKpiCard
            title="P25 分位"
            value={stats.p25 || "—"}
            unit={stats.p25 ? "k" : ""}
            helper="入门薪资区间下界"
          />
          <TremorKpiCard
            title="P75 分位"
            value={stats.p75 || "—"}
            unit={stats.p75 ? "k" : ""}
            helper="资深薪资区间上界"
          />
          <TremorKpiCard
            title="岗位样本"
            value={stats.sample || 0}
            unit="个"
            helper={data?.sample_jobs?.length ? `样本 ${data.sample_jobs.length} 条岗位` : "尚未抓取"}
          />
        </TremorKpiGrid>
        <Tabs defaultValue="salary" className="space-y-4">
          <TabsList className="flex flex-wrap">
            <TabsTrigger value="salary">
              <Banknote className="mr-1.5 size-3.5" /> 薪资 / 趋势
            </TabsTrigger>
            <TabsTrigger value="skills">
              <Sparkles className="mr-1.5 size-3.5" /> 热门技能
            </TabsTrigger>
            <TabsTrigger value="compare">
              <Award className="mr-1.5 size-3.5" /> Offer 分位
            </TabsTrigger>
            <TabsTrigger value="jobs">
              <Briefcase className="mr-1.5 size-3.5" /> 样本岗位
            </TabsTrigger>
          </TabsList>

          <TabsContent value="salary">
            <div className="grid gap-4 lg:grid-cols-2">
              <TremorPanel
                title="薪资中位数趋势"
                description="P25 / 中位 / P75 三条曲线"
              >
                <MarketSalaryChart data={data?.salary_trends ?? []} />
              </TremorPanel>
              <TremorPanel
                title="岗位供给量趋势"
                description="按月统计的样本岗位数"
              >
                <JobTrendChart
                  data={(data?.salary_trends ?? []).map((s) => ({
                    period: s.period,
                    job_count: s.sample_size ?? 0,
                    median_k: s.median_k,
                  }))}
                />
              </TremorPanel>
            </div>
          </TabsContent>

          <TabsContent value="skills">
            <TremorPanel
              title="热门技能需求"
              description="分数越高表示招聘需求越强 · 点击查看岗位详情"
            >
              <HotSkillsRadar data={data?.hot_skills ?? []} />
              <SkillBars data={data?.hot_skills ?? []} />
            </TremorPanel>
          </TabsContent>

          <TabsContent value="compare">
            <div className="grid gap-4 lg:grid-cols-2">
              <TremorPanel
                title="我的 Offer 分位"
                description={`对比 ${role} · ${city} 整体水平`}
              >
                <CompareToMarket
                  myOffer={myOffer}
                  median={stats.median}
                  p25={stats.p25}
                  p75={stats.p75}
                  onChange={setMyOffer}
                />
              </TremorPanel>
              <TremorPanel
                title="分位对照表"
                description="用最近一期数据估算"
              >
                <PercentileTable
                  role={role}
                  city={city}
                  median={stats.median}
                  p25={stats.p25}
                  p75={stats.p75}
                />
              </TremorPanel>
            </div>
          </TabsContent>

          <TabsContent value="jobs">
            <TremorPanel
              title="样本岗位"
              description={`来源 ${data?.provider ?? "—"} · ${data?.sample_jobs?.length ?? 0} 条`}
              actions={
                <div className="flex items-center gap-1 text-xs">
                  {(
                    [
                      { key: "salary_desc", label: "薪资" },
                      { key: "company", label: "公司" },
                      { key: "title", label: "岗位" },
                    ] as const
                  ).map((s) => (
                    <button
                      key={s.key}
                      onClick={() => setSort(s.key)}
                      className={cn(
                        "rounded border px-2 py-0.5 transition",
                        sort === s.key
                          ? "border-blue-300 bg-blue-50 text-blue-700"
                          : "border-slate-200 text-slate-600 hover:bg-slate-50",
                      )}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              }
            >
              {!sortedJobs.length ? (
                <p className="py-12 text-center text-sm text-muted-foreground">
                  暂无样本岗位 — 调整关键词再试
                </p>
              ) : (
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {sortedJobs.map((j: JobPosting) => (
                    <JobCard key={`${j.source}-${j.external_id}`} job={j} />
                  ))}
                </div>
              )}
            </TremorPanel>
          </TabsContent>
        </Tabs>
      </TremorShell>)</ErrorBoundary>
  );
}

// ---------------------------------------------------------------------------
// Sub-blocks
// ---------------------------------------------------------------------------

function JobCard({ job }: { job: JobPosting }) {
  return (
    <a
      href={job.url || "#"}
      target="_blank"
      rel="noreferrer"
      className="group block rounded-lg border bg-white/70 p-3 transition hover:-translate-y-0.5 hover:bg-white hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-2">
        <h4 className="line-clamp-2 text-sm font-semibold text-slate-800 group-hover:text-blue-700">
          {job.title}
        </h4>
        <Badge variant="outline" className="text-[10px]">
          {job.source}
        </Badge>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <Building2 className="h-3 w-3" />
          {job.company}
        </span>
        {job.city && (
          <span className="inline-flex items-center gap-1">
            <MapPin className="h-3 w-3" />
            {job.city}
          </span>
        )}
        {job.salary_min_k && job.salary_max_k && (
          <span className="inline-flex items-center gap-1 font-medium text-emerald-700">
            <Banknote className="h-3 w-3" />
            {job.salary_min_k}-{job.salary_max_k}k
          </span>
        )}
      </div>
      {job.skills && job.skills.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {job.skills.slice(0, 5).map((s) => (
            <span
              key={s}
              className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground"
            >
              {s}
            </span>
          ))}
        </div>
      )}
    </a>
  );
}

function SkillBars({ data }: { data: SkillDemand[] }) {
  if (!data?.length) return null;
  const top = data.slice(0, 8);
  const max = Math.max(...top.map((s) => s.demand_score)) || 1;
  return (
    <ul className="mt-4 space-y-1.5">
      {top.map((s) => {
        const pct = Math.round((s.demand_score / max) * 100);
        return (
          <li key={s.skill} className="flex items-center gap-2 text-xs">
            <span className="w-24 truncate text-slate-700">{s.skill}</span>
            <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
              <div
                className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-indigo-400 to-violet-500"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="w-12 text-right tabular-nums text-muted-foreground">
              {s.demand_score}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function CompareToMarket({
  myOffer,
  median,
  p25,
  p75,
  onChange,
}: {
  myOffer: number;
  median: number;
  p25: number;
  p75: number;
  onChange: (v: number) => void;
}) {
  const max = Math.max(p75 * 1.2, myOffer * 1.1, median * 1.2, 1);
  const myPct = Math.min(1, myOffer / max);
  const medianPct = median ? Math.min(1, median / max) : 0;
  const p25Pct = p25 ? Math.min(1, p25 / max) : 0;
  const p75Pct = p75 ? Math.min(1, p75 / max) : 0;

  // 估算分位: 基于线性插值
  const percentile = React.useMemo(() => {
    if (!median) return 0;
    if (myOffer <= p25) return Math.max(0, Math.round(((myOffer / Math.max(p25, 1)) * 25)));
    if (myOffer <= median) {
      return Math.round(25 + ((myOffer - p25) / Math.max(median - p25, 1)) * 25);
    }
    if (myOffer <= p75) {
      return Math.round(50 + ((myOffer - median) / Math.max(p75 - median, 1)) * 25);
    }
    return Math.min(99, Math.round(75 + ((myOffer - p75) / Math.max(p75, 1)) * 25));
  }, [myOffer, median, p25, p75]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <label className="text-xs text-muted-foreground">我的 Offer (k/月)</label>
        <Input
          type="number"
          min={1}
          max={200}
          value={myOffer}
          onChange={(e) => onChange(Math.max(1, Number(e.target.value || 1)))}
          className="h-8 w-24"
        />
        <Badge variant="outline" className="ml-auto">
          分位 · P{percentile}
        </Badge>
      </div>

      <div className="space-y-3">
        {/* ruler */}
        <div className="relative h-3 rounded-full bg-gradient-to-r from-rose-300 via-amber-200 to-emerald-300">
          {/* p25 / median / p75 markers */}
          {p25 > 0 && (
            <div
              className="absolute -top-1 h-5 w-0.5 bg-slate-600"
              style={{ left: `${p25Pct * 100}%` }}
              aria-label="p25"
            />
          )}
          {median > 0 && (
            <div
              className="absolute -top-1.5 h-6 w-0.5 bg-blue-700"
              style={{ left: `${medianPct * 100}%` }}
              aria-label="median"
            />
          )}
          {p75 > 0 && (
            <div
              className="absolute -top-1 h-5 w-0.5 bg-slate-600"
              style={{ left: `${p75Pct * 100}%` }}
              aria-label="p75"
            />
          )}
          {/* my offer marker */}
          <div
            className="absolute -top-2 h-7 w-1.5 rounded-sm bg-blue-600 shadow"
            style={{ left: `calc(${myPct * 100}% - 3px)` }}
            aria-label="my offer"
          />
        </div>
        <div className="flex justify-between text-[10px] text-muted-foreground">
          <span>0k</span>
          <span>P25 · {p25 || "—"}k</span>
          <span>中位 · {median || "—"}k</span>
          <span>P75 · {p75 || "—"}k</span>
          <span>{Math.round(max)}k</span>
        </div>
      </div>

      <p className="rounded-md border border-blue-100 bg-blue-50/60 p-2 text-[11px] text-blue-700">
        你的 Offer 落在市场 P{percentile}, {myOffer < median ? "低于" : myOffer > median ? "高于" : "等于"} 中位 {Math.abs(myOffer - median).toFixed(1)}k。
      </p>
    </div>
  );
}

function PercentileTable({
  role,
  city,
  median,
  p25,
  p75,
}: {
  role: string;
  city: string;
  median: number;
  p25: number;
  p75: number;
}) {
  const rows = [
    { label: "入门 / 校招 (P25)", value: p25, hint: "校招 / 应届生中位" },
    { label: "中级 / 中位 (P50)", value: median, hint: "3-5 年经验" },
    { label: "资深 / 高阶 (P75)", value: p75, hint: "5-8 年经验" },
  ];
  return (
    <div className="space-y-3">
      <div className="rounded-md bg-slate-50 p-3 text-xs text-slate-600">
        <p className="font-medium text-slate-800">
          {role} · {city}
        </p>
        <p className="mt-1">单位:k 人民币 / 月</p>
      </div>
      <ul className="divide-y rounded-md border bg-white">
        {rows.map((r) => (
          <li key={r.label} className="flex items-center justify-between p-3 text-sm">
            <div>
              <p className="font-medium text-slate-800">{r.label}</p>
              <p className="text-[11px] text-muted-foreground">{r.hint}</p>
            </div>
            <span className="text-base font-semibold text-blue-700 tabular-nums">
              {r.value || "—"}
              {r.value ? "k" : ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}