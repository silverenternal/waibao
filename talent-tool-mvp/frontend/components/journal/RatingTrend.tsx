"use client";

/**
 * v8.1 T3602 — RatingTrend
 *
 * 显示 rating_trend(用户, days=30) 的折线图.
 *
 * 数据: GET /api/v8_1/journal/trend?user_id=...&days=30
 */

import * as React from "react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface RatingPoint {
  created_at: string;
  role: string;
  score: number;
}

export interface RatingTrendProps {
  points: RatingPoint[];
  className?: string;
}

export function RatingTrend({ points, className }: RatingTrendProps) {
  const max = 10;
  const min = 0;
  const width = 100;
  const height = 100;

  if (points.length === 0) {
    return (
      <Card className={cn("p-6 text-center text-sm text-slate-500", className)}>
        还没有评分记录
      </Card>
    );
  }

  const sorted = [...points].sort((a, b) =>
    a.created_at.localeCompare(b.created_at),
  );

  const polyline = sorted
    .map((p, idx) => {
      const x = (idx / Math.max(1, sorted.length - 1)) * width;
      const y = height - ((p.score - min) / (max - min)) * height;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  const avg = sorted.reduce((s, p) => s + p.score, 0) / sorted.length;
  const latest = sorted[sorted.length - 1];

  return (
    <Card className={cn("p-4", className)}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-800">评分趋势</h3>
        <div className="text-xs text-slate-500">
          平均 <span className="font-medium text-slate-800">{avg.toFixed(1)}</span>
          {" · "}
          最新 <span className="font-medium text-slate-800">{latest.score.toFixed(1)}</span>
          {" · "}
          {sorted.length} 条
        </div>
      </div>
      <svg
        viewBox={`-2 -2 ${width + 4} ${height + 4}`}
        className="w-full h-32"
        role="img"
        aria-label="rating trend chart"
      >
        {/* grid */}
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <line
            key={t}
            x1={0}
            x2={width}
            y1={height * t}
            y2={height * t}
            stroke="#e2e8f0"
            strokeWidth={0.3}
          />
        ))}
        <polyline
          fill="none"
          stroke="#4f46e5"
          strokeWidth={1}
          points={polyline}
        />
        {sorted.map((p, idx) => {
          const x = (idx / Math.max(1, sorted.length - 1)) * width;
          const y = height - ((p.score - min) / (max - min)) * height;
          return (
            <circle
              key={idx}
              cx={x}
              cy={y}
              r={1.4}
              fill="#4f46e5"
            >
              <title>{`${p.role}: ${p.score}`}</title>
            </circle>
          );
        })}
      </svg>
    </Card>
  );
}

export default RatingTrend;