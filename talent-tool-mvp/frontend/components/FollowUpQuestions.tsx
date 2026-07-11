"use client";

/**
 * FollowUpQuestions — renders the open info-gaps surfaced by the Clarifier
 * Agent and lets the user answer in one tap. Submitted answers are merged
 * into the local question list (optimistic) and dispatched via the
 * `onAnswer` callback — typically wired to a journal entry or a
 * `/api/conversations` message so the next `synthesize()` pass absorbs them.
 */

import * as React from "react";
import { MessageCircleQuestion, Send, SkipForward, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  PRIORITY_COLOR,
  PRIORITY_LABEL,
  type FollowUpQuestion,
  type Priority,
} from "@/lib/api-clarification";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

export interface FollowUpQuestionsProps {
  questions: FollowUpQuestion[] | undefined | null;
  /**
   * Fired when the user submits an answer. Parent decides how to persist it
   * (e.g. POST to `/api/conversations`, or append a journal entry).
   * `index` matches the question's position in the original array.
   */
  onAnswer?: (question: FollowUpQuestion, answer: string, index: number) => void;
  /** Override the title shown in the card header. */
  title?: string;
  className?: string;
}

export function FollowUpQuestions({
  questions,
  onAnswer,
  title = "智能体追问",
  className,
}: FollowUpQuestionsProps) {
  const items = (questions ?? []).map((q, i) => ({ q, i }));

  if (items.length === 0) {
    return (
      <Card className={className}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="size-4 text-emerald-500" />
            {title}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="rounded-lg border border-dashed bg-muted/30 px-3 py-3 text-sm text-muted-foreground">
            目前没有需要补充的信息 — 智能体认为你的画像已经够清晰。
          </p>
        </CardContent>
      </Card>
    );
  }

  const open = items.filter(({ q }) => !q.answered);
  const answered = items.filter(({ q }) => q.answered);

  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <MessageCircleQuestion className="size-4 text-blue-500" />
            {title}
          </CardTitle>
          <span className="text-xs text-muted-foreground">
            {open.length > 0 ? `待回答 ${open.length}` : "已全部回答"}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {open.map(({ q, i }) => (
          <FollowUpItem
            key={`open-${i}`}
            question={q}
            index={i}
            onAnswer={onAnswer}
          />
        ))}
        {answered.length > 0 && (
          <details className="rounded-lg border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            <summary className="cursor-pointer select-none">
              已回答 {answered.length} 条
            </summary>
            <ul className="mt-2 space-y-1.5">
              {answered.map(({ q, i }) => (
                <li key={`ans-${i}`}>
                  <span className="font-medium text-foreground">{q.question}</span>
                  <span className="ml-1">→ {q.answer}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

function FollowUpItem({
  question,
  index,
  onAnswer,
}: {
  question: FollowUpQuestion;
  index: number;
  onAnswer?: (q: FollowUpQuestion, answer: string, i: number) => void;
}) {
  const [draft, setDraft] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [collapsed, setCollapsed] = React.useState(false);

  async function submit() {
    const text = draft.trim();
    if (!text) return;
    setSubmitting(true);
    try {
      await Promise.resolve(onAnswer?.(question, text, index));
      setCollapsed(true);
      setDraft("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <article
      className={cn(
        "rounded-xl border bg-card p-4 shadow-sm transition-opacity",
        collapsed && "opacity-60",
      )}
    >
      <header className="flex items-start gap-2">
        <span className="grid size-7 shrink-0 place-items-center rounded-full bg-blue-100 text-blue-700">
          <Sparkles className="size-3.5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-foreground">{question.question}</p>
          <p className="mt-1 text-xs text-muted-foreground">{question.purpose}</p>
        </div>
        <PriorityChip priority={question.priority} />
      </header>

      {!collapsed && (
        <div className="mt-3 space-y-2">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="一键回复智能体..."
            className="min-h-20 resize-y text-sm"
            disabled={submitting}
          />
          <div className="flex items-center justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setCollapsed(true)}
              disabled={submitting}
            >
              <SkipForward className="size-3.5" />
              稍后
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={submit}
              disabled={!draft.trim() || submitting}
            >
              <Send className="size-3.5" />
              {submitting ? "发送中..." : "回复"}
            </Button>
          </div>
        </div>
      )}
    </article>
  );
}

function PriorityChip({ priority }: { priority: Priority }) {
  return (
    <span
      className={cn(
        "shrink-0 rounded-md border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide",
        PRIORITY_COLOR[priority],
      )}
    >
      {PRIORITY_LABEL[priority]}
    </span>
  );
}