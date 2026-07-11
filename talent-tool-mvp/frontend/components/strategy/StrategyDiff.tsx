"use client";

/**
 * StrategyDiff (T205).
 *
 * Side-by-side comparison of two strategy snapshots. The parent is expected
 * to compute the diff via `diffStrategyLists()` from `lib/api-strategy.ts`
 * (or pass the raw before/after arrays and let this component call it).
 *
 *   ┌───────── 旧版本 ─────────┐ │ ┌───────── 新版本 ─────────┐
 *   │  red: 移除  / red-line    │ │ │  green: 新增              │
 *   │  amber: 修改 (before)     │ │ │  amber: 修改 (after)      │
 *   │  unchanged: muted         │ │ │  unchanged: muted         │
 *   └───────────────────────────┘ │ └───────────────────────────┘
 *
 * When `before` and `after` are identical, we show a friendly "无差异" hint.
 */

import * as React from "react";
import {
  Plus,
  Minus,
  Pencil,
  Equal,
  ChevronDown,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import {
  type StrategyItem,
  type StrategyDiff,
  diffStrategyLists,
  LEVEL_LABEL,
  LEVEL_ORDER,
} from "@/lib/api-strategy";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface StrategyDiffProps {
  before: StrategyItem[];
  after: StrategyItem[];
  /** Optional pre-computed diff. If omitted, the component computes it. */
  diff?: StrategyDiff;
  /** Label rendered above the left column. */
  beforeLabel?: string;
  /** Label rendered above the right column. */
  afterLabel?: string;
  className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StrategyDiffView({
  before,
  after,
  diff: diffProp,
  beforeLabel = "旧版本",
  afterLabel = "新版本",
  className,
}: StrategyDiffProps) {
  const diff = React.useMemo(
    () => diffProp ?? diffStrategyLists(before, after),
    [before, after, diffProp],
  );

  const totalChanges =
    diff.added.length + diff.removed.length + diff.changed.length;
  const identical = totalChanges === 0;

  // Bucket each side so we can render paired rows.
  const beforeBuckets = React.useMemo(
    () => bucketForBefore(diff),
    [diff],
  );
  const afterBuckets = React.useMemo(() => bucketForAfter(diff, after), [diff, after]);

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {/* Summary chips */}
      <header className="flex flex-wrap items-center gap-2">
        <SummaryChip
          kind="added"
          count={diff.added.length}
          label="新增"
        />
        <SummaryChip
          kind="removed"
          count={diff.removed.length}
          label="删除"
        />
        <SummaryChip
          kind="changed"
          count={diff.changed.length}
          label="修改"
        />
        {identical && (
          <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-500">
            <Equal className="size-3" /> 无差异
          </span>
        )}
      </header>

      {/* Two columns */}
      <div className="grid gap-3 lg:grid-cols-2">
        <DiffColumn
          title={beforeLabel}
          tone="remove"
          buckets={beforeBuckets}
        />
        <DiffColumn
          title={afterLabel}
          tone="add"
          buckets={afterBuckets}
        />
      </div>

      {/* Detail panel for changed items — full descriptions */}
      {diff.changed.length > 0 && (
        <details className="rounded-lg border border-amber-200 bg-amber-50/60 p-3">
          <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium text-amber-900">
            <Pencil className="size-3.5" />
            修改明细 ({diff.changed.length})
            <ChevronDown className="size-3.5" />
          </summary>
          <ul className="mt-2 space-y-2">
            {diff.changed.map(({ before: b, after: a }) => (
              <li
                key={b.id}
                className="rounded-md border border-amber-200 bg-white p-3 text-xs"
              >
                <div className="mb-1 flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className="border-amber-300 bg-amber-100 text-amber-800"
                  >
                    {LEVEL_LABEL[b.level]}
                  </Badge>
                  <span className="font-medium text-slate-800">{b.title}</span>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded border border-rose-200 bg-rose-50/60 p-2">
                    <div className="mb-0.5 text-[10px] font-semibold text-rose-700">
                      修改前
                    </div>
                    <p className="whitespace-pre-wrap text-slate-700">
                      {b.description || "(无)"}
                    </p>
                    {b.horizon && (
                      <p className="mt-1 text-[10px] text-slate-500">
                        horizon: {b.horizon}
                      </p>
                    )}
                  </div>
                  <div className="rounded border border-emerald-200 bg-emerald-50/60 p-2">
                    <div className="mb-0.5 text-[10px] font-semibold text-emerald-700">
                      修改后
                    </div>
                    <p className="whitespace-pre-wrap text-slate-700">
                      {a.description || "(无)"}
                    </p>
                    {a.horizon && (
                      <p className="mt-1 text-[10px] text-slate-500">
                        horizon: {a.horizon}
                      </p>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </details>
      )}

      {!identical && (
        <p className="text-[11px] text-slate-400">
          按层级分组展示;红框 = 旧版本 / 删除,绿框 = 新版本 / 新增。
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary chip
// ---------------------------------------------------------------------------

function SummaryChip({
  kind,
  count,
  label,
}: {
  kind: "added" | "removed" | "changed";
  count: number;
  label: string;
}) {
  if (count === 0) return null;
  const tone =
    kind === "added"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : kind === "removed"
        ? "border-rose-200 bg-rose-50 text-rose-700"
        : "border-amber-200 bg-amber-50 text-amber-700";
  const Icon = kind === "added" ? Plus : kind === "removed" ? Minus : Pencil;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs",
        tone,
      )}
    >
      <Icon className="size-3" />
      {label} {count}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Column buckets
// ---------------------------------------------------------------------------

interface ColumnBucket {
  level: import("@/lib/api-strategy").StrategyLevel;
  entries: ColumnEntry[];
}

type ColumnEntry =
  | { kind: "removed"; item: StrategyItem }
  | { kind: "added"; item: StrategyItem }
  | { kind: "changed-before"; item: StrategyItem }
  | { kind: "changed-after"; item: StrategyItem }
  | { kind: "unchanged"; item: StrategyItem };

function bucketForBefore(diff: StrategyDiff): ColumnBucket[] {
  const byLevel = new Map<
    import("@/lib/api-strategy").StrategyLevel,
    ColumnEntry[]
  >();
  const push = (
    lvl: import("@/lib/api-strategy").StrategyLevel,
    e: ColumnEntry,
  ) => {
    const arr = byLevel.get(lvl) ?? [];
    arr.push(e);
    byLevel.set(lvl, arr);
  };
  for (const it of diff.removed) push(it.level, { kind: "removed", item: it });
  for (const { before: b } of diff.changed)
    push(b.level, { kind: "changed-before", item: b });
  return LEVEL_ORDER.filter((l) => byLevel.has(l)).map((l) => ({
    level: l,
    entries: byLevel.get(l) ?? [],
  }));
}

function bucketForAfter(
  diff: StrategyDiff,
  after: StrategyItem[],
): ColumnBucket[] {
  const byLevel = new Map<
    import("@/lib/api-strategy").StrategyLevel,
    ColumnEntry[]
  >();
  const push = (
    lvl: import("@/lib/api-strategy").StrategyLevel,
    e: ColumnEntry,
  ) => {
    const arr = byLevel.get(lvl) ?? [];
    arr.push(e);
    byLevel.set(lvl, arr);
  };
  for (const it of diff.added) push(it.level, { kind: "added", item: it });
  for (const { after: a } of diff.changed)
    push(a.level, { kind: "changed-after", item: a });

  // Unchanged items — anything in `after` that wasn't touched.
  const touched = new Set<string>();
  for (const it of diff.added) touched.add(it.id);
  for (const { after: a } of diff.changed) touched.add(a.id);
  for (const it of after) {
    if (!touched.has(it.id)) push(it.level, { kind: "unchanged", item: it });
  }

  return LEVEL_ORDER.filter((l) => byLevel.has(l)).map((l) => ({
    level: l,
    entries: byLevel.get(l) ?? [],
  }));
}

// ---------------------------------------------------------------------------
// Column renderer
// ---------------------------------------------------------------------------

function DiffColumn({
  title,
  tone,
  buckets,
}: {
  title: string;
  tone: "add" | "remove";
  buckets: ColumnBucket[];
}) {
  const isAdd = tone === "add";
  return (
    <section
      className={cn(
        "rounded-xl border bg-white p-3",
        isAdd ? "border-emerald-200" : "border-rose-200",
      )}
    >
      <h4
        className={cn(
          "mb-2 flex items-center gap-2 text-sm font-semibold",
          isAdd ? "text-emerald-800" : "text-rose-800",
        )}
      >
        {isAdd ? (
          <Plus className="size-3.5" />
        ) : (
          <Minus className="size-3.5" />
        )}
        {title}
      </h4>

      {buckets.length === 0 ? (
        <p className="rounded-md border border-dashed border-slate-200 bg-slate-50/60 px-3 py-4 text-center text-xs text-slate-400">
          无项目
        </p>
      ) : (
        <div className="space-y-3">
          {buckets.map((b) => (
            <div key={b.level}>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                {LEVEL_LABEL[b.level]}
              </div>
              <ul className="space-y-1.5">
                {b.entries.map((e) => (
                  <DiffRow key={`${e.kind}-${e.item.id}`} entry={e} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function DiffRow({ entry }: { entry: ColumnEntry }) {
  switch (entry.kind) {
    case "added":
      return (
        <li className="rounded-md border border-emerald-200 bg-emerald-50/70 p-2 text-xs">
          <div className="flex items-center gap-1 font-medium text-emerald-800">
            <Plus className="size-3" /> 新增 · {LEVEL_LABEL[entry.item.level]}
          </div>
          <div className="mt-0.5 text-slate-800">{entry.item.title}</div>
          {entry.item.description && (
            <p className="mt-1 whitespace-pre-wrap text-slate-600">
              {entry.item.description}
            </p>
          )}
        </li>
      );
    case "removed":
      return (
        <li className="rounded-md border border-rose-200 bg-rose-50/70 p-2 text-xs">
          <div className="flex items-center gap-1 font-medium text-rose-800">
            <Minus className="size-3" /> 删除 · {LEVEL_LABEL[entry.item.level]}
          </div>
          <div className="mt-0.5 text-slate-800 line-through">
            {entry.item.title}
          </div>
          {entry.item.description && (
            <p className="mt-1 whitespace-pre-wrap text-slate-500 line-through">
              {entry.item.description}
            </p>
          )}
        </li>
      );
    case "changed-before":
      return (
        <li className="rounded-md border border-amber-200 bg-amber-50/60 p-2 text-xs">
          <div className="flex items-center gap-1 font-medium text-amber-800">
            <Pencil className="size-3" /> 修改前
          </div>
          <div className="mt-0.5 text-slate-800">{entry.item.title}</div>
          {entry.item.description && (
            <p className="mt-1 line-clamp-2 whitespace-pre-wrap text-slate-600">
              {entry.item.description}
            </p>
          )}
        </li>
      );
    case "changed-after":
      return (
        <li className="rounded-md border border-amber-200 bg-amber-50/60 p-2 text-xs">
          <div className="flex items-center gap-1 font-medium text-amber-800">
            <Pencil className="size-3" /> 修改后
          </div>
          <div className="mt-0.5 text-slate-800">{entry.item.title}</div>
          {entry.item.description && (
            <p className="mt-1 line-clamp-2 whitespace-pre-wrap text-slate-600">
              {entry.item.description}
            </p>
          )}
        </li>
      );
    case "unchanged":
      return (
        <li className="rounded-md border border-slate-200 bg-slate-50/60 p-2 text-xs text-slate-600">
          <div className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-slate-400">
            <Equal className="size-3" /> unchanged
          </div>
          <div className="mt-0.5 text-slate-700">{entry.item.title}</div>
        </li>
      );
  }
}

// Re-export Button so the parent page can compose header CTAs without
// importing it twice.
export { Button as StrategyDiffButton };