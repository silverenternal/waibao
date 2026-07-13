"use client";

/**
 * v9.1 — EmotionDistribution
 *
 * 纯 SVG 实现的情绪分布组件:
 *  - 左: 主情绪环形分布(同心环,扇形按频次切分)
 *  - 右: 强度直方图(0-25 / 25-50 / 50-75 / 75-100)
 *
 * 不引入额外依赖,沿用 emotion-timeline-chart 的色板与温和风格.
 */

import * as React from "react";

import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";

export interface EmotionDistributionProps {
  points: Array<{
    primary_emotion?: string | null;
    intensity?: number | null;
  }>;
  className?: string;
}

const PALETTE = [
  "#6366f1", // indigo
  "#f97316", // orange
  "#10b981", // emerald
  "#ec4899", // pink
  "#0ea5e9", // sky
  "#f59e0b", // amber
  "#8b5cf6", // violet
  "#14b8a6", // teal
  "#ef4444", // rose
  "#64748b", // slate
];

interface BucketRow {
  label: string;
  count: number;
  range: [number, number];
}

const BUCKETS: BucketRow[] = [
  { label: "微风", count: 0, range: [0, 25] },
  { label: "微波", count: 0, range: [25, 50] },
  { label: "涌动", count: 0, range: [50, 75] },
  { label: "浪潮", count: 0, range: [75, 100] },
];

function safeEmotion(s: string | null | undefined): string {
  if (!s) return "未标记";
  return s.length > 10 ? `${s.slice(0, 9)}…` : s;
}

export function EmotionDistribution({ points, className }: EmotionDistributionProps) {
  const { donut, total } = React.useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of points) {
      const key = safeEmotion(p.primary_emotion ?? null);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    const total = points.length;
    const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    const top = sorted.slice(0, 8);
    const others = sorted.slice(8).reduce((a, [, v]) => a + v, 0);
    if (others > 0) top.push(["其他", others]);
    return { donut: top, total };
  }, [points]);

  const buckets = React.useMemo(() => {
    const map = new Map(BUCKETS.map((b) => [b.label, { ...b }]));
    for (const p of points) {
      if (p.intensity == null) continue;
      const pct = Math.max(0, Math.min(100, Math.round(p.intensity * 100)));
      for (const b of BUCKETS) {
        if (pct >= b.range[0] && (pct < b.range[1] || (pct === 100 && b.range[1] === 100))) {
          const row = map.get(b.label)!;
          row.count += 1;
          break;
        }
      }
    }
    return [...map.values()];
  }, [points]);

  if (total === 0) {
    return (
      <Card className={cn("border-dashed", className)}>
        <CardContent className="flex items-center gap-2 py-10 text-xs text-slate-500">
          暂无情绪数据 — 检测或记录后将自动生成分布。
        </CardContent>
      </Card>
    );
  }

  const cx = 110;
  const cy = 110;
  const outer = 100;
  const inner = 60;

  // 预计算扇形角度
  const slices: Array<{ start: number; end: number; color: string; label: string; count: number }> = [];
  let cursor = -Math.PI / 2;
  for (let i = 0; i < donut.length; i++) {
    const [label, count] = donut[i];
    const angle = (count / total) * Math.PI * 2;
    slices.push({
      start: cursor,
      end: cursor + angle,
      color: PALETTE[i % PALETTE.length],
      label,
      count,
    });
    cursor += angle;
  }

  return (
    <div className={cn("grid gap-6 lg:grid-cols-2", className)}>
      {/* Donut */}
      <Card>
        <CardContent>
          <header className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-800">主情绪频次</h3>
            <span className="text-xs text-muted-foreground">共 {total} 条记录</span>
          </header>
          <div className="flex flex-col items-center gap-4 sm:flex-row">
            <svg viewBox="0 0 220 220" width={220} height={220} aria-label="emotion donut">
              <circle cx={cx} cy={cy} r={outer} fill="#f8fafc" />
              {slices.map((s, i) => {
                const path = donutSlice(cx, cy, inner, outer, s.start, s.end);
                return (
                  <path
                    key={i}
                    d={path}
                    fill={s.color}
                    opacity={0.92}
                  />
                );
              })}
              <circle cx={cx} cy={cy} r={inner - 2} fill="white" />
              <text
                x={cx}
                y={cy - 4}
                textAnchor="middle"
                fontSize="22"
                fontWeight="600"
                fill="#0f172a"
              >
                {total}
              </text>
              <text
                x={cx}
                y={cy + 14}
                textAnchor="middle"
                fontSize="11"
                fill="#64748b"
              >
                总样本
              </text>
            </svg>
            <ul className="flex-1 space-y-1.5 text-xs">
              {slices.map((s, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span
                    className="inline-block size-2.5 rounded-sm"
                    style={{ background: s.color }}
                  />
                  <span className="flex-1 truncate text-slate-700">{s.label}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {s.count} · {((s.count / total) * 100).toFixed(0)}%
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </CardContent>
      </Card>

      {/* Intensity histogram */}
      <Card>
        <CardContent>
          <header className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-800">强度分布</h3>
            <span className="text-xs text-muted-foreground">
              缺失 {points.filter((p) => p.intensity == null).length} 条
            </span>
          </header>
          <IntensityHistogram buckets={buckets} />
          <ul className="mt-4 grid grid-cols-4 gap-2 text-center text-[11px] text-muted-foreground">
            {buckets.map((b) => (
              <li key={b.label}>
                <span className="block text-sm font-semibold text-slate-800 tabular-nums">
                  {b.count}
                </span>
                <span>{b.label}</span>
                <span className="block text-[10px]">
                  {b.range[0]}–{b.range[1]}%
                </span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-blocks
// ---------------------------------------------------------------------------

function IntensityHistogram({ buckets }: { buckets: BucketRow[] }) {
  const max = Math.max(1, ...buckets.map((b) => b.count));
  const w = 320;
  const h = 160;
  const padding = 12;
  const innerW = w - padding * 2;
  const innerH = h - padding * 2;
  const barW = innerW / buckets.length - 8;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full" aria-label="intensity histogram">
      <defs>
        <linearGradient id="intensityFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#6366f1" stopOpacity={0.85} />
          <stop offset="100%" stopColor="#a5b4fc" stopOpacity={0.4} />
        </linearGradient>
      </defs>
      {/* baseline */}
      <line
        x1={padding}
        y1={h - padding}
        x2={w - padding}
        y2={h - padding}
        stroke="#e2e8f0"
      />
      {/* dashed mid grid */}
      <line
        x1={padding}
        y1={padding + innerH / 2}
        x2={w - padding}
        y2={padding + innerH / 2}
        stroke="#eef2f7"
        strokeDasharray="3 3"
      />
      {buckets.map((b, i) => {
        const x = padding + i * (innerW / buckets.length) + 4;
        const ratio = b.count / max;
        const barH = Math.max(2, ratio * (innerH - 8));
        const y = h - padding - barH;
        return (
          <g key={b.label}>
            <rect
              x={x}
              y={y}
              width={barW}
              height={barH}
              rx={3}
              fill="url(#intensityFill)"
            />
            <text
              x={x + barW / 2}
              y={y - 4}
              textAnchor="middle"
              fontSize="10"
              fill="#475569"
              className="tabular-nums"
            >
              {b.count}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function donutSlice(
  cx: number,
  cy: number,
  rInner: number,
  rOuter: number,
  startAngle: number,
  endAngle: number,
): string {
  // 处理整圆
  if (endAngle - startAngle >= Math.PI * 2 - 1e-6) {
    return [
      `M ${cx + rOuter} ${cy}`,
      `A ${rOuter} ${rOuter} 0 1 1 ${cx - rOuter} ${cy}`,
      `A ${rOuter} ${rOuter} 0 1 1 ${cx + rOuter} ${cy}`,
      `M ${cx + rInner} ${cy}`,
      `A ${rInner} ${rInner} 0 1 0 ${cx - rInner} ${cy}`,
      `A ${rInner} ${rInner} 0 1 0 ${cx + rInner} ${cy}`,
      "Z",
    ].join(" ");
  }
  const x0 = cx + rOuter * Math.cos(startAngle);
  const y0 = cy + rOuter * Math.sin(startAngle);
  const x1 = cx + rOuter * Math.cos(endAngle);
  const y1 = cy + rOuter * Math.sin(endAngle);
  const x2 = cx + rInner * Math.cos(endAngle);
  const y2 = cy + rInner * Math.sin(endAngle);
  const x3 = cx + rInner * Math.cos(startAngle);
  const y3 = cy + rInner * Math.sin(startAngle);
  const largeArc = endAngle - startAngle > Math.PI ? 1 : 0;
  return [
    `M ${x0} ${y0}`,
    `A ${rOuter} ${rOuter} 0 ${largeArc} 1 ${x1} ${y1}`,
    `L ${x2} ${y2}`,
    `A ${rInner} ${rInner} 0 ${largeArc} 0 ${x3} ${y3}`,
    "Z",
  ].join(" ");
}

export default EmotionDistribution;