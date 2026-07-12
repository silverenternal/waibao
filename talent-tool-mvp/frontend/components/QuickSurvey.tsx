"use client";

/**
 * T1106 — 3 题内嵌快速问卷.
 *
 * 在用户使用 1 周后或重要功能首次完成时自动弹出.
 * 调用 /api/feedback/quick-survey.
 */

import * as React from "react";
import { Star, X, CheckCircle2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface Question {
  key: "easy_to_use" | "value" | "speed";
  label: string;
  hint: string;
}

const QUESTIONS: Question[] = [
  { key: "easy_to_use", label: "易用性", hint: "界面是否清晰、操作是否顺手?" },
  { key: "value", label: "价值感", hint: "是否真正帮您节省时间 / 找到合适的机会?" },
  { key: "speed", label: "响应速度", hint: "匹配 / 加载 / 反馈是否及时?" },
];

export interface QuickSurveyProps {
  /** 触发场景,埋点用 (e.g. 'first_match' / 'first_handoff'). */
  trigger?: string;
  /** 当前使用功能,写入 feature_used. */
  featureUsed?: string;
  /** 已点过关闭后是否允许重新打开 (默认 false). */
  reopen?: boolean;
  /** 提交完成后回调. */
  onSubmit?: (data: { easy_to_use: number; value: number; speed: number; comment?: string }) => void;
}

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("sb_token") || "";
}

export function QuickSurvey({
  trigger = "manual",
  featureUsed,
  reopen = false,
  onSubmit,
}: QuickSurveyProps) {
  const storageKey = `wb_quick_survey_done_${trigger}`;
  const [open, setOpen] = React.useState(true);
  const [step, setStep] = React.useState(0);
  const [scores, setScores] = React.useState<Record<string, number>>({});
  const [comment, setComment] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    if (!reopen && typeof window !== "undefined") {
      if (localStorage.getItem(storageKey)) setOpen(false);
    }
  }, [reopen, storageKey]);

  const finish = async () => {
    setSubmitting(true);
    try {
      const payload = {
        easy_to_use: scores.easy_to_use,
        value: scores.value,
        speed: scores.speed,
        comment: comment || undefined,
        feature_used: featureUsed,
        metadata: { trigger },
      };
      const res = await fetch("/api/feedback/quick-survey", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        if (typeof window !== "undefined") {
          localStorage.setItem(storageKey, "1");
        }
        onSubmit?.({ ...payload });
        setOpen(false);
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  const isFinal = step === QUESTIONS.length;
  const q = QUESTIONS[step];
  const progress = Math.min(step / QUESTIONS.length, 1);

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-2xl border bg-background shadow-2xl">
        <div className="flex items-center justify-between border-b px-5 py-3">
          <p className="text-sm font-medium">快速问卷 · 共 3 题</p>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rounded p-1 text-muted-foreground hover:bg-muted"
            aria-label="关闭"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="h-1 bg-muted">
          <div
            className="h-full bg-primary transition-all"
            style={{ width: `${progress * 100}%` }}
          />
        </div>

        <div className="px-5 py-6">
          {!isFinal ? (
            <div className="space-y-4">
              <div>
                <h3 className="text-base font-semibold">{q.label}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{q.hint}</p>
              </div>
              <div className="flex justify-between gap-2">
                {[1, 2, 3, 4, 5].map((i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => {
                      setScores((s) => ({ ...s, [q.key]: i }));
                      // 自动前进,稍作停顿以提供反馈
                      setTimeout(() => setStep((cur) => cur + 1), 200);
                    }}
                    className={cn(
                      "flex flex-1 flex-col items-center gap-1 rounded-lg border px-2 py-3 transition-all",
                      scores[q.key] === i
                        ? "border-primary bg-primary/10"
                        : "border-muted hover:bg-muted",
                    )}
                  >
                    <Star
                      className={cn(
                        "size-6",
                        scores[q.key] === i ? "text-amber-500" : "text-muted-foreground/40",
                      )}
                      fill={scores[q.key] === i ? "currentColor" : "none"}
                    />
                    <span className="text-xs">{i} 分</span>
                  </button>
                ))}
              </div>
              {step > 0 && (
                <button
                  type="button"
                  onClick={() => setStep((s) => Math.max(0, s - 1))}
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  上一题
                </button>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-emerald-600">
                <CheckCircle2 className="size-5" />
                <h3 className="text-base font-semibold">最后一步</h3>
              </div>
              <p className="text-sm text-muted-foreground">
                还有什么想告诉我们的吗? (选填)
              </p>
              <Textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="任何具体的功能建议或遇到的问题..."
                className="min-h-24 text-sm"
              />
              <div className="flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={() => setStep(2)}>
                  上一题
                </Button>
                <Button size="sm" disabled={submitting} onClick={finish}>
                  {submitting ? "提交中..." : "完成问卷"}
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default QuickSurvey;