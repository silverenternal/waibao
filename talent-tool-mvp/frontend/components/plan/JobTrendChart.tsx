"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

interface TrendRow {
  period: string;
  job_count: number;
  median_k?: number;
}

interface Props {
  data: TrendRow[];
  height?: number;
  metric?: "job_count" | "median_k";
}

export function JobTrendChart({
  data,
  height = 260,
  metric = "job_count",
}: Props) {
  if (!data || data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm text-muted-foreground"
        style={{ height }}
      >
        暂无趋势数据
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 10, right: 24, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
        <XAxis dataKey="period" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} width={56} />
        <Tooltip
          formatter={(v) => {
            const num = typeof v === "number" ? v : Number(v ?? 0);
            return metric === "median_k" ? [`${num}k`, "中位薪资"] : [num, "岗位数"];
          }}
        />
        <Bar dataKey={metric} radius={[6, 6, 0, 0]}>
          {data.map((row, idx) => (
            <Cell
              key={idx}
              fill={
                row.job_count > 1000
                  ? "#10b981"
                  : row.job_count > 500
                    ? "#6366f1"
                    : "#94a3b8"
              }
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export default JobTrendChart;