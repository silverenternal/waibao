"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  ComposedChart,
  Legend,
} from "recharts";
import type { SalaryPoint } from "@/lib/api-market";

interface Props {
  data: SalaryPoint[];
  height?: number;
  currency?: string;
}

export function MarketSalaryChart({
  data,
  height = 280,
  currency = "CNY",
}: Props) {
  if (!data || data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm text-muted-foreground"
        style={{ height }}
      >
        暂无薪资数据
      </div>
    );
  }

  const unit = currency === "CNY" ? "k" : "k";

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart
        data={data}
        margin={{ top: 10, right: 24, bottom: 0, left: 0 }}
      >
        <defs>
          <linearGradient id="salaryFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
        <XAxis dataKey="period" tick={{ fontSize: 12 }} />
        <YAxis
          tick={{ fontSize: 12 }}
          tickFormatter={(v) => `${v}${unit}`}
          width={56}
        />
        <Tooltip
          formatter={(v) => [`${typeof v === "number" ? v : 0}${unit}`, ""]}
          labelStyle={{ color: "#475569" }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Area
          type="monotone"
          dataKey="p75_k"
          stroke="#a5b4fc"
          strokeDasharray="4 2"
          fill="none"
          name="P75"
        />
        <Area
          type="monotone"
          dataKey="p25_k"
          stroke="#a5b4fc"
          strokeDasharray="4 2"
          fill="none"
          name="P25"
        />
        <Line
          type="monotone"
          dataKey="median_k"
          stroke="#6366f1"
          strokeWidth={2.5}
          dot={{ r: 3 }}
          name="中位数"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export default MarketSalaryChart;