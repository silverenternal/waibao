"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { EvalScores } from "@/lib/api-match-eval";

export interface EvalComparisonProps {
  candidateEval?: EvalScores | null;
  employerEval?: EvalScores | null;
  loading?: boolean;
}

const DIMENSIONS: Array<{ key: keyof EvalScores; label: string }> = [
  { key: "skill", label: "技能" },
  { key: "communication", label: "沟通" },
  { key: "culture", label: "文化契合" },
  { key: "potential", label: "潜力" },
];

function renderStars(value?: number | string) {
  const v = typeof value === "number" ? value : 0;
  const full = Math.round(v);
  return "★".repeat(full) + "☆".repeat(Math.max(0, 5 - full));
}

/**
 * 候选人 vs 雇主 双向评分对比表.
 */
export function EvalComparison({
  candidateEval,
  employerEval,
  loading,
}: EvalComparisonProps) {
  if (loading) {
    return (
      <Card>
        <CardContent className="p-6 text-slate-400 text-sm">加载中…</CardContent>
      </Card>
    );
  }

  if (!candidateEval && !employerEval) {
    return (
      <Card>
        <CardContent className="p-6 text-slate-500 text-sm">
          双方尚未提交互评
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">双方评分对比</CardTitle>
      </CardHeader>
      <CardContent>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b">
              <th className="py-2 pr-4 font-medium text-slate-600">维度</th>
              <th className="py-2 pr-4 font-medium text-slate-600">候选人评分</th>
              <th className="py-2 pr-4 font-medium text-slate-600">雇主评分</th>
              <th className="py-2 font-medium text-slate-600">差距</th>
            </tr>
          </thead>
          <tbody>
            {DIMENSIONS.map(({ key, label }) => {
              const c = candidateEval?.[key];
              const e = employerEval?.[key];
              const gap =
                typeof c === "number" && typeof e === "number"
                  ? Math.abs(c - e).toFixed(1)
                  : "—";
              return (
                <tr key={key} className="border-b last:border-0">
                  <td className="py-2 pr-4 text-slate-700">{label}</td>
                  <td className="py-2 pr-4 font-mono text-slate-800">
                    {renderStars(c)}
                  </td>
                  <td className="py-2 pr-4 font-mono text-slate-800">
                    {renderStars(e)}
                  </td>
                  <td className="py-2">
                    <Badge variant="outline">{gap}</Badge>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}