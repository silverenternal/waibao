"use client";

import * as React from "react";
import { Sparkles, TrendingUp } from "lucide-react";

export interface MatchCounterfactualProps {
  if_have?: string;
  score_lift?: number;
  loading?: boolean;
}

/**
 * "如果……会更匹配"反事实匹配卡片.
 */
export function MatchCounterfactual({
  if_have,
  score_lift,
  loading,
}: MatchCounterfactualProps) {
  if (loading) {
    return (
      <div className="text-sm text-slate-400">正在生成反事实…</div>
    );
  }
  const lift = typeof score_lift === "number" ? score_lift : 0;
  const pct = (lift * 100).toFixed(1);

  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-4">
      <div className="flex items-center gap-2 mb-2">
        <Sparkles className="text-indigo-600" size={18} aria-hidden />
        <h4 className="text-sm font-semibold text-indigo-900">
          如果……会更匹配
        </h4>
      </div>
      <p className="text-sm text-slate-800 mb-3">
        {if_have || "暂无反事实建议"}
      </p>
      <div className="flex items-center gap-2 text-sm">
        <TrendingUp className="text-emerald-600" size={16} aria-hidden />
        <span className="text-slate-600">预计分数提升</span>
        <span className="font-mono font-semibold text-emerald-700">+{pct}%</span>
      </div>
    </div>
  );
}