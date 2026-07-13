"use client";

/**
 * HRMetrics (v8.1) — shadcn-admin inspired metric grid for employer dashboard.
 *
 * Mirrors the metric tiles on satnaing/shadcn-admin's Dashboard page:
 *   - 4-column responsive grid (1 on mobile → 4 on desktop)
 *   - Each tile: label, value, sub-trend (delta vs last period), small sparkline
 *   - Color-banded accents (indigo / emerald / amber / rose) so the recruiter
 *     can scan health at a glance
 *
 * Recruiter / HR data we're surfacing (v8.1 T3701-T3710):
 *   - Time-to-hire            (战略 → 招聘效率)
 *   - Cost-per-hire           (招聘预算)
 *   - Funnel conversion       (v8.1 T3710 命中率)
 *   - Open roles / critical fills
 */

import * as React from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Clock,
  DollarSign,
  Target,
  Briefcase,
  TrendingUp,
  TrendingDown,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";

export interface HRMetric {
  id: string;
  label: string;
  value: number | string;
  unit?: string;
  deltaPct?: number; // positive = good, negative = bad
  spark?: number[]; // 12-week sparkline data
  icon: "clock" | "dollar" | "target" | "briefcase" | "users";
  tone: "indigo" | "emerald" | "amber" | "rose" | "sky";
  helper?: string;
}

const ICON_MAP = {
  clock: Clock,
  dollar: DollarSign,
  target: Target,
  briefcase: Briefcase,
  users: Users,
} as const;

const TONE_CLASSES: Record<HRMetric["tone"], { rail: string; text: string; ring: string }> = {
  indigo: { rail: "bg-indigo-500", text: "text-indigo-700 dark:text-indigo-300", ring: "ring-indigo-200/60" },
  emerald: { rail: "bg-emerald-500", text: "text-emerald-700 dark:text-emerald-300", ring: "ring-emerald-200/60" },
  amber: { rail: "bg-amber-500", text: "text-amber-700 dark:text-amber-300", ring: "ring-amber-200/60" },
  rose: { rail: "bg-rose-500", text: "text-rose-700 dark:text-rose-300", ring: "ring-rose-200/60" },
  sky: { rail: "bg-sky-500", text: "text-sky-700 dark:text-sky-300", ring: "ring-sky-200/60" },
};

interface SparklineProps {
  points: number[];
  tone: HRMetric["tone"];
}
// Tiny inline SVG sparkline so we don't drag Recharts into the metric tile
function Sparkline({ points, tone }: SparklineProps) {
  const w = 80;
  const h = 24;
  const data = points.length ? points : [0];
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const stepX = w / Math.max(1, data.length - 1);
  const path = data
    .map((d, i) => {
      const x = i * stepX;
      const y = h - ((d - min) / span) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const stroke = {
    indigo: "#6366f1",
    emerald: "#10b981",
    amber: "#f59e0b",
    rose: "#f43f5e",
    sky: "#0ea5e9",
  }[tone];
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      width={w}
      height={h}
      className="overflow-visible"
      aria-hidden
    >
      <path
        d={path}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export interface HRMetricsProps {
  metrics?: HRMetric[];
  loading?: boolean;
}

const DEFAULT_METRICS: HRMetric[] = [
  {
    id: "time_to_hire",
    label: "平均到岗天数",
    value: 28,
    unit: "天",
    deltaPct: -12,
    icon: "clock",
    tone: "indigo",
    spark: [34, 32, 31, 33, 30, 29, 28, 27, 26, 28, 27, 28],
    helper: "较上季度缩短 12%",
  },
  {
    id: "cost_per_hire",
    label: "人均招聘成本",
    value: "¥4,200",
    deltaPct: -8,
    icon: "dollar",
    tone: "emerald",
    spark: [5200, 5000, 4800, 4700, 4600, 4500, 4400, 4300, 4250, 4250, 4200, 4200],
    helper: "ATS 同步节省 ¥600",
  },
  {
    id: "hit_rate",
    label: "推荐命中率",
    value: 64,
    unit: "%",
    deltaPct: 6,
    icon: "target",
    tone: "sky",
    spark: [48, 50, 52, 55, 53, 56, 58, 60, 61, 62, 63, 64],
    helper: "v8.1 T3710 反馈循环",
  },
  {
    id: "open_roles",
    label: "在招岗位",
    value: 12,
    icon: "briefcase",
    tone: "amber",
    spark: [10, 11, 12, 11, 13, 12, 12, 14, 13, 12, 12, 12],
    helper: "3 个 P0 / 9 个 P1",
  },
];

export function HRMetrics({ metrics, loading }: HRMetricsProps) {
  const items = metrics ?? DEFAULT_METRICS;
  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="p-4">
            <Skeleton className="h-4 w-24 mb-3" />
            <Skeleton className="h-8 w-16 mb-2" />
            <Skeleton className="h-3 w-32" />
          </Card>
        ))}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((m) => {
        const Icon = ICON_MAP[m.icon];
        const cls = TONE_CLASSES[m.tone];
        const positive = (m.deltaPct ?? 0) >= 0;
        return (
          <Card
            key={m.id}
            className={cn(
              "relative overflow-hidden p-4 transition-shadow hover:shadow-md",
              "ring-1 ring-inset",
              cls.ring,
            )}
          >
            <div className={cn("absolute left-0 top-0 h-full w-1", cls.rail)} />
            <div className="flex items-start justify-between">
              <div className="min-w-0 flex-1">
                <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  {m.label}
                </span>
                <div className="mt-2 flex items-baseline gap-1">
                  <span className="text-2xl font-bold tabular-nums tracking-tight">
                    {m.value}
                  </span>
                  {m.unit && (
                    <span className="text-sm text-muted-foreground">{m.unit}</span>
                  )}
                </div>
                {m.helper && (
                  <p className="mt-1 text-xs text-muted-foreground">{m.helper}</p>
                )}
              </div>
              <div className="flex flex-col items-end gap-2">
                <div className={cn("rounded-md p-1.5", cls.text, "bg-current/10")}>
                  <Icon className={cn("h-4 w-4", cls.text)} />
                </div>
                {m.spark && <Sparkline points={m.spark} tone={m.tone} />}
              </div>
            </div>
            {typeof m.deltaPct === "number" && (
              <div className="mt-3 flex items-center gap-1 text-xs">
                <Badge
                  variant={positive ? "secondary" : "destructive"}
                  className="gap-0.5 px-1.5 py-0"
                >
                  {positive ? (
                    <TrendingUp className="h-3 w-3" />
                  ) : (
                    <TrendingDown className="h-3 w-3" />
                  )}
                  {positive ? "+" : ""}
                  {m.deltaPct}%
                </Badge>
                <span className="text-muted-foreground">vs 上期</span>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
