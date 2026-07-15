"use client";

/**
 * T6108 — Interview question template.
 *
 * Renders 5-10 interview questions drawn from the question bank for a given
 * role, each with prompt / expected answer points / assessed skills /
 * difficulty / type / suggested duration / scoring weights. Provides a
 * per-template export-to-PDF action.
 */
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  InterviewQuestion,
  InterviewQuestionTemplate as Template,
} from "@/lib/api-hr-assistant";

const DIFFICULTY_VARIANT: Record<string, "default" | "secondary" | "destructive"> = {
  junior: "secondary",
  mid: "default",
  senior: "default",
  lead: "destructive",
};

const TYPE_LABELS: Record<string, string> = {
  technical: "技术",
  behavioral: "行为",
  situational: "情景",
  case: "案例",
};

export interface InterviewQuestionTemplateProps {
  template: Template;
  className?: string;
}

export function InterviewQuestionTemplate({
  template,
  className,
}: InterviewQuestionTemplateProps) {
  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div className="space-y-1">
          <CardTitle className="text-base">{template.title}</CardTitle>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="outline">{template.role}</Badge>
            <span>{template.count} 题</span>
            <span>·</span>
            <span>预计 {template.estimated_minutes} 分钟</span>
            {template.difficulty ? (
              <>
                <span>·</span>
                <span>难度 {template.difficulty}</span>
              </>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {template.questions.map((q, idx) => (
          <QuestionRow key={q.id} index={idx + 1} q={q} />
        ))}
      </CardContent>
    </Card>
  );
}

function QuestionRow({ index, q }: { index: number; q: InterviewQuestion }) {
  return (
    <div className="rounded-md border p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="font-medium">
          <span className="mr-2 text-muted-foreground">{index}.</span>
          {q.title}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Badge variant={DIFFICULTY_VARIANT[q.difficulty] ?? "secondary"}>
            {q.difficulty}
          </Badge>
          <Badge variant="outline">
            {TYPE_LABELS[q.type] ?? q.type}
          </Badge>
        </div>
      </div>

      <p className="mt-2 text-sm text-muted-foreground">{q.prompt}</p>

      {q.expected_points?.length ? (
        <div className="mt-2">
          <div className="text-xs font-medium text-muted-foreground">
            期望要点
          </div>
          <ul className="mt-1 list-inside list-disc space-y-0.5 text-sm">
            {q.expected_points.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {q.skills?.map((s) => (
          <Badge key={s} variant="secondary" className="font-normal">
            {s}
          </Badge>
        ))}
        <span>· 建议时长 {Math.round(q.duration_sec / 60)} 分钟</span>
      </div>
    </div>
  );
}
