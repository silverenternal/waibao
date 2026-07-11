"use client";

/**
 * EmotionWeekSummary (T605)
 *
 * Auto-computes a per-week summary card from the emotion timeline:
 *   - 平均情绪倾向 (-1..1)
 *   - 平均强度 (%)
 *   - 触发次数
 *   - 关注告警次数
 *   - 主导情绪 (频次最高的 `primary_emotion`)
 *
 * Renders the last `weeks` weeks in a horizontal scroll layout so the
 * page surfaces a long-term view even when the chart only shows days.
 */

import * as React from "react";
import {
  Activity,
  Heart,
  TrendingUp,
  AlertTriangle,
  Smile,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export interface EmotionWeekSummaryRow {
  weekStart: string;
  avgSentiment: number;
  avgIntensity: number;
  triggerCount: number;
  alertCount: number;
  dominantEmotion?: string;
}

export interface EmotionWeekSummaryProps {
  rows: EmotionWeekSummaryRow[];
  className?: string;
}

export function EmotionWeekSummary({ rows, className }: EmotionWeekSummaryProps) {
  if (rows.length === 0) {
    return (
      <Card className={cn("border-dashed", className)}>
        <CardContent className="flex items-center gap-2 py-4 text-xs text-slate-500">
          <Heart className="size-4 text-slate-400" />
          还没有足够的情绪记录生成周报。
        </CardContent>
      </Card>
    );
  }
  return (
    <div className={cn("flex gap-3 overflow-x-auto pb-1", className)}>
      {rows.map((r) => (
        <Card
          key={r.weekStart}
          className={cn(
            "min-w-[220px] shrink-0",
            r.alertCount > 0 ? "border-rose-200 bg-rose-50/30" : "border-slate-200",
          )}
        >
          <CardHeader className="pb-1">
            <CardTitle className="text-xs">
              {formatWeek(r.weekStart)}
            </CardTitle>
            <CardDescription className="text-[10px]">
              {r.triggerCount} 次触发 · {r.alertCount} 次告警
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-1.5 text-[11px]">
            <Stat
              icon={<Smile className="size-3 text-indigo-500" />}
              label="平均情绪"
              value={`${r.avgSentiment.toFixed(2)}`}
              color={
                r.avgSentiment > 0.2
                  ? "text-emerald-700"
                  : r.avgSentiment < -0.2
                    ? "text-rose-700"
                    : "text-slate-700"
              }
            />
            <Stat
              icon={<Activity className="size-3 text-amber-500" />}
              label="平均强度"
              value={`${Math.round(r.avgIntensity)}%`}
            />
            {r.dominantEmotion && (
              <Badge
                variant="outline"
                className="border-violet-300 bg-violet-50 text-[10px] text-violet-700"
              >
                <TrendingUp className="mr-1 size-3" />
                {r.dominantEmotion}
              </Badge>
            )}
            {r.alertCount > 0 && (
              <p className="inline-flex items-center gap-1 text-[10px] text-rose-700">
                <AlertTriangle className="size-3" />
                需关注
              </p>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <p className="flex items-center gap-2">
      {icon}
      <span className="text-slate-500">{label}</span>
      <span className={cn("ml-auto font-semibold tabular-nums", color)}>{value}</span>
    </p>
  );
}

function formatWeek(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getFullYear()}年${d.getMonth() + 1}月第${Math.ceil(
    (d.getDate() + 6 - d.getDay()) / 7,
  )}周`;
}

// ---------------------------------------------------------------------------
// Helper — group raw timeline rows into weekly summaries.
// Exported so the page can call it directly when formatting data.
// ---------------------------------------------------------------------------

export interface RawTimelineRow {
  recorded_at: string;
  primary_emotion?: string | null;
  sentiment?: number | null;
  intensity?: number | null;
  needs_attention?: boolean | null;
  trigger_text?: string | null;
}

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

export function weeklyAggregate(rows: RawTimelineRow[], weeks = 4): EmotionWeekSummaryRow[] {
  if (rows.length === 0) return [];
  const buckets = new Map<string, RawTimelineRow[]>();
  for (const r of rows) {
    const d = new Date(r.recorded_at);
    if (Number.isNaN(d.getTime())) continue;
    const dow = d.getDay();
    const mondayOffset = (dow + 6) % 7;
    const monday = new Date(d.getTime() - mondayOffset * 24 * 60 * 60 * 1000);
    monday.setHours(0, 0, 0, 0);
    const key = monday.toISOString().slice(0, 10);
    const list = buckets.get(key) ?? [];
    list.push(r);
    buckets.set(key, list);
  }
  return [...buckets.entries()]
    .sort(([a], [b]) => (a < b ? 1 : -1))
    .slice(0, weeks)
    .map(([weekStart, list]) => {
      const sentiments = list
        .map((x) => x.sentiment)
        .filter((x): x is number => typeof x === "number");
      const intensities = list
        .map((x) => x.intensity)
        .filter((x): x is number => typeof x === "number");
      const emotionCount = new Map<string, number>();
      for (const x of list) {
        if (x.primary_emotion) {
          emotionCount.set(x.primary_emotion, (emotionCount.get(x.primary_emotion) ?? 0) + 1);
        }
      }
      const dominantEmotion = [...emotionCount.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];

      return {
        weekStart,
        avgSentiment: sentiments.length
          ? sentiments.reduce((a, b) => a + b, 0) / sentiments.length
          : 0,
        avgIntensity: intensities.length
          ? (intensities.reduce((a, b) => a + b, 0) / intensities.length) * 100
          : 0,
        triggerCount: list.filter((x) => x.trigger_text).length,
        alertCount: list.filter((x) => x.needs_attention).length,
        dominantEmotion,
      };
    });
}

void WEEK_MS; // keep tree-shake quiet
