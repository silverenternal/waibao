"use client";

/**
 * StrategyMap (T205).
 *
 * Four-layer stacked visual: Vision (top, biggest) → Planning → Strategy →
 * Tactic (bottom, smallest). Each layer renders as an offset card with a
 * coloured left rail, an icon, level label, horizon tag, and one-or-more
 * item cards inside. Items with the same `level` are stacked vertically
 * inside their lane.
 *
 *   ┌─────────── Vision (largest, indigo) ────────────┐
 *   │   ┌──────── Planning (large, sky) ────────┐     │
 *   │   │   ┌──── Strategy (medium, emerald) ─┐│     │
 *   │   │   │   ┌── Tactic (small, amber) ──┐││     │
 *   │   │   │   │  ...items inside each...  │││     │
 *   │   │   │   └───────────────────────────┘││     │
 *   │   │   └───────────────────────────────┘│     │
 *   │   └────────────────────────────────────┘     │
 *   └───────────────────────────────────────────────┘
 *
 * Pure presentation — data flows in via props. Empty layers trigger a
 * dashed "no content" placeholder (GapAlert covers the loud, page-level
 * warning case; this is the per-layer silent fallback).
 */

import * as React from "react";
import {
  Telescope,
  CalendarRange,
  Compass,
  Zap,
  Inbox,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

import {
  type StrategyItem,
  type StrategyLevel,
  LEVEL_LABEL,
  LEVEL_DESCRIPTION,
  LEVEL_ORDER,
} from "@/lib/api-strategy";

// ---------------------------------------------------------------------------
// Per-level visual config: bigger → smaller (top → bottom).
// ---------------------------------------------------------------------------

interface LevelVisual {
  level: StrategyLevel;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Tailwind gradient / ring classes for the lane. */
  wrapper: string;
  rail: string;
  title: string;
  /** Padding scale: outer padding shrinks as the layer shrinks. */
  pad: string;
  /** Inside the lane, the gap between items. */
  itemGap: string;
  /** Horizontal indent from the layer above (creates the stair-step look). */
  indent: string;
}

const VISUAL: Record<StrategyLevel, LevelVisual> = {
  vision: {
    level: "vision",
    label: LEVEL_LABEL.vision,
    description: LEVEL_DESCRIPTION.vision,
    icon: Telescope,
    wrapper:
      "bg-gradient-to-br from-indigo-50 via-white to-indigo-50 ring-1 ring-indigo-200 shadow-sm",
    rail: "bg-indigo-500",
    title: "text-indigo-900",
    pad: "p-6",
    itemGap: "gap-3",
    indent: "mx-0",
  },
  planning: {
    level: "planning",
    label: LEVEL_LABEL.planning,
    description: LEVEL_DESCRIPTION.planning,
    icon: CalendarRange,
    wrapper:
      "bg-gradient-to-br from-sky-50 via-white to-sky-50 ring-1 ring-sky-200",
    rail: "bg-sky-500",
    title: "text-sky-900",
    pad: "p-5",
    itemGap: "gap-2",
    indent: "mx-6 sm:mx-10",
  },
  strategy: {
    level: "strategy",
    label: LEVEL_LABEL.strategy,
    description: LEVEL_DESCRIPTION.strategy,
    icon: Compass,
    wrapper:
      "bg-gradient-to-br from-emerald-50 via-white to-emerald-50 ring-1 ring-emerald-200",
    rail: "bg-emerald-500",
    title: "text-emerald-900",
    pad: "p-4",
    itemGap: "gap-2",
    indent: "mx-12 sm:mx-20",
  },
  tactic: {
    level: "tactic",
    label: LEVEL_LABEL.tactic,
    description: LEVEL_DESCRIPTION.tactic,
    icon: Zap,
    wrapper:
      "bg-gradient-to-br from-amber-50 via-white to-amber-50 ring-1 ring-amber-200",
    rail: "bg-amber-500",
    title: "text-amber-900",
    pad: "p-4",
    itemGap: "gap-1.5",
    indent: "mx-16 sm:mx-32",
  },
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface StrategyMapProps {
  /** Items grouped by level. Missing levels or empty arrays render placeholders. */
  items: Partial<Record<StrategyLevel, StrategyItem[]>> | null;
  /** Called when the user clicks an item — used by the parent to open detail. */
  onItemClick?: (item: StrategyItem) => void;
  /** Highlight a specific item id (used by the timeline → map navigation). */
  highlightedId?: string | null;
  className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StrategyMap({
  items,
  onItemClick,
  highlightedId,
  className,
}: StrategyMapProps) {
  return (
    <div className={cn("flex flex-col gap-3", className)}>
      {LEVEL_ORDER.map((lvl) => (
        <LayerLane
          key={lvl}
          level={lvl}
          items={(items?.[lvl] ?? []) as StrategyItem[]}
          onItemClick={onItemClick}
          highlightedId={highlightedId}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// One lane = one level.
// ---------------------------------------------------------------------------

function LayerLane({
  level,
  items,
  onItemClick,
  highlightedId,
}: {
  level: StrategyLevel;
  items: StrategyItem[];
  onItemClick?: (item: StrategyItem) => void;
  highlightedId?: string | null;
}) {
  const v = VISUAL[level];
  const Icon = v.icon;

  return (
    <section
      aria-label={v.label}
      data-level={level}
      className={cn(
        "relative rounded-xl",
        v.wrapper,
        v.indent,
      )}
    >
      {/* Coloured left rail */}
      <span
        aria-hidden
        className={cn(
          "absolute inset-y-3 left-0 w-1 rounded-r-full",
          v.rail,
        )}
      />

      <div className={cn("flex flex-col", v.pad)}>
        {/* Lane header */}
        <header className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "inline-flex size-7 items-center justify-center rounded-full bg-white shadow-sm ring-1 ring-black/5",
                v.title,
              )}
            >
              <Icon className="size-4" />
            </span>
            <div>
              <h3 className={cn("text-sm font-semibold", v.title)}>
                {v.label}
              </h3>
              <p className="text-[11px] text-slate-500">{v.description}</p>
            </div>
          </div>

          <Badge variant="outline" className="border-slate-200 bg-white/70">
            {items.length} 项
          </Badge>
        </header>

        {/* Items */}
        {items.length === 0 ? (
          <EmptyLanePlaceholder level={level} />
        ) : (
          <ul className={cn("flex flex-col", v.itemGap)}>
            {items.map((it) => (
              <li key={it.id}>
                <ItemCard
                  item={it}
                  level={level}
                  highlighted={it.id === highlightedId}
                  onClick={onItemClick}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Per-item card — visual weight scales with level (top → bottom, smaller).
// ---------------------------------------------------------------------------

function ItemCard({
  item,
  level,
  highlighted,
  onClick,
}: {
  item: StrategyItem;
  level: StrategyLevel;
  highlighted: boolean;
  onClick?: (it: StrategyItem) => void;
}) {
  const isClickable = Boolean(onClick);

  const sizeClasses =
    level === "vision"
      ? "p-3 text-sm"
      : level === "planning"
        ? "p-2.5 text-[13px]"
        : level === "strategy"
          ? "p-2 text-[13px]"
          : "p-2 text-xs";

  return (
    <button
      type="button"
      disabled={!isClickable}
      onClick={onClick ? () => onClick(item) : undefined}
      className={cn(
        "block w-full rounded-lg border border-slate-200 bg-white/90 text-left shadow-sm transition",
        "hover:border-blue-300 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
        "disabled:cursor-default disabled:hover:border-slate-200 disabled:hover:shadow-sm",
        highlighted && "ring-2 ring-blue-500 border-blue-300",
        sizeClasses,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium text-slate-900">{item.title}</div>
          {item.description && (
            <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-slate-600">
              {item.description}
            </p>
          )}
        </div>
        {item.horizon && (
          <Badge
            variant="outline"
            className="shrink-0 border-slate-200 bg-slate-50 text-[10px] text-slate-600"
          >
            {item.horizon}
          </Badge>
        )}
      </div>
      {(item.owner_role || item.owner_user_id) && (
        <div className="mt-1.5 flex items-center gap-2 text-[10px] text-slate-500">
          <span>Owner · {item.owner_role}</span>
          <span>·</span>
          <span className="tabular-nums">
            {new Date(item.created_at).toLocaleDateString("en-GB", {
              day: "2-digit",
              month: "short",
            })}
          </span>
        </div>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Silent placeholder for an empty lane (GapAlert handles the loud case).
// ---------------------------------------------------------------------------

function EmptyLanePlaceholder({ level }: { level: StrategyLevel }) {
  const v = VISUAL[level];
  const Icon = Inbox;
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-md border border-dashed border-slate-200 bg-white/60 px-3 py-2 text-xs text-slate-500",
      )}
    >
      <Icon className="size-3.5" />
      <span>
        {LEVEL_LABEL[level]}层暂未填写 — 在下方输入框补充。
      </span>
      <span className={cn("ml-auto h-1.5 w-1.5 rounded-full", v.rail)} />
    </div>
  );
}

// Re-export Card pieces so other components (e.g. the page) can compose
// the map inside larger shells without re-importing from /ui/card.
export { Card as StrategyMapCard, CardContent as StrategyMapCardContent, CardHeader as StrategyMapCardHeader, CardTitle as StrategyMapCardTitle };