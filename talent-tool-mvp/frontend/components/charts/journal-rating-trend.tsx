"use client";

/**
 * JournalRatingTrend (T606)
 *
 * Stacked area chart showing how AI ratings (excellent / good / warning)
 * trend across the user's diary history. Aggregates per week so a 90-day
 * window stays scannable; the trend line on top mirrors the average rating
 * (3=excellent, 2=good, 1=warning) for an at-a-glance health signal.
 */

import * as React from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
  ComposedChart,
  Line,
} from "recharts";

import { cn } from "@/lib/utils";

export interface JournalRatingBucket {
  /** ISO week start (Monday). */
  week: string;
  /** Number of entries tagged `excellent`. */
  excellent: number;
  /** Number of entries tagged `good`. */
  good: number;
  /** Number of entries tagged `warning`. */
  warning: number;
  /** Mean numeric rating for the week (1..3) — null when no entries. */
  avgNumeric: number | null;
}

export interface JournalRatingTrendProps {
  data: JournalRatingBucket[];
  height?: number;
  className?: string;
}

export function JournalRatingTrend({
  data,
  height = 300,
  className,
}: JournalRatingTrendProps) {
  return (
    <div className={cn("w-full", className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 16, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#eef2f7" strokeDasharray="3 3" />
          <XAxis
            dataKey="week"
            tick={{ fontSize: 11, fill: "#475569" }}
            tickLine={false}
            axisLine={{ stroke: "#e2e8f0" }}
          />
          <YAxis
            yAxisId="count"
            tick={{ fontSize: 11, fill: "#475569" }}
            tickLine={false}
            axisLine={{ stroke: "#e2e8f0" }}
            width={36}
            allowDecimals={false}
          />
          <YAxis
            yAxisId="score"
            orientation="right"
            domain={[0.5, 3.5]}
            ticks={[1, 2, 3]}
            tickFormatter={(v: number) => ratingLabel(v)}
            tick={{ fontSize: 11, fill: "#475569" }}
            tickLine={false}
            axisLine={{ stroke: "#e2e8f0" }}
            width={56}
          />

          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine
            yAxisId="score"
            y={2}
            stroke="#cbd5e1"
            strokeDasharray="2 4"
            label={{
              value: "稳定",
              fill: "#94a3b8",
              fontSize: 10,
              position: "right",
            }}
          />

          <Area
            yAxisId="count"
            type="monotone"
            dataKey="warning"
            stackId="rating"
            stroke="#f43f5e"
            fill="#f43f5e33"
            name="需关注"
          />
          <Area
            yAxisId="count"
            type="monotone"
            dataKey="good"
            stackId="rating"
            stroke="#0ea5e9"
            fill="#0ea5e933"
            name="稳定"
          />
          <Area
            yAxisId="count"
            type="monotone"
            dataKey="excellent"
            stackId="rating"
            stroke="#10b981"
            fill="#10b98133"
            name="极佳"
          />

          <Line
            yAxisId="score"
            type="monotone"
            dataKey="avgNumeric"
            stroke="#6366f1"
            strokeWidth={2.5}
            dot={{ r: 3, stroke: "#6366f1", fill: "#fff" }}
            activeDot={{ r: 5 }}
            isAnimationActive={false}
            name="平均评级"
            connectNulls
          />
          <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------

function CustomTooltip(props: { active?: boolean; payload?: any[]; label?: string }) {
  const { active, payload, label } = props;
  if (!active || !payload?.length) return null;
  const datum = payload[0]?.payload as JournalRatingBucket | undefined;
  if (!datum) return null;
  const total = datum.excellent + datum.good + datum.warning;
  return (
    <div className="rounded-md border border-slate-200 bg-white p-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-slate-700">{label}</p>
      <ul className="space-y-0.5 text-slate-600">
        <li>总计 {total} 篇日记</li>
        {datum.avgNumeric != null && (
          <li>平均评级: {ratingLabel(datum.avgNumeric)}</li>
        )}
        <li className="grid grid-cols-[auto_auto_1fr] gap-1 pt-1">
          <span className="inline-block size-2 rounded-full bg-emerald-500" />
          <span className="text-slate-500">极佳</span>
          <span className="text-right font-medium tabular-nums">{datum.excellent}</span>
        </li>
        <li className="grid grid-cols-[auto_auto_1fr] gap-1">
          <span className="inline-block size-2 rounded-full bg-sky-500" />
          <span className="text-slate-500">稳定</span>
          <span className="text-right font-medium tabular-nums">{datum.good}</span>
        </li>
        <li className="grid grid-cols-[auto_auto_1fr] gap-1">
          <span className="inline-block size-2 rounded-full bg-rose-500" />
          <span className="text-slate-500">需关注</span>
          <span className="text-right font-medium tabular-nums">{datum.warning}</span>
        </li>
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers (also re-exported for the page to call directly)
// ---------------------------------------------------------------------------

export function ratingLabel(score: number | null | undefined): string {
  if (score == null || Number.isNaN(score)) return "—";
  if (score >= 2.66) return "极佳";
  if (score >= 1.66) return "稳定";
  return "需关注";
}

export function ratingScore(rating: string | null | undefined): number | null {
  if (rating === "excellent") return 3;
  if (rating === "good") return 2;
  if (rating === "warning") return 1;
  return null;
}

export interface RawJournalRow {
  id: string;
  journal_date: string;
  ai_rating: string | null;
}

export function weeklyAggregate(
  rows: RawJournalRow[],
  weeks = 12,
): JournalRatingBucket[] {
  const buckets = new Map<string, RawJournalRow[]>();
  for (const r of rows) {
    const d = new Date(r.journal_date);
    if (Number.isNaN(d.getTime())) continue;
    const dow = d.getDay();
    const mondayOffset = (dow + 6) % 7;
    const monday = new Date(d.getTime() - mondayOffset * 86_400_000);
    monday.setHours(0, 0, 0, 0);
    const key = monday.toISOString().slice(0, 10);
    const list = buckets.get(key) ?? [];
    list.push(r);
    buckets.set(key, list);
  }
  return [...buckets.entries()]
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .slice(-weeks)
    .map(([week, list]) => {
      const scores = list
        .map((r) => ratingScore(r.ai_rating))
        .filter((v): v is number => v != null);
      return {
        week,
        excellent: list.filter((r) => r.ai_rating === "excellent").length,
        good: list.filter((r) => r.ai_rating === "good").length,
        warning: list.filter((r) => r.ai_rating === "warning").length,
        avgNumeric: scores.length
          ? scores.reduce((a, b) => a + b, 0) / scores.length
          : null,
      };
    });
}
