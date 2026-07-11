"use client";

/**
 * StakeholderMatrix (T602)
 *
 * Three-dimensional matrix card used by the employer talent-image page.
 * Each row = one persona (boss / HR / dept-head / admin) and the visual
 * is an x/y scatter position derived from:
 *
 *   x  →  "alignment with consensus" (0..100)
 *   y  →  "content weight"           (0..100, falls back to 50 when empty)
 *
 * Below the plot, a legend summarises each persona + a tiny alignment bar.
 * Designed responsive — the plot itself is fixed-aspect (square) on
 * desktop and shrinks on mobile.
 */

import * as React from "react";
import {
  Briefcase,
  Building2,
  Users as UsersIcon,
  ClipboardList,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

import type { StakeholderStance, StakeholderRole } from "@/lib/api-clarification";

export interface StakeholderMatrixProps {
  stances: StakeholderStance[];
  /** Override Y coordinate (content weight) — defaults to alignment. */
  weightsByRole?: Partial<Record<StakeholderRole, number>>;
  className?: string;
}

const ROLE_META: Record<
  StakeholderRole,
  {
    label: string;
    color: string;
    /** Solid hex used inside the SVG `<circle>` fills. */
    fill: string;
    icon: React.ComponentType<{ className?: string }>;
  }
> = {
  boss: {
    label: "老板",
    color: "bg-indigo-100 text-indigo-700 border-indigo-200",
    fill: "#6366f1",
    icon: Building2,
  },
  hr: {
    label: "HR",
    color: "bg-sky-100 text-sky-700 border-sky-200",
    fill: "#0ea5e9",
    icon: Briefcase,
  },
  dept_head: {
    label: "部门负责人",
    color: "bg-emerald-100 text-emerald-700 border-emerald-200",
    fill: "#10b981",
    icon: UsersIcon,
  },
  admin: {
    label: "行政",
    color: "bg-slate-100 text-slate-700 border-slate-200",
    fill: "#64748b",
    icon: ClipboardList,
  },
};

const PLOT_SIZE = 320;
const PADDING = 32;

export function StakeholderMatrix({
  stances,
  weightsByRole,
  className,
}: StakeholderMatrixProps) {
  // Defaults: include all 4 roles so the legend doesn't shrink when some stances are missing.
  const visible: StakeholderStance[] = React.useMemo(() => {
    const map = new Map<StakeholderRole, StakeholderStance>();
    for (const s of stances) map.set(s.role, s);
    return (["boss", "hr", "dept_head", "admin"] as StakeholderRole[]).map(
      (r) =>
        map.get(r) ?? {
          role: r,
          alignment: 30,
          summary: "未提交",
        },
    );
  }, [stances]);

  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">多方共识矩阵</CardTitle>
        <p className="text-[11px] text-slate-500">
          X 轴 = 与共识一致度 · Y 轴 = 提交内容权重 · 圆点越大=影响力越强
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex justify-center lg:justify-start">
          <svg
            role="img"
            aria-label="多方共识矩阵"
            viewBox={`0 0 ${PLOT_SIZE} ${PLOT_SIZE}`}
            width="100%"
            style={{ maxWidth: PLOT_SIZE }}
            className="h-auto"
          >
            <defs>
              <linearGradient id="matrix-bg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#eef2ff" />
                <stop offset="100%" stopColor="#f8fafc" />
              </linearGradient>
            </defs>

            {/* Background */}
            <rect
              x={PADDING}
              y={PADDING}
              width={PLOT_SIZE - PADDING * 2}
              height={PLOT_SIZE - PADDING * 2}
              fill="url(#matrix-bg)"
              stroke="#e2e8f0"
              rx={8}
            />

            {/* Vertical grid (x = alignment) */}
            {[25, 50, 75].map((t) => (
              <line
                key={`x-${t}`}
                x1={xFor(t)}
                y1={PADDING}
                x2={xFor(t)}
                y2={PLOT_SIZE - PADDING}
                stroke="#cbd5e1"
                strokeDasharray="3 3"
                strokeWidth={1}
              />
            ))}
            {/* Horizontal grid (y = weight) */}
            {[25, 50, 75].map((t) => (
              <line
                key={`y-${t}`}
                x1={PADDING}
                y1={yFor(t)}
                x2={PLOT_SIZE - PADDING}
                y2={yFor(t)}
                stroke="#cbd5e1"
                strokeDasharray="3 3"
                strokeWidth={1}
              />
            ))}

            {/* Axes labels */}
            <text
              x={PADDING}
              y={PLOT_SIZE - 8}
              fontSize={10}
              fill="#64748b"
            >
              0
            </text>
            <text
              x={PLOT_SIZE - PADDING - 8}
              y={PLOT_SIZE - 8}
              fontSize={10}
              fill="#64748b"
              textAnchor="end"
            >
              100 一致
            </text>
            <text
              x={6}
              y={PADDING + 10}
              fontSize={10}
              fill="#64748b"
            >
              强
            </text>
            <text
              x={6}
              y={PLOT_SIZE - PADDING - 4}
              fontSize={10}
              fill="#64748b"
            >
              弱
            </text>

            {/* Dots */}
            {visible.map((s, idx) => {
              const w = weightsByRole?.[s.role] ?? s.alignment ?? 50;
              const cx = xFor(s.alignment);
              const cy = yFor(w);
              const meta = ROLE_META[s.role];
              const radius = 8 + Math.min(8, Math.max(0, s.alignment / 25));
              return (
                <g key={s.role}>
                  <circle
                    cx={cx}
                    cy={cy}
                    r={radius}
                    fill={meta.fill}
                    fillOpacity={0.25}
                  />
                  <circle
                    cx={cx}
                    cy={cy}
                    r={Math.max(4, radius - 3)}
                    fill={meta.fill}
                  />
                  <text
                    x={cx + radius + 4}
                    y={cy + 4}
                    fontSize={11}
                    fill="#1f2937"
                  >
                    {meta.label}
                  </text>
                  <text
                    x={cx + radius + 4}
                    y={cy + 16}
                    fontSize={9}
                    fill="#64748b"
                  >
                    对齐 {Math.round(s.alignment)}%
                  </text>
                  {idx === 0 && (
                    <text
                      x={xFor(50)}
                      y={yFor(50) - 8}
                      fontSize={9}
                      textAnchor="middle"
                      fill="#94a3b8"
                    >
                      中位区
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        </div>

        {/* Legend / breakdown bars */}
        <ul className="grid gap-2 sm:grid-cols-2">
          {visible.map((s) => {
            const meta = ROLE_META[s.role];
            const Icon = meta.icon;
            return (
              <li
                key={s.role}
                className={cn(
                  "flex items-start gap-3 rounded-lg border bg-white p-3",
                  meta.color,
                )}
              >
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-white shadow-sm ring-1 ring-black/5">
                  <Icon className="size-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">{meta.label}</span>
                    <Badge
                      variant="outline"
                      className="ml-auto border-white/40 bg-white/70 text-[10px]"
                    >
                      {Math.round(s.alignment)}% 一致
                    </Badge>
                  </div>
                  <div className="mt-1 h-1.5 w-full rounded-full bg-white/70 shadow-inner">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.min(100, Math.max(0, s.alignment))}%`,
                        backgroundColor: meta.fill,
                      }}
                    />
                  </div>
                  {s.summary && (
                    <p className="mt-1 line-clamp-2 text-[11px] text-slate-700">
                      {s.summary}
                    </p>
                  )}
                  {s.emphasis && s.emphasis.length > 0 && (
                    <p className="mt-1 text-[10px] text-slate-600">
                      重点:{s.emphasis.join("、")}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Coordinates (SVG helpers)
// ---------------------------------------------------------------------------

function xFor(pct: number): number {
  return PADDING + ((PLOT_SIZE - PADDING * 2) * clamp(pct)) / 100;
}
function yFor(pct: number): number {
  return PADDING + (PLOT_SIZE - PADDING * 2) * (1 - clamp(pct) / 100);
}
function clamp(v: number): number {
  if (Number.isNaN(v)) return 0;
  return Math.max(0, Math.min(100, v));
}
