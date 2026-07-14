"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v9.1 — 计划进度页 (T3606)
 *
 *  - KPI band (总体进度 / 已完成 / 进行中 / 长期未推进)
 *  - 进度仪表环 (SVG 自绘)
 *  - PlanProgressTracker 列表
 *  - 历史打卡 Timeline 摘要
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Target,
  CheckCircle2,
  Clock,
  AlertTriangle,
  History,
  TrendingUp,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  PlanProgressTracker,
} from "@/components/plan/PlanProgressTracker";
import {
  fetchPlanProgress,
  type PlanProgress,
} from "@/lib/api-plan";
import { createClient } from "@/lib/supabase";
import {
  TremorKpiCard,
  TremorKpiGrid,
  TremorPanel,
  TremorShell,
} from "@/components/charts/tremor-shell";
import { cn } from "@/lib/utils";

export default function ProgressPage() {
  const router = useRouter();
  const [userId, setUserId] = React.useState<string | null>(null);
  const [data, setData] = React.useState<PlanProgress | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(
    async (uid: string) => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchPlanProgress(uid);
        setData(res);
      } catch (e) {
        setError(e instanceof Error ? e.message : "加载失败");
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  React.useEffect(() => {
    let cancelled = false;
    async function resolveUser() {
      try {
        const supabase = createClient();
        const { data: session } = await supabase.auth.getSession();
        const uid = session?.session?.user?.id;
        if (!cancelled && uid) {
          setUserId(uid);
          await load(uid);
          return;
        }
      } catch {
        /* ignore */
      }
      if (!cancelled) {
        const devId =
          (typeof window !== "undefined" &&
            window.localStorage.getItem("dev_user_id")) ||
          "demo-user";
        setUserId(devId);
        await load(devId);
      }
    }
    void resolveUser();
    return () => {
      cancelled = true;
    };
  }, [load]);

  const stats = React.useMemo(() => {
    if (!data) {
      return {
        overall: 0,
        done: 0,
        active: 0,
        stale: 0,
        byBucket: { short: 0, mid: 0, long: 0 },
      };
    }
    const items = data.items;
    return {
      overall: Math.round((data.overall_progress ?? 0) * 100),
      done: items.filter((i) => i.completed).length,
      active: items.filter((i) => !i.completed && i.progress > 0).length,
      stale: data.stale_items?.length ?? 0,
      byBucket: {
        short: items.filter((i) => i.bucket === "short").length,
        mid: items.filter((i) => i.bucket === "mid").length,
        long: items.filter((i) => i.bucket === "long").length,
      },
    };
  }, [data]);

  const toolbar = (
    <>
      <Button asChild size="sm" variant="outline">
        <Link href="/jobseeker/plan">
          <ArrowLeft className="mr-1.5 size-3.5" /> 返回规划
        </Link>
      </Button>
      <Button asChild size="sm">
        <Link href="/jobseeker/plan/market-insights">
          <TrendingUp className="mr-1.5 size-3.5" /> 行情参考
        </Link>
      </Button>
    </>
  );

  return (
    <ErrorBoundary>(<TremorShell
        title="执行进度"
        subtitle="追踪你的职业规划执行情况 · 支持打卡和动态调整"
        badge={data ? `${stats.overall}% 完成` : "加载中"}
        toolbar={toolbar}
      >
        {/* KPI band */}
        <TremorKpiGrid>
          <TremorKpiCard
            title="总体完成度"
            value={`${stats.overall}%`}
            helper={data ? `${data.items.length} 个任务` : "—"}
          />
          <TremorKpiCard
            title="已完成"
            value={stats.done}
            unit="项"
            helper="累计已勾选"
          />
          <TremorKpiCard
            title="进行中"
            value={stats.active}
            unit="项"
            helper="已开始但未完成"
          />
          <TremorKpiCard
            title="长期未推进"
            value={stats.stale}
            unit="项"
            helper={stats.stale > 0 ? "建议尽快打卡或调整" : "状态良好"}
          />
        </TremorKpiGrid>
        {error && (
          <Card className="border-rose-200 bg-rose-50/60">
            <CardContent className="flex items-center gap-3 p-3 text-sm text-rose-700">
              <AlertTriangle className="size-4" />
              <span>{error}</span>
              <Button
                size="sm"
                variant="outline"
                className="ml-auto"
                onClick={() => userId && load(userId)}
              >
                重试
              </Button>
            </CardContent>
          </Card>
        )}
        <div className="grid gap-4 lg:grid-cols-3">
          {/* gauge */}
          <TremorPanel
            title="总体进度仪表"
            description="按比例绘制的同心环"
          >
            <ProgressGauge
              value={stats.overall}
              short={stats.byBucket.short}
              mid={stats.byBucket.mid}
              long={stats.byBucket.long}
            />
          </TremorPanel>

          {/* bucket distribution */}
          <TremorPanel
            title="桶分布"
            description="按短 / 中 / 长期拆分"
            className="lg:col-span-2"
          >
            <div className="grid grid-cols-3 gap-3">
              {(
                [
                  {
                    key: "short",
                    label: "短期",
                    tone: "from-emerald-50 to-emerald-100 border-emerald-200",
                    text: "text-emerald-700",
                  },
                  {
                    key: "mid",
                    label: "中期",
                    tone: "from-sky-50 to-sky-100 border-sky-200",
                    text: "text-sky-700",
                  },
                  {
                    key: "long",
                    label: "长期",
                    tone: "from-violet-50 to-violet-100 border-violet-200",
                    text: "text-violet-700",
                  },
                ] as const
              ).map((b) => {
                const count = stats.byBucket[b.key];
                return (
                  <div
                    key={b.key}
                    className={cn(
                      "rounded-xl border bg-gradient-to-br p-4",
                      b.tone,
                    )}
                  >
                    <p className="text-xs text-muted-foreground">{b.label}任务</p>
                    <p className={cn("mt-1 text-2xl font-semibold", b.text)}>
                      {count}
                    </p>
                  </div>
                );
              })}
            </div>
            <div className="mt-4 flex flex-wrap gap-3 text-xs">
              <Badge variant="outline" className="gap-1">
                <Target className="size-3" /> {stats.byBucket.short} 短期
              </Badge>
              <Badge variant="outline" className="gap-1">
                <Clock className="size-3" /> {stats.byBucket.mid} 中期
              </Badge>
              <Badge variant="outline" className="gap-1">
                <Sparkles className="size-3" /> {stats.byBucket.long} 长期
              </Badge>
              {data?.updated_at && (
                <span className="ml-auto text-muted-foreground">
                  最近更新 · {new Date(data.updated_at).toLocaleString()}
                </span>
              )}
            </div>
          </TremorPanel>
        </div>
        {/* tracker */}
        {data && userId ? (
          <PlanProgressTracker
            userId={userId}
            data={data}
            onChanged={() => void load(userId)}
          />
        ) : loading ? (
          <Card>
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              加载中…
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
              <History className="size-6 text-slate-400" />
              <p className="text-sm text-slate-500">
                尚未生成职业规划,先去
                <Button
                  variant="link"
                  className="px-1"
                  onClick={() => router.push("/jobseeker/plan")}
                >
                  生成规划
                </Button>
                再来打卡吧。
              </p>
            </CardContent>
          </Card>
        )}
      </TremorShell>)</ErrorBoundary>
  );
}

// ---------------------------------------------------------------------------
// ProgressGauge — 自绘 SVG 同心环
// ---------------------------------------------------------------------------

function ProgressGauge({
  value,
  short,
  mid,
  long,
}: {
  value: number;
  short: number;
  mid: number;
  long: number;
}) {
  const total = Math.max(1, short + mid + long);
  const arcs = [
    { key: "short", count: short, color: "#10b981", label: "短期" },
    { key: "mid", count: mid, color: "#0ea5e9", label: "中期" },
    { key: "long", count: long, color: "#8b5cf6", label: "长期" },
  ];

  // three rings
  const cx = 110;
  const cy = 110;
  const rOuter = 88;
  const stroke = 14;
  const rMid = 70;
  const rInner = 52;

  const ratio = Math.min(1, Math.max(0, value / 100));

  return (
    <div className="flex flex-col items-center gap-4 sm:flex-row">
      <svg viewBox="0 0 220 220" width={220} height={220} aria-label="progress gauge">
        {/* background rings */}
        <circle cx={cx} cy={cy} r={rOuter} stroke="#e2e8f0" strokeWidth={stroke} fill="none" />
        <circle cx={cx} cy={cy} r={rMid} stroke="#e2e8f0" strokeWidth={stroke} fill="none" />
        <circle cx={cx} cy={cy} r={rInner} stroke="#e2e8f0" strokeWidth={stroke} fill="none" />

        {/* overall progress — outer ring */}
        {ratio > 0 && (
          <circle
            cx={cx}
            cy={cy}
            r={rOuter}
            stroke="#6366f1"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${2 * Math.PI * rOuter * ratio} ${2 * Math.PI * rOuter}`}
            transform={`rotate(-90 ${cx} ${cy})`}
            fill="none"
          />
        )}

        {/* bucket arcs — middle ring */}
        {(() => {
          let cursor = 0;
          return arcs.map((a) => {
            if (a.count === 0) return null;
            const portion = a.count / total;
            const start = cursor;
            cursor += portion;
            const dash = `${2 * Math.PI * rMid * portion} ${2 * Math.PI * rMid}`;
            const offset = -2 * Math.PI * rMid * start;
            return (
              <circle
                key={a.key}
                cx={cx}
                cy={cy}
                r={rMid}
                stroke={a.color}
                strokeWidth={stroke}
                fill="none"
                strokeDasharray={dash}
                strokeDashoffset={offset}
                transform={`rotate(-90 ${cx} ${cy})`}
                strokeLinecap="butt"
              />
            );
          });
        })()}

        {/* inner ring — completed indicator */}
        {ratio > 0 && (
          <circle
            cx={cx}
            cy={cy}
            r={rInner}
            stroke="#10b981"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${2 * Math.PI * rInner * ratio} ${2 * Math.PI * rInner}`}
            transform={`rotate(-90 ${cx} ${cy})`}
            fill="none"
            opacity={0.85}
          />
        )}

        <text x={cx} y={cy - 4} textAnchor="middle" fontSize="34" fontWeight="700" fill="#0f172a">
          {value}%
        </text>
        <text x={cx} y={cy + 16} textAnchor="middle" fontSize="11" fill="#64748b">
          综合完成度
        </text>
      </svg>

      <ul className="flex-1 space-y-2 text-xs">
        {arcs.map((a) => (
          <li key={a.key} className="flex items-center gap-2">
            <span
              className="inline-block size-2.5 rounded-sm"
              style={{ background: a.color }}
            />
            <span className="flex-1 text-slate-700">{a.label}</span>
            <span className="tabular-nums text-muted-foreground">{a.count} 项</span>
          </li>
        ))}
        <li className="mt-3 flex items-center gap-2 text-[11px] text-muted-foreground">
          <CheckCircle2 className="size-3 text-emerald-500" />
          外环 · 综合
        </li>
        <li className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <Clock className="size-3 text-blue-500" />
          中环 · 桶分布
        </li>
        <li className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <Target className="size-3 text-emerald-500" />
          内环 · 完成度
        </li>
      </ul>
    </div>
  );
}