"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";
import type { FunnelStageMetric } from "@/lib/types";

interface RecruitmentFunnelProps {
  stages: FunnelStageMetric[];
  className?: string;
  /** 漏斗条颜色,从粗到细渐变. */
  palette?: string[];
}

const DEFAULT_PALETTE = [
  "#2563eb", // blue-600
  "#3b82f6", // blue-500
  "#0ea5e9", // sky-500
  "#06b6d4", // cyan-500
  "#10b981", // emerald-500
  "#22c55e", // green-500
];

export function RecruitmentFunnel({
  stages,
  className,
  palette = DEFAULT_PALETTE,
}: RecruitmentFunnelProps) {
  const max = useMemo(
    () => Math.max(1, ...stages.map((s) => s.candidates)),
    [stages],
  );

  const enriched = useMemo(
    () =>
      stages.map((s, i) => {
        const ratio = s.candidates / max;
        const prev = i > 0 ? stages[i - 1].candidates : 0;
        const conversion =
          prev > 0 ? round((s.candidates / prev) * 100, 1) : null;
        return {
          ...s,
          ratio,
          conversion,
          color: palette[i % palette.length],
        };
      }),
    [stages, max, palette],
  );

  if (stages.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-8 text-center">
        No funnel data in the selected period.
      </p>
    );
  }

  return (
    <div className={cn("space-y-3", className)}>
      {enriched.map((stage, i) => (
        <div key={stage.stage}>
          <div className="flex items-center justify-between mb-1 text-sm">
            <span className="font-medium capitalize">{stage.stage}</span>
            <div className="flex items-center gap-2">
              <span className="font-semibold">
                {stage.candidates.toLocaleString()}
              </span>
              {stage.conversion !== null && (
                <span
                  className={cn(
                    "text-xs px-1.5 py-0.5 rounded",
                    stage.conversion >= 50
                      ? "bg-emerald-100 text-emerald-700"
                      : stage.conversion >= 20
                        ? "bg-amber-100 text-amber-700"
                        : "bg-red-100 text-red-700",
                  )}
                >
                  {stage.conversion}%
                </span>
              )}
            </div>
          </div>
          <div className="h-9 rounded-md bg-muted overflow-hidden">
            <div
              className="h-full transition-all duration-500 flex items-center px-2"
              style={{
                width: `${Math.max(2, stage.ratio * 100)}%`,
                backgroundColor: stage.color,
              }}
            >
              {stage.ratio > 0.25 && (
                <span className="text-[11px] text-white font-medium">
                  {stage.events.toLocaleString()} events
                </span>
              )}
            </div>
          </div>
          {i < enriched.length - 1 && (
            <div className="flex justify-center py-0.5">
              <div className="w-px h-2 bg-slate-200" />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function round(n: number, digits: number): number {
  const m = 10 ** digits;
  return Math.round(n * m) / m;
}