"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SOURCE_LABEL, SOURCE_COLOR } from "@/lib/api-company-review";

export interface ReviewListProps {
  reviews: Array<{
    id: string;
    source: string;
    title: string;
    content: string;
    pros?: string | null;
    cons?: string | null;
    rating: number;
    job_title?: string | null;
    employment_status?: string | null;
    created_at?: string | null;
    author?: string | null;
    helpful_count: number;
  }>;
  loading?: boolean;
}

export function ReviewList({ reviews, loading }: ReviewListProps) {
  if (loading) {
    return (
      <Card>
        <CardContent className="p-6 text-slate-400 text-sm">加载评价中…</CardContent>
      </Card>
    );
  }

  if (!reviews.length) {
    return (
      <Card>
        <CardContent className="p-6 text-slate-500 text-sm">暂无评价</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {reviews.map((r) => (
        <Card key={r.id}>
          <CardHeader className="pb-2">
            <div className="flex items-start justify-between gap-2">
              <CardTitle className="text-base">{r.title}</CardTitle>
              <Badge className={SOURCE_COLOR[r.source] ?? "bg-slate-100"}>
                {SOURCE_LABEL[r.source] ?? r.source}
              </Badge>
            </div>
            <div className="flex items-center gap-3 text-xs text-slate-500 mt-1">
              <span>{r.author}</span>
              {r.job_title && <span>· {r.job_title}</span>}
              {r.employment_status && <span>· {r.employment_status}</span>}
              <span className="text-amber-500">{"★".repeat(Math.round(r.rating))}</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-sm text-slate-700 line-clamp-3">{r.content}</p>
            {r.pros && (
              <div className="text-xs">
                <span className="text-emerald-600 font-medium">优点: </span>
                <span className="text-slate-600">{r.pros}</span>
              </div>
            )}
            {r.cons && (
              <div className="text-xs">
                <span className="text-rose-600 font-medium">缺点: </span>
                <span className="text-slate-600">{r.cons}</span>
              </div>
            )}
            <div className="flex items-center justify-between text-xs text-slate-400 pt-1 border-t">
              <span>{r.created_at?.slice(0, 10) ?? ""}</span>
              <span>👍 {r.helpful_count}</span>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}