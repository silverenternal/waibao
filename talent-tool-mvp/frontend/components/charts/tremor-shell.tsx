"use client";

/**
 * Tremor-style analytics shell — adapted from @tremor/react Dashboard patterns.
 *
 * We don't pull @tremor/react (heavy Tailwind config, clashing with our shadcn
 * v4). Instead, we replicate the visual language: banded KPI cards on top,
 * area-chart panel + legend, and "ring + delta" delta indicator.
 *
 * Components:
 *   <TremorShell>          – page wrapper with title + filter toolbar
 *   <TremorKpiGrid>        – 4-up row of large KPI cards
 *   <TremorKpiCard>        – single KPI w/ delta + sparkline area
 *   <TremorDelta>          – green/red pill for change
 *   <TremorPanel>          – section panel (header + children)
 *
 * Used in:
 *   /mothership/analytics/funnel          (T1803 + v8.1 T3710)
 *   /mothership/analytics/channels        (T1804 channel ROI)
 *   /mothership/analytics/salary          (T2402 薪资分位)
 *   /mothership/analytics/predictive      (T2803 命中率预测)
 *   /mothership/analytics/bias-impact     (v8.1 T3704)
 */

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown } from "lucide-react";

type DeltaTone = "increase" | "decrease" | "neutral";

export interface TremorDeltaProps {
  delta: number; // percentage points, can be negative
  label?: string;
  tone?: DeltaTone; // explicit override (auto-derived if omitted)
  className?: string;
}

export function TremorDelta({ delta, label, tone, className }: TremorDeltaProps) {
  const auto: DeltaTone = delta > 0 ? "increase" : delta < 0 ? "decrease" : "neutral";
  const finalTone = tone ?? auto;
  const Icon = finalTone === "increase" ? TrendingUp : finalTone === "decrease" ? TrendingDown : null;
  const toneCls =
    finalTone === "increase"
      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 ring-emerald-200"
      : finalTone === "decrease"
      ? "bg-rose-500/15 text-rose-700 dark:text-rose-300 ring-rose-200"
      : "bg-muted text-muted-foreground ring-border";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset tabular-nums",
        toneCls,
        className,
      )}
      aria-label={label ?? `${delta > 0 ? "up" : "down"} ${Math.abs(delta)}%`}
    >
      {Icon && <Icon className="h-3 w-3" />}
      {delta > 0 ? "+" : ""}
      {delta.toFixed(1)}%
      {label && <span className="ml-0.5 text-foreground/70">{label}</span>}
    </span>
  );
}

export interface TremorKpiCardProps {
  title: string;
  value: string | number;
  unit?: string;
  delta?: number;
  helper?: string;
  spark?: number[];
  className?: string;
}

function sparkPath(pts: number[], w = 120, h = 36) {
  if (!pts.length) return "";
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = max - min || 1;
  const stepX = w / Math.max(1, pts.length - 1);
  return pts
    .map((d, i) => {
      const x = i * stepX;
      const y = h - ((d - min) / span) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function TremorKpiCard({ title, value, unit, delta, helper, spark, className }: TremorKpiCardProps) {
  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="pb-1">
        <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-end justify-between gap-2">
          <div>
            <div className="text-2xl font-bold tabular-nums leading-tight">
              {value}
              {unit && <span className="ml-0.5 text-base font-medium text-muted-foreground">{unit}</span>}
            </div>
            <div className="mt-2 flex items-center gap-2">
              {typeof delta === "number" && <TremorDelta delta={delta} />}
              {helper && <span className="text-xs text-muted-foreground">{helper}</span>}
            </div>
          </div>
          {spark && spark.length > 1 && (
            <svg viewBox="0 0 120 36" width={120} height={36} aria-hidden>
              <defs>
                <linearGradient id="tremorFill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="currentColor" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="currentColor" stopOpacity={0} />
                </linearGradient>
              </defs>
              <path d={sparkPath(spark) + ` L120,36 L0,36 Z`} fill="url(#tremorFill)" className="text-primary" />
              <path d={sparkPath(spark)} fill="none" stroke="currentColor" strokeWidth={1.5} className="text-primary" />
            </svg>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export interface TremorKpiGridProps {
  children: React.ReactNode;
  className?: string;
}
/** 4-column responsive grid mirroring Tremor `Grid` + `Card` defaults */
export function TremorKpiGrid({ children, className }: TremorKpiGridProps) {
  return (
    <div
      className={cn(
        "grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4",
        className,
      )}
    >
      {children}
    </div>
  );
}

export interface TremorPanelProps {
  title?: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function TremorPanel({ title, description, actions, children, className }: TremorPanelProps) {
  return (
    <Card className={className}>
      {(title || actions) && (
        <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
          <div>
            {title && <CardTitle>{title}</CardTitle>}
            {description && (
              <p className="mt-1 text-xs text-muted-foreground">{description}</p>
            )}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </CardHeader>
      )}
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export interface TremorShellProps {
  title: string;
  subtitle?: string;
  badge?: string;
  toolbar?: React.ReactNode;
  children: React.ReactNode;
}

export function TremorShell({ title, subtitle, badge, toolbar, children }: TremorShellProps) {
  return (
    <div className="space-y-6 p-4 md:p-8">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight md:text-3xl">{title}</h1>
            {badge && <Badge variant="secondary">{badge}</Badge>}
          </div>
          {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
        </div>
        {toolbar && <div className="flex flex-wrap items-center gap-2">{toolbar}</div>}
      </header>
      {children}
    </div>
  );
}
