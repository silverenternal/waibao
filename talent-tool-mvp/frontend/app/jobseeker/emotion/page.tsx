"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v9.1 — Emotion timeline page (T605).
 *
 * Layout:
 *   ┌─ Header (sticky · title · range toggle · refresh) ───────┐
 *   ├─ KPI band  (count / alerts / avg / mood band)           │
 *   ├─ Tabs    折线图 / 情绪分布 / 日报                           │
 *   │   ├─ tab 折线: chart + detail + correlation              │
 *   │   ├─ tab 分布: emotion donut + intensity histogram       │
 *   │   └─ tab 日报: EmotionWeekSummary + EmotionCareCard      │
 *   └─ 关怀 / 风险 trigger correlation  (sticky bottom?)       │
 *
 * Clicking a chart point surfaces its day in the `EmotionEventDetail`
 * side card. The page polls every 60s so newly detected emotions surface
 * without a manual refresh.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Loader2,
  RefreshCcw,
  Heart,
  AlertTriangle,
  CalendarRange,
  Activity,
  PieChart as PieChartIcon,
  Notebook,
  HeartHandshake,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

import {
  EmotionTimelineChart,
  type EmotionPoint,
} from "@/components/charts/emotion-timeline-chart";
import {
  EmotionEventDetail,
  type EmotionEventDetailData,
} from "@/components/EmotionEventDetail";
import {
  EmotionWeekSummary,
  weeklyAggregate,
  type RawTimelineRow,
} from "@/components/EmotionWeekSummary";
import { EmotionTriggerCorrelation } from "@/components/EmotionTriggerCorrelation";
import {
  EmotionCareCard,
  type CareTicket,
  type CareAction,
} from "@/components/emotion/EmotionCareCard";
import {
  TremorKpiCard,
  TremorKpiGrid,
  TremorPanel,
} from "@/components/charts/tremor-shell";
import { EmotionDistribution } from "@/components/emotion/EmotionDistribution";

const POLL_MS = 60_000;

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

async function authHeaders(): Promise<HeadersInit> {
  if (typeof window !== "undefined") {
    const legacy = window.localStorage.getItem("sb_token");
    if (legacy) return { Authorization: `Bearer ${legacy}` };
  }
  try {
    const { createClient } = await import("@/lib/supabase");
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (token) return { Authorization: `Bearer ${token}` };
  } catch {
    /* ignore */
  }
  return {};
}

interface CareApiResponse {
  ticket?: CareTicket;
  actions?: CareAction[];
}

export default function EmotionTimelinePage() {
  const router = useRouter();
  const [points, setPoints] = React.useState<EmotionPoint[]>([]);
  const [journalPoints, setJournalPoints] = React.useState<
    { date: string; moodScore: number; rating: "excellent" | "good" | "warning" | null }[]
  >([]);
  const [selected, setSelected] = React.useState<EmotionEventDetailData | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [days, setDays] = React.useState(30);
  const [care, setCare] = React.useState<CareApiResponse | null>(null);

  const load = React.useCallback(
    async (manual = false) => {
      if (manual) setRefreshing(true);
      else setLoading(true);
      setError(null);
      try {
        const headers = await authHeaders();
        const [emoResp, jourResp] = await Promise.all([
          fetch(`${API_BASE}/api/emotion/timeline?days=${days}`, {
            headers,
            cache: "no-store",
          }),
          fetch(`${API_BASE}/api/journal/timeline?days=${Math.min(days, 60)}`, {
            headers,
            cache: "no-store",
          }),
        ]);
        if (!emoResp.ok) throw new Error(`情绪接口 ${emoResp.status}`);
        if (!jourResp.ok) throw new Error(`日记接口 ${jourResp.status}`);
        const emoJson = (await emoResp.json()) as { data: RawTimelineRow[] };
        const jourJson = (await jourResp.json()) as {
          data: Array<{
            id: string;
            journal_date: string;
            mood_score: number | null;
            ai_rating: string | null;
            content: string;
          }>;
        };

        const emotionPoints: EmotionPoint[] = (emoJson.data ?? []).map((r) => {
          const dateStr = (r.recorded_at ?? "").slice(0, 10);
          const matched = (jourJson.data ?? []).find(
            (j) => j.journal_date === dateStr,
          );
          return {
            date: dateStr,
            sentiment: r.sentiment ?? null,
            intensity: r.intensity ?? null,
            needs_attention: !!r.needs_attention,
            primary_emotion: r.primary_emotion ?? undefined,
            trigger_text: r.trigger_text ?? null,
            journal_rating:
              matched?.ai_rating === "excellent" ||
              matched?.ai_rating === "good" ||
              matched?.ai_rating === "warning"
                ? matched.ai_rating
                : null,
            journal_content: matched?.content ?? null,
          };
        });

        // Build correlation joined set: same date in both.
        const journalMood = (jourJson.data ?? [])
          .filter((j) => typeof j.mood_score === "number")
          .map((j) => ({
            date: j.journal_date,
            moodScore: j.mood_score as number,
            rating:
              j.ai_rating === "excellent" ||
              j.ai_rating === "good" ||
              j.ai_rating === "warning"
                ? (j.ai_rating as "excellent" | "good" | "warning")
                : null,
          }));

        setPoints(emotionPoints);
        setJournalPoints(journalMood);

        // If detail panel was empty, fold in the newest row.
        setSelected((prev) => prev ?? toDetail(emotionPoints[emotionPoints.length - 1]));

        // Optionally fetch active care ticket (best-effort)
        try {
          const careResp = await fetch(`${API_BASE}/api/emotion/care/active`, {
            headers,
            cache: "no-store",
          });
          if (careResp.ok) {
            const careJson = (await careResp.json()) as CareApiResponse;
            setCare(careJson);
          }
        } catch {
          /* care is optional */
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "加载失败");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [days],
  );

  React.useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  // ---------------------------------------------------------------- stats
  const { alerts, avg, count, lastEventAt, spark, prevAvg } = React.useMemo(() => {
    const sentiments = points
      .map((p) => p.sentiment)
      .filter((v): v is number => typeof v === "number");
    const sum = sentiments.reduce((a, b) => a + b, 0);
    const mean = sentiments.length ? sum / sentiments.length : 0;
    const half = Math.floor(sentiments.length / 2);
    const prev =
      sentiments.length > 4
        ? sentiments.slice(0, half).reduce((a, b) => a + b, 0) / Math.max(1, half)
        : null;
    return {
      count: points.length,
      alerts: points.filter((p) => p.needs_attention).length,
      avg: mean,
      lastEventAt: points[points.length - 1]?.date ?? null,
      spark: sentiments.slice(-14),
      prevAvg: prev,
    };
  }, [points]);

  const deltaPct = React.useMemo(() => {
    if (prevAvg == null || Math.abs(prevAvg) < 1e-6) return null;
    return ((avg - prevAvg) / Math.abs(prevAvg)) * 100;
  }, [avg, prevAvg]);

  const moodBand = React.useMemo(() => {
    if (avg > 0.2) return { label: "状态向好", tone: "emerald" as const };
    if (avg < -0.2) return { label: "需要支持", tone: "rose" as const };
    return { label: "平稳", tone: "slate" as const };
  }, [avg]);

  const weeklyRows = React.useMemo(
    () => weeklyAggregate(points as unknown as RawTimelineRow[], 4),
    [points],
  );

  const correlation = React.useMemo(() => {
    const out: {
      date: string;
      sentiment: number;
      moodScore: number;
      journalRating: "excellent" | "good" | "warning" | null;
    }[] = [];
    for (const p of points) {
      const mood = journalPoints.find((j) => j.date === p.date);
      if (mood && p.sentiment != null) {
        out.push({
          date: p.date,
          sentiment: p.sentiment,
          moodScore: mood.moodScore,
          journalRating: mood.rating,
        });
      }
    }
    return out;
  }, [points, journalPoints]);

  return (
    <ErrorBoundary>(<div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-100">
        <header className="sticky top-0 z-20 border-b bg-white/80 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => router.push("/jobseeker")}
                aria-label="返回"
              >
                <ArrowLeft className="size-4" />
              </Button>
              <div>
                <h1 className="flex items-center gap-2 text-xl font-semibold text-foreground">
                  <Heart className="size-5 text-pink-500" />
                  情绪时间线
                </h1>
                <p className="text-xs text-muted-foreground">
                  折线 · 触发事件 · 关联日记 · 周报 · 关怀,数据每 {Math.round(POLL_MS / 1000)} 秒刷新
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="hidden gap-1 sm:flex">
                {[14, 30, 60, 90].map((d) => (
                  <Button
                    key={d}
                    size="sm"
                    variant={d === days ? "default" : "outline"}
                    onClick={() => setDays(d)}
                  >
                    {d} 天
                  </Button>
                ))}
              </div>
              <Button
                variant="outline"
                size="icon-sm"
                onClick={() => load(true)}
                disabled={refreshing}
                aria-label="刷新"
              >
                <RefreshCcw className={cn("size-4", refreshing && "animate-spin")} />
              </Button>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-6xl space-y-6 px-6 py-6">
          {/* KPI band — Tremor style */}
          <TremorKpiGrid>
            <TremorKpiCard
              title="记录数"
              value={count}
              unit="条"
              helper={`最近 ${days} 天`}
              spark={spark.length > 1 ? spark : undefined}
            />
            <TremorKpiCard
              title="关注告警"
              value={alerts}
              unit="次"
              delta={alerts > 0 ? alerts * 8 : 0}
              helper={alerts > 0 ? "建议联系 HR" : "状态稳定"}
            />
            <TremorKpiCard
              title="情绪均值"
              value={avg.toFixed(2)}
              helper={`${days} 天滑动平均`}
              delta={deltaPct ?? undefined}
            />
            <TremorKpiCard
              title="状态带"
              value={moodBand.label}
              helper={
                lastEventAt ? `最近记录 · ${lastEventAt}` : "尚无记录"
              }
            />
          </TremorKpiGrid>

          {care?.ticket && (
            <section className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                <HeartHandshake className="size-4 text-rose-500" />
                关怀与建议
                <Badge variant="destructive" className="ml-auto text-[10px]">
                  待处理
                </Badge>
              </div>
              <EmotionCareCard
                ticket={care.ticket}
                actions={care.actions ?? []}
              />
            </section>
          )}

          {loading ? (
            <Card>
              <CardContent className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500">
                <Loader2 className="size-4 animate-spin text-blue-500" />
                加载情绪数据…
              </CardContent>
            </Card>
          ) : error ? (
            <Card className="border-rose-200 bg-rose-50/60">
              <CardContent className="flex flex-col items-center gap-3 py-10 text-sm text-rose-700">
                <AlertTriangle className="size-5" />
                <span>{error}</span>
                <Button variant="outline" size="sm" onClick={() => load(true)}>
                  重试
                </Button>
              </CardContent>
            </Card>
          ) : (
            <Tabs defaultValue="timeline" className="space-y-4">
              <TabsList className="w-full sm:w-fit">
                <TabsTrigger value="timeline">
                  <Activity className="mr-1.5 size-3.5" /> 折线图
                </TabsTrigger>
                <TabsTrigger value="distribution">
                  <PieChartIcon className="mr-1.5 size-3.5" /> 情绪分布
                </TabsTrigger>
                <TabsTrigger value="weekly">
                  <CalendarRange className="mr-1.5 size-3.5" /> 周报
                </TabsTrigger>
              </TabsList>

              <TabsContent value="timeline">
                <div className="grid gap-4 lg:grid-cols-3">
                  <TremorPanel
                    title="情绪倾向 · 强度 · 触发事件"
                    description="点击任意点查看当日详情"
                    className="lg:col-span-2"
                  >
                    <EmotionTimelineChart
                      data={points}
                      height={340}
                      onPointClick={(p) => setSelected(toDetail(p))}
                    />
                  </TremorPanel>
                  <EmotionEventDetail
                    event={selected}
                    onClose={() => setSelected(null)}
                    onOpenJournal={(id) => router.push(`/jobseeker/journal/${id}`)}
                  />
                </div>

                <div className="mt-4">
                  <EmotionTriggerCorrelation joined={correlation} />
                </div>
              </TabsContent>

              <TabsContent value="distribution">
                <TremorPanel
                  title="情绪分布"
                  description="按主情绪频次 + 强度直方图"
                >
                  <EmotionDistribution points={points} />
                </TremorPanel>
              </TabsContent>

              <TabsContent value="weekly">
                <section className="space-y-3">
                  <header className="flex items-center gap-2">
                    <Notebook className="size-4 text-violet-500" />
                    <h2 className="text-sm font-semibold text-slate-800">
                      按周汇总
                    </h2>
                    <Badge variant="outline" className="ml-auto text-[10px]">
                      最近 {weeklyRows.length} 周
                    </Badge>
                  </header>
                  <EmotionWeekSummary rows={weeklyRows} />
                </section>
              </TabsContent>
            </Tabs>
          )}
        </main>
      </div>)</ErrorBoundary>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toDetail(p?: EmotionPoint): EmotionEventDetailData | null {
  if (!p) return null;
  return {
    recorded_at: p.date,
    primary_emotion: p.primary_emotion ?? null,
    sentiment: p.sentiment ?? null,
    intensity: p.intensity ?? null,
    trigger_text: p.trigger_text ?? null,
    needs_attention: !!p.needs_attention,
    journal_rating: p.journal_rating ?? null,
    journal_content: p.journal_content ?? null,
  };
}