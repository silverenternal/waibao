"use client";

/**
 * T2301 — CompareRadar
 * 5 维度雷达图 (SVG),纯客户端渲染,无外部依赖.
 */

import { useMemo } from "react";
import { cn } from "@/lib/utils";

export interface RadarSeries {
  id: string;
  name: string;
  values: Record<string, number>; // dimension -> 0..100
  color?: string;
}

interface CompareRadarProps {
  series: RadarSeries[];
  dimensions: { key: string; label: string }[];
  size?: number;
  className?: string;
}

const PALETTE = [
  "#6366f1", // indigo
  "#f59e0b", // amber
  "#10b981", // emerald
  "#ef4444", // red
  "#3b82f6", // blue
];

export function CompareRadar({
  series,
  dimensions,
  size = 320,
  className,
}: CompareRadarProps) {
  const cx = size / 2;
  const cy = size / 2;
  const radius = size / 2 - 32;

  const angleStep = (Math.PI * 2) / Math.max(dimensions.length, 1);

  const pointFor = (dimIdx: number, value: number) => {
    const angle = -Math.PI / 2 + angleStep * dimIdx;
    const r = (Math.min(Math.max(value, 0), 100) / 100) * radius;
    return {
      x: cx + Math.cos(angle) * r,
      y: cy + Math.sin(angle) * r,
    };
  };

  const axisLabels = useMemo(() => {
    return dimensions.map((d, i) => {
      const angle = -Math.PI / 2 + angleStep * i;
      const labelR = radius + 16;
      return {
        x: cx + Math.cos(angle) * labelR,
        y: cy + Math.sin(angle) * labelR,
        label: d.label,
      };
    });
  }, [dimensions, radius, cx, cy, angleStep]);

  const gridLevels = [0.25, 0.5, 0.75, 1.0];

  return (
    <div className={cn("flex flex-col items-center gap-4", className)}>
      <svg width={size} height={size} role="img" aria-label="5 维度雷达图">
        {/* Grid */}
        {gridLevels.map((level) => (
          <polygon
            key={level}
            points={dimensions
              .map((_, i) => {
                const p = pointFor(i, level * 100);
                return `${p.x},${p.y}`;
              })
              .join(" ")}
            fill="none"
            stroke="#e5e7eb"
            strokeWidth={1}
          />
        ))}
        {/* Axes */}
        {dimensions.map((_, i) => {
          const p = pointFor(i, 100);
          return (
            <line
              key={i}
              x1={cx}
              y1={cy}
              x2={p.x}
              y2={p.y}
              stroke="#e5e7eb"
              strokeWidth={1}
            />
          );
        })}
        {/* Series polygons */}
        {series.map((s, sIdx) => {
          const color = s.color || PALETTE[sIdx % PALETTE.length];
          const points = dimensions
            .map((d, i) => {
              const v = s.values[d.key] ?? 0;
              const p = pointFor(i, v);
              return `${p.x},${p.y}`;
            })
            .join(" ");
          return (
            <g key={s.id}>
              <polygon
                points={points}
                fill={color}
                fillOpacity={0.18}
                stroke={color}
                strokeWidth={2}
              />
              {dimensions.map((d, i) => {
                const v = s.values[d.key] ?? 0;
                const p = pointFor(i, v);
                return (
                  <circle
                    key={d.key}
                    cx={p.x}
                    cy={p.y}
                    r={3}
                    fill={color}
                  />
                );
              })}
            </g>
          );
        })}
        {/* Axis labels */}
        {axisLabels.map((l, i) => (
          <text
            key={i}
            x={l.x}
            y={l.y}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={11}
            fill="#374151"
          >
            {l.label}
          </text>
        ))}
      </svg>
      {/* Legend */}
      <div className="flex flex-wrap gap-3 justify-center">
        {series.map((s, i) => (
          <div key={s.id} className="flex items-center gap-1.5 text-xs">
            <span
              className="inline-block w-3 h-3 rounded-sm"
              style={{ background: s.color || PALETTE[i % PALETTE.length] }}
            />
            <span>{s.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}