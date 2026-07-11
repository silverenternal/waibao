"use client";

/**
 * EmotionTriggerCorrelation (T605)
 *
 * Lightweight correlation card that joins the emotion timeline with the
 * journal entries on `journal_date`, then renders a small scatter +
 * Pearson r-value badge.
 *
 * Why this exists: the user often wants to know whether the dip on a
 * given day was caused by a specific diary entry (or vice versa).
 */

import * as React from "react";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ZAxis,
} from "recharts";
import { Link2, ArrowDownUp } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export interface EmotionJournalPoint {
  date: string;
  sentiment: number;
  moodScore: number;
  journalRating: "excellent" | "good" | "warning" | null;
}

export interface EmotionTriggerCorrelationProps {
  joined: EmotionJournalPoint[];
  className?: string;
}

export function EmotionTriggerCorrelation({
  joined,
  className,
}: EmotionTriggerCorrelationProps) {
  const data = joined
    .filter((p) => Number.isFinite(p.sentiment) && Number.isFinite(p.moodScore))
    .map((p) => ({
      ...p,
      sentiment: p.sentiment,
      moodScore: p.moodScore,
      rating: p.journalRating,
    }));

  const r = React.useMemo(() => pearson(data), [data]);
  const band = bandFor(r);
  const label = correlationLabel(r);

  if (data.length === 0) {
    return (
      <Card className={cn("border-dashed", className)}>
        <CardContent className="flex items-center gap-2 py-4 text-xs text-slate-500">
          <Link2 className="size-4 text-slate-400" />
          暂无可关联的数据,先写日记或检测情绪即可生成。
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <ArrowDownUp className="size-4 text-violet-500" />
          情绪 vs 日记相关性
        </CardTitle>
        <CardDescription>
          {data.length} 个数据点 · 同日情绪倾向与日记心情评分的 Pearson 相关系数
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-2 pb-2">
          <Badge
            variant="outline"
            className={cn(
              "text-xs font-semibold",
              band === "high" && "border-emerald-300 bg-emerald-50 text-emerald-700",
              band === "mid" && "border-amber-300 bg-amber-50 text-amber-700",
              band === "low" && "border-rose-300 bg-rose-50 text-rose-700",
            )}
          >
            r = {r.toFixed(2)} · {label}
          </Badge>
        </div>
        <div style={{ height: 240 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="#eef2f7" strokeDasharray="3 3" />
              <XAxis
                dataKey="sentiment"
                type="number"
                domain={[-1.05, 1.05]}
                tick={{ fontSize: 11, fill: "#475569" }}
                name="情绪倾向"
              />
              <YAxis
                dataKey="moodScore"
                type="number"
                domain={[-1.05, 1.05]}
                tick={{ fontSize: 11, fill: "#475569" }}
                name="日记心情"
                width={56}
              />
              <ZAxis dataKey="date" range={[60, 60]} />
              <Tooltip
                cursor={{ strokeDasharray: "3 3" }}
                content={(p: any) => {
                  if (!p.active || !p.payload?.length) return null;
                  const d = p.payload[0].payload;
                  return (
                    <div className="rounded-md border border-slate-200 bg-white p-2 text-xs shadow-md">
                      <p className="mb-1 font-medium text-slate-700">{d.date}</p>
                      <p>情绪倾向: <span className="font-medium tabular-nums">{d.sentiment.toFixed(2)}</span></p>
                      <p>日记心情: <span className="font-medium tabular-nums">{d.moodScore.toFixed(2)}</span></p>
                      {d.rating && (
                        <p className="text-[11px] text-slate-500">日记评级: {ratingLabel(d.rating)}</p>
                      )}
                    </div>
                  );
                }}
              />
              <Scatter data={data} fill="#6366f1" />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pearson(points: { sentiment: number; moodScore: number }[]): number {
  if (points.length < 2) return 0;
  const n = points.length;
  const sx = points.reduce((a, p) => a + p.sentiment, 0);
  const sy = points.reduce((a, p) => a + p.moodScore, 0);
  const sxx = points.reduce((a, p) => a + p.sentiment * p.sentiment, 0);
  const syy = points.reduce((a, p) => a + p.moodScore * p.moodScore, 0);
  const sxy = points.reduce((a, p) => a + p.sentiment * p.moodScore, 0);
  const num = n * sxy - sx * sy;
  const den = Math.sqrt((n * sxx - sx * sx) * (n * syy - sy * sy));
  if (!den) return 0;
  return Math.max(-1, Math.min(1, num / den));
}

function bandFor(r: number): "high" | "mid" | "low" {
  const a = Math.abs(r);
  if (a >= 0.5) return "high";
  if (a >= 0.25) return "mid";
  return "low";
}

function correlationLabel(r: number): string {
  const a = Math.abs(r);
  if (a >= 0.7) return r > 0 ? "强正相关" : "强负相关";
  if (a >= 0.5) return r > 0 ? "中等正相关" : "中等负相关";
  if (a >= 0.25) return "弱相关";
  return "无显著相关";
}

function ratingLabel(rating: "excellent" | "good" | "warning"): string {
  switch (rating) {
    case "excellent":
      return "极佳";
    case "good":
      return "稳定";
    case "warning":
      return "需关注";
    default:
      return rating;
  }
}
