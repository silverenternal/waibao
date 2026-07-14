"use client";
import { ErrorBoundary } from "@/components/ErrorBoundary";

/**
 * T1106 — 用户反馈历史页.
 *
 * 展示当前用户提交过的所有 NPS / 主动反馈 / 问卷答案.
 * 数据源: GET /api/feedback/me
 */

import * as React from "react";
import { Star, MessageSquare, ClipboardList, BarChart3 } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

interface FeedbackRow {
  id: string;
  category: string;
  score: number | null;
  comment: string | null;
  feature_used: string | null;
  created_at: string;
}

const CATEGORY_LABEL: Record<string, { label: string; icon: React.ComponentType<{ className?: string }>; color: string }> = {
  nps: { label: "NPS 评分", icon: BarChart3, color: "bg-blue-100 text-blue-700" },
  bug: { label: "Bug 报告", icon: MessageSquare, color: "bg-rose-100 text-rose-700" },
  feature_request: { label: "功能建议", icon: MessageSquare, color: "bg-violet-100 text-violet-700" },
  praise: { label: "表扬", icon: Star, color: "bg-emerald-100 text-emerald-700" },
  complaint: { label: "投诉", icon: MessageSquare, color: "bg-amber-100 text-amber-700" },
  survey: { label: "快速问卷", icon: ClipboardList, color: "bg-slate-100 text-slate-700" },
  other: { label: "其他", icon: MessageSquare, color: "bg-slate-100 text-slate-700" },
};

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("sb_token") || "";
}

export default function FeedbackHistoryPage() {
  const [data, setData] = React.useState<FeedbackRow[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/feedback/me?limit=100", {
          headers: { Authorization: `Bearer ${getToken()}` },
        });
        if (!res.ok) {
          setError(`加载失败 (${res.status})`);
          return;
        }
        const json = await res.json();
        if (!cancelled) setData(json.data || []);
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <ErrorBoundary>(<div className="mx-auto max-w-3xl px-4 py-10 sm:py-14">
        <header className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight">我的反馈历史</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            你提交过的所有反馈、评分和问卷都在这里。
          </p>
        </header>
        <Card>
          <CardHeader>
            <CardTitle>反馈记录</CardTitle>
            <CardDescription>
              最近 100 条,按时间倒序。你的反馈帮助我们改进产品。
            </CardDescription>
          </CardHeader>
          <CardContent>
            {data === null && !error && <LoadingSkeleton />}
            {error && (
              <p className="rounded-md bg-rose-50 p-3 text-sm text-rose-700">{error}</p>
            )}
            {data && data.length === 0 && (
              <p className="rounded-md bg-muted/40 p-6 text-center text-sm text-muted-foreground">
                暂无反馈记录。试试页面右下角的反馈按钮?
              </p>
            )}
            {data && data.length > 0 && (
              <ul className="space-y-3">
                {data.map((row) => {
                  const cat = CATEGORY_LABEL[row.category] ?? CATEGORY_LABEL.other;
                  const Icon = cat.icon;
                  return (
                    <li
                      key={row.id}
                      className="rounded-lg border p-4 transition-colors hover:bg-muted/30"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span
                            className={cn(
                              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                              cat.color,
                            )}
                          >
                            <Icon className="size-3" />
                            {cat.label}
                          </span>
                          {row.score != null && (
                            <Badge variant="outline" className="font-mono">
                              {row.score}
                              {row.category === "nps" ? " / 10" : " / 5"}
                            </Badge>
                          )}
                          {row.feature_used && (
                            <Badge variant="secondary">{row.feature_used}</Badge>
                          )}
                        </div>
                        <time className="text-xs text-muted-foreground">
                          {new Date(row.created_at).toLocaleString("zh-CN")}
                        </time>
                      </div>
                      {row.comment && (
                        <p className="mt-2 text-sm text-foreground">{row.comment}</p>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>)</ErrorBoundary>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((i) => (
        <div key={i} className="rounded-lg border p-4">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="mt-2 h-3 w-full" />
          <Skeleton className="mt-1 h-3 w-2/3" />
        </div>
      ))}
    </div>
  );
}