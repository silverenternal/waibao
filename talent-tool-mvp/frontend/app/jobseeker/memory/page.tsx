"use client";

/**
 * 求职者 — 我的记忆 (v9.1 Jobseeker 辅助模块)
 *
 * Backed by `/api/memory/memories`.  Users can:
 *   - 浏览由 Agent 维护的统一记忆 (Mem0)
 *   - 按 6 大类型 (事实 / 偏好 / 事件 / 任务 / 情景 / 摘要) 过滤
 *   - 内联编辑 / 保存 / 取消
 *   - 单条删除 / 批量遗忘 (GDPR)
 *   - 语义查询
 *
 * 视觉特性: 中文精致排版 · 时间线分类 · 响应式 · 可访问。
 */

import * as React from "react";
import {
  AlertTriangle,
  Brain,
  Calendar,
  Check,
  Edit3,
  Filter,
  Loader2,
  RefreshCcw,
  Search,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

interface Memory {
  id: string;
  user_id: string;
  tenant_id: string;
  content: string;
  summary: string | null;
  source_agent: string;
  type: "fact" | "preference" | "event" | "summary" | "task" | "episodic";
  confidence: number;
  decay_score: number;
  access_count: number;
  last_accessed: string | null;
  metadata: Record<string, unknown>;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

type MemoryType = Memory["type"];

// ---------------------------------------------------------------------------
// 类型元数据 (中文 label + 图标 + 配色)
// ---------------------------------------------------------------------------

const TYPE_META: Record<
  MemoryType,
  { label: string; icon: React.ReactNode; color: string; soft: string; ring: string }
> = {
  fact: {
    label: "事实",
    icon: <Brain className="size-3" />,
    color: "bg-blue-600",
    soft: "bg-blue-50 text-blue-700",
    ring: "ring-blue-200",
  },
  preference: {
    label: "偏好",
    icon: <Sparkles className="size-3" />,
    color: "bg-pink-500",
    soft: "bg-pink-50 text-pink-700",
    ring: "ring-pink-200",
  },
  event: {
    label: "事件",
    icon: <Calendar className="size-3" />,
    color: "bg-emerald-600",
    soft: "bg-emerald-50 text-emerald-700",
    ring: "ring-emerald-200",
  },
  summary: {
    label: "摘要",
    icon: <Brain className="size-3" />,
    color: "bg-violet-600",
    soft: "bg-violet-50 text-violet-700",
    ring: "ring-violet-200",
  },
  task: {
    label: "任务",
    icon: <Edit3 className="size-3" />,
    color: "bg-amber-600",
    soft: "bg-amber-50 text-amber-700",
    ring: "ring-amber-200",
  },
  episodic: {
    label: "情景",
    icon: <Calendar className="size-3" />,
    color: "bg-slate-600",
    soft: "bg-slate-100 text-slate-700",
    ring: "ring-slate-200",
  },
};

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function decayColor(score: number): string {
  if (score >= 0.7) return "text-emerald-600";
  if (score >= 0.4) return "text-amber-600";
  return "text-rose-600";
}

// ---------------------------------------------------------------------------
// 主页面
// ---------------------------------------------------------------------------

export default function MemoryPage() {
  const [memories, setMemories] = React.useState<Memory[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const [queryText, setQueryText] = React.useState("");
  const [typeFilter, setTypeFilter] = React.useState<"all" | MemoryType>("all");
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editingContent, setEditingContent] = React.useState("");
  const [pending, setPending] = React.useState(false);

  const fetchAll = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url = new URL("/api/memory/memories", window.location.origin);
      url.searchParams.set("limit", "100");
      if (typeFilter !== "all") url.searchParams.set("types", typeFilter);
      const res = await fetch(url.toString(), { credentials: "include" });
      if (!res.ok) {
        throw new Error(`获取记忆失败 (HTTP ${res.status})`);
      }
      const data: Memory[] = await res.json();
      setMemories(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [typeFilter]);

  React.useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  // ---- 操作 ----------------------------------------------------------------

  const handleQuery = async () => {
    if (!queryText.trim()) {
      void fetchAll();
      return;
    }
    setPending(true);
    setError(null);
    try {
      const res = await fetch("/api/memory/memories/query", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query_text: queryText,
          top_k: 20,
          types: typeFilter === "all" ? [] : [typeFilter],
        }),
      });
      if (!res.ok) throw new Error(`查询失败 (HTTP ${res.status})`);
      const data: Memory[] = await res.json();
      setMemories(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm("确定删除该条记忆?此操作不可撤销。")) return;
    try {
      const res = await fetch(`/api/memory/memories/${id}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!res.ok) throw new Error(`删除失败 (HTTP ${res.status})`);
      setMemories((arr) => arr.filter((m) => m.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleSaveEdit = async (id: string) => {
    setPending(true);
    try {
      const res = await fetch(`/api/memory/memories/${id}`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: editingContent }),
      });
      if (!res.ok) throw new Error(`保存失败 (HTTP ${res.status})`);
      setMemories((arr) =>
        arr.map((m) =>
          m.id === id
            ? {
                ...m,
                content: editingContent,
                updated_at: new Date().toISOString(),
              }
            : m,
        ),
      );
      setEditingId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  const handleChangeType = async (id: string, type: MemoryType) => {
    // 本地乐观更新 + 后端 PATCH (后端若支持 metadata.type)
    setMemories((arr) =>
      arr.map((m) => (m.id === id ? { ...m, type } : m)),
    );
    try {
      await fetch(`/api/memory/memories/${id}`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metadata: { type } }),
      });
    } catch {
      /* 静默: 分类本地已生效 */
    }
  };

  const handleForgetAll = async () => {
    const scope = typeFilter === "all" ? "全部" : TYPE_META[typeFilter].label;
    if (!window.confirm(`将删除所有${scope}类型的记忆,此操作不可撤销。继续吗?`)) {
      return;
    }
    setPending(true);
    try {
      const res = await fetch("/api/memory/memories/forget", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: typeFilter === "all" ? undefined : typeFilter,
        }),
      });
      if (!res.ok) throw new Error(`批量遗忘失败 (HTTP ${res.status})`);
      const data = (await res.json()) as { deleted?: number };
      window.alert(`已删除 ${data.deleted ?? 0} 条记忆`);
      void fetchAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  // ---- 派生数据: 按类型分组 -----------------------------------------------

  const groupedByType = React.useMemo(() => {
    const buckets: Record<MemoryType, Memory[]> = {
      fact: [],
      preference: [],
      event: [],
      summary: [],
      task: [],
      episodic: [],
    };
    for (const m of memories) {
      buckets[m.type]?.push(m);
    }
    return buckets;
  }, [memories]);

  const typeCounts = React.useMemo(() => {
    const counts: Record<MemoryType, number> = {
      fact: 0,
      preference: 0,
      event: 0,
      summary: 0,
      task: 0,
      episodic: 0,
    };
    for (const m of memories) counts[m.type] += 1;
    return counts;
  }, [memories]);

  const filteredGroups = React.useMemo(() => {
    if (typeFilter === "all") {
      return (Object.keys(groupedByType) as MemoryType[])
        .map((t) => ({ type: t, items: groupedByType[t] }))
        .filter((g) => g.items.length > 0);
    }
    return [{ type: typeFilter, items: groupedByType[typeFilter] }];
  }, [groupedByType, typeFilter]);

  // ---- 渲染 ---------------------------------------------------------------

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-50">
      <main className="mx-auto max-w-5xl space-y-6 px-4 py-6 sm:py-8">
        {/* Hero */}
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
              <span
                aria-hidden
                className="inline-flex size-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-violet-600 text-white shadow-sm"
              >
                <Brain className="size-5" />
              </span>
              我的记忆
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              统一记忆库 (Mem0) · 跨 Agent 上下文共享 · 共 {memories.length} 条
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void fetchAll()}
              disabled={pending}
              aria-label="刷新"
            >
              <RefreshCcw className="size-4" />
              <span className="ml-1.5 hidden sm:inline">刷新</span>
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleForgetAll}
              disabled={pending || memories.length === 0}
            >
              <Trash2 className="size-4" />
              <span className="ml-1.5">批量遗忘</span>
            </Button>
          </div>
        </header>

        {/* 分类计数 (快速切换) */}
        <section aria-label="按类型浏览" className="grid grid-cols-3 gap-2 sm:grid-cols-6">
          <TypePill
            label="全部"
            active={typeFilter === "all"}
            count={memories.length}
            onClick={() => setTypeFilter("all")}
          />
          {(Object.keys(TYPE_META) as MemoryType[]).map((t) => (
            <TypePill
              key={t}
              label={TYPE_META[t].label}
              active={typeFilter === t}
              count={typeCounts[t]}
              onClick={() => setTypeFilter(t)}
              dotClass={TYPE_META[t].color}
            />
          ))}
        </section>

        {/* 查询与过滤 */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">查找记忆</CardTitle>
            <CardDescription>支持语义查询 — 输入关键词即可跨所有记忆搜索</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <div className="relative flex-1">
                <Search
                  aria-hidden
                  className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400"
                />
                <Input
                  className="pl-8"
                  value={queryText}
                  onChange={(e) => setQueryText(e.target.value)}
                  placeholder="例如:薪资期望 / 远程办公偏好 / 已面试公司"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void handleQuery();
                  }}
                  aria-label="语义查询"
                />
              </div>
              <Select
                value={typeFilter}
                onValueChange={(v) => setTypeFilter(v as typeof typeFilter)}
              >
                <SelectTrigger className="w-full sm:w-[180px]" aria-label="按类型过滤">
                  <Filter className="mr-2 size-4 text-slate-500" />
                  <SelectValue placeholder="全部类型" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部类型</SelectItem>
                  {(Object.keys(TYPE_META) as MemoryType[]).map((t) => (
                    <SelectItem key={t} value={t}>
                      {TYPE_META[t].label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button onClick={handleQuery} disabled={pending} className="shrink-0">
                {pending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Search className="size-4" />
                )}
                <span className="ml-1.5">查询</span>
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* 错误提示 */}
        {error && (
          <Card className="border-rose-200 bg-rose-50">
            <CardContent className="flex items-center gap-2 p-3 text-sm text-rose-700">
              <AlertTriangle className="size-4" />
              {error}
            </CardContent>
          </Card>
        )}

        {/* 加载骨架 */}
        {loading ? (
          <div className="space-y-3" role="status" aria-label="加载记忆中">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-28 w-full rounded-xl" />
            ))}
            <span className="sr-only">正在加载记忆…</span>
          </div>
        ) : memories.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-2 py-12 text-center text-sm text-slate-500">
              <Brain className="size-6 text-slate-300" />
              <p>暂无记忆</p>
              <p className="text-xs text-slate-400">
                Agent 在对话中会自动写入你的偏好与事实。
              </p>
            </CardContent>
          </Card>
        ) : (
          /* 按类型分组的时间线 */
          <div className="space-y-8">
            {filteredGroups.map(({ type, items }) => (
              <section key={type} aria-labelledby={`group-${type}`}>
                <div className="mb-3 flex items-center gap-2">
                  <span
                    aria-hidden
                    className={cn("size-2 rounded-full", TYPE_META[type].color)}
                  />
                  <h2
                    id={`group-${type}`}
                    className="text-sm font-semibold text-slate-800"
                  >
                    {TYPE_META[type].label}
                  </h2>
                  <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                    {items.length}
                  </Badge>
                </div>

                <ol className="relative ml-3 border-l-2 border-dashed border-slate-200 pl-6">
                  {items.map((m) => (
                    <li key={m.id} className="mb-4 last:mb-0">
                      <span
                        aria-hidden
                        className={cn(
                          "absolute -left-[9px] mt-3 size-4 rounded-full ring-4 ring-white",
                          TYPE_META[type].color,
                          TYPE_META[type].ring,
                        )}
                      />
                      <MemoryCard
                        memory={m}
                        editing={editingId === m.id}
                        editingContent={editingContent}
                        pending={pending}
                        onStartEdit={() => {
                          setEditingId(m.id);
                          setEditingContent(m.content);
                        }}
                        onCancelEdit={() => setEditingId(null)}
                        onChangeContent={setEditingContent}
                        onSave={() => void handleSaveEdit(m.id)}
                        onDelete={() => void handleDelete(m.id)}
                        onChangeType={(t) => void handleChangeType(m.id, t)}
                      />
                    </li>
                  ))}
                </ol>
              </section>
            ))}
          </div>
        )}

        {/* 帮助说明 */}
        <Card className="border-slate-200/70 bg-slate-50/60">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="size-4 text-amber-500" />
              记忆如何工作
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 text-xs text-slate-600 sm:text-sm">
            <p>
              · 每个 Agent 在每次对话时,会自动把与你相关的记忆注入到上下文,形成跨 Agent 共享。
            </p>
            <p>
              · 记忆会随时间衰减 (decay_score),被反复访问的记忆会被拉回到 1.0。
            </p>
            <p>· 你可以随时编辑、删除或批量遗忘 (GDPR) — 一切都由你掌控。</p>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 子组件
// ---------------------------------------------------------------------------

function TypePill({
  label,
  count,
  active,
  onClick,
  dotClass,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
  dotClass?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors",
        active
          ? "border-slate-900 bg-slate-900 text-white shadow-sm"
          : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50",
      )}
    >
      {dotClass && (
        <span
          aria-hidden
          className={cn("size-1.5 rounded-full", active ? "bg-white" : dotClass)}
        />
      )}
      <span>{label}</span>
      <span
        className={cn(
          "rounded px-1 text-[10px]",
          active ? "bg-white/20 text-white" : "bg-slate-100 text-slate-500",
        )}
      >
        {count}
      </span>
    </button>
  );
}

function MemoryCard({
  memory,
  editing,
  editingContent,
  pending,
  onStartEdit,
  onCancelEdit,
  onChangeContent,
  onSave,
  onDelete,
  onChangeType,
}: {
  memory: Memory;
  editing: boolean;
  editingContent: string;
  pending: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onChangeContent: (v: string) => void;
  onSave: () => void;
  onDelete: () => void;
  onChangeType: (t: MemoryType) => void;
}) {
  const meta = TYPE_META[memory.type];

  return (
    <article
      className={cn(
        "rounded-lg border bg-white p-4 shadow-xs transition",
        "border-slate-200 hover:shadow-sm",
        editing && "border-blue-300 ring-2 ring-blue-100",
      )}
    >
      {/* Header */}
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Badge className={cn("gap-1 border-transparent", meta.soft)}>
          {meta.icon}
          <span>{meta.label}</span>
        </Badge>
        <Badge variant="outline" className="text-[10px]">
          {memory.source_agent}
        </Badge>
        <span
          className={cn(
            "text-[11px] font-medium tabular-nums",
            decayColor(memory.decay_score),
          )}
          title="记忆活跃度 — 频繁访问会回到 1.0"
        >
          活跃度 {memory.decay_score.toFixed(2)}
        </span>
        <span className="text-[11px] text-slate-400 tabular-nums">
          置信度 {memory.confidence.toFixed(2)}
        </span>
        {memory.is_archived && (
          <Badge variant="secondary" className="text-[10px]">
            已归档
          </Badge>
        )}
        <time
          dateTime={memory.created_at}
          className="ml-auto text-[11px] text-slate-400"
        >
          {formatDateTime(memory.created_at)}
        </time>
      </div>

      {/* 内容 / 编辑 */}
      {editing ? (
        <div className="space-y-2">
          <Textarea
            value={editingContent}
            onChange={(e) => onChangeContent(e.target.value)}
            rows={3}
            className="text-sm"
            aria-label="编辑记忆内容"
          />
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={onSave} disabled={pending}>
              {pending ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Check className="size-3.5" />
              )}
              <span className="ml-1">保存</span>
            </Button>
            <Button size="sm" variant="outline" onClick={onCancelEdit}>
              <X className="size-3.5" />
              <span className="ml-1">取消</span>
            </Button>
          </div>
        </div>
      ) : (
        <>
          <p className="text-sm leading-relaxed text-slate-800">
            {memory.content}
          </p>
          {memory.summary && (
            <p className="mt-1.5 text-xs italic text-slate-500">
              {memory.summary}
            </p>
          )}

          {/* 分类调整 */}
          <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-slate-100 pt-2">
            <span className="text-[11px] text-slate-400">分类</span>
            {(Object.keys(TYPE_META) as MemoryType[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => onChangeType(t)}
                aria-pressed={memory.type === t}
                className={cn(
                  "rounded-full border px-2 py-0.5 text-[11px] transition-colors",
                  memory.type === t
                    ? cn("border-transparent", TYPE_META[t].soft)
                    : "border-slate-200 text-slate-500 hover:border-slate-300 hover:bg-slate-50",
                )}
              >
                {TYPE_META[t].label}
              </button>
            ))}
          </div>

          {/* 操作 */}
          <div className="mt-3 flex items-center gap-1.5">
            <Button size="sm" variant="ghost" onClick={onStartEdit}>
              <Edit3 className="size-3.5" />
              <span className="ml-1">编辑</span>
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="text-rose-600 hover:bg-rose-50 hover:text-rose-700"
              onClick={onDelete}
            >
              <Trash2 className="size-3.5" />
              <span className="ml-1">删除</span>
            </Button>
            <span className="ml-auto text-[11px] text-slate-400">
              访问 {memory.access_count} 次
              {memory.last_accessed && ` · 最近 ${formatDateTime(memory.last_accessed)}`}
            </span>
          </div>
        </>
      )}
    </article>
  );
}