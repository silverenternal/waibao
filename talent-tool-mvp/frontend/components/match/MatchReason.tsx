"use client";

import * as React from "react";
import { CheckCircle2 } from "lucide-react";

export interface MatchReasonProps {
  reasons: string[];
  loading?: boolean;
}

/**
 * 匹配"为什么匹配"列表 — 绿色对勾样式.
 */
export function MatchReason({ reasons, loading }: MatchReasonProps) {
  if (loading) {
    return <div className="text-sm text-slate-400">正在生成解释…</div>;
  }
  if (!reasons || reasons.length === 0) {
    return (
      <div className="text-sm text-slate-500 italic">
        暂无优势要点
      </div>
    );
  }
  return (
    <ul className="space-y-2">
      {reasons.map((r, i) => (
        <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
          <CheckCircle2
            className="mt-0.5 shrink-0 text-emerald-600"
            size={16}
            aria-hidden
          />
          <span>{r}</span>
        </li>
      ))}
    </ul>
  );
}