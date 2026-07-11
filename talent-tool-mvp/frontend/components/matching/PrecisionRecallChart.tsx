"use client";

import * as React from "react";
import {
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export interface PrecisionRecallChartProps {
  history: Array<{
    recorded_at: string;
    precision: number;
    recall: number;
    f1: number;
  }>;
}

/**
 * Precision / Recall / F1 时间序列图.
 */
export function PrecisionRecallChart({ history }: PrecisionRecallChartProps) {
  const data = history.map((h) => ({
    date: h.recorded_at?.slice(0, 10) ?? "",
    precision: Number((h.precision * 100).toFixed(2)),
    recall: Number((h.recall * 100).toFixed(2)),
    f1: Number((h.f1 * 100).toFixed(2)),
  }));

  if (data.length === 0) {
    return (
      <div className="text-sm text-slate-400 italic p-6">
        暂无历史数据
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#64748b" />
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
        <Line
          type="monotone"
          dataKey="precision"
          stroke="#10b981"
          strokeWidth={2}
          dot={{ r: 3 }}
        />
        <Line
          type="monotone"
          dataKey="recall"
          stroke="#3b82f6"
          strokeWidth={2}
          dot={{ r: 3 }}
        />
        <Line
          type="monotone"
          dataKey="f1"
          stroke="#8b5cf6"
          strokeWidth={2}
          dot={{ r: 3 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}