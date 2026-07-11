"use client";

import * as React from "react";
import { AlertTriangle } from "lucide-react";

export interface MatchWeakPointsProps {
  weak_points: string[];
  loading?: boolean;
}

/**
 * 匹配"为什么不匹配"列表 — 黄色三角警示样式.
 */
export function MatchWeakPoints({ weak_points, loading }: MatchWeakPointsProps) {
  if (loading) {
    return <div className="text-sm text-slate-400">正在分析差距…</div>;
  }
  if (!weak_points || weak_points.length === 0) {
    return (
      <div className="text-sm text-emerald-700 italic">
        未发现明显差距
      </div>
    );
  }
  return (
    <ul className="space-y-2">
      {weak_points.map((w, i) => (
        <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
          <AlertTriangle
            className="mt-0.5 shrink-0 text-amber-500"
            size={16}
            aria-hidden
          />
          <span>{w}</span>
        </li>
      ))}
    </ul>
  );
}