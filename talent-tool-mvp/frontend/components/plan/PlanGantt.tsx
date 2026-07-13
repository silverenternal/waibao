"use client";

/**
 * v8.1 T3606 — PlanGantt
 *
 * 简单 SVG 甘特图. 横轴时间, 纵轴任务. 显示 progress + 状态.
 */

import * as React from "react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface GanttTask {
  title: string;
  progress: number;
  completed: boolean;
  duration?: string;
  bucket: "short" | "mid" | "long";
  priority?: string;
}

export interface GanttMilestone {
  title: string;
  target_date: string;
  completed: boolean;
}

export interface PlanGanttProps {
  tasks: GanttTask[];
  milestones: GanttMilestone[];
  className?: string;
}

const ROW_HEIGHT = 28;
const PADDING = 12;

const BUCKET_LABEL = {
  short: "短期",
  mid: "中期",
  long: "长期",
} as const;

export function PlanGantt({ tasks, milestones, className }: PlanGanttProps) {
  if (tasks.length === 0 && milestones.length === 0) {
    return (
      <Card className={cn("p-6 text-center text-sm text-slate-500", className)}>
        暂无计划任务
      </Card>
    );
  }
  const rowCount = Math.max(1, tasks.length + milestones.length);
  const height = PADDING * 2 + rowCount * ROW_HEIGHT;
  const width = 600;
  return (
    <Card className={cn("p-4", className)}>
      <h3 className="text-sm font-semibold text-slate-800 mb-3">规划甘特图</h3>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        role="img"
        aria-label="plan gantt chart"
      >
        {/* tasks */}
        {tasks.map((t, idx) => {
          const y = PADDING + idx * ROW_HEIGHT;
          const barWidth = (width - PADDING * 2) * 0.7;
          const progressWidth = barWidth * Math.max(0, Math.min(1, t.progress));
          const color =
            t.priority === "high"
              ? "#ef4444"
              : t.completed
              ? "#10b981"
              : "#3b82f6";
          return (
            <g key={`task-${idx}`}>
              <text
                x={4}
                y={y + ROW_HEIGHT / 2 + 4}
                fontSize="10"
                fill="#475569"
              >
                {BUCKET_LABEL[t.bucket]} · {t.title}
              </text>
              <rect
                x={120}
                y={y + 4}
                width={barWidth}
                height={ROW_HEIGHT - 12}
                fill="#e2e8f0"
                rx={2}
              />
              <rect
                x={120}
                y={y + 4}
                width={progressWidth}
                height={ROW_HEIGHT - 12}
                fill={color}
                rx={2}
              />
              <text
                x={120 + barWidth + 6}
                y={y + ROW_HEIGHT / 2 + 4}
                fontSize="10"
                fill="#64748b"
              >
                {Math.round(t.progress * 100)}%
              </text>
            </g>
          );
        })}
        {/* milestones */}
        {milestones.map((m, idx) => {
          const y = PADDING + (tasks.length + idx) * ROW_HEIGHT;
          return (
            <g key={`ms-${idx}`}>
              <polygon
                points={`${width - 30},${y + 4} ${width - 18},${y + ROW_HEIGHT / 2} ${width - 30},${y + ROW_HEIGHT - 4} ${width - 42},${y + ROW_HEIGHT / 2}`}
                fill={m.completed ? "#10b981" : "#f59e0b"}
              />
              <text
                x={4}
                y={y + ROW_HEIGHT / 2 + 4}
                fontSize="10"
                fill="#475569"
              >
                🏁 {m.title} ({m.target_date})
              </text>
            </g>
          );
        })}
      </svg>
    </Card>
  );
}

export default PlanGantt;