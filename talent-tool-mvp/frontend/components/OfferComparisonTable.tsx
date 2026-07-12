"use client";

/**
 * OfferComparisonTable — 雷达图 + 表格对比 (T1302).
 *
 * Props:
 *   - offers: AnnualTotal[]
 *   - titles: string[]                // 每个 offer 名字
 *   - radar: { base, net_monthly, equity_pv, benefits, total_comp } -> numbers[] per offer
 *
 * 设计:
 *   - 用 recharts RadarChart
 *   - 颜色按顺序映射(蓝/绿/紫/橙/...)
 */

import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Legend,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

interface OfferComparisonTableProps {
  titles: string[];
  radar: {
    base: number[];
    net_monthly: number[];
    equity_pv: number[];
    benefits: number[];
    total_comp: number[];
  };
}

const COLORS = ["#0ea5e9", "#10b981", "#a855f7", "#f97316", "#e11d48"];

export function OfferComparisonTable({ titles, radar }: OfferComparisonTableProps) {
  // 转化成 radar charts 数据:一行 = 一个维度,列 = offer
  const dims = Object.keys(radar);
  const data = dims.map((dim) => {
    const row: Record<string, any> = { dim: prettyDim(dim) };
    titles.forEach((t, idx) => {
      row[t] = radar[dim as keyof typeof radar][idx] || 0;
    });
    return row;
  });

  return (
    <div className="space-y-4" data-testid="offer-radar">
      <div className="h-80 w-full">
        <ResponsiveContainer>
          <RadarChart data={data}>
            <PolarGrid strokeDasharray="3 3" />
            <PolarAngleAxis dataKey="dim" tick={{ fontSize: 12 }} />
            <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
            {titles.map((t, idx) => (
              <Radar
                key={t}
                name={t}
                dataKey={t}
                stroke={COLORS[idx % COLORS.length]}
                fill={COLORS[idx % COLORS.length]}
                fillOpacity={0.18}
              />
            ))}
            <Legend />
            <Tooltip />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="text-left p-2 bg-slate-50">维度</th>
              {titles.map((t, idx) => (
                <th
                  key={t}
                  className="text-right p-2 bg-slate-50"
                  style={{ color: COLORS[idx % COLORS.length] }}
                >
                  {t}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dims.map((dim) => (
              <tr key={dim} className="border-b border-slate-100">
                <td className="p-2 font-medium text-slate-700">{prettyDim(dim)}</td>
                {titles.map((_, idx) => (
                  <td key={idx} className="text-right p-2 tabular-nums text-slate-700">
                    {(radar[dim as keyof typeof radar][idx] || 0).toFixed(1)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function prettyDim(d: string) {
  return {
    base: "Base",
    net_monthly: "月到手",
    equity_pv: "股权年化",
    benefits: "福利",
    total_comp: "总包",
  }[d] || d;
}

export default OfferComparisonTable;
