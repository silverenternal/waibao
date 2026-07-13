"use client";

/**
 * v8.0 T3902 — Global feedback widget.
 *
 * Floating bottom-right bubble for capturing user feedback:
 *   • 5-star rating
 *   • Bug report
 *   • Feature request
 *   • General feedback
 *
 * Auto-attaches context:
 *   - current page URL
 *   - user role / tenant (from data-* attributes on root or session)
 *   - user agent
 *   - viewport size
 *
 * Server contract: `POST /api/feedback/v2` (see backend/api/feedback_v2.py).
 */

import * as React from "react";
import {
  AlertCircle,
  Bug,
  Lightbulb,
  Loader2,
  MessageSquare,
  Send,
  Star,
  ThumbsUp,
  X,
  CheckCircle2,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";

export type FeedbackType = "rating" | "bug" | "feature" | "experience" | "performance";

export interface FeedbackWidgetProps {
  /** API base path. Default: /api/feedback */
  apiBase?: string;
  /** Disable the widget (e.g. for admin pages). */
  disabled?: boolean;
  /** Pre-fill page context. */
  defaultPage?: string;
  /** Optional default feature name. */
  defaultFeature?: string;
  /** Hide the floating button — useful for embedding inline. */
  inline?: boolean;
}

const TYPE_OPTIONS: Array<{ value: FeedbackType; label: string; icon: React.ReactNode }> = [
  { value: "rating", label: "评分", icon: <Star className="h-4 w-4" /> },
  { value: "bug", label: "Bug", icon: <Bug className="h-4 w-4" /> },
  { value: "feature", label: "建议", icon: <Lightbulb className="h-4 w-4" /> },
  { value: "experience", label: "体验", icon: <MessageSquare className="h-4 w-4" /> },
  { value: "performance", label: "性能", icon: <AlertCircle className="h-4 w-4" /> },
];

type View = "closed" | "select" | "form" | "thanks";

function collectContext(): Record<string, unknown> {
  if (typeof window === "undefined") return {};
  return {
    page_url: window.location.href,
    path: window.location.pathname,
    user_agent: navigator.userAgent,
    viewport: {
      w: window.innerWidth,
      h: window.innerHeight,
    },
    locale: navigator.language,
    referrer: document.referrer || null,
    ts: new Date().toISOString(),
  };
}

function getUserContext(): { user_id?: string; tenant_id?: string; role?: string } {
  if (typeof document === "undefined") return {};
  const root = document.body;
  return {
    user_id: root.getAttribute("data-user-id") || undefined,
    tenant_id: root.getAttribute("data-tenant-id") || undefined,
    role: root.getAttribute("data-user-role") || undefined,
  };
}

export function FeedbackWidget({
  apiBase = "/api/feedback",
  disabled = false,
  defaultPage,
  defaultFeature,
  inline = false,
}: FeedbackWidgetProps) {
  const [view, setView] = React.useState<View>("closed");
  const [type, setType] = React.useState<FeedbackType>("rating");
  const [rating, setRating] = React.useState<number>(0);
  const [comment, setComment] = React.useState("");
  const [title, setTitle] = React.useState("");
  const [page, setPage] = React.useState(defaultPage || "");
  const [feature, setFeature] = React.useState(defaultFeature || "");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [submittedId, setSubmittedId] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (typeof window !== "undefined" && !page) {
      setPage(window.location.pathname);
    }
  }, [page]);

  if (disabled) return null;

  const reset = () => {
    setType("rating");
    setRating(0);
    setComment("");
    setTitle("");
    setError(null);
    setSubmittedId(null);
  };

  const close = () => {
    setView("closed");
    reset();
  };

  const submit = async () => {
    if (type !== "rating" && comment.trim().length < 1) {
      setError("请填写反馈内容");
      return;
    }
    if (type === "rating" && rating === 0) {
      setError("请选择评分");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        type,
        comment: comment || (type === "rating" ? `评分 ${rating}/5` : ""),
        page,
        feature,
        metadata: { ...collectContext(), ...getUserContext() },
      };
      if (type === "rating" && rating > 0) {
        body.rating = rating;
      }
      if (title) body.title = title;
      const res = await fetch(`${apiBase}/v2`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      setSubmittedId(data.id || null);
      setView("thanks");
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败,请稍后再试");
    } finally {
      setSubmitting(false);
    }
  };

  // ---- Inline mode (embedded form) ----
  if (inline) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-900">用户反馈</h3>
        </div>
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {TYPE_OPTIONS.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => setType(o.value)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs",
                  type === o.value
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-200 bg-white text-slate-700 hover:border-slate-300",
                )}
              >
                {o.icon}
                {o.label}
              </button>
            ))}
          </div>
          {type === "rating" && (
            <StarRating value={rating} onChange={setRating} />
          )}
          {type !== "rating" && (
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="标题 (可选)"
              maxLength={200}
            />
          )}
          <Textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder={
              type === "rating"
                ? "补充说明 (可选)"
                : "详细描述 (必填)"
            }
            rows={4}
            maxLength={4000}
          />
          {error && <p className="text-xs text-rose-600">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button size="sm" onClick={submit} disabled={submitting}>
              {submitting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
              提交
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // ---- Floating widget mode ----
  return (
    <>
      {view === "closed" && (
        <button
          type="button"
          onClick={() => setView("select")}
          aria-label="Open feedback widget"
          className="fixed bottom-6 right-6 z-50 flex h-12 w-12 items-center justify-center rounded-full bg-slate-900 text-white shadow-lg transition hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-500"
        >
          <MessageSquare className="h-5 w-5" />
        </button>
      )}

      {view !== "closed" && (
        <div
          className="fixed bottom-6 right-6 z-50 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl"
          role="dialog"
          aria-label="Feedback"
        >
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50 px-4 py-2.5">
            <h2 className="text-sm font-semibold text-slate-900">用户反馈</h2>
            <button
              type="button"
              onClick={close}
              aria-label="Close"
              className="rounded p-1 text-slate-500 hover:bg-slate-200"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          {view === "select" && (
            <div className="grid grid-cols-2 gap-2 p-3">
              {TYPE_OPTIONS.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => {
                    setType(o.value);
                    setView("form");
                  }}
                  className="flex items-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-left text-sm text-slate-700 hover:border-slate-400 hover:bg-slate-50"
                >
                  {o.icon}
                  {o.label}
                </button>
              ))}
            </div>
          )}

          {view === "form" && (
            <div className="space-y-3 p-3">
              <div className="flex flex-wrap gap-1.5">
                {TYPE_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => setType(o.value)}
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs",
                      type === o.value
                        ? "border-slate-900 bg-slate-900 text-white"
                        : "border-slate-200 bg-white text-slate-700",
                    )}
                  >
                    {o.icon}
                    {o.label}
                  </button>
                ))}
              </div>
              {type === "rating" && (
                <StarRating value={rating} onChange={setRating} />
              )}
              {type !== "rating" && (
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="标题 (可选)"
                  maxLength={200}
                />
              )}
              <Textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder={type === "rating" ? "补充说明 (可选)" : "详细描述 (必填)"}
                rows={4}
                maxLength={4000}
              />
              {error && (
                <p className="text-xs text-rose-600">{error}</p>
              )}
              <div className="flex items-center justify-between text-xs text-slate-500">
                <span>页面: {page || "-"}</span>
                <span>{comment.length}/4000</span>
              </div>
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="outline" onClick={() => setView("select")}>
                  返回
                </Button>
                <Button size="sm" onClick={submit} disabled={submitting}>
                  {submitting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
                  提交
                </Button>
              </div>
            </div>
          )}

          {view === "thanks" && (
            <div className="space-y-3 p-4 text-center">
              <div className="flex justify-center">
                <CheckCircle2 className="h-10 w-10 text-emerald-500" />
              </div>
              <h3 className="text-sm font-semibold text-slate-900">感谢您的反馈!</h3>
              <p className="text-xs text-slate-600">
                {submittedId
                  ? `已记录 (#${submittedId.slice(0, 8)}), 我们会尽快处理.`
                  : "已记录, 我们会尽快处理."}
              </p>
              <Button size="sm" onClick={close}>
                <ThumbsUp className="h-3 w-3" /> 完成
              </Button>
            </div>
          )}
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Star rating
// ---------------------------------------------------------------------------


function StarRating({
  value,
  onChange,
}: {
  value: number;
  onChange: (n: number) => void;
}) {
  return (
    <div className="flex items-center gap-1" role="radiogroup" aria-label="rating">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          onClick={() => onChange(n)}
          className={cn(
            "rounded p-1 transition",
            value >= n ? "text-amber-400" : "text-slate-300 hover:text-slate-400",
          )}
        >
          <Star className="h-6 w-6 fill-current" />
        </button>
      ))}
      <span className="ml-2 text-xs text-slate-500">
        {value > 0 ? `${value}/5` : "请选择"}
      </span>
    </div>
  );
}

export default FeedbackWidget;
