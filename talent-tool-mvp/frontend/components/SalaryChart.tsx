"use client";

/**
 * SalaryChart — 薪资分位图 (T1302).
 *
 * Props:
 *   - band: [p10, p25, p50, p75, p90]
 *   - yourValue: 当前 offer 在 band 单位下的数值
 *   - unit: 显示单位 (USD/CNY/SGD)
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Cell,
} from "recharts";

const DEFAULT_DATA = [
  { name: "p10", value: 25, color: "#94a3b8" },
  { name: "p25", value: 35, color: "#64748b" },
  { name: "p50", value: 50, color: "#0ea5e9" },
  { name: "p75", value: 70, color: "#6366f1" },
  { name: "p90", value: 100, color: "#a855f7" },
];

const PALETTE: Record<string, string> = {
  p10: "#cbd5e1",
  p25: "#94a3b8",
  p50: "#0ea5e9",
  p75: "#6366f1",
  p90: "#a855f7",
};

export function SalaryChart({
  band,
  yourValue,
  unit = "k$",
}: {
  band: number[];
  yourValue?: number;
  unit?: string;
}) {
  const data = DEFAULT_DATA.map((d, idx) => ({
    ...d,
    name: d.name,
    value: band[idx] ?? d.value,
    color: PALETTE[d.name],
  }));
  return (
    <div className="border rounded-2xl bg-white p-5 shadow-sm" data-testid="salary-chart">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-base font-semibold text-slate-800">市场分位</h3>
        <div className="text-xs text-slate-500">单位:{unit}</div>
      </div>
      <div className="h-56 w-full">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 24, right: 12, bottom: 8, left: 4 }}>
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip
              formatter={(v) => `${Number(v) || 0} ${unit}`}
              contentStyle={{
                borderRadius: 8,
                border: "1px solid #e2e8f0",
                fontSize: 12,
              }}
            />
            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
              {data.map((d) => (
                <Cell key={d.name} fill={d.color} />
              ))}
            </Bar>
            {yourValue !== undefined && (
              <ReferenceLine
                y={yourValue}
                stroke="#ef4444"
                strokeDasharray="4 4"
                label={{
                  value: `你 ${Math.round(yourValue)} ${unit}`,
                  position: "insideTopRight",
                  fontSize: 11,
                  fill: "#ef4444",
                }}
              />
            )}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default SalaryChart;
