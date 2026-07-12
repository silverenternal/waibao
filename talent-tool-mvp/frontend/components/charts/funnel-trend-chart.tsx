"use client";

import { cn } from "@/lib/utils";

interface TrendBucket {
  week_start: string;
  week_end: string;
  by_stage: Record<string, number>;
}

interface FunnelTrendChartProps {
  trend: TrendBucket[];
  className?: string;
}

/**
 * T1803 — Weekly trend (13 weeks).
 *
 * Stacked-ish bar showing sourced / hired counts per week, with the
 * sourced/hired ratio summarised on the right.
 */
export function FunnelTrendChart({ trend, className }: FunnelTrendChartProps) {
  if (!trend?.length) {
    return (
      <p className="text-sm text-muted-foreground py-6 text-center">
        No trend data.
      </p>
    );
  }

  const maxSourced = Math.max(
    ...trend.map((t) => t.by_stage.sourced || 0),
    1,
  );

  return (
    <div className={cn("space-y-2", className)}>
      {trend.map((t) => {
        const sourced = t.by_stage.sourced || 0;
        const hired = t.by_stage.hired || 0;
        const pct = (sourced / maxSourced) * 100;
        const ratio = sourced > 0 ? ((hired / sourced) * 100).toFixed(1) : "0";
        return (
          <div key={t.week_start} className="space-y-0.5">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium">
                {t.week_start} → {t.week_end}
              </span>
              <span className="text-muted-foreground">
                sourced {sourced} · hired {hired} · {ratio}%
              </span>
            </div>
            <div className="h-2.5 rounded bg-muted overflow-hidden flex">
              <div
                className="h-full bg-blue-500 transition-all duration-300"
                style={{ width: `${pct}%` }}
              />
              <div
                className="h-full bg-emerald-500 transition-all duration-300"
                style={{
                  width: `${(hired / maxSourced) * 100}%`,
                  marginLeft: "-2px",
                }}
              />
            </div>
          </div>
        );
      })}
      <div className="flex items-center gap-3 pt-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-2 bg-blue-500 rounded-sm" />
          sourced
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-2 bg-emerald-500 rounded-sm" />
          hired
        </span>
      </div>
    </div>
  );
}
