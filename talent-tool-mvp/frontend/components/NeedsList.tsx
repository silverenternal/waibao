"use client";

/**
 * NeedsList — renders the three "real-needs" buckets produced by the
 * Clarifier Agent (must_haves / nice_to_haves / deal_breakers).
 *
 * Each item is normalised through `normaliseList()` because the LLM may
 * return either a plain string or an object with `{value, reasoning, ...}`.
 * Hovering reveals the reasoning and provenance chips.
 */

import * as React from "react";
import { Check, Heart, Slash, Lightbulb, Info } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  NEEDS_GROUPS,
  NEEDS_GROUP_LABEL,
  SOURCE_LABEL,
  normaliseList,
  type NeedsGroup,
  type NormalisedItem,
} from "@/lib/api-clarification";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const GROUP_META: Record<
  NeedsGroup,
  {
    icon: React.ComponentType<{ className?: string }>;
    accent: string;
    emptyHint: string;
    badgeClass: string;
  }
> = {
  must_haves: {
    icon: Check,
    accent: "text-emerald-700",
    badgeClass: "border-emerald-200 bg-emerald-50 text-emerald-700",
    emptyHint: "还没提取到核心需求 — 多跟智能体聊聊,或在档案里补充期望。",
  },
  nice_to_haves: {
    icon: Heart,
    accent: "text-violet-700",
    badgeClass: "border-violet-200 bg-violet-50 text-violet-700",
    emptyHint: "加分项还没出现 — 可以聊聊理想的工作环境/团队/技术栈。",
  },
  deal_breakers: {
    icon: Slash,
    accent: "text-rose-700",
    badgeClass: "border-rose-200 bg-rose-50 text-rose-700",
    emptyHint: "没有明显的底线 — 可以列出明确不能接受的事情。",
  },
};

export interface NeedsListProps {
  /**
   * Raw values from the clarifier row. Each bucket may be missing or
   * contain either strings or `{value, reasoning, ...}` objects.
   */
  must_haves?: unknown;
  nice_to_haves?: unknown;
  deal_breakers?: unknown;
  className?: string;
  /** Override the title shown in the card header. */
  title?: string;
}

export function NeedsList({
  must_haves,
  nice_to_haves,
  deal_breakers,
  className,
  title = "真实需求",
}: NeedsListProps) {
  const groups: Record<NeedsGroup, NormalisedItem[]> = {
    must_haves: normaliseList(must_haves),
    nice_to_haves: normaliseList(nice_to_haves),
    deal_breakers: normaliseList(deal_breakers),
  };

  const total = groups.must_haves.length + groups.nice_to_haves.length + groups.deal_breakers.length;

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <Lightbulb className="size-4 text-amber-500" />
            {title}
          </CardTitle>
          <span className="text-xs text-muted-foreground">
            {total > 0 ? `共 ${total} 条` : "暂无数据"}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {NEEDS_GROUPS.map((group) => (
          <NeedsGroupSection key={group} group={group} items={groups[group]} />
        ))}
      </CardContent>
    </Card>
  );
}

function NeedsGroupSection({
  group,
  items,
}: {
  group: NeedsGroup;
  items: NormalisedItem[];
}) {
  const meta = GROUP_META[group];
  const Icon = meta.icon;

  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2">
        <Icon className={cn("size-4", meta.accent)} aria-hidden />
        <h4 className={cn("text-sm font-medium", meta.accent)}>
          {NEEDS_GROUP_LABEL[group]}
        </h4>
        <span className="text-xs text-muted-foreground">
          {items.length > 0 ? `${items.length} 项` : "未提取"}
        </span>
      </div>

      {items.length === 0 ? (
        <p className="rounded-lg border border-dashed bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          {meta.emptyHint}
        </p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {items.map((item, i) => (
            <NeedsItemPill key={`${group}-${i}-${item.text}`} item={item} group={group} />
          ))}
        </ul>
      )}
    </section>
  );
}

function NeedsItemPill({
  item,
  group,
}: {
  item: NormalisedItem;
  group: NeedsGroup;
}) {
  const meta = GROUP_META[group];
  return (
    <li className="group relative">
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium",
          meta.badgeClass,
        )}
      >
        {item.text}
        {item.confidence !== undefined && item.confidence < 0.6 && (
          <Info className="size-3 opacity-60" aria-label="低置信度" />
        )}
      </span>
      {(item.reasoning || (item.sources && item.sources.length > 0)) && (
        <div
          className="pointer-events-none absolute left-1/2 top-full z-20 mt-2 hidden w-64 -translate-x-1/2 rounded-lg border bg-popover p-3 text-xs text-popover-foreground shadow-md group-hover:block group-focus-within:block"
          role="tooltip"
        >
          {item.reasoning && (
            <p className="leading-relaxed text-foreground/90">{item.reasoning}</p>
          )}
          {item.sources && item.sources.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {item.sources.map((s) => (
                <span
                  key={s}
                  className="rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
                >
                  {SOURCE_LABEL[s] ?? s}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </li>
  );
}