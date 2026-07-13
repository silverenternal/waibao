"use client";

/**
 * 求职者 — 我的工单 (v9.1 Jobseeker 辅助模块)
 *
 * 特性:
 *   - 状态 / 类别 / 优先级筛选
 *   - 工单分组展示 (按状态)
 *   - SLA 实时倒计时
 *   - 新建工单内联表单
 *   - 中文精致排版 · 响应式 · 可访问
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Filter,
  Loader2,
  Plus,
  Search,
  Send,
  Sparkles,
  Ticket as TicketIcon,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { TicketCard } from "@/components/tickets/TicketCard";

import {
  ticketsApi,
  type Ticket,
  type TicketCreatePayload,
  type TicketPriority,
  type TicketCategory,
  type TicketStatus,
  TICKET_PRIORITIES,
  TICKET_CATEGORIES,
  TICKET_STATUSES,
  PRIORITY_LABEL,
  PRIORITY_COLOR,
  CATEGORY_LABEL,
  STATUS_LABEL,
  STATUS_COLOR,
} from "@/lib/api-tickets";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; tickets: Ticket[] }
  | { kind: "error"; message: string };

type StatusFilter = "all" | TicketStatus;
type SortMode = "updated" | "sla" | "priority";

const SORT_LABEL: Record<SortMode, string> = {
  updated: "最近更新",
  sla: "SLA 紧急度",
  priority: "优先级",
};

const PRIORITY_RANK: Record<TicketPriority, number> = {
  urgent: 0,
  high: 1,
  normal: 2,
  low: 3,
};

export default function MyTicketsPage() {
  const router = useRouter();
  const [state, setState] = React.useState<LoadState>({ kind: "loading" });
  const [creating, setCreating] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);

  // 筛选 / 搜索状态
  const [statusFilter, setStatusFilter] = React.useState<StatusFilter>("all");
  const [categoryFilter, setCategoryFilter] = React.useState<"all" | TicketCategory>(
    "all",
  );
  const [keyword, setKeyword] = React.useState("");
  const [sortMode, setSortMode] = React.useState<SortMode>("updated");

  const [form, setForm] = React.useState<TicketCreatePayload>({
    title: "",
    description: "",
    priority: "normal",
    category: "hr",
  });

  // ---- 加载 ----------------------------------------------------------------

  const load = React.useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const resp = await ticketsApi.myTickets({ limit: 100 });
      setState({ kind: "ready", tickets: resp.items });
    } catch (e: unknown) {
      setState({
        kind: "error",
        message: e instanceof Error ? e.message : "加载失败",
      });
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  // ---- 创建 ---------------------------------------------------------------

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title.trim()) {
      setCreateError("请填写工单标题");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      await ticketsApi.create({ ...form, title: form.title.trim() });
      setForm({ title: "", description: "", priority: "normal", category: "hr" });
      await load();
    } catch (e: unknown) {
      setCreateError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setCreating(false);
    }
  }

  // ---- 派生: 筛选 + 排序 + 分组 --------------------------------------------

  const filtered = React.useMemo(() => {
    if (state.kind !== "ready") return [];
    const kw = keyword.trim().toLowerCase();
    return state.tickets.filter((t) => {
      if (statusFilter !== "all" && t.status !== statusFilter) return false;
      if (categoryFilter !== "all" && t.category !== categoryFilter) return false;
      if (kw) {
        const blob = `${t.title} ${t.description ?? ""}`.toLowerCase();
        if (!blob.includes(kw)) return false;
      }
      return true;
    });
  }, [state, statusFilter, categoryFilter, keyword]);

  const sorted = React.useMemo(() => {
    const list = [...filtered];
    if (sortMode === "updated") {
      list.sort(
        (a, b) =>
          new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
      );
    } else if (sortMode === "priority") {
      list.sort((a, b) => PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority]);
    } else if (sortMode === "sla") {
      list.sort((a, b) => {
        const at = a.sla_due_at ? new Date(a.sla_due_at).getTime() : Infinity;
        const bt = b.sla_due_at ? new Date(b.sla_due_at).getTime() : Infinity;
        return at - bt;
      });
    }
    return list;
  }, [filtered, sortMode]);

  const grouped = React.useMemo(() => {
    const buckets: Record<string, Ticket[]> = {};
    for (const t of sorted) {
      buckets[t.status] = buckets[t.status] ?? [];
      buckets[t.status].push(t);
    }
    return buckets;
  }, [sorted]);

  // 状态计数
  const statusCounts = React.useMemo(() => {
    if (state.kind !== "ready") return null;
    const counts: Record<TicketStatus, number> = {
      open: 0,
      in_progress: 0,
      awaiting_user: 0,
      resolved: 0,
      closed: 0,
    };
    for (const t of state.tickets) counts[t.status] += 1;
    return counts;
  }, [state]);

  const totalCount = state.kind === "ready" ? state.tickets.length : 0;

  // ---- 渲染 ---------------------------------------------------------------

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-50">
      {/* 顶部 */}
      <header className="sticky top-0 z-20 border-b border-slate-200/70 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
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
              <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
                <span
                  aria-hidden
                  className="inline-flex size-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-sm"
                >
                  <TicketIcon className="size-4" />
                </span>
                我的工单
              </h1>
              <p className="text-xs text-slate-500">
                提问 HR · 查看处理进度 · SLA 倒计时实时刷新
              </p>
            </div>
          </div>
          {state.kind === "ready" && (
            <Badge variant="secondary" className="px-2 py-1 text-xs">
              共 {totalCount} 条
            </Badge>
          )}
        </div>
      </header>

      <main className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-6">
        {/* ============== 新建工单 ============== */}
        <Card>
          <CardContent className="p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                <Plus className="size-4 text-blue-500" />
                提交新工单
              </h2>
              <Badge variant="outline" className="border-blue-200 bg-blue-50 text-blue-700">
                <Sparkles className="size-3" />
                智能体也会自动建单
              </Badge>
            </div>

            <form onSubmit={handleCreate} className="space-y-3">
              <Input
                value={form.title}
                onChange={(e) =>
                  setForm((p) => ({ ...p, title: e.target.value }))
                }
                placeholder="一句话描述你的问题,例如:请假流程不清楚 / 薪资条异常"
                maxLength={200}
                required
                aria-label="工单标题"
              />
              <Textarea
                value={form.description}
                onChange={(e) =>
                  setForm((p) => ({ ...p, description: e.target.value }))
                }
                placeholder="详细背景 (选填):时间、相关政策编号、期望的解决方案..."
                rows={3}
                maxLength={10000}
                className="resize-y"
                aria-label="详细描述"
              />

              <div className="flex flex-wrap items-center gap-3">
                <FilterSelect
                  label="类别"
                  value={form.category}
                  onChange={(v) =>
                    setForm((p) => ({ ...p, category: v as TicketCategory }))
                  }
                  options={TICKET_CATEGORIES.map((c) => ({
                    value: c,
                    label: CATEGORY_LABEL[c] ?? c,
                  }))}
                />
                <FilterSelect
                  label="优先级"
                  value={form.priority}
                  onChange={(v) =>
                    setForm((p) => ({ ...p, priority: v as TicketPriority }))
                  }
                  options={TICKET_PRIORITIES.map((p) => ({
                    value: p,
                    label: PRIORITY_LABEL[p],
                  }))}
                />
                <div className="ml-auto flex items-center gap-3">
                  {createError && (
                    <span role="alert" className="text-xs text-rose-600">
                      {createError}
                    </span>
                  )}
                  <Button
                    type="submit"
                    disabled={creating || !form.title.trim()}
                    className="gap-1.5"
                  >
                    {creating ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <Send className="size-3.5" />
                    )}
                    提交工单
                  </Button>
                </div>
              </div>
            </form>
          </CardContent>
        </Card>

        {/* ============== 筛选区 ============== */}
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="relative min-w-0 flex-1 sm:max-w-xs">
                <Search
                  aria-hidden
                  className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400"
                />
                <Input
                  className="pl-8"
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  placeholder="搜索标题 / 描述"
                  aria-label="搜索"
                />
                {keyword && (
                  <button
                    type="button"
                    onClick={() => setKeyword("")}
                    aria-label="清除搜索"
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                  >
                    <X className="size-3.5" />
                  </button>
                )}
              </div>

              <FilterSelect
                label="类别"
                value={categoryFilter}
                onChange={(v) =>
                  setCategoryFilter(v as "all" | TicketCategory)
                }
                options={[
                  { value: "all", label: "全部" },
                  ...TICKET_CATEGORIES.map((c) => ({
                    value: c,
                    label: CATEGORY_LABEL[c] ?? c,
                  })),
                ]}
              />

              <FilterSelect
                label="排序"
                value={sortMode}
                onChange={(v) => setSortMode(v as SortMode)}
                options={[
                  { value: "updated", label: SORT_LABEL.updated },
                  { value: "sla", label: SORT_LABEL.sla },
                  { value: "priority", label: SORT_LABEL.priority },
                ]}
              />

              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setStatusFilter("all");
                  setCategoryFilter("all");
                  setKeyword("");
                  setSortMode("updated");
                }}
                className="ml-auto text-slate-500"
              >
                重置筛选
              </Button>
            </div>

            {/* 状态 pills */}
            <div className="flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                onClick={() => setStatusFilter("all")}
                aria-pressed={statusFilter === "all"}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                  statusFilter === "all"
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-200 bg-white text-slate-600 hover:border-slate-300",
                )}
              >
                全部 {statusCounts ? `· ${totalCount}` : ""}
              </button>
              {TICKET_STATUSES.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStatusFilter(s)}
                  aria-pressed={statusFilter === s}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                    statusFilter === s
                      ? "border-slate-900 bg-slate-900 text-white"
                      : "border-slate-200 bg-white text-slate-600 hover:border-slate-300",
                  )}
                >
                  <Badge
                    variant="outline"
                    className={cn(
                      "border px-1.5 py-0 text-[10px]",
                      STATUS_COLOR[s],
                      statusFilter === s && "bg-white/20 text-white",
                    )}
                  >
                    {STATUS_LABEL[s]}
                  </Badge>
                  {statusCounts && (
                    <span className="text-[10px] tabular-nums opacity-70">
                      {statusCounts[s]}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* ============== 列表区 ============== */}
        <section aria-label="工单列表">
          {state.kind === "loading" && (
            <div className="space-y-3" role="status" aria-label="加载工单中">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-28 w-full rounded-xl" />
              ))}
              <span className="sr-only">正在加载工单…</span>
            </div>
          )}

          {state.kind === "error" && (
            <Card className="border-rose-200 bg-rose-50">
              <CardContent className="flex items-center gap-2 py-6 text-sm text-rose-700">
                <AlertCircle className="size-4" />
                {state.message}
                <Button
                  variant="outline"
                  size="sm"
                  className="ml-auto"
                  onClick={() => void load()}
                >
                  重试
                </Button>
              </CardContent>
            </Card>
          )}

          {state.kind === "ready" && sorted.length === 0 && (
            <Card>
              <CardContent className="flex flex-col items-center gap-2 py-12 text-center text-sm text-slate-500">
                <CheckCircle2 className="size-6 text-emerald-500" />
                {totalCount === 0 ? (
                  <>
                    <p>还没有工单,有问题随时来找 HR。</p>
                    <p className="text-xs text-slate-400">
                      智能体也会在你对话时自动建单。
                    </p>
                  </>
                ) : (
                  <p>当前筛选下没有匹配的工单。</p>
                )}
              </CardContent>
            </Card>
          )}

          {state.kind === "ready" && sorted.length > 0 && (
            <div className="space-y-6">
              {TICKET_STATUSES.map((status) => {
                const list = grouped[status] ?? [];
                if (list.length === 0) return null;
                return (
                  <div key={status}>
                    <div className="mb-2 flex items-center gap-2">
                      <Badge
                        variant="outline"
                        className={cn("border", STATUS_COLOR[status])}
                      >
                        {STATUS_LABEL[status]}
                      </Badge>
                      <span className="text-xs text-slate-500 tabular-nums">
                        {list.length}
                      </span>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {list.map((t) => (
                        <button
                          key={t.id}
                          type="button"
                          onClick={() => router.push(`/my-tickets/${t.id}`)}
                          className="block w-full cursor-pointer rounded-lg text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                          aria-label={`查看工单 ${t.title}`}
                        >
                          <TicketCard ticket={t} compact showAssignee={false} />
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* 优先级图例 */}
        {state.kind === "ready" && state.tickets.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
            <Filter className="size-3" />
            <span>优先级:</span>
            {TICKET_PRIORITIES.map((p) => (
              <Badge
                key={p}
                variant="outline"
                className={cn("border", PRIORITY_COLOR[p])}
              >
                {PRIORITY_LABEL[p]}
              </Badge>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 紧凑 select 组件
// ---------------------------------------------------------------------------

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string | undefined;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="inline-flex items-center gap-1.5 text-xs text-slate-600">
      <span className="text-slate-500">{label}:</span>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-800 transition-colors focus:border-blue-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-200"
        aria-label={label}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}