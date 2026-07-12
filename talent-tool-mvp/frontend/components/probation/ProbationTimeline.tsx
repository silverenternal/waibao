"use client";

import * as React from "react";
import type { ProbationTask } from "@/lib/api-probation";

export interface ProbationTimelineProps {
  hireDate: string;
  tasks: ProbationTask[];
}

/**
 * 试用期时间轴: 入职当天 / D+30 / D+90 / D+180.
 */
export function ProbationTimeline({ hireDate, tasks }: ProbationTimelineProps) {
  const hire = new Date(hireDate);
  const today = new Date();

  const stages = [
    { label: "入职引导", offset: 0, color: "emerald" },
    { label: "D+30 检查", offset: 30, color: "blue" },
    { label: "D+30 评估", offset: 30, color: "blue" },
    { label: "D+90 评估", offset: 90, color: "amber" },
    { label: "D+180 转正", offset: 180, color: "rose" },
  ];

  const daysSince = Math.floor((today.getTime() - hire.getTime()) / (1000 * 60 * 60 * 24));

  return (
    <div className="space-y-4">
      <div className="text-sm text-slate-500">
        入职: {hireDate} ({daysSince} 天)
      </div>
      <ol className="relative border-l-2 border-slate-200 ml-2 space-y-4">
        {stages.map((s, i) => {
          const due = new Date(hire.getTime() + s.offset * 24 * 60 * 60 * 1000);
          const isPast = due <= today;
          const isCurrent = !isPast && i === stages.findIndex(st => {
            const d = new Date(hire.getTime() + st.offset * 24 * 60 * 60 * 1000);
            return d > today;
          });
          const task = tasks.find((t) => t.due_at && new Date(t.due_at).toDateString() === due.toDateString());
          const completed = !!task?.completed_at;
          return (
            <li key={i} className="ml-6 relative">
              <span
                className={`absolute -left-[33px] flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                  completed
                    ? "bg-emerald-500 text-white"
                    : isPast
                      ? "bg-slate-400 text-white"
                      : isCurrent
                        ? `bg-${s.color}-500 text-white animate-pulse`
                        : "bg-slate-200 text-slate-500"
                }`}
              >
                {completed ? "✓" : i + 1}
              </span>
              <div>
                <p className="font-medium text-sm">{s.label}</p>
                <p className="text-xs text-slate-500">
                  {due.toISOString().slice(0, 10)}
                  {completed && " · 已完成"}
                  {!completed && isPast && " · 已逾期"}
                  {!completed && isCurrent && " · 进行中"}
                  {!completed && !isPast && !isCurrent && " · 待开始"}
                </p>
                {task?.description && (
                  <p className="text-xs text-slate-600 mt-1">{task.description}</p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
