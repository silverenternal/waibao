"use client";

/**
 * GapAlert (T205).
 *
 * A red warning banner surfaced when one or more of the 4 strategy levels
 * (Vision / Planning / Strategy / Tactic) is empty. The page wires this to
 * the grouped strategy map response.
 *
 *   ┌────────────────────────────────────────────────────────────┐
 *   │  ⚠ 战略地图有 2 层缺失                                       │
 *   │  以下层级尚未填写,会拖慢执行对齐:                            │
 *   │  • 愿景 (Vision) — 3-5 年想成为什么                         │
 *   │  • 战术 (Tactic) — 本季度的可执行动作                        │
 *   │  [在下方补充缺失层级]                                       │
 *   └────────────────────────────────────────────────────────────┘
 *
 * Variants:
 *   - "banner" — full-width card (default, top of page)
 *   - "inline" — slim pill, useful for slotting next to a heading
 *
 * When `missing` is empty the component renders nothing.
 */

import * as React from "react";
import { AlertOctagon, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

import {
  type StrategyLevel,
  LEVEL_LABEL,
  LEVEL_DESCRIPTION,
} from "@/lib/api-strategy";

export interface GapAlertProps {
  /** Which levels are missing (or empty). Order doesn't matter. */
  missing: StrategyLevel[];
  /** Called when the user clicks the CTA — typically scrolls to the input. */
  onCtaClick?: () => void;
  /** Custom CTA label; defaults to "在下方补充缺失层级". */
  ctaLabel?: string;
  /** Banner = full card; inline = slim pill. */
  variant?: "banner" | "inline";
  className?: string;
}

export function GapAlert({
  missing,
  onCtaClick,
  ctaLabel = "在下方补充缺失层级",
  variant = "banner",
  className,
}: GapAlertProps) {
  if (missing.length === 0) return null;

  if (variant === "inline") {
    return (
      <div
        role="alert"
        className={cn(
          "inline-flex items-center gap-2 rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-xs text-rose-700",
          className,
        )}
      >
        <AlertOctagon className="size-3.5" />
        <span className="font-medium">
          缺失 {missing.length} 层:{missing.map((l) => LEVEL_LABEL[l]).join(" / ")}
        </span>
      </div>
    );
  }

  return (
    <div
      role="alert"
      className={cn(
        "rounded-xl border border-rose-200 bg-rose-50/80 p-4 shadow-sm",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-rose-100 text-rose-600">
          <AlertOctagon className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-rose-900">
            战略地图有 {missing.length} 层缺失
          </h3>
          <p className="mt-0.5 text-xs text-rose-700">
            以下层级尚未填写,会拖慢后续招聘 / OKR / 复盘对齐:
          </p>
          <ul className="mt-2 space-y-1">
            {missing.map((lvl) => (
              <li
                key={lvl}
                className="flex items-baseline gap-2 text-xs text-rose-800"
              >
                <span aria-hidden className="size-1 rounded-full bg-rose-500" />
                <span className="font-medium">{LEVEL_LABEL[lvl]}</span>
                <span className="text-rose-600/80">
                  ({lvl}) — {LEVEL_DESCRIPTION[lvl]}
                </span>
              </li>
            ))}
          </ul>
          {onCtaClick && (
            <Button
              variant="outline"
              size="sm"
              onClick={onCtaClick}
              className="mt-3 gap-1 border-rose-300 bg-white text-rose-700 hover:bg-rose-100"
            >
              {ctaLabel}
              <ChevronRight className="size-3.5" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}