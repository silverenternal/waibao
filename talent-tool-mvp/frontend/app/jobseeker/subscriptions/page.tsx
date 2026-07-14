"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * v9.1 — 求职者订阅规则 CRUD.
 *
 * 功能:
 *  - 列表展示 (卡片 / 表格切换)
 *  - 搜索 / 筛选 (按状态:全部 / 启用 / 暂停)
 *  - 新增 / 编辑 / 删除 / 启停
 *  - 实时匹配预览 (走 /subscriptions/:id/matches)
 *  - 一键复制规则
 *
 * 设计:
 *  - 中文精致:渐变 / 圆角 / 状态色
 *  - 响应式:移动单列 / lg 双列
 *  - 可访问:dialog/role/aria-label/focus 环
 *  - 客户端 state,操作直接走 apiClient
 */

import * as React from "react";
import {
  Bell,
  BellOff,
  CheckCheck,
  Copy,
  Edit3,
  Filter,
  LayoutGrid,
  List as ListIcon,
  Loader2,
  Pause,
  Play,
  Plus,
  Search,
  Sparkles,
  Trash2,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import type { Subscription, JobMatch } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { SubscriptionForm } from "@/components/SubscriptionForm";
import { SubscriptionMatchList } from "@/components/SubscriptionMatch";

type ViewMode = "grid" | "list";
type StatusFilter = "all" | "active" | "paused";

interface ToastState {
  kind: "success" | "error" | "info";
  message: string;
  id: number;
}

export default function SubscriptionsPage() {
  const [subs, setSubs] = React.useState<Subscription[]>([]);
  const [matches, setMatches] = React.useState<Record<string, JobMatch[]>>({});
  const [loading, setLoading] = React.useState(true);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [editTarget, setEditTarget] = React.useState<Subscription | null>(null);
  const [deleteTarget, setDeleteTarget] = React.useState<Subscription | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const [search, setSearch] = React.useState("");
  const [status, setStatus] = React.useState<StatusFilter>("all");
  const [view, setView] = React.useState<ViewMode>("grid");
  const [toast, setToast] = React.useState<ToastState | null>(null);

  const showToast = React.useCallback(
    (kind: ToastState["kind"], message: string) => {
      const id = Date.now();
      setToast({ kind, message, id });
      window.setTimeout(() => {
        setToast((t) => (t?.id === id ? null : t));
      }, 2800);
    },
    [],
  );

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const { subscriptions } = await apiClient.subscriptions.list();
      setSubs(subscriptions);
      const entries = await Promise.all(
        subscriptions.map(async (s) => {
          try {
            const m = await apiClient.subscriptions.matches(s.id, 4);
            return [s.id, m.matches] as const;
          } catch {
            return [s.id, []] as const;
          }
        }),
      );
      setMatches(Object.fromEntries(entries));
    } catch (err) {
      console.error("[subscriptions] load failed", err);
      showToast("error", "加载订阅失败,请稍后重试");
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  React.useEffect(() => {
    void load();
  }, [load]);

  // 派生
  const filtered = React.useMemo(() => {
    let arr = subs;
    if (status === "active") arr = arr.filter((s) => s.enabled);
    else if (status === "paused") arr = arr.filter((s) => !s.enabled);
    if (search.trim()) {
      const q = search.toLowerCase();
      arr = arr.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.criteria.role?.toLowerCase().includes(q) ||
          s.criteria.city?.toLowerCase().includes(q) ||
          s.criteria.skills?.some((sk) => sk.toLowerCase().includes(q)),
      );
    }
    return arr;
  }, [subs, status, search]);

  const activeCount = subs.filter((s) => s.enabled).length;
  const pausedCount = subs.length - activeCount;
  const totalMatches = Object.values(matches).reduce(
    (acc, arr) => acc + arr.length,
    0,
  );

  // ---- 操作 ----
  const onCreate = async (body: {
    name: string;
    criteria: Subscription["criteria"];
    channels: string[];
  }) => {
    setSubmitting(true);
    try {
      await apiClient.subscriptions.create(body);
      setCreateOpen(false);
      showToast("success", `已创建「${body.name}」`);
      await load();
    } catch {
      showToast("error", "创建失败,请稍后重试");
    } finally {
      setSubmitting(false);
    }
  };

  const onEditSave = async (body: {
    name: string;
    criteria: Subscription["criteria"];
    channels: string[];
  }) => {
    if (!editTarget) return;
    setSubmitting(true);
    try {
      await apiClient.subscriptions.update(editTarget.id, body);
      setEditTarget(null);
      showToast("success", `已更新「${body.name}」`);
      await load();
    } catch {
      showToast("error", "保存失败,请稍后重试");
    } finally {
      setSubmitting(false);
    }
  };

  const onToggle = async (s: Subscription) => {
    try {
      await apiClient.subscriptions.update(s.id, { enabled: !s.enabled });
      showToast(
        "info",
        s.enabled ? `已暂停「${s.name}」` : `已启用「${s.name}」`,
      );
      await load();
    } catch {
      showToast("error", "操作失败");
    }
  };

  const onDuplicate = async (s: Subscription) => {
    setSubmitting(true);
    try {
      await apiClient.subscriptions.create({
        name: `${s.name} - 副本`,
        criteria: { ...s.criteria },
        channels: [...s.channels],
      });
      showToast("success", `已复制为新订阅`);
      await load();
    } catch {
      showToast("error", "复制失败");
    } finally {
      setSubmitting(false);
    }
  };

  const onDelete = async () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    setSubmitting(true);
    try {
      await apiClient.subscriptions.delete(target.id);
      setDeleteTarget(null);
      showToast("success", `已删除「${target.name}」`);
      await load();
    } catch {
      showToast("error", "删除失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ErrorBoundary>(<div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-10">
        {/* 顶部 */}
        <header className="mb-6 sm:mb-8">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full bg-indigo-100 px-3 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300">
                <Bell className="size-3.5" aria-hidden="true" />
                订阅规则
              </div>
              <h1 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">
                想看什么工作,让 AI 主动推给你
              </h1>
              <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                创建多个订阅,按角色、地点、薪资、远程偏好匹配;命中时通过你设置的通道推送。
              </p>
            </div>
            <Button
              onClick={() => setCreateOpen(true)}
              className="bg-gradient-to-r from-indigo-600 to-violet-600 text-white hover:from-indigo-700 hover:to-violet-700"
            >
              <Plus className="mr-1.5 size-4" aria-hidden="true" />
              新建订阅
            </Button>
          </div>
        </header>
        {/* KPI */}
        <section
          aria-label="订阅统计"
          className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4"
        >
          <Kpi
            label="订阅总数"
            value={subs.length}
            icon={Bell}
            tone="indigo"
          />
          <Kpi label="启用中" value={activeCount} icon={CheckCheck} tone="emerald" />
          <Kpi label="已暂停" value={pausedCount} icon={BellOff} tone="slate" />
          <Kpi
            label="近 7 天命中"
            value={totalMatches}
            icon={Sparkles}
            tone="amber"
          />
        </section>
        {/* 工具栏 */}
        <Card className="mb-4">
          <CardContent className="space-y-3 p-3 sm:p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="relative flex-1 sm:max-w-xs">
                <Search
                  className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                  aria-hidden="true"
                />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="搜索名称、角色、城市、技能…"
                  className="pl-9"
                  aria-label="搜索订阅"
                />
              </div>
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <Filter
                  className="size-3.5 text-muted-foreground"
                  aria-hidden="true"
                />
                <FilterChip
                  active={status === "all"}
                  onClick={() => setStatus("all")}
                  label="全部"
                  count={subs.length}
                />
                <FilterChip
                  active={status === "active"}
                  onClick={() => setStatus("active")}
                  label="启用中"
                  count={activeCount}
                  tone="emerald"
                />
                <FilterChip
                  active={status === "paused"}
                  onClick={() => setStatus("paused")}
                  label="已暂停"
                  count={pausedCount}
                  tone="slate"
                />
                <div className="ml-auto flex items-center gap-1 rounded-md border bg-background p-0.5">
                  <button
                    type="button"
                    onClick={() => setView("grid")}
                    className={cn(
                      "inline-flex size-7 items-center justify-center rounded-sm transition-colors",
                      view === "grid"
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-muted",
                    )}
                    aria-label="网格视图"
                    aria-pressed={view === "grid"}
                  >
                    <LayoutGrid className="size-3.5" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setView("list")}
                    className={cn(
                      "inline-flex size-7 items-center justify-center rounded-sm transition-colors",
                      view === "list"
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-muted",
                    )}
                    aria-label="列表视图"
                    aria-pressed={view === "list"}
                  >
                    <ListIcon className="size-3.5" aria-hidden="true" />
                  </button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
        {/* 列表 */}
        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-56 w-full" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          subs.length === 0 ? (
            <EmptyState
              title="还没有订阅"
              description="创建一个订阅,匹配引擎会按你的偏好主动推送合适的工作。"
              icon={<Bell className="size-6" />}
              action={
                <Button onClick={() => setCreateOpen(true)}>
                  <Plus className="mr-1.5 size-4" aria-hidden="true" />
                  新建第一个订阅
                </Button>
              }
            />
          ) : (
            <EmptyState
              title="没有匹配的订阅"
              description="试试清除搜索或切换状态筛选。"
              icon={<Filter className="size-6" />}
              action={
                <Button
                  variant="outline"
                  onClick={() => {
                    setSearch("");
                    setStatus("all");
                  }}
                >
                  清除筛选
                </Button>
              }
            />
          )
        ) : view === "grid" ? (
          <div className="grid gap-4 sm:grid-cols-2">
            {filtered.map((s) => (
              <SubscriptionCard
                key={s.id}
                sub={s}
                matches={matches[s.id] ?? []}
                onToggle={() => onToggle(s)}
                onEdit={() => setEditTarget(s)}
                onDelete={() => setDeleteTarget(s)}
                onDuplicate={() => onDuplicate(s)}
              />
            ))}
          </div>
        ) : (
          <SubscriptionList
            items={filtered}
            matches={matches}
            onToggle={onToggle}
            onEdit={(s) => setEditTarget(s)}
            onDelete={(s) => setDeleteTarget(s)}
            onDuplicate={onDuplicate}
          />
        )}
        {/* 创建/编辑 Dialog */}
        <Dialog
          open={createOpen || editTarget !== null}
          onOpenChange={(o) => {
            if (!o) {
              setCreateOpen(false);
              setEditTarget(null);
            }
          }}
        >
          <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
            <DialogHeader>
              <DialogTitle>
                {editTarget ? "编辑订阅" : "新建订阅"}
              </DialogTitle>
              <DialogDescription>
                {editTarget
                  ? "调整规则后,匹配引擎会重新计算。"
                  : "设定后立即开始匹配,命中会通过你勾选的通道推送。"}
              </DialogDescription>
            </DialogHeader>
            {editTarget ? (
              <SubscriptionForm
                key={editTarget.id}
                initial={{
                  name: editTarget.name,
                  criteria: editTarget.criteria,
                  channels: editTarget.channels,
                }}
                onSubmit={onEditSave}
                submitting={submitting}
                onCancel={() => setEditTarget(null)}
              />
            ) : (
              <SubscriptionForm
                key="new"
                onSubmit={onCreate}
                submitting={submitting}
                onCancel={() => setCreateOpen(false)}
              />
            )}
          </DialogContent>
        </Dialog>
        {/* 删除确认 Dialog */}
        <Dialog
          open={deleteTarget !== null}
          onOpenChange={(o) => !o && setDeleteTarget(null)}
        >
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2 text-rose-700 dark:text-rose-300">
                <Trash2 className="size-4" aria-hidden="true" />
                删除订阅?
              </DialogTitle>
              <DialogDescription>
                将永久删除订阅「
                <span className="font-semibold text-foreground">
                  {deleteTarget?.name}
                </span>
                」及其历史匹配;此操作不可撤销。
              </DialogDescription>
            </DialogHeader>
            <div className="flex justify-end gap-2 pt-2">
              <DialogClose
                render={
                  <Button variant="ghost" size="sm">
                    取消
                  </Button>
                }
              />
              <Button
                size="sm"
                className="bg-rose-600 text-white hover:bg-rose-700"
                onClick={onDelete}
                disabled={submitting}
              >
                {submitting ? (
                  <span className="flex items-center gap-1">
                    <Loader2 className="size-3 animate-spin" aria-hidden="true" />
                    删除中
                  </span>
                ) : (
                  "确认删除"
                )}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
        {/* Toast */}
        {toast && (
          <div
            role="status"
            aria-live="polite"
            className={cn(
              "fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-full px-4 py-2 text-sm shadow-lg ring-1 backdrop-blur",
              toast.kind === "success" &&
                "bg-emerald-50/95 text-emerald-800 ring-emerald-200/60 dark:bg-emerald-950/80 dark:text-emerald-200 dark:ring-emerald-900",
              toast.kind === "error" &&
                "bg-rose-50/95 text-rose-800 ring-rose-200/60 dark:bg-rose-950/80 dark:text-rose-200 dark:ring-rose-900",
              toast.kind === "info" &&
                "bg-indigo-50/95 text-indigo-800 ring-indigo-200/60 dark:bg-indigo-950/80 dark:text-indigo-200 dark:ring-indigo-900",
            )}
          >
            {toast.message}
          </div>
        )}
      </div>)</ErrorBoundary>
  );
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

function Kpi({
  label,
  value,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number;
  icon: LucideIcon;
  tone: "indigo" | "emerald" | "slate" | "amber";
}) {
  const toneCls: Record<typeof tone, string> = {
    indigo:
      "bg-indigo-50 text-indigo-700 ring-indigo-200/60 dark:bg-indigo-950/40 dark:text-indigo-200 dark:ring-indigo-900",
    emerald:
      "bg-emerald-50 text-emerald-700 ring-emerald-200/60 dark:bg-emerald-950/40 dark:text-emerald-200 dark:ring-emerald-900",
    slate:
      "bg-slate-50 text-slate-700 ring-slate-200/60 dark:bg-slate-900/40 dark:text-slate-200 dark:ring-slate-800",
    amber:
      "bg-amber-50 text-amber-800 ring-amber-200/60 dark:bg-amber-950/40 dark:text-amber-200 dark:ring-amber-900",
  };
  return (
    <div
      className={cn("rounded-xl p-3 ring-1 sm:p-4", toneCls[tone])}
      role="status"
      aria-label={`${label}: ${value}`}
    >
      <div className="flex items-center justify-between text-xs sm:text-sm">
        <span className="font-medium opacity-80">{label}</span>
        <Icon className="size-4 opacity-70" aria-hidden="true" />
      </div>
      <p className="mt-1.5 text-2xl font-bold tabular-nums">{value}</p>
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  label,
  count,
  tone = "indigo",
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  count: number;
  tone?: "indigo" | "emerald" | "slate";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium transition-colors",
        active
          ? tone === "emerald"
            ? "border-emerald-300/60 bg-emerald-100 text-emerald-700"
            : tone === "slate"
              ? "border-slate-300 bg-slate-100 text-slate-700"
              : "border-indigo-300/60 bg-indigo-100 text-indigo-700"
          : "border-border text-muted-foreground hover:bg-muted",
      )}
    >
      {label}
      <span
        className={cn(
          "rounded-full bg-background/70 px-1.5 py-0.5 text-[10px] tabular-nums",
        )}
      >
        {count}
      </span>
    </button>
  );
}

function SubscriptionCard({
  sub,
  matches,
  onToggle,
  onEdit,
  onDelete,
  onDuplicate,
}: {
  sub: Subscription;
  matches: JobMatch[];
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onDuplicate: () => void;
}) {
  return (
    <Card
      className={cn(
        "group relative overflow-hidden transition-all hover:-translate-y-0.5 hover:shadow-md",
        !sub.enabled && "opacity-75",
      )}
    >
      {/* 顶部渐变条 */}
      <div
        className={cn(
          "h-1 w-full",
          sub.enabled
            ? "bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500"
            : "bg-slate-300 dark:bg-slate-700",
        )}
        aria-hidden="true"
      />
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <CardTitle className="truncate text-base">{sub.name}</CardTitle>
              {!sub.enabled && (
                <Badge variant="secondary" className="h-4 px-1.5 text-[9px]">
                  已暂停
                </Badge>
              )}
            </div>
            <CardDescription className="mt-0.5 text-[11px]">
              创建于 {new Date(sub.created_at).toLocaleDateString("zh-CN")} ·
              最近更新 {new Date(sub.updated_at).toLocaleDateString("zh-CN")}
            </CardDescription>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={sub.enabled}
            aria-label={`${sub.enabled ? "暂停" : "启用"} ${sub.name}`}
            onClick={onToggle}
            className={cn(
              "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary",
              sub.enabled ? "bg-primary" : "bg-muted-foreground/30",
            )}
          >
            <span
              className={cn(
                "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
                sub.enabled ? "translate-x-4" : "translate-x-0.5",
              )}
            />
          </button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* 条件摘要 */}
        <div className="flex flex-wrap gap-1.5">
          {sub.criteria.role && (
            <Chip icon={Sparkles} label={sub.criteria.role} />
          )}
          {sub.criteria.city && (
            <Chip icon={Filter} label={sub.criteria.city} />
          )}
          {sub.criteria.salary_min ? (
            <Chip
              icon={Sparkles}
              label={`≥ ${sub.criteria.currency ?? "GBP"} ${sub.criteria.salary_min.toLocaleString()}`}
            />
          ) : null}
          {sub.criteria.seniority && (
            <Chip icon={Sparkles} label={sub.criteria.seniority} />
          )}
          {sub.criteria.remote_policy && (
            <Chip icon={Sparkles} label={sub.criteria.remote_policy} />
          )}
        </div>
        {(sub.criteria.skills?.length ?? 0) > 0 && (
          <div className="flex flex-wrap gap-1">
            {(sub.criteria.skills ?? []).map((sk) => (
              <Badge
                key={sk}
                variant="outline"
                className="h-5 px-1.5 text-[10px]"
              >
                {sk}
              </Badge>
            ))}
          </div>
        )}

        {/* 通道 */}
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <span>通道:</span>
          {sub.channels.length === 0 ? (
            <span className="italic">未选择</span>
          ) : (
            sub.channels.map((c) => (
              <Badge
                key={c}
                variant="secondary"
                className="h-4 px-1.5 text-[9px]"
              >
                {c}
              </Badge>
            ))
          )}
        </div>

        {/* 匹配预览 */}
        <div className="rounded-lg border bg-muted/30 p-2">
          <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            最近匹配
          </p>
          <SubscriptionMatchList
            matches={matches}
            subscriptionName={sub.name}
          />
        </div>

        {/* 操作 */}
        <div className="flex flex-wrap items-center gap-1.5 border-t pt-3">
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-xs"
            onClick={onToggle}
            aria-label={sub.enabled ? "暂停" : "启用"}
          >
            {sub.enabled ? (
              <>
                <Pause className="mr-1 size-3.5" aria-hidden="true" />
                暂停
              </>
            ) : (
              <>
                <Play className="mr-1 size-3.5" aria-hidden="true" />
                启用
              </>
            )}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-xs"
            onClick={onEdit}
          >
            <Edit3 className="mr-1 size-3.5" aria-hidden="true" />
            编辑
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-xs"
            onClick={onDuplicate}
          >
            <Copy className="mr-1 size-3.5" aria-hidden="true" />
            复制
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto h-7 px-2 text-xs text-rose-600 hover:text-rose-700"
            onClick={onDelete}
            aria-label="删除订阅"
          >
            <Trash2 className="mr-1 size-3.5" aria-hidden="true" />
            删除
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function SubscriptionList({
  items,
  matches,
  onToggle,
  onEdit,
  onDelete,
  onDuplicate,
}: {
  items: Subscription[];
  matches: Record<string, JobMatch[]>;
  onToggle: (s: Subscription) => void;
  onEdit: (s: Subscription) => void;
  onDelete: (s: Subscription) => void;
  onDuplicate: (s: Subscription) => void;
}) {
  return (
    <Card>
      <CardContent className="p-0">
        <ul className="divide-y" role="list">
          {items.map((s) => {
            const m = matches[s.id] ?? [];
            return (
              <li
                key={s.id}
                className={cn(
                  "flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:gap-4",
                  !s.enabled && "bg-muted/30",
                )}
              >
                <button
                  type="button"
                  role="switch"
                  aria-checked={s.enabled}
                  aria-label={`${s.enabled ? "暂停" : "启用"} ${s.name}`}
                  onClick={() => onToggle(s)}
                  className={cn(
                    "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                    s.enabled ? "bg-primary" : "bg-muted-foreground/30",
                  )}
                >
                  <span
                    className={cn(
                      "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
                      s.enabled ? "translate-x-4" : "translate-x-0.5",
                    )}
                  />
                </button>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <p className="text-sm font-medium leading-tight">
                      {s.name}
                    </p>
                    {!s.enabled && (
                      <Badge variant="secondary" className="h-4 px-1.5 text-[9px]">
                        已暂停
                      </Badge>
                    )}
                    <Badge variant="outline" className="h-4 px-1.5 text-[9px]">
                      {m.length} 命中
                    </Badge>
                  </div>
                  <p className="mt-0.5 line-clamp-1 text-[11px] text-muted-foreground">
                    {[
                      s.criteria.role,
                      s.criteria.city,
                      s.criteria.seniority,
                      s.criteria.remote_policy,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-xs"
                    onClick={() => onEdit(s)}
                  >
                    <Edit3 className="mr-1 size-3.5" aria-hidden="true" />
                    编辑
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-xs"
                    onClick={() => onDuplicate(s)}
                  >
                    <Copy className="mr-1 size-3.5" aria-hidden="true" />
                    复制
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-xs text-rose-600 hover:text-rose-700"
                    onClick={() => onDelete(s)}
                  >
                    <Trash2 className="mr-1 size-3.5" aria-hidden="true" />
                    删除
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

function Chip({
  icon: Icon,
  label,
}: {
  icon: LucideIcon;
  label: string;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium text-foreground">
      <Icon className="size-3" aria-hidden="true" />
      {label}
    </span>
  );
}
