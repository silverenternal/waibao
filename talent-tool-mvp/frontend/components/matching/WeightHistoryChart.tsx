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

export interface WeightHistoryChartProps {
  history: Array<{
    created_at?: string;
    weights: Record<string, number>;
  }>;
}

/**
 * 权重历史柱状图: 横轴=维度, 纵轴=权重值.
 */
export function WeightHistoryChart({ history }: WeightHistoryChartProps) {
  if (!history || history.length === 0) {
    return (
      <div className="text-sm text-slate-400 italic p-6">暂无历史记录</div>
    );
  }
  const dims = Array.from(
    new Set(history.flatMap((h) => Object.keys(h.weights || {})))
  );
  // 取最近 5 次
  const recent = history.slice(0, 5).reverse();

  const data = dims.map((d) => {
    const row: Record<string, string | number> = { dimension: d };
    for (const item of recent) {
      const key = item.created_at?.slice(0, 10) ?? "?";
      row[key] = Number(((item.weights?.[d] ?? 0) * 100).toFixed(2));
    }
    return row;
  });

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="dimension" tick={{ fontSize: 11 }} stroke="#64748b" />
        <YAxis
          domain={[0, 100]}
          tick={{ fontSize: 11 }}
          stroke="#64748b"
          tickFormatter={(v) => `${v}%`}
        />
        <Tooltip
          contentStyle={{ fontSize: 12 }}
          formatter={(v) => `${typeof v === "number" ? v : 0}%`}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {recent.map((item, i) => (
          <Bar
            key={item.created_at ?? i}
            dataKey={item.created_at?.slice(0, 10) ?? `r${i}`}
            fill={["#10b981", "#3b82f6", "#8b5cf6", "#f59e0b", "#ef4444"][i % 5]}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}