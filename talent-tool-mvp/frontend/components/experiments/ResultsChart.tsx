/**
 * ResultsChart (T805): 柱状图展示 lift 与 p-value (轻量 SVG, 不依赖 chart 库).
 */
"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SignificanceIndicator } from "@/components/experiments/SignificanceIndicator";
import type { ResultsSummary, ResultsVariant } from "@/lib/api-ab";

interface ResultsChartProps {
  results: ResultsSummary;
  metricName?: string;
}

function liftColor(v: ResultsVariant): string {
  if (v.is_baseline) return "bg-slate-300";
  if (v.lift_vs_baseline > 0.05) return "bg-emerald-500";
  if (v.lift_vs_baseline < -0.05) return "bg-rose-500";
  return "bg-amber-400";
}

function liftDisplay(v: ResultsVariant): string {
  if (v.is_baseline) return "baseline";
  const sign = v.lift_vs_baseline > 0 ? "+" : "";
  return `${sign}${(v.lift_vs_baseline * 100).toFixed(1)}%`;
}

export function ResultsChart({ results, metricName }: ResultsChartProps) {
  const variants = results.variants;
  if (variants.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Results — {metricName || results.metric_name}</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground py-8 text-center">
          No samples recorded for this metric yet.
        </CardContent>
      </Card>
    );
  }

  // p-value 取最小非基线 variant 的
  const bestP = variants.reduce((m, v) => (v.is_baseline ? m : Math.min(m, v.p_value)), 1.0);
  const conf = 1 - bestP;
  const significant = conf >= 0.95;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle className="text-base">Results — {metricName || results.metric_name}</CardTitle>
        <SignificanceIndicator confidence={conf} pValue={bestP} significant={significant} />
      </CardHeader>
      <CardContent className="space-y-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-xs uppercase text-muted-foreground">
              <th className="text-left py-2">Variant</th>
              <th className="text-right">n</th>
              <th className="text-right">Mean</th>
              <th className="text-right">StdDev</th>
              <th className="text-right">Lift vs baseline</th>
              <th className="text-right">p-value</th>
            </tr>
          </thead>
          <tbody>
            {variants.map((v) => (
              <tr key={v.name} className="border-b last:border-0">
                <td className="py-2 font-medium">
                  {v.name}
                  {v.is_baseline && (
                    <span className="ml-2 text-[10px] uppercase tracking-wide text-muted-foreground">
                      baseline
                    </span>
                  )}
                </td>
                <td className="text-right font-mono">{v.n}</td>
                <td className="text-right font-mono">{v.mean.toFixed(4)}</td>
                <td className="text-right font-mono text-muted-foreground">
                  {v.stddev.toFixed(4)}
                </td>
                <td className="text-right">
                  <div className="flex items-center justify-end gap-2">
                    <span className="font-mono w-16 text-right">{liftDisplay(v)}</span>
                    {!v.is_baseline && (
                      <div className="h-2 w-24 rounded-full bg-muted overflow-hidden">
                        <div
                          className={`h-full ${liftColor(v)}`}
                          style={{
                            width: `${Math.min(100, Math.abs(v.lift_vs_baseline) * 100)}%`,
                          }}
                        />
                      </div>
                    )}
                  </div>
                </td>
                <td className="text-right font-mono text-muted-foreground">
                  {v.is_baseline ? "—" : v.p_value.toFixed(3)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-xs text-muted-foreground">
          Total samples: {results.n_total}. Welch&apos;s t-test (normal approx.).
        </p>
      </CardContent>
    </Card>
  );
}
