"use client";

/**
 * Emotion timeline page (T605).
 *
 * Layout:
 *   ┌─ Header ─────────────────────────────────────┐
 *   ├─ Stat strip (count / alerts / last 7d avg)   │
 *   ├─ Timeline chart (large, clickable points)    │
 *   ├─ Side panel: detail + correlation cards      │
 *   ├─ Weekly summary strip                        │
 *   └─ Daily correlation card (emotion vs diary)   │
 *
 * Clicking a point on the chart pulls that day's data into the
 * `EmotionEventDetail` side card. The page polls every 60s so newly
 * detected emotions surface without a manual refresh.
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
  TrendingUp,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

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
  const { alerts, avg30d, count, lastEventAt } = React.useMemo(() => {
    const sentiments = points
      .map((p) => p.sentiment)
      .filter((v): v is number => typeof v === "number");
    return {
      count: points.length,
      alerts: points.filter((p) => p.needs_attention).length,
      avg30d: sentiments.length
        ? sentiments.reduce((a, b) => a + b, 0) / sentiments.length
        : 0,
      lastEventAt: points[points.length - 1]?.date ?? null,
    };
  }, [points]);

  const weeklyRows = React.useMemo(
    () => weeklyAggregate(points as unknown as RawTimelineRow[], 4),
    [points],
  );

  const correlation = React.useMemo(() => {
    const out: { date: string; sentiment: number; moodScore: number; journalRating: "excellent" | "good" | "warning" | null }[] = [];
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
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
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
                折线 + 触发事件叠加,数据每 {Math.round(POLL_MS / 1000)} 秒刷新
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
        {/* Stats */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard
            label="记录数"
            value={count.toString()}
            icon={<CalendarRange className="size-4 text-blue-500" />}
          />
          <StatCard
            label="关注告警"
            value={alerts.toString()}
            tone={alerts > 0 ? "rose" : "emerald"}
            icon={<AlertTriangle className="size-4 text-rose-500" />}
          />
          <StatCard
            label={`${days}天均值`}
            value={avg30d.toFixed(2)}
            icon={<TrendingUp className="size-4 text-emerald-500" />}
          />
          <StatCard
            label="最近记录"
            value={lastEventAt ?? "—"}
            icon={<Heart className="size-4 text-pink-500" />}
            small
          />
        </div>

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
          <>
            {/* Chart + detail */}
            <div className="grid gap-4 lg:grid-cols-3">
              <Card className="lg:col-span-2">
                <CardContent className="py-4">
                  <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-800">
                    <TrendingUp className="size-4 text-indigo-500" />
                    情绪倾向 · 强度 · 触发事件
                  </h2>
                  <EmotionTimelineChart
                    data={points}
                    height={340}
                    onPointClick={(p) => setSelected(toDetail(p))}
                  />
                </CardContent>
              </Card>
              <EmotionEventDetail
                event={selected}
                onClose={() => setSelected(null)}
                onOpenJournal={(id) => router.push(`/journal/${id}`)}
              />
            </div>

            {/* Weekly strip */}
            <section className="space-y-2">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                <CalendarRange className="size-4 text-violet-500" />
                按周汇总
                <Badge variant="outline" className="ml-auto text-[10px]">
                  最近 {weeklyRows.length} 周
                </Badge>
              </h2>
              <EmotionWeekSummary rows={weeklyRows} />
            </section>

            {/* Correlation */}
            <EmotionTriggerCorrelation joined={correlation} />
          </>
        )}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-blocks
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  icon,
  tone,
  small,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  tone?: "emerald" | "rose";
  small?: boolean;
}) {
  return (
    <Card
      className={cn(
        tone === "rose"
          ? "border-rose-200 bg-rose-50/30"
          : tone === "emerald"
            ? "border-emerald-200 bg-emerald-50/30"
            : "border-slate-200",
      )}
    >
      <CardContent className="flex items-center gap-2 py-3">
        <span className="grid size-8 place-items-center rounded-lg bg-white shadow-sm ring-1 ring-black/5">
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
          <p
            className={cn(
              "font-semibold tabular-nums text-slate-900",
              small ? "text-xs" : "text-base",
            )}
          >
            {value}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

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
