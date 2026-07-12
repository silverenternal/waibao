"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  DIMENSION_LABELS,
  DIMENSIONS,
  type DimensionKey,
  type ProbationScores,
  submitReview,
} from "@/lib/api-probation";

export interface ReviewFormProps {
  employeeId: string;
  orgId: string;
  reviewStage: "30" | "90" | "180" | "final";
  onSubmitted?: (review: unknown) => void;
}

/**
 * 试用期评估表单 — 5 维度评分 (1-5).
 */
export function ReviewForm({ employeeId, orgId, reviewStage, onSubmitted }: ReviewFormProps) {
  const [scores, setScores] = React.useState<ProbationScores>({
    performance: 3,
    learning: 3,
    integration: 3,
    attitude: 3,
    potential: 3,
  });
  const [comments, setComments] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [done, setDone] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const avg =
    (Object.values(scores) as number[]).reduce((a, b) => a + b, 0) / DIMENSIONS.length;

  const setScore = (k: DimensionKey, v: number) => {
    setScores((s) => ({ ...s, [k]: Math.max(1, Math.min(5, v)) }));
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const review = await submitReview(employeeId, orgId, reviewStage, scores, comments);
      setDone(true);
      onSubmitted?.(review);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <p className="text-lg font-medium text-emerald-600">评估已提交</p>
          <p className="text-sm text-slate-500 mt-2">平均分 {avg.toFixed(2)} / 5</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          D+{reviewStage} 试用期评估
          <span className="ml-3 text-sm font-normal text-slate-500">
            平均: <b className="text-slate-900">{avg.toFixed(2)}</b>
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {DIMENSIONS.map((dim) => (
          <div key={dim} className="space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-700">{DIMENSION_LABELS[dim]}</span>
              <span className="text-sm font-medium">{scores[dim]} / 5</span>
            </div>
            <div className="flex gap-2">
              {[1, 2, 3, 4, 5].map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-label={`${DIMENSION_LABELS[dim]}-${v}`}
                  className={`flex-1 py-1.5 rounded border text-sm font-medium transition-all ${
                    scores[dim] === v
                      ? "bg-blue-500 text-white border-blue-500"
                      : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"
                  }`}
                  onClick={() => setScore(dim, v)}
                >
                  {v}
                </button>
              ))}
            </div>
          </div>
        ))}

        <div className="space-y-1">
          <label htmlFor="comments" className="text-sm text-slate-700">
            评语
          </label>
          <textarea
            id="comments"
            rows={4}
            value={comments}
            onChange={(e) => setComments(e.target.value)}
            placeholder="工作亮点 / 改进建议 / 综合评价…"
            className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-200"
          />
        </div>

        {error && (
          <p className="text-sm text-rose-600 bg-rose-50 px-3 py-2 rounded">{error}</p>
        )}

        <div className="flex gap-2 pt-2">
          <Button disabled={submitting} onClick={handleSubmit}>
            {submitting ? "提交中…" : "提交评估"}
          </Button>
          <Button variant="outline" onClick={() => setScores({
            performance: 3, learning: 3, integration: 3, attitude: 3, potential: 3,
          })}>
            重置
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
