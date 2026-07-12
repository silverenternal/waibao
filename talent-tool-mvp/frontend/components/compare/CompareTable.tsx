"use client";

/**
 * T2301 — CompareTable
 * 详细对比表 (5 维度 × N 项),支持差异高亮 + 整体评分列.
 */

import { useMemo } from "react";
import { cn } from "@/lib/utils";

export interface CompareItem {
  id: string;
  name: string;
  type: "candidate" | "role";
  dimensions: Record<string, { dimension: string; label: string; score: number }>;
  attributes?: Record<string, unknown>;
  overall_score?: number;
}

export interface CompareDimension {
  dimension: string;
  label: string;
  spread: number;
  stddev: number;
  values: number[];
  items: string[];
  rank: number;
}

interface CompareTableProps {
  items: CompareItem[];
  dimensions: CompareDimension[];
  highlightThreshold?: number; // spread ≥ threshold 视为高亮
  className?: string;
}

export function CompareTable({
  items,
  dimensions,
  highlightThreshold = 15,
  className,
}: CompareTableProps) {
  const dimByKey = useMemo(() => {
    const m: Record<string, CompareDimension> = {};
    for (const d of dimensions) m[d.dimension] = d;
    return m;
  }, [dimensions]);

  const maxSpread = useMemo(
    () => Math.max(...dimensions.map((d) => d.spread), 1),
    [dimensions]
  );

  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className="min-w-full text-sm border-collapse">
        <thead>
          <tr className="border-b">
            <th className="text-left p-3 font-medium sticky left-0 bg-background z-10">
              维度
            </th>
            {items.map((it) => (
              <th key={it.id} className="text-center p-3 font-medium min-w-[120px]">
                <div className="flex flex-col gap-0.5">
                  <span>{it.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {it.type === "candidate" ? "候选人" : "岗位"}
                  </span>
                </div>
              </th>
            ))}
            <th className="text-center p-3 font-medium w-28">差异</th>
          </tr>
        </thead>
        <tbody>
          {/* Overall row */}
          <tr className="border-b bg-muted/30">
            <td className="p-3 font-medium sticky left-0 bg-muted/30">综合分</td>
            {items.map((it) => (
              <td key={it.id} className="text-center p-3 font-semibold">
                {(it.overall_score ?? 0).toFixed(1)}
              </td>
            ))}
            <td className="text-center p-3">—</td>
          </tr>
          {/* Dimensions */}
          {dimensions.map((d) => {
            const isHot = d.spread >= highlightThreshold;
            return (
              <tr
                key={d.dimension}
                className={cn(
                  "border-b transition-colors",
                  isHot && "bg-amber-50 dark:bg-amber-950/20"
                )}
              >
                <td className="p-3 font-medium sticky left-0 bg-inherit">
                  <div className="flex items-center gap-2">
                    <span>{d.label}</span>
                    {isHot && (
                      <span
                        className="text-xs px-1.5 py-0.5 rounded bg-amber-200 dark:bg-amber-800 text-amber-900 dark:text-amber-100"
                        title={`差异 ${d.spread.toFixed(1)} 分`}
                      >
                        高差异
                      </span>
                    )}
                  </div>
                </td>
                {items.map((it, i) => {
                  const score = d.values[i] ?? 0;
                  return (
                    <td key={it.id} className="text-center p-3">
                      <ScoreCell score={score} max={100} />
                    </td>
                  );
                })}
                <td className="text-center p-3">
                  <div className="flex flex-col items-center gap-1">
                    <span className="font-semibold">{d.spread.toFixed(1)}</span>
                    <SpreadBar
                      spread={d.spread}
                      max={maxSpread}
                      className="w-16 h-1.5"
                    />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ScoreCell({ score, max }: { score: number; max: number }) {
  const pct = Math.min((score / max) * 100, 100);
  const tone =
    score >= 80
      ? "text-emerald-600"
      : score >= 60
      ? "text-blue-600"
      : score >= 40
      ? "text-amber-600"
      : "text-red-500";
  return (
    <div className="flex flex-col items-center gap-1">
      <span className={cn("font-semibold", tone)}>{score.toFixed(1)}</span>
      <div className="w-16 h-1.5 bg-muted rounded">
        <div
          className={cn(
            "h-full rounded transition-all",
            score >= 80
              ? "bg-emerald-500"
              : score >= 60
              ? "bg-blue-500"
              : score >= 40
              ? "bg-amber-500"
              : "bg-red-500"
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function SpreadBar({
  spread,
  max,
  className,
}: {
  spread: number;
  max: number;
  className?: string;
}) {
  const pct = max > 0 ? Math.min((spread / max) * 100, 100) : 0;
  return (
    <div
      className={cn("bg-muted rounded overflow-hidden", className)}
      role="progressbar"
      aria-valuenow={Math.round(pct)}
    >
      <div
        className="h-full bg-amber-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}