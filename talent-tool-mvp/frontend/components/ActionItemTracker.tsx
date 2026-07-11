"use client";

/**
 * ActionItemTracker (T606)
 *
 * Interactive checklist for the action items returned by the journal
 * agent (and any user-added items). Each row supports:
 *   - toggle state (open → in_progress → done)
 *   - dismiss
 *   - origin chip ("智能体推荐" / "我添加的")
 *   - due date hint (when present)
 *
 * Mutations are local-first + server sync:
 *   onClick handlers call the API, then optimistically update the row.
 *   Failures revert via the lightweight `failedIds` Set so the row can be
 *   retried with a one-click button.
 */

import * as React from "react";
import {
  Plus,
  Trash2,
  Loader2,
  Check,
  CircleDashed,
  PlayCircle,
  X,
  Sparkles,
  Calendar,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

export type ActionItemState = "open" | "in_progress" | "done" | "dismissed";

export interface ActionItem {
  id: string;
  title: string;
  description?: string | null;
  state: ActionItemState;
  origin: "agent" | "user";
  due_date?: string | null;
  source_text?: string | null;
  journal_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface ActionItemTrackerProps {
  items: ActionItem[];
  loading?: boolean;
  /** Optimistic toggle. Page wires this to PATCH /api/action-items/{id}. */
  onToggleState?: (
    item: ActionItem,
    next: ActionItemState,
  ) => Promise<void> | void;
  /** Delete/dismiss — PATCH to "dismissed" or DELETE. */
  onDismiss?: (item: ActionItem) => Promise<void> | void;
  /** Add a new item — POST /api/action-items. */
  onCreate?: (title: string) => Promise<void> | void;
  className?: string;
  title?: string;
}

const STATE_ORDER: ActionItemState[] = ["open", "in_progress", "done", "dismissed"];

const STATE_META: Record<
  ActionItemState,
  { wrap: string; label: string; icon: React.ComponentType<{ className?: string }> }
> = {
  open: {
    wrap: "bg-slate-50 text-slate-700",
    label: "待办",
    icon: CircleDashed,
  },
  in_progress: {
    wrap: "bg-amber-50 text-amber-700",
    label: "进行中",
    icon: PlayCircle,
  },
  done: {
    wrap: "bg-emerald-50 text-emerald-700",
    label: "完成",
    icon: Check,
  },
  dismissed: {
    wrap: "bg-rose-50 text-rose-700",
    label: "已忽略",
    icon: X,
  },
};

export function ActionItemTracker({
  items,
  loading,
  onToggleState,
  onDismiss,
  onCreate,
  className,
  title = "行动项跟踪",
}: ActionItemTrackerProps) {
  const [draft, setDraft] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [failedIds, setFailedIds] = React.useState<Set<string>>(new Set());

  const grouped = React.useMemo(() => {
    const map: Record<ActionItemState, ActionItem[]> = {
      open: [],
      in_progress: [],
      done: [],
      dismissed: [],
    };
    for (const it of items) {
      const s = STATE_ORDER.includes(it.state) ? it.state : "open";
      map[s].push(it);
    }
    return map;
  }, [items]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const title = draft.trim();
    if (!title || !onCreate) return;
    setBusy(true);
    setError(null);
    try {
      await onCreate(title);
      setDraft("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "添加失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleToggle(item: ActionItem) {
    if (!onToggleState) return;
    const idx = STATE_ORDER.indexOf(item.state);
    const next = STATE_ORDER[(idx + 1) % 3] as ActionItemState; // skip dismissed in the loop
    setFailedIds((prev) => {
      const next2 = new Set(prev);
      next2.delete(item.id);
      return next2;
    });
    try {
      await onToggleState(item, next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新失败");
      setFailedIds((prev) => new Set(prev).add(item.id));
    }
  }

  async function handleDismiss(item: ActionItem) {
    if (!onDismiss) return;
    setFailedIds((prev) => {
      const next2 = new Set(prev);
      next2.delete(item.id);
      return next2;
    });
    try {
      await onDismiss(item);
    } catch (err) {
      setError(err instanceof Error ? err.message : "忽略失败");
      setFailedIds((prev) => new Set(prev).add(item.id));
    }
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Sparkles className="size-4 text-violet-500" />
          {title}
          <Badge variant="outline" className="ml-auto text-[10px]">
            {items.filter((i) => i.state !== "dismissed").length} 待处理
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && (
          <div className="rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700">
            {error}
          </div>
        )}

        {onCreate && (
          <form onSubmit={handleCreate} className="flex items-center gap-2">
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="添加新的行动项 (例如:约 1on1 复盘)"
              className="h-8"
              disabled={busy}
            />
            <Button
              type="submit"
              size="sm"
              disabled={busy || !draft.trim()}
              className="h-8 gap-1"
            >
              {busy ? <Loader2 className="size-3 animate-spin" /> : <Plus className="size-3.5" />}
              添加
            </Button>
          </form>
        )}

        {loading && items.length === 0 ? (
          <ul className="space-y-1.5">
            {Array.from({ length: 3 }).map((_, i) => (
              <li key={i}>
                <Skeleton className="h-12 w-full" />
              </li>
            ))}
          </ul>
        ) : items.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-3 py-6 text-center text-xs text-slate-500">
            还没有行动项。提交一篇日记,智能体会自动生成建议。
          </p>
        ) : (
          <div className="space-y-3">
            {(["open", "in_progress", "done"] as ActionItemState[]).map((s) =>
              grouped[s].length === 0 ? null : (
                <section key={s}>
                  <h4 className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">
                    {STATE_META[s].label} · {grouped[s].length}
                  </h4>
                  <ul className="space-y-1.5">
                    {grouped[s].map((it) => (
                      <Row
                        key={it.id}
                        item={it}
                        failed={failedIds.has(it.id)}
                        onToggle={handleToggle}
                        onDismiss={handleDismiss}
                      />
                    ))}
                  </ul>
                </section>
              ),
            )}

            {grouped.dismissed.length > 0 && (
              <details className="rounded-md border border-slate-200 bg-slate-50/60 px-2 py-1.5">
                <summary className="cursor-pointer text-[10px] font-medium uppercase tracking-wide text-slate-500">
                  已忽略 · {grouped.dismissed.length}
                </summary>
                <ul className="mt-1.5 space-y-1.5">
                  {grouped.dismissed.map((it) => (
                    <Row
                      key={it.id}
                      item={it}
                      failed={failedIds.has(it.id)}
                      onToggle={handleToggle}
                      onDismiss={handleDismiss}
                    />
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Per-row
// ---------------------------------------------------------------------------

function Row({
  item,
  failed,
  onToggle,
  onDismiss,
}: {
  item: ActionItem;
  failed: boolean;
  onToggle: (item: ActionItem) => void;
  onDismiss: (item: ActionItem) => void;
}) {
  const meta = STATE_META[item.state];
  const Icon = meta.icon;
  return (
    <li
      className={cn(
        "flex items-start gap-2 rounded-md border bg-white p-2 text-xs",
        failed ? "border-rose-300 bg-rose-50/60" : "border-slate-200",
      )}
    >
      <button
        type="button"
        onClick={() => onToggle(item)}
        className={cn(
          "mt-0.5 grid size-5 shrink-0 place-items-center rounded-md border transition",
          item.state === "done"
            ? "border-emerald-500 bg-emerald-500 text-white"
            : item.state === "in_progress"
              ? "border-amber-500 bg-amber-50 text-amber-700"
              : "border-slate-300 bg-white text-slate-400 hover:border-blue-400 hover:text-blue-500",
        )}
        aria-label="切换状态"
      >
        <Icon className="size-3" />
      </button>
      <div className="min-w-0 flex-1 space-y-0.5">
        <p
          className={cn(
            "text-slate-800",
            item.state === "done" && "line-through text-slate-400",
            item.state === "dismissed" && "text-slate-400",
          )}
        >
          {item.title}
        </p>
        <div className="flex flex-wrap items-center gap-1 text-[10px] text-slate-500">
          <Badge
            variant="outline"
            className={cn(
              "text-[10px]",
              item.origin === "agent"
                ? "border-violet-200 bg-violet-50 text-violet-700"
                : "border-blue-200 bg-blue-50 text-blue-700",
            )}
          >
            {item.origin === "agent" ? "智能体推荐" : "我添加的"}
          </Badge>
          {item.due_date && (
            <span className="inline-flex items-center gap-1">
              <Calendar className="size-3" />
              {item.due_date}
            </span>
          )}
        </div>
        {failed && (
          <p className="text-[10px] text-rose-600">同步失败,再点一次按钮重试</p>
        )}
      </div>
      <button
        type="button"
        onClick={() => onDismiss(item)}
        className="shrink-0 rounded-md p-1 text-slate-400 transition hover:bg-slate-100 hover:text-rose-500"
        aria-label="忽略"
        title="忽略"
      >
        <Trash2 className="size-3.5" />
      </button>
    </li>
  );
}
