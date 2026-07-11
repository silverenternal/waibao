"use client";

import * as React from "react";
import {
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export interface BucketDistributionChartProps {
  distribution: Record<
    string,
    {
      count: number;
      placed_rate: number;
      rejected_rate: number;
      pending_rate?: number;
      avg_harmonic?: number;
    }
  >;
}

/**
 * 按 harmonic_score 分桶的转化率分布柱状图.
 */
export function BucketDistributionChart({
  distribution,
}: BucketDistributionChartProps) {
  const buckets = Object.keys(distribution).sort();
  const data = buckets.map((b) => ({
    bucket: b,
    placed: Number((distribution[b].placed_rate * 100).toFixed(1)),
    rejected: Number((distribution[b].rejected_rate * 100).toFixed(1)),
    pending: Number(((distribution[b].pending_rate ?? 0) * 100).toFixed(1)),
    count: distribution[b].count,
  }));

  if (data.length === 0) {
    return (
      <div className="text-sm text-slate-400 italic p-6">暂无桶数据</div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="bucket" tick={{ fontSize: 11 }} stroke="#64748b" />
        <YAxis
          domain={[0, 100]}
          tick={{ fontSize: 11 }}
          stroke="#64748b"
          tickFormatter={(v) => `${v}%`}
        />
        <Tooltip
          contentStyle={{ fontSize: 12 }}
          formatter={(v, k) => {
            const num = typeof v === "number" ? v : 0;
            return k === "count" ? num : `${num}%`;
          }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="placed" stackId="a" fill="#10b981" name="已入职" />
        <Bar dataKey="pending" stackId="a" fill="#94a3b8" name="进行中" />
        <Bar dataKey="rejected" stackId="a" fill="#ef4444" name="已拒绝" />
      </BarChart>
    </ResponsiveContainer>
  );
}