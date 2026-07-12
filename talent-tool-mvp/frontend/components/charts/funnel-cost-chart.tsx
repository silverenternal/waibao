"use client";

import { cn } from "@/lib/utils";

interface FunnelCostStage {
  stage: string;
  candidates: number;
  total_cost_cents: number;
  avg_cost_cents: number;
}

interface FunnelCostChartProps {
  stages: FunnelCostStage[];
  className?: string;
}

/**
 * T1803 — Cost overlay on the funnel.
 *
 * Shows total cost (¥) per stage with avg cost per candidate annotation.
 */
export function FunnelCostChart({ stages, className }: FunnelCostChartProps) {
  if (!stages?.length) {
    return (
      <p className="text-sm text-muted-foreground py-6 text-center">
        No cost data.
      </p>
    );
  }

  const maxCost = Math.max(...stages.map((s) => s.total_cost_cents || 0));

  return (
    <div className={cn("space-y-3", className)}>
      {stages.map((s) => {
        const pct = maxCost > 0 ? (s.total_cost_cents / maxCost) * 100 : 0;
        const yuan = (s.total_cost_cents / 100).toFixed(0);
        const avg = (s.avg_cost_cents / 100).toFixed(0);
        return (
          <div key={s.stage}>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="font-medium capitalize">{s.stage}</span>
              <div className="flex items-center gap-3 text-muted-foreground">
                <span>{s.candidates.toLocaleString()} 人</span>
                <span>¥{avg} / 人</span>
                <span className="font-semibold text-foreground">¥{yuan}</span>
              </div>
            </div>
            <div className="h-3 rounded-md bg-muted overflow-hidden">
              <div
                className="h-full rounded-md bg-gradient-to-r from-amber-500 to-orange-500 transition-all duration-500"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
