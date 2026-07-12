"use client";

/**
 * T1106 — 浮动反馈按钮 + 弹层 (右下角).
 *
 * - 用户点击浮标 -> 弹出小卡片 (留言 / NPS 评分 / 快速问卷 三个 tab)
 * - 通过 fetch 调用 /api/feedback 系列接口
 * - 同一会话内只弹一次 NPS (localStorage 标记)
 */

import * as React from "react";
import { MessageCircle, X, Star } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";

type Tab = "nps" | "survey" | "comment";

const TAB_LABELS: Record<Tab, string> = {
  nps: "NPS 评分",
  survey: "快速问卷",
  comment: "留言反馈",
};

export interface FeedbackWidgetProps {
  /** 默认展示位置 (默认右下). */
  position?: "bottom-right" | "bottom-left";
  /** 默认隐藏,只通过外部 trigger 显示 (用于嵌入其他页面). */
  initialOpen?: boolean;
}

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("sb_token") || "";
}

export function FeedbackWidget({
  position = "bottom-right",
  initialOpen = false,
}: FeedbackWidgetProps) {
  const [open, setOpen] = React.useState(initialOpen);
  const [tab, setTab] = React.useState<Tab>("nps");

  return (
    <div
      className={cn(
        "fixed z-50",
        position === "bottom-right" ? "bottom-4 right-4" : "bottom-4 left-4",
      )}
    >
      {open ? (
        <div className="w-[320px] rounded-xl border bg-background shadow-xl">
          <div className="flex items-center justify-between rounded-t-xl bg-primary/5 px-4 py-2">
            <p className="text-sm font-medium">给我们反馈</p>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded p-1 text-muted-foreground hover:bg-muted"
              aria-label="关闭"
            >
              <X className="size-4" />
            </button>
          </div>
          <div className="flex border-b">
            {(Object.keys(TAB_LABELS) as Tab[]).map((k) => (
              <button
                key={k}
                onClick={() => setTab(k)}
                className={cn(
                  "flex-1 px-3 py-2 text-xs font-medium transition-colors",
                  tab === k
                    ? "border-b-2 border-primary text-primary"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {TAB_LABELS[k]}
              </button>
            ))}
          </div>
          <div className="p-4">
            {tab === "nps" && <NPSForm onDone={() => setOpen(false)} />}
            {tab === "survey" && <SurveyForm onDone={() => setOpen(false)} />}
            {tab === "comment" && <CommentForm onDone={() => setOpen(false)} />}
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="grid size-12 place-items-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105"
          aria-label="打开反馈"
        >
          <MessageCircle className="size-5" />
        </button>
      )}
    </div>
  );
}

function NPSForm({ onDone }: { onDone: () => void }) {
  const [score, setScore] = React.useState<number | null>(null);
  const [comment, setComment] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [done, setDone] = React.useState(false);

  const submit = async () => {
    if (score == null) return;
    setSubmitting(true);
    try {
      const res = await fetch("/api/feedback/nps", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ score, comment: comment || undefined }),
      });
      if (res.ok) {
        setDone(true);
        if (typeof window !== "undefined") {
          localStorage.setItem("wb_nps_done", "1");
        }
        setTimeout(onDone, 1200);
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    return (
      <p className="py-6 text-center text-sm text-emerald-600">
        感谢反馈!我们会持续改进。
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        0 = 完全不会推荐,10 = 一定会推荐
      </p>
      <div className="grid grid-cols-11 gap-1">
        {Array.from({ length: 11 }, (_, i) => (
          <button
            key={i}
            type="button"
            onClick={() => setScore(i)}
            className={cn(
              "rounded border py-1.5 text-xs font-medium transition-colors",
              score === i
                ? "border-primary bg-primary text-primary-foreground"
                : "border-muted hover:bg-muted",
            )}
          >
            {i}
          </button>
        ))}
      </div>
      {score != null && (
        <p className="text-xs text-muted-foreground">
          {score <= 6 ? "很遗憾听到不满意的体验" : score <= 8 ? "还不错,但还能更好" : "感谢您的高度认可!"}
        </p>
      )}
      <Textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="有什么我们可以改进的? (选填)"
        className="min-h-16 text-sm"
      />
      <Button
        size="sm"
        className="w-full"
        disabled={score == null || submitting}
        onClick={submit}
      >
        {submitting ? "提交中..." : "提交评分"}
      </Button>
    </div>
  );
}

function SurveyForm({ onDone }: { onDone: () => void }) {
  const [easy, setEasy] = React.useState(0);
  const [value, setValue] = React.useState(0);
  const [speed, setSpeed] = React.useState(0);
  const [comment, setComment] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [done, setDone] = React.useState(false);

  const submit = async () => {
    if (!easy || !value || !speed) return;
    setSubmitting(true);
    try {
      const res = await fetch("/api/feedback/quick-survey", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          easy_to_use: easy,
          value,
          speed,
          comment: comment || undefined,
        }),
      });
      if (res.ok) {
        setDone(true);
        setTimeout(onDone, 1200);
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    return (
      <p className="py-6 text-center text-sm text-emerald-600">
        感谢您的反馈!
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <RatingRow label="易用性" value={easy} onChange={setEasy} />
      <RatingRow label="价值感" value={value} onChange={setValue} />
      <RatingRow label="响应速度" value={speed} onChange={setSpeed} />
      <Textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="补充说明 (选填)"
        className="min-h-14 text-sm"
      />
      <Button
        size="sm"
        className="w-full"
        disabled={!easy || !value || !speed || submitting}
        onClick={submit}
      >
        {submitting ? "提交中..." : "提交问卷"}
      </Button>
    </div>
  );
}

function RatingRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-sm">{label}</span>
      <div className="flex gap-1">
        {[1, 2, 3, 4, 5].map((i) => (
          <button
            key={i}
            type="button"
            onClick={() => onChange(i)}
            aria-label={`${label} ${i} 分`}
            className={cn(
              "transition-transform hover:scale-110",
              value >= i ? "text-amber-500" : "text-muted-foreground/40",
            )}
          >
            <Star className="size-5" fill={value >= i ? "currentColor" : "none"} />
          </button>
        ))}
      </div>
    </div>
  );
}

function CommentForm({ onDone }: { onDone: () => void }) {
  const [category, setCategory] = React.useState("bug");
  const [comment, setComment] = React.useState("");
  const [feature, setFeature] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [done, setDone] = React.useState(false);

  const submit = async () => {
    if (!comment.trim()) return;
    setSubmitting(true);
    try {
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          category,
          comment,
          feature_used: feature || undefined,
        }),
      });
      if (res.ok) {
        setDone(true);
        setTimeout(onDone, 1200);
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    return (
      <p className="py-6 text-center text-sm text-emerald-600">已收到,谢谢!</p>
    );
  }

  return (
    <div className="space-y-3">
      <select
        value={category}
        onChange={(e) => setCategory(e.target.value)}
        className="w-full rounded-md border bg-background px-3 py-2 text-sm"
      >
        <option value="bug">报告 Bug</option>
        <option value="feature_request">功能建议</option>
        <option value="praise">表扬</option>
        <option value="complaint">投诉</option>
        <option value="other">其他</option>
      </select>
      <Input
        value={feature}
        onChange={(e) => setFeature(e.target.value)}
        placeholder="涉及的功能 (选填,如:匹配 / 协作房间)"
      />
      <Textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="请描述您的反馈..."
        className="min-h-24 text-sm"
      />
      <Button
        size="sm"
        className="w-full"
        disabled={!comment.trim() || submitting}
        onClick={submit}
      >
        {submitting ? "提交中..." : "提交反馈"}
      </Button>
    </div>
  );
}

export default FeedbackWidget;