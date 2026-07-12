"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SOURCE_LABEL, SOURCE_COLOR } from "@/lib/api-company-review";

export interface InterviewExperienceListProps {
  interviews: Array<{
    id: string;
    source: string;
    job_title: string;
    difficulty: number;
    experience: "positive" | "neutral" | "negative";
    process?: string | null;
    questions: string[];
    result: "offer" | "rejected" | "pending" | "no_response";
    created_at?: string | null;
    author?: string | null;
  }>;
  loading?: boolean;
}

const EXP_COLOR: Record<string, string> = {
  positive: "bg-emerald-100 text-emerald-700",
  neutral: "bg-slate-100 text-slate-700",
  negative: "bg-rose-100 text-rose-700",
};
const EXP_LABEL: Record<string, string> = {
  positive: "体验好",
  neutral: "体验一般",
  negative: "体验差",
};
const RESULT_COLOR: Record<string, string> = {
  offer: "bg-emerald-100 text-emerald-700",
  rejected: "bg-rose-100 text-rose-700",
  pending: "bg-amber-100 text-amber-700",
  no_response: "bg-slate-100 text-slate-600",
};
const RESULT_LABEL: Record<string, string> = {
  offer: "已获 offer",
  rejected: "被拒",
  pending: "进行中",
  no_response: "无回应",
};

export function InterviewExperienceList({
  interviews,
  loading,
}: InterviewExperienceListProps) {
  if (loading) {
    return (
      <Card>
        <CardContent className="p-6 text-slate-400 text-sm">加载面试经验中…</CardContent>
      </Card>
    );
  }

  if (!interviews.length) {
    return (
      <Card>
        <CardContent className="p-6 text-slate-500 text-sm">暂无面试经验</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {interviews.map((it) => (
        <Card key={it.id}>
          <CardHeader className="pb-2">
            <div className="flex items-start justify-between gap-2">
              <CardTitle className="text-base">{it.job_title}</CardTitle>
              <div className="flex gap-1">
                <Badge className={SOURCE_COLOR[it.source] ?? "bg-slate-100"}>
                  {SOURCE_LABEL[it.source] ?? it.source}
                </Badge>
                <Badge className={EXP_COLOR[it.experience]}>
                  {EXP_LABEL[it.experience]}
                </Badge>
                <Badge className={RESULT_COLOR[it.result]}>
                  {RESULT_LABEL[it.result]}
                </Badge>
              </div>
            </div>
            <div className="flex items-center gap-3 text-xs text-slate-500 mt-1">
              <span>{it.author}</span>
              <span>· 难度 {"★".repeat(it.difficulty)}{"☆".repeat(5 - it.difficulty)}</span>
              <span>· {it.created_at?.slice(0, 10) ?? ""}</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {it.process && (
              <div className="text-xs">
                <span className="text-slate-500 font-medium">流程: </span>
                <span className="text-slate-700">{it.process}</span>
              </div>
            )}
            {it.questions.length > 0 && (
              <div className="text-xs">
                <div className="text-slate-500 font-medium mb-1">面试题:</div>
                <ul className="list-disc list-inside space-y-0.5 text-slate-700">
                  {it.questions.slice(0, 5).map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}