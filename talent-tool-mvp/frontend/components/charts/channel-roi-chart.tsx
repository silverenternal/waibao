"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";
import type { ChannelAttribution } from "@/lib/types";

interface ChannelRoiChartProps {
  channels: ChannelAttribution[];
  className?: string;
}

/** 柱状(ROI) + 折线(cost_per_hire) — 用纯 SVG 渲染,避免引入图表库. */
export function ChannelRoiChart({ channels, className }: ChannelRoiChartProps) {
  const data = useMemo(() => {
    if (channels.length === 0) return null;
    const maxRoi = Math.max(0.1, ...channels.map((c) => Math.abs(c.roi)));
    const maxCph = Math.max(
      1,
      ...channels.map((c) => (c.cost_per_hire > 0 ? c.cost_per_hire : 0)),
    );
    return { maxRoi, maxCph };
  }, [channels]);

  if (!data || channels.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-8 text-center">
        No channel attribution data in the selected period.
      </p>
    );
  }

  const w = 100; // viewBox width %
  const h = 220;
  const barW = (w - 8) / channels.length;
  const padX = 4;

  return (
    <div className={cn("w-full", className)}>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        className="w-full"
        style={{ height: `${h}px` }}
      >
        {/* baseline */}
        <line
          x1="0"
          y1={h - 20}
          x2={w}
          y2={h - 20}
          stroke="#e2e8f0"
          strokeWidth="0.2"
        />
        {/* bars (ROI) */}
        {channels.map((c, i) => {
          const ratio = c.roi > 0 ? c.roi / data.maxRoi : 0;
          const barH = ratio * (h - 40);
          const x = padX + i * barW + barW * 0.15;
          const bw = barW * 0.7;
          const y = h - 20 - barH;
          const fill = c.roi >= 1 ? "#10b981" : c.roi >= 0 ? "#3b82f6" : "#ef4444";
          return (
            <g key={c.channel}>
              <rect
                x={x}
                y={y}
                width={bw}
                height={Math.max(0.5, barH)}
                fill={fill}
                rx="0.4"
              />
              <text
                x={x + bw / 2}
                y={y - 1}
                textAnchor="middle"
                fontSize="3"
                fill="#0f172a"
              >
                {c.roi.toFixed(2)}
              </text>
              <text
                x={x + bw / 2}
                y={h - 14}
                textAnchor="middle"
                fontSize="3"
                fill="#475569"
              >
                {c.channel.slice(0, 10)}
              </text>
            </g>
          );
        })}
        {/* cph line */}
        <polyline
          points={channels
            .map((c, i) => {
              const x = padX + i * barW + barW / 2;
              const v = c.cost_per_hire > 0 ? c.cost_per_hire / data.maxCph : 0;
              const y = h - 20 - v * (h - 40);
              return `${x},${y}`;
            })
            .join(" ")}
          fill="none"
          stroke="#f59e0b"
          strokeWidth="0.5"
        />
        {channels.map((c, i) => {
          const x = padX + i * barW + barW / 2;
          const v = c.cost_per_hire > 0 ? c.cost_per_hire / data.maxCph : 0;
          const y = h - 20 - v * (h - 40);
          return (
            <circle key={c.channel} cx={x} cy={y} r="0.9" fill="#f59e0b" />
          );
        })}
      </svg>

      {/* legend */}
      <div className="flex items-center gap-4 text-xs text-muted-foreground mt-2">
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 bg-emerald-500 rounded-sm" /> ROI ≥ 1
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 bg-blue-500 rounded-sm" /> ROI 0~1
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 bg-red-500 rounded-sm" /> ROI &lt; 0
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-0.5 bg-amber-500" /> cost/hire
        </span>
      </div>
    </div>
  );
}