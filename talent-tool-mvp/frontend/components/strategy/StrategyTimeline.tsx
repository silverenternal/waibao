"use client";

/**
 * StrategyTimeline (T205).
 *
 * Vertical timeline of every company_strategy row, grouped by calendar
 * day. Clicking an entry hands the item back to the parent via
 * `onSelect(item)` so the page can:
 *   - highlight it in the map (via StrategyMap's `highlightedId`)
 *   - open a detail drawer / navigate to a detail route
 *
 *   ┌─ 2026-07-10 ────────────────────────────────────────┐
 *   │  ● Vision  "成为 AI 原生 HR 平台"        · 3年       │
 *   │  ● Strategy "攻下 10 家头部客户"        · 1年       │
 *   ├─ 2026-07-05 ────────────────────────────────────────┤
 *   │  ● Tactic  "启动雇主品牌投放"           · 季度      │
 *   └─────────────────────────────────────────────────────┘
 *
 * Level-aware dot colours mirror the strategy map lanes so visual identity
 * stays consistent across the page.
 */

import * as React from "react";
import { Calendar, ChevronRight } from "lucide-react";

import { cn, formatRelativeTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import {
  type StrategyItem,
  type StrategyLevel,
  groupByDate,
  LEVEL_LABEL,
  LEVEL_ORDER,
} from "@/lib/api-strategy";

// ---------------------------------------------------------------------------
// Per-level visual config — must match StrategyMap.tsx lane colours.
// ---------------------------------------------------------------------------

const LEVEL_DOT: Record<StrategyLevel, string> = {
  vision: "bg-indigo-500 ring-indigo-200",
  planning: "bg-sky-500 ring-sky-200",
  strategy: "bg-emerald-500 ring-emerald-200",
  tactic: "bg-amber-500 ring-amber-200",
};

const LEVEL_BADGE: Record<StrategyLevel, string> = {
  vision: "border-indigo-200 bg-indigo-50 text-indigo-700",
  planning: "border-sky-200 bg-sky-50 text-sky-700",
  strategy: "border-emerald-200 bg-emerald-50 text-emerald-700",
  tactic: "border-amber-200 bg-amber-50 text-amber-700",
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface StrategyTimelineProps {
  /** Flat list of items to render — use `flattenStrategyMap()` upstream. */
  items: StrategyItem[];
  /** Highlight a specific item id (e.g. the row currently shown in the map). */
  selectedId?: string | null;
  onSelect?: (item: StrategyItem) => void;
  /** Optional: max number of items to render; older rows collapse under "more". */
  maxItems?: number;
  className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StrategyTimeline({
  items,
  selectedId,
  onSelect,
  maxItems,
  className,
}: StrategyTimelineProps) {
  const [expanded, setExpanded] = React.useState(false);

  const sorted = React.useMemo(
    () =>
      [...items].sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      ),
    [items],
  );

  const visible = React.useMemo(() => {
    if (!maxItems || expanded || sorted.length <= maxItems) return sorted;
    return sorted.slice(0, maxItems);
  }, [sorted, maxItems, expanded]);

  const groups = React.useMemo(() => groupByDate(visible), [visible]);
  const hidden = maxItems && !expanded ? Math.max(0, sorted.length - maxItems) : 0;

  if (items.length === 0) {
    return (
      <div
        className={cn(
          "rounded-lg border border-dashed border-slate-200 bg-slate-50/60 px-3 py-6 text-center text-xs text-slate-400",
          className,
        )}
      >
        暂无历史记录 — 提交愿景文本后会在此生成时间线。
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <ol className="relative ml-3 space-y-4 border-l border-slate-200 pl-5">
        {groups.map((g) => (
          <DayGroup
            key={g.date}
            date={g.date}
            items={g.items}
            selectedId={selectedId}
            onSelect={onSelect}
          />
        ))}
      </ol>

      {hidden > 0 && (
        <Button
          variant="outline"
          size="sm"
          onClick={() => setExpanded(true)}
          className="self-start gap-1"
        >
          展开剩余 {hidden} 条
          <ChevronRight className="size-3.5" />
        </Button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// One calendar-day grouping
// ---------------------------------------------------------------------------

function DayGroup({
  date,
  items,
  selectedId,
  onSelect,
}: {
  date: string;
  items: StrategyItem[];
  selectedId?: string | null;
  onSelect?: (it: StrategyItem) => void;
}) {
  // Render levels in fixed order so the per-day list looks consistent.
  const byLevel = React.useMemo(() => {
    const m: Partial<Record<StrategyLevel, StrategyItem[]>> = {};
    for (const it of items) {
      const arr = (m[it.level] ??= []);
      arr.push(it);
    }
    return m;
  }, [items]);

  return (
    <li>
      <div className="absolute -left-[7px] flex size-3.5 items-center justify-center rounded-full bg-white ring-2 ring-slate-200" />
      <div className="-mt-0.5 mb-2 flex items-center gap-2 text-xs font-semibold text-slate-700">
        <Calendar className="size-3.5 text-slate-400" />
        <span>{date}</span>
        <span className="text-[10px] font-normal text-slate-400">
          · {items.length} 条
        </span>
      </div>
      <ul className="space-y-1.5">
        {LEVEL_ORDER.flatMap((lvl) => byLevel[lvl] ?? []).map((it) => (
          <TimelineRow
            key={it.id}
            item={it}
            selected={it.id === selectedId}
            onSelect={onSelect}
          />
        ))}
      </ul>
    </li>
  );
}

// ---------------------------------------------------------------------------
// One row
// ---------------------------------------------------------------------------

function TimelineRow({
  item,
  selected,
  onSelect,
}: {
  item: StrategyItem;
  selected: boolean;
  onSelect?: (it: StrategyItem) => void;
}) {
  const isClickable = Boolean(onSelect);
  return (
    <li>
      <button
        type="button"
        disabled={!isClickable}
        onClick={onSelect ? () => onSelect(item) : undefined}
        className={cn(
          "group flex w-full items-start gap-3 rounded-md border bg-white px-3 py-2 text-left transition",
          "hover:border-blue-300 hover:bg-blue-50/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
          "disabled:cursor-default disabled:hover:border-slate-200 disabled:hover:bg-white",
          selected
            ? "border-blue-400 ring-2 ring-blue-200"
            : "border-slate-200",
        )}
      >
        <span
          aria-hidden
          className={cn(
            "mt-1 inline-flex size-2.5 shrink-0 rounded-full ring-4",
            LEVEL_DOT[item.level],
          )}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant="outline"
              className={cn("border", LEVEL_BADGE[item.level])}
            >
              {LEVEL_LABEL[item.level]}
            </Badge>
            <span className="truncate text-sm font-medium text-slate-900">
              {item.title}
            </span>
            {item.horizon && (
              <span className="text-[10px] text-slate-500">
                · {item.horizon}
              </span>
            )}
          </div>
          {item.description && (
            <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">
              {item.description}
            </p>
          )}
        </div>
        <span className="shrink-0 text-[10px] tabular-nums text-slate-400">
          {formatRelativeTime(item.created_at)}
        </span>
      </button>
    </li>
  );
}