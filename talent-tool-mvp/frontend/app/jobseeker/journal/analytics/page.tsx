"use client";

/**
 * Journal analytics page (T3606 / v9.1).
 *
 * Layout:
 *   ┌─ Sticky toolbar (range + refresh + 语音/编辑) ──┐
 *   ├─ 4-up Tremor-style KPI grid (count / 极佳 / 关注 / 警告) ┤
 *   ├─ Tremor panel · 评级趋势 Recharts ComposedChart ┤
 *   ├─ 2-col · 智能体建议历史 + 警告时间线           ┤
 *   └─ 行动项追踪(三态 + 自由创建)                  ┤
 *
 * 接入:lib/api-journal (timeline / action-items),无需额外请求;
 * 派生数据全部在 useMemo 里,30/60/90 天切换即时。
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  Calendar,
  ChevronDown,
  Lightbulb,
  Loader2,
  Mic,
  PenLine,
  RefreshCcw,
  Sparkles,
  TrendingUp,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

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
import {
  TremorKpiGrid,
  TremorKpiCard,
  TremorPanel,
  TremorShell,
} from "@/components/charts/tremor-shell";

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

const RANGES = [
  { label: "30 天", days: 30 },
  { label: "60 天", days: 60 },
  { label: "90 天", days: 90 },
] as const;

const POLL_MS = 90_000;

// ---------------------------------------------------------------------------
// 页面
// ---------------------------------------------------------------------------

export default function JournalAnalyticsPage() {
  const router = useRouter();
  const [days, setDays] = React.useState<60 | 30 | 90>(60);
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
    const lastRating = [...entries]
      .reverse()
      .find((e) => !!e.ai_rating)?.ai_rating;
    return { total, ...ratings, warningCount, lastRating };
  }, [entries]);

  // 派生 sparkline(过去 N 周,平均评级 0-3)
  const ratingSpark = React.useMemo(
    () =>
      buckets
        .map((b) => (b.avgNumeric == null ? 0 : b.avgNumeric))
        .filter((v) => v > 0),
    [buckets],
  );

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

  // ----------------------------------------------------------------- render
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100/50">
      <TremorShell
        title="日记 AI 分析"
        subtitle="评级趋势 · 智能体建议 · 行动项追踪 · 告警时间线"
        badge={`${stats.total} 篇 / ${days} 天`}
        toolbar={
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.push("/jobseeker/journal")}
              className="gap-1"
            >
              <ArrowLeft className="size-3.5" /> 返回日记
            </Button>
            <div
              className="flex items-center rounded-md border bg-white p-0.5"
              role="radiogroup"
              aria-label="时间范围"
            >
              {RANGES.map((r) => (
                <button
                  key={r.days}
                  type="button"
                  role="radio"
                  aria-checked={r.days === days}
                  onClick={() => setDays(r.days)}
                  className={cn(
                    "h-7 rounded px-2.5 text-xs font-medium transition",
                    r.days === days
                      ? "bg-slate-900 text-white"
                      : "text-slate-600 hover:bg-slate-100",
                  )}
                >
                  {r.label}
                </button>
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
              variant="outline"
              size="sm"
              onClick={() => router.push("/jobseeker/journal")}
              className="gap-1"
            >
              <PenLine className="size-3.5" /> 写新日记
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/jobseeker/journal/voice")}
              className="gap-1"
            >
              <Mic className="size-3.5" /> 语音
            </Button>
          </>
        }
      >
        {loading && <LoadingState />}
        {error && !loading && (
          <ErrorState message={error} onRetry={() => load(true)} />
        )}

        {!loading && !error && (
          <>
            {/* KPI 网格 */}
            <TremorKpiGrid>
              <TremorKpiCard
                title="日记总数"
                value={stats.total}
                unit="篇"
                helper={`最近 ${days} 天`}
                spark={ratingSpark}
              />
              <TremorKpiCard
                title="极佳 / 稳定"
                value={stats.excellent + stats.good}
                helper={`极佳 ${stats.excellent} · 稳定 ${stats.good}`}
              />
              <TremorKpiCard
                title="需关注"
                value={stats.warning}
                helper={
                  stats.warning > 0
                    ? "留意近期负面信号"
                    : "近期没有需要关注的"
                }
              />
              <TremorKpiCard
                title="警告累计"
                value={stats.warningCount}
                unit="条"
                helper={
                  stats.lastRating
                    ? `最近评级: ${stats.lastRating}`
                    : "暂无评级"
                }
              />
            </TremorKpiGrid>

            {/* 趋势图 */}
            <TremorPanel
              title="AI 评级趋势"
              description={`按周聚合,堆叠面积 + 平均评级折线 · 最近 ${buckets.length} 周`}
              actions={
                <Badge variant="outline" className="text-[10px]">
                  <Calendar className="mr-1 size-3" />
                  {days} 天
                </Badge>
              }
            >
              {buckets.length === 0 ? (
                <EmptyChart
                  icon={TrendingUp}
                  title="暂无可视化的日记记录"
                  description="写几篇日记,智能体会自动生成评级并在此呈现趋势。"
                  actionLabel="去写日记"
                  onAction={() => router.push("/jobseeker/journal")}
                />
              ) : (
                <JournalRatingTrend data={buckets} height={320} />
              )}
            </TremorPanel>

            {/* 建议历史 + 警告时间线 */}
            <div className="grid gap-4 lg:grid-cols-2">
              <TremorPanel
                title="智能体建议历史"
                description="按评级过滤;展开后查看原文与警示"
                actions={
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
                }
                className="h-full"
              >
                {entries.length === 0 ? (
                  <EmptyChart
                    icon={Lightbulb}
                    title="暂无建议"
                    description="提交第一篇日记后,智能体会给出今日的改进建议。"
                  />
                ) : (
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
                    title=""
                    description=""
                  />
                )}
              </TremorPanel>

              <TremorPanel
                title="告警时间线"
                description="按日记日期纵向展示,识别反复出现的警示"
                actions={
                  <Badge variant="outline" className="text-[10px]">
                    {warningRows.length} 条
                  </Badge>
                }
                className="h-full"
              >
                {warningRows.length === 0 ? (
                  <EmptyChart
                    icon={AlertTriangle}
                    title="近期日记无明显警告"
                    description="继续保持 — 出现新警示时会自动出现在这里。"
                  />
                ) : (
                  <JournalWarningTimeline
                    rows={warningRows}
                    title=""
                  />
                )}
              </TremorPanel>
            </div>

            {/* 行动项追踪 */}
            <TremorPanel
              title="行动项追踪"
              description="三态:待办 / 进行中 / 已完成 · 也可手动创建"
            >
              <ActionItemTracker
                items={items}
                loading={false}
                onToggleState={handleToggle}
                onDismiss={handleDismiss}
                onCreate={handleCreate}
              />
            </TremorPanel>
          </>
        )}
      </TremorShell>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 内嵌实现:行动项追踪(三态 + 创建)
// ---------------------------------------------------------------------------

function ActionItemTracker({
  items,
  loading,
  onToggleState,
  onDismiss,
  onCreate,
}: {
  items: ActionItem[];
  loading: boolean;
  onToggleState: (item: ActionItem, next: ActionItemState) => void;
  onDismiss: (item: ActionItem) => void;
  onCreate: (title: string) => Promise<void> | void;
}) {
  const [draft, setDraft] = React.useState("");
  const [creating, setCreating] = React.useState(false);

  async function handleAdd() {
    const t = draft.trim();
    if (!t) return;
    setCreating(true);
    try {
      await onCreate(t);
      setDraft("");
    } finally {
      setCreating(false);
    }
  }

  const visible = items.filter((i) => i.state !== "dismissed");
  const counts = React.useMemo(() => {
    const c = { open: 0, in_progress: 0, done: 0 };
    for (const i of visible) {
      if (i.state in c) c[i.state as keyof typeof c] += 1;
    }
    return c;
  }, [visible]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
        <Badge variant="secondary" className="text-[10px]">
          {counts.open} 待办
        </Badge>
        <Badge
          variant="secondary"
          className="bg-blue-100 text-blue-700 text-[10px]"
        >
          {counts.in_progress} 进行中
        </Badge>
        <Badge
          variant="secondary"
          className="bg-emerald-100 text-emerald-700 text-[10px]"
        >
          {counts.done} 已完成
        </Badge>
      </div>

      <div className="flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void handleAdd();
            }
          }}
          placeholder="新建一个行动项,例如:周三前完成 offer 谈判脚本"
          aria-label="新建行动项"
          className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
        />
        <Button
          size="sm"
          onClick={handleAdd}
          disabled={!draft.trim() || creating}
        >
          {creating ? "创建中…" : "添加"}
        </Button>
      </div>

      {loading ? (
        <p className="rounded-md border border-dashed border-slate-200 bg-slate-50 p-4 text-center text-xs text-slate-500">
          加载中…
        </p>
      ) : visible.length === 0 ? (
        <p className="rounded-md border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-xs text-slate-500">
          还没有行动项 — 提交日记后智能体会自动生成,也可以手动新建。
        </p>
      ) : (
        <ul className="space-y-1.5">
          {visible.map((item) => (
            <ActionItemRow
              key={item.id}
              item={item}
              onToggleState={(next) => onToggleState(item, next)}
              onDismiss={() => onDismiss(item)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function ActionItemRow({
  item,
  onToggleState,
  onDismiss,
}: {
  item: ActionItem;
  onToggleState: (next: ActionItemState) => void;
  onDismiss: () => void;
}) {
  const variants: Array<{
    key: ActionItemState;
    label: string;
    className: string;
  }> = [
    { key: "open", label: "待办", className: "bg-slate-100 text-slate-700" },
    {
      key: "in_progress",
      label: "进行中",
      className: "bg-blue-100 text-blue-700",
    },
    {
      key: "done",
      label: "已完成",
      className: "bg-emerald-100 text-emerald-700",
    },
  ];
  const current = variants.find((v) => v.key === item.state) ?? variants[0];
  const cycle = () => {
    const idx = variants.findIndex((v) => v.key === item.state);
    onToggleState(variants[(idx + 1) % variants.length].key);
  };

  return (
    <li className="group flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm transition hover:border-slate-300 hover:shadow-sm">
      <button
        type="button"
        onClick={cycle}
        aria-label={`切换状态:当前 ${current.label},点击循环`}
        className={cn(
          "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium transition hover:opacity-80",
          current.className,
        )}
        title={`点击循环状态 (当前: ${current.label})`}
      >
        {current.label}
        <ChevronDown className="size-3" />
      </button>
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "truncate",
            item.state === "done" && "text-slate-400 line-through",
          )}
        >
          {item.title}
        </p>
        {item.description && (
          <p className="line-clamp-1 text-[11px] text-slate-500">
            {item.description}
          </p>
        )}
      </div>
      {item.origin === "agent" && (
        <Badge variant="outline" className="text-[10px]">
          <Sparkles className="mr-1 size-3" /> 智能体
        </Badge>
      )}
      <Button
        size="icon-xs"
        variant="ghost"
        onClick={onDismiss}
        aria-label="忽略该行动项"
        title="忽略"
      >
        ✕
      </Button>
    </li>
  );
}

// ---------------------------------------------------------------------------
// 子块
// ---------------------------------------------------------------------------

function LoadingState() {
  return (
    <Card>
      <CardContent className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
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

function EmptyChart({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div
      role="status"
      className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-slate-200 bg-slate-50/40 px-3 py-8 text-center"
    >
      <span className="grid size-10 place-items-center rounded-full bg-white text-slate-400 shadow-sm ring-1 ring-slate-200">
        <Icon className="size-4" />
      </span>
      <p className="text-sm font-medium text-slate-700">{title}</p>
      <p className="max-w-sm text-xs text-slate-500">{description}</p>
      {actionLabel && onAction && (
        <Button size="sm" variant="outline" onClick={onAction} className="mt-1">
          {actionLabel}
        </Button>
      )}
    </div>
  );
}

export { cn };
