"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SalaryDistribution } from "@/lib/api-salary";

export interface SalaryDistributionChartProps {
  distribution: SalaryDistribution | null;
  loading?: boolean;
}

/**
 * 薪资分布箱线图 (P10/P25/P50/P75/P90).
 */
export function SalaryDistributionChart({
  distribution,
  loading,
}: SalaryDistributionChartProps) {
  if (loading) {
    return (
      <Card>
        <CardContent className="p-6 text-slate-400 text-sm">加载中…</CardContent>
      </Card>
    );
  }
  if (!distribution) {
    return (
      <Card>
        <CardContent className="p-6 text-slate-500 text-sm">暂无数据</CardContent>
      </Card>
    );
  }

  const { p10_k, p25_k, p50_k, p75_k, p90_k, sample_size, currency } =
    distribution;
  const symbol = currency === "CNY" ? "¥" : currency === "USD" ? "$" : "";
  const min = p10_k;
  const max = p90_k;
  const span = Math.max(1, max - min);

  const toPct = (v: number) => ((v - min) / span) * 100;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          薪资分布 ({distribution.city} · {distribution.seniority})
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="text-xs text-slate-500">
          基于 {sample_size.toLocaleString()} 份样本 · {currency}
        </div>

        {/* 箱线图 (水平条) */}
        <div className="relative h-12 bg-slate-100 rounded">
          {/* P10-P90 whisker */}
          <div
            className="absolute top-1/2 -translate-y-1/2 h-1 bg-slate-300"
            style={{
              left: `${toPct(p10_k)}%`,
              width: `${toPct(p90_k) - toPct(p10_k)}%`,
            }}
          />
          {/* P25-P75 box */}
          <div
            className="absolute top-1/2 -translate-y-1/2 h-8 bg-amber-200 border border-amber-400 rounded"
            style={{
              left: `${toPct(p25_k)}%`,
              width: `${toPct(p75_k) - toPct(p25_k)}%`,
            }}
          />
          {/* P50 median */}
          <div
            className="absolute top-0 bottom-0 w-1 bg-amber-700"
            style={{ left: `${toPct(p50_k)}%` }}
          />
          {/* 端点 */}
          <div
            className="absolute top-1/2 -translate-y-1/2 w-1 h-6 bg-slate-500"
            style={{ left: `${toPct(p10_k)}%` }}
          />
          <div
            className="absolute top-1/2 -translate-y-1/2 w-1 h-6 bg-slate-500"
            style={{ left: `${toPct(p90_k)}%` }}
          />
        </div>

        {/* 标签行 */}
        <div className="grid grid-cols-5 gap-2 text-center text-xs">
          <div>
            <div className="text-slate-500">P10</div>
            <div className="font-medium">
              {symbol}
              {p10_k}k
            </div>
          </div>
          <div>
            <div className="text-slate-500">P25</div>
            <div className="font-medium">
              {symbol}
              {p25_k}k
            </div>
          </div>
          <div>
            <div className="text-amber-700 font-bold">P50 中位数</div>
            <div className="font-bold">
              {symbol}
              {p50_k}k
            </div>
          </div>
          <div>
            <div className="text-slate-500">P75</div>
            <div className="font-medium">
              {symbol}
              {p75_k}k
            </div>
          </div>
          <div>
            <div className="text-slate-500">P90</div>
            <div className="font-medium">
              {symbol}
              {p90_k}k
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}