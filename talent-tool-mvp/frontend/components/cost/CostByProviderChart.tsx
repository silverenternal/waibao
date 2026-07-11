/**
 * CostByProviderChart (T806): 横条形柱状图,纯 SVG,不引入图表库.
 */
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ProviderCost } from "@/lib/api-cost";

interface CostByProviderChartProps {
  data: ProviderCost[];
}

const COLORS = [
  "#2563eb",
  "#0891b2",
  "#059669",
  "#d97706",
  "#dc2626",
  "#7c3aed",
  "#db2777",
];

export function CostByProviderChart({ data }: CostByProviderChartProps) {
  if (data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cost by Provider</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground py-8 text-center">
          No cost data yet. Costs appear within ~30s after the first provider call.
        </CardContent>
      </Card>
    );
  }
  const max = Math.max(...data.map((d) => d.cost_usd));
  const total = data.reduce((s, d) => s + d.cost_usd, 0);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Cost by Provider</CardTitle>
        <span className="text-xs text-muted-foreground">
          Total ${total.toFixed(2)}
        </span>
      </CardHeader>
      <CardContent className="space-y-3">
        {data.map((row, idx) => {
          const pct = max > 0 ? (row.cost_usd / max) * 100 : 0;
          return (
            <div key={row.provider} className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <span className="flex items-center gap-2">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ backgroundColor: COLORS[idx % COLORS.length] }}
                  />
                  <span className="font-mono">{row.provider}</span>
                </span>
                <span className="font-mono">${row.cost_usd.toFixed(4)}</span>
              </div>
              <div className="h-2 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full"
                  style={{
                    width: `${pct}%`,
                    backgroundColor: COLORS[idx % COLORS.length],
                  }}
                />
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
