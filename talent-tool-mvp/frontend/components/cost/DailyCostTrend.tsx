/**
 * DailyCostTrend (T806) — SVG 折线图,展示日成本走势.
 */
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { DailyCostPoint } from "@/lib/api-cost";

interface DailyCostTrendProps {
  data: DailyCostPoint[];
}

export function DailyCostTrend({ data }: DailyCostTrendProps) {
  if (data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Daily Cost Trend</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground py-8 text-center">
          Waiting for daily aggregations. Latency target: &lt; 60s per write.
        </CardContent>
      </Card>
    );
  }
  const width = 720;
  const height = 200;
  const padding = 32;
  const max = Math.max(...data.map((d) => d.cost_usd), 0.001);
  const xStep = (width - padding * 2) / Math.max(1, data.length - 1);
  const points = data.map((d, i) => {
    const x = padding + i * xStep;
    const y = height - padding - (d.cost_usd / max) * (height - padding * 2);
    return { x, y, ...d };
  });
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  const area = `${path} L ${points[points.length - 1].x} ${height - padding} L ${points[0].x} ${height - padding} Z`;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Daily Cost Trend</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-48"
            role="img"
            aria-label="Daily cost trend"
          >
            <defs>
              <linearGradient id="cost-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity="0.4" />
                <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity="0" />
              </linearGradient>
            </defs>
            <path d={area} fill="url(#cost-fill)" />
            <path d={path} stroke="hsl(var(--primary))" strokeWidth={2} fill="none" />
            {points.map((p) => (
              <circle key={p.date} cx={p.x} cy={p.y} r={3} fill="hsl(var(--primary))" />
            ))}
          </svg>
        </div>
        <div className="flex justify-between text-xs text-muted-foreground mt-2 px-2">
          <span>{data[0].date}</span>
          <span>{data[data.length - 1].date}</span>
        </div>
      </CardContent>
    </Card>
  );
}
