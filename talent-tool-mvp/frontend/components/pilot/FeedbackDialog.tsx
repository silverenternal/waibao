"use client";

/**
 * T1702 — 主动反馈弹窗 (支持 bug / feature_request / praise / complaint / other).
 *
 * - 通过 fetch 调 /api/pilot/feedback
 * - 受控 / 非受控 open 都支持
 */

import * as React from "react";
import { MessageCircle, Send, Loader2, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogClose,
} from "@/components/ui/dialog";

export const FEEDBACK_CATEGORIES = [
  { value: "bug", label: "Bug 报告" },
  { value: "feature_request", label: "功能建议" },
  { value: "praise", label: "表扬" },
  { value: "complaint", label: "投诉" },
  { value: "other", label: "其他" },
] as const;

export type FeedbackCategory = (typeof FEEDBACK_CATEGORIES)[number]["value"];

export interface FeedbackDialogProps {
  /** 受控 open. */
  open?: boolean;
  /** open 状态变化回调. */
  onOpenChange?: (open: boolean) => void;
  /** 当前 pilot program id. */
  programId?: string;
  /** 当前使用功能 (写入 feature_used). */
  featureUsed?: string;
  /** 提交完成回调. */
  onSubmit?: (data: { category: FeedbackCategory; comment: string }) => void;
  /** 触发按钮文案 (默认 "反馈"). */
  triggerLabel?: string;
}

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("sb_token") || "";
}

export function FeedbackDialog({
  open: openProp,
  onOpenChange,
  programId,
  featureUsed,
  onSubmit,
  triggerLabel = "反馈",
}: FeedbackDialogProps) {
  const [open, setOpen] = React.useState(openProp ?? false);
  const [category, setCategory] = React.useState<FeedbackCategory>("bug");
  const [comment, setComment] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (openProp !== undefined) setOpen(openProp);
  }, [openProp]);

  const setOpenAndNotify = (next: boolean) => {
    setOpen(next);
    onOpenChange?.(next);
    if (!next) {
      // reset
      setComment("");
      setCategory("bug");
      setError(null);
    }
  };

  const submit = async () => {
    if (!comment.trim()) {
      setError("请填写反馈内容");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/pilot/feedback", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          category,
          comment: comment.trim(),
          feature_used: featureUsed,
          program_id: programId,
        }),
      });
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(text || `HTTP ${res.status}`);
      }
      onSubmit?.({ category, comment: comment.trim() });
      setOpenAndNotify(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpenAndNotify}>
      {openProp === undefined && (
        <Button
          variant="outline"
          size="sm"
          onClick={() => setOpenAndNotify(true)}
        >
          <MessageCircle className="mr-2 size-4" />
          {triggerLabel}
        </Button>
      )}

      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>告诉我们您的想法</DialogTitle>
          <DialogDescription>
            所有反馈都会直接送达产品团队,通常 1-2 个工作日内回复.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <label className="text-sm font-medium">类别</label>
            <div className="mt-2 flex flex-wrap gap-2">
              {FEEDBACK_CATEGORIES.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => setCategory(c.value)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs transition",
                    category === c.value
                      ? "border-primary bg-primary text-primary-foreground"
                      : "bg-background hover:bg-muted",
                  )}
                  aria-pressed={category === c.value}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-sm font-medium" htmlFor="fb-comment">
              详细描述
            </label>
            <Textarea
              id="fb-comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="请描述您遇到的问题或建议..."
              rows={5}
              maxLength={2000}
              className="mt-2"
              aria-invalid={!!error}
            />
            <p className="mt-1 text-right text-xs text-muted-foreground">
              {comment.length} / 2000
            </p>
          </div>

          {error && (
            <p className="text-sm text-rose-600" role="alert">
              {error}
            </p>
          )}
        </div>

        <DialogFooter className="gap-2">
          <DialogClose {...({ asChild: true } as any)}>
            <Button variant="ghost" disabled={submitting}>
              <X className="mr-1 size-4" />
              取消
            </Button>
          </DialogClose>
          <Button onClick={submit} disabled={submitting || !comment.trim()}>
            {submitting ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                提交中
              </>
            ) : (
              <>
                <Send className="mr-2 size-4" />
                提交
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default FeedbackDialog;