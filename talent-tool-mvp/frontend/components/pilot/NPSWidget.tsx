"use client";

/**
 * T1702 — NPS 评分组件 (0-10).
 *
 * - 0-6  : Detractor (红)
 * - 7-8  : Passive   (黄)
 * - 9-10 : Promoter  (绿)
 * - 提交后立即乐观 UI,服务端反馈真实 NPS 概览
 */

import * as React from "react";
import { Star, Send, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export type NPSBucket = "detractor" | "passive" | "promoter";

export interface NPSWidgetProps {
  /** 当前 pilot program id (可选). */
  programId?: string;
  /** 当前使用功能 (写入 feature_used). */
  featureUsed?: string;
  /** 提交完成回调 (用于上层更新 UI / 关闭弹层). */
  onSubmit?: (data: { score: number; bucket: NPSBucket }) => void;
  /** 受控 open (默认内部 state). */
  open?: boolean;
  /** 显示模式: card (默认) / inline / compact. */
  variant?: "card" | "inline" | "compact";
}

function bucketOf(score: number): NPSBucket {
  if (score >= 9) return "promoter";
  if (score <= 6) return "detractor";
  return "passive";
}

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("sb_token") || "";
}

const BUCKET_COLOR: Record<NPSBucket, string> = {
  promoter: "bg-emerald-500 hover:bg-emerald-600",
  passive: "bg-amber-500 hover:bg-amber-600",
  detractor: "bg-rose-500 hover:bg-rose-600",
};

const BUCKET_LABEL: Record<NPSBucket, string> = {
  promoter: "推荐者",
  passive: "中立者",
  detractor: "贬损者",
};

export function NPSWidget({
  programId,
  featureUsed,
  onSubmit,
  open: openProp,
  variant = "card",
}: NPSWidgetProps) {
  const [open, setOpen] = React.useState(openProp ?? true);
  const [score, setScore] = React.useState<number | null>(null);
  const [comment, setComment] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [done, setDone] = React.useState<NPSBucket | null>(null);

  React.useEffect(() => {
    if (openProp !== undefined) setOpen(openProp);
  }, [openProp]);

  if (!open) return null;

  const submit = async () => {
    if (score === null) return;
    setSubmitting(true);
    try {
      const res = await fetch("/api/pilot/feedback/nps", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          score,
          comment: comment || undefined,
          feature_used: featureUsed,
          program_id: programId,
        }),
      });
      if (res.ok) {
        const bucket = bucketOf(score);
        setDone(bucket);
        onSubmit?.({ score, bucket });
        // 1.2s 后自动关闭
        setTimeout(() => setOpen(false), 1200);
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    return (
      <div
        className={cn(
          "rounded-xl border bg-background p-6 text-center shadow-sm",
          variant === "inline" && "p-3",
        )}
        role="status"
        aria-live="polite"
      >
        <div className="text-2xl">
          {done === "promoter" ? "🎉" : done === "passive" ? "🙏" : "😟"}
        </div>
        <p className="mt-2 font-semibold">感谢您的反馈!</p>
        <p className="text-sm text-muted-foreground">
          您被记录为 <span className="font-medium">{BUCKET_LABEL[done]}</span>。
        </p>
      </div>
    );
  }

  if (variant === "compact") {
    return (
      <div className="flex items-center gap-2">
        {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => setScore(n)}
            className={cn(
              "h-8 w-8 rounded-md border text-sm font-medium transition",
              score === n
                ? BUCKET_COLOR[bucketOf(n)] + " text-white border-transparent"
                : "bg-background hover:bg-muted",
            )}
            aria-label={`NPS 评分 ${n}`}
            aria-pressed={score === n}
          >
            {n}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "rounded-xl border bg-background p-5 shadow-sm",
        variant === "inline" && "border-none shadow-none p-0",
      )}
      role="dialog"
      aria-label="NPS 评分"
    >
      <div className="mb-3 flex items-center gap-2">
        <Star className="size-4 text-amber-500" aria-hidden />
        <h3 className="text-sm font-semibold">您向同事推荐的可能性?</h3>
      </div>
      <p className="mb-4 text-xs text-muted-foreground">
        0 = 完全不可能 · 10 = 非常推荐
      </p>

      <div className="grid grid-cols-11 gap-1.5">
        {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => setScore(n)}
            className={cn(
              "h-10 rounded-md border text-sm font-medium transition",
              score === n
                ? BUCKET_COLOR[bucketOf(n)] + " text-white border-transparent"
                : "bg-background hover:bg-muted",
            )}
            aria-label={`NPS 评分 ${n}`}
            aria-pressed={score === n}
          >
            {n}
          </button>
        ))}
      </div>

      {score !== null && (
        <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
          <span className={cn("size-2 rounded-full", BUCKET_COLOR[bucketOf(score)])} />
          <span>{BUCKET_LABEL[bucketOf(score)]}</span>
        </div>
      )}

      {score !== null && (
        <div className="mt-4 space-y-3">
          <Textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="(可选) 您为什么打这个分?"
            rows={2}
            maxLength={1000}
            aria-label="NPS 备注"
          />
          <Button
            onClick={submit}
            disabled={submitting}
            className="w-full"
            size="sm"
          >
            {submitting ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                提交中...
              </>
            ) : (
              <>
                <Send className="mr-2 size-4" />
                提交反馈
              </>
            )}
          </Button>
        </div>
      )}
    </div>
  );
}

export default NPSWidget;