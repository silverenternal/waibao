"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SalaryTrend } from "@/lib/api-salary";

export interface SalaryTrendChartProps {
  trend: SalaryTrend | null;
  loading?: boolean;
}

export function SalaryTrendChart({ trend, loading }: SalaryTrendChartProps) {
  if (loading) {
    return (
      <Card>
        <CardContent className="p-6 text-slate-400 text-sm">加载中…</CardContent>
      </Card>
    );
  }
  if (!trend || trend.points.length === 0) {
    return (
      <Card>
        <CardContent className="p-6 text-slate-500 text-sm">暂无趋势数据</CardContent>
      </Card>
    );
  }

  const values = trend.points.map((p) => p.median_k);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(1, max - min);
  const toPct = (v: number) => ((v - min) / span) * 100;

  const trendColor =
    trend.change_6m_pct > 0
      ? "text-emerald-600"
      : trend.change_6m_pct < 0
        ? "text-rose-600"
        : "text-slate-600";

  const trendArrow = trend.change_6m_pct > 0 ? "↑" : trend.change_6m_pct < 0 ? "↓" : "→";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center justify-between">
          <span>薪资趋势 ({trend.period})</span>
          <span className={`text-sm ${trendColor}`}>
            {trendArrow} {Math.abs(trend.change_6m_pct).toFixed(1)}% (6 个月)
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="relative h-32">
          <svg className="w-full h-full" viewBox="0 0 400 100" preserveAspectRatio="none">
            <polyline
              fill="none"
              stroke="#f59e0b"
              strokeWidth="2"
              points={trend.points
                .map((p, i) => {
                  const x = (i / Math.max(1, trend.points.length - 1)) * 400;
                  const y = 100 - toPct(p.median_k);
                  return `${x},${y}`;
                })
                .join(" ")}
            />
            {trend.points.map((p, i) => {
              const x = (i / Math.max(1, trend.points.length - 1)) * 400;
              const y = 100 - toPct(p.median_k);
              return (
                <circle
                  key={i}
                  cx={x}
                  cy={y}
                  r="2"
                  fill="#f59e0b"
                />
              );
            })}
          </svg>
        </div>
        <div className="flex justify-between text-xs text-slate-500 mt-2">
          <span>{trend.points[0]?.period}</span>
          <span>{trend.points[trend.points.length - 1]?.period}</span>
        </div>
      </CardContent>
    </Card>
  );
}