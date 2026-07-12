"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SOURCE_LABEL, SOURCE_COLOR } from "@/lib/api-company-review";

export interface CompanyRatingProps {
  ratings: Array<{
    source: string;
    score: number;
    review_count: number;
    recommend_pct?: number | null;
    ceo_pct?: number | null;
    breakdown: Record<string, number>;
  }>;
  aggregatedScore?: number | null;
  loading?: boolean;
}

function Stars({ value }: { value: number }) {
  const full = Math.round(value);
  return (
    <span className="text-amber-500">
      {"★".repeat(full)}
      <span className="text-slate-300">{"★".repeat(Math.max(0, 5 - full))}</span>
    </span>
  );
}

/**
 * 公司综合评分 (3 源聚合).
 *
 * 展示:
 * - 顶部: 聚合分 (3 源平均, 0-5)
 * - 各源评分卡片 (看准 + Glassdoor + 脉脉)
 * - 维度拆解 (compensation / culture / management / worklife)
 */
export function CompanyRating({ ratings, aggregatedScore, loading }: CompanyRatingProps) {
  if (loading) {
    return (
      <Card>
        <CardContent className="p-6 text-slate-400 text-sm">加载评分中…</CardContent>
      </Card>
    );
  }

  if (!ratings.length) {
    return (
      <Card>
        <CardContent className="p-6 text-slate-500 text-sm">暂无评分数据</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* 聚合分 */}
      {aggregatedScore != null && (
        <Card>
          <CardContent className="p-6 flex items-center gap-6">
            <div className="text-5xl font-bold text-amber-600">
              {aggregatedScore.toFixed(1)}
            </div>
            <div className="flex-1">
              <div className="text-lg font-medium">综合评分 (3 源聚合)</div>
              <div className="text-sm text-slate-500">
                基于 {ratings.length} 个评价来源 ·
                总计 {ratings.reduce((a, b) => a + b.review_count, 0)} 条评价
              </div>
              <div className="mt-1">
                <Stars value={aggregatedScore} />
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 各源评分 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {ratings.map((r) => (
          <Card key={r.source}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center justify-between text-base">
                <span>{SOURCE_LABEL[r.source] ?? r.source}</span>
                <Badge className={SOURCE_COLOR[r.source] ?? "bg-slate-100"}>
                  {r.source}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-baseline gap-2">
                <span className="text-3xl font-bold">{r.score.toFixed(1)}</span>
                <span className="text-sm text-slate-500">/ 5.0</span>
              </div>
              <div className="text-xs text-slate-500">
                {r.review_count.toLocaleString()} 条评价
              </div>
              {r.recommend_pct != null && (
                <div className="text-xs">
                  推荐比例:{" "}
                  <span className="font-medium text-emerald-600">
                    {r.recommend_pct.toFixed(0)}%
                  </span>
                </div>
              )}
              {r.ceo_pct != null && (
                <div className="text-xs">
                  CEO 好评:{" "}
                  <span className="font-medium">{r.ceo_pct.toFixed(0)}%</span>
                </div>
              )}
              {Object.keys(r.breakdown).length > 0 && (
                <div className="space-y-1 mt-2 pt-2 border-t">
                  {Object.entries(r.breakdown).map(([k, v]) => (
                    <div key={k} className="flex justify-between text-xs">
                      <span className="text-slate-500">{k}</span>
                      <span className="font-medium">{Number(v).toFixed(1)}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}