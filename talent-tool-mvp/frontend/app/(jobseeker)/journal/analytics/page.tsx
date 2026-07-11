"use client";

/**
 * Journal analytics page (T606).
 *
 * Layout:
 *   ┌─ Header (range selector + refresh) ───────────┐
 *   ├─ Top stat strip (count / ai-rating / warnings) │
 *   ├─ Rating trend chart (12 weeks stacked area)   │
 *   ├─ AI advice list + warning timeline (2 cols)   │
 *   └─ Action item tracker                          │
 *
 * All API access flows through `frontend/lib/api-journal.ts`.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Calendar,
  ChevronDown,
  Loader2,
  Notebook,
  AlertTriangle,
  Lightbulb,
  Sparkles,
  TrendingUp,
  RefreshCcw,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

import {
  journalApi,
  actionItemsApi,
  type JournalEntry,
  type ActionItem,
  type ActionItemState,
} from "@/lib/api-journal";

import {
  JournalRatingTrend,
  weeklyAggregate,
  type JournalRatingBucket,
} from "@/components/charts/journal-rating-trend";
import {
  JournalAdviceList,
  type JournalRating,
} from "@/components/JournalAdviceList";
import {
  JournalWarningTimeline,
  type JournalWarningRow,
} from "@/components/JournalWarningTimeline";
import { ActionItemTracker } from "@/components/ActionItemTracker";

const RANGES = [
  { label: "30 天", days: 30 },
  { label: "60 天", days: 60 },
  { label: "90 天", days: 90 },
];

const POLL_MS = 90_000;

export default function JournalAnalyticsPage() {
  const router = useRouter();
  const [days, setDays] = React.useState(60);
  const [entries, setEntries] = React.useState<JournalEntry[]>([]);
  const [items, setItems] = React.useState<ActionItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [adviceFilter, setAdviceFilter] =
    React.useState<JournalRating | "all">("all");
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(
    async (manual = false) => {
      if (manual) setRefreshing(true);
      else setLoading(true);
      setError(null);
      try {
        const [jourResp, actResp] = await Promise.all([
          journalApi.timeline({ days }),
          actionItemsApi.list({ limit: 200 }),
        ]);
        setEntries(jourResp.data ?? []);
        setItems(actResp.items ?? []);
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

  // ----------------------------------------------------------------- derived
  const buckets: JournalRatingBucket[] = React.useMemo(
    () =>
      weeklyAggregate(
        entries.map((e) => ({
          id: e.id,
          journal_date: e.journal_date,
          ai_rating: e.ai_rating ?? null,
        })),
        12,
      ),
    [entries],
  );

  const stats = React.useMemo(() => {
    const total = entries.length;
    const ratings = entries.reduce(
      (acc, e) => {
        if (e.ai_rating === "excellent") acc.excellent += 1;
        else if (e.ai_rating === "good") acc.good += 1;
        else if (e.ai_rating === "warning") acc.warning += 1;
        return acc;
      },
      { excellent: 0, good: 0, warning: 0 },
    );
    const warningCount = entries.reduce(
      (acc, e) => acc + (e.ai_warnings ?? []).length,
      0,
    );
    return { total, ...ratings, warningCount };
  }, [entries]);

  const warningRows: JournalWarningRow[] = React.useMemo(
    () =>
      entries
        .filter((e) => (e.ai_warnings ?? []).length > 0)
        .map((e) => ({
          id: e.id,
          journal_date: e.journal_date,
          ai_rating: e.ai_rating ?? null,
          ai_warnings: e.ai_warnings ?? [],
          content: e.content,
        })),
    [entries],
  );

  // ----------------------------------------------------------------- actions
  async function handleToggle(
    item: ActionItem,
    next: ActionItemState,
  ): Promise<void> {
    setItems((prev) =>
      prev.map((it) => (it.id === item.id ? { ...it, state: next } : it)),
    );
    await actionItemsApi.setState(item.id, next);
  }
  async function handleDismiss(item: ActionItem): Promise<void> {
    setItems((prev) =>
      prev.map((it) => (it.id === item.id ? { ...it, state: "dismissed" } : it)),
    );
    await actionItemsApi.dismiss(item.id);
  }
  async function handleCreate(title: string): Promise<void> {
    const resp = await actionItemsApi.create({ title, origin: "user" });
    setItems((prev) => [resp.item, ...prev]);
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100">
      <header className="sticky top-0 z-20 border-b bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => router.push("/jobseeker/journal")}
              aria-label="返回日记"
            >
              <ArrowLeft className="size-4" />
            </Button>
            <div>
              <h1 className="flex items-center gap-2 text-xl font-semibold text-foreground">
                <Notebook className="size-5 text-blue-500" />
                日记 AI 分析
              </h1>
              <p className="text-xs text-muted-foreground">
                rating 趋势 · 智能体建议 · 行动项追踪
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="hidden gap-1 sm:flex">
              {RANGES.map((r) => (
                <Button
                  key={r.days}
                  size="sm"
                  variant={r.days === days ? "default" : "outline"}
                  onClick={() => setDays(r.days)}
                >
                  {r.label}
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
              <RefreshCcw
                className={cn("size-4", refreshing && "animate-spin")}
              />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.push("/jobseeker/journal")}
              className="gap-1"
            >
              <ChevronDown className="size-4 -rotate-90" />
              返回日记
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-6 py-6">
        {loading && <LoadingState />}
        {error && !loading && (
          <ErrorState message={error} onRetry={() => load(true)} />
        )}

        {!loading && !error && (
          <>
            {/* Stats */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard
                label="日记总数"
                value={stats.total.toString()}
                icon={<Calendar className="size-4 text-blue-500" />}
              />
              <StatCard
                label="极佳 / 稳定"
                value={`${stats.excellent + stats.good}`}
                sub={`极佳 ${stats.excellent} · 稳定 ${stats.good}`}
                icon={<Lightbulb className="size-4 text-emerald-500" />}
                tone="emerald"
              />
              <StatCard
                label="需关注"
                value={stats.warning.toString()}
                icon={<AlertTriangle className="size-4 text-rose-500" />}
                tone={stats.warning > 0 ? "rose" : undefined}
              />
              <StatCard
                label="警告累计"
                value={stats.warningCount.toString()}
                icon={<Sparkles className="size-4 text-violet-500" />}
              />
            </div>

            {/* Trend chart */}
            <Card>
              <CardContent className="py-4">
                <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-800">
                  <TrendingUp className="size-4 text-indigo-500" />
                  AI 评级趋势
                  <Badge variant="outline" className="ml-auto text-[10px]">
                    最近 {buckets.length} 周
                  </Badge>
                </h2>
                {buckets.length === 0 ? (
                  <p className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-3 py-6 text-center text-xs text-slate-500">
                    暂无可视化的日记记录。写几篇日记,智能体会自动生成评级。
                  </p>
                ) : (
                  <JournalRatingTrend data={buckets} height={320} />
                )}
              </CardContent>
            </Card>

            {/* Advice list + warning timeline */}
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="space-y-2">
                <div className="flex flex-wrap gap-1">
                  {(
                    [
                      { key: "all", label: "全部" },
                      { key: "excellent", label: "极佳" },
                      { key: "good", label: "稳定" },
                      { key: "warning", label: "需关注" },
                    ] as Array<{ key: JournalRating | "all"; label: string }>
                  ).map((f) => (
                    <Button
                      key={f.key}
                      size="sm"
                      variant={adviceFilter === f.key ? "default" : "outline"}
                      onClick={() => setAdviceFilter(f.key)}
                      className="h-7 text-xs"
                    >
                      {f.label}
                    </Button>
                  ))}
                </div>
                <JournalAdviceList
                  entries={entries.map((e) => ({
                    id: e.id,
                    journal_date: e.journal_date,
                    content: e.content,
                    mood_score: e.mood_score ?? null,
                    ai_rating: e.ai_rating,
                    ai_advice: e.ai_advice ?? null,
                    ai_warnings: e.ai_warnings ?? [],
                  }))}
                  ratingFilter={adviceFilter}
                />
              </div>

              <JournalWarningTimeline rows={warningRows} />
            </div>

            {/* Action items */}
            <ActionItemTracker
              items={items}
              loading={false}
              onToggleState={handleToggle}
              onDismiss={handleDismiss}
              onCreate={handleCreate}
            />
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
  sub,
  tone,
  icon,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "emerald" | "rose";
  icon: React.ReactNode;
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
          <p className="text-[10px] uppercase tracking-wide text-slate-500">
            {label}
          </p>
          <p className="font-semibold tabular-nums text-slate-900">{value}</p>
          {sub && (
            <p className="text-[10px] text-slate-500">{sub}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function LoadingState() {
  return (
    <Card>
      <CardContent className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin text-blue-500" />
        加载日记数据…
      </CardContent>
    </Card>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <Card className="border-rose-200 bg-rose-50/60">
      <CardContent className="flex flex-col items-center justify-center gap-3 py-10 text-sm text-rose-700">
        <AlertTriangle className="size-5" />
        <span>{message}</span>
        <Button variant="outline" size="sm" onClick={onRetry}>
          重试
        </Button>
      </CardContent>
    </Card>
  );
}

export { cn };
